from datetime import timedelta

import pytest

from app import push
from app import service as S
from app.database import SessionLocal

APPLE = "https://web.push.apple.com/QGuQyavXutnMbbRA"
KEYS = {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "auth": "tBHItJI5svbpez7KI4CCXg"}


def act(client, auth, a, **kw):
    return client.post("/api/actions", json={"act": a, **kw}, headers=auth)


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "send", lambda db, sub, payload: out.append(payload) or True)
    return out


def run_until(clock, end, sent_keys):
    """Fait tourner la boucle minute par minute jusqu'à `end`, note l'heure de chaque envoi."""
    db = SessionLocal()
    try:
        while clock.now.strftime("%Y-%m-%d %H:%M") < end:
            for k in push.tick(db, clock.now):
                sent_keys.append((clock.now.strftime("%H:%M"), k))
            clock.now += timedelta(minutes=1)
    finally:
        db.close()


def test_abonnement_et_reglages(client, auth):
    r = client.get("/api/push", headers=auth).json()
    assert r["prefs"] == {"nap": True, "feed": True, "bed": False, "lead": 15} and r["devices"] == 0 and len(r["key"]) > 80
    bad = client.post("/api/push/subscribe", json={"endpoint": "https://exemple.invalid/x", "keys": KEYS}, headers=auth)
    assert bad.status_code == 422
    r = client.post("/api/push/subscribe", json={"endpoint": APPLE, "keys": KEYS}, headers=auth)
    assert r.status_code == 200 and r.json()["devices"] == 1
    r = client.put("/api/push/prefs", json={"feed": False, "lead": 10}, headers=auth).json()
    assert r["prefs"] == {"nap": True, "feed": False, "bed": False, "lead": 10}
    assert client.put("/api/push/prefs", json={"lead": 7}, headers=auth).status_code == 422
    r = client.post("/api/push/unsubscribe", json={"endpoint": APPLE}, headers=auth).json()
    assert r["devices"] == 0


def test_sieste_annoncee_une_fois_15_min_avant(client, auth, clock, sent):
    client.post("/api/push/subscribe", json={"endpoint": APPLE, "keys": KEYS}, headers=auth)
    clock.set("2026-10-24 07:00")
    t = act(client, auth, "wake").json()["today"]
    nap = t["dial"]["naps"][0]
    keys = []
    run_until(clock, "2026-10-24 " + S.E.fmt(nap["start"] + 20), keys)
    assert keys == [(S.E.fmt(nap["start"] - 15), "2026-10-24|nap|0|1")]
    assert sent[0]["title"].startswith("Bébé : sieste 1 vers ") and "Dans 15 min environ" in sent[0]["body"]


def test_rien_pendant_une_sieste_ni_la_nuit(client, auth, clock, sent):
    client.post("/api/push/subscribe", json={"endpoint": APPLE, "keys": KEYS}, headers=auth)
    clock.set("2026-10-24 07:00")
    act(client, auth, "wake")
    act(client, auth, "feed")
    clock.set("2026-10-24 07:30")
    act(client, auth, "nap_start")      # elle dort jusqu'après l'heure du biberon (10:00)
    keys = []
    run_until(clock, "2026-10-24 10:30", keys)
    assert keys == []
    clock.set("2026-10-24 19:00")
    act(client, auth, "nap_end")
    act(client, auth, "bed")
    run_until(clock, "2026-10-24 23:00", keys)
    assert keys == []


def test_biberon_trois_heures_apres(client, auth, clock, sent):
    client.post("/api/push/subscribe", json={"endpoint": APPLE, "keys": KEYS}, headers=auth)
    client.put("/api/push/prefs", json={"nap": False}, headers=auth)
    clock.set("2026-10-24 07:00")
    act(client, auth, "wake")
    r = act(client, auth, "feed").json()
    keys = []
    run_until(clock, "2026-10-24 10:30", keys)
    assert keys == [("09:45", f"feed|{r['today']['feeds'][0]['id']}|1")]
    assert sent[0]["title"] == "Bébé : biberon vers 10:00"
