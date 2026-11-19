from datetime import timedelta

import pytest

from app import push
from app.database import SessionLocal

from conftest import PASSWORD
from test_push import APPLE, KEYS, act, run_until


@pytest.fixture
def auth_b(client, auth):
    r = client.post("/api/login", json={"username": "pb", "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def ids(client, auth, auth_b):
    return client.get("/api/me", headers=auth).json()["id"], client.get("/api/me", headers=auth_b).json()["id"]


@pytest.fixture
def later(monkeypatch):
    out = []
    monkeypatch.setattr(push, "send_later", lambda notices: out.extend(notices))
    return out


def test_semaine_vide_puis_nuits_choisies(client, auth, ids, later):
    a, b = ids
    w = client.get("/api/nights", headers=auth).json()
    # Samedi 24 octobre : la semaine du lundi 19, nuits passées jusqu'à vendredi
    assert w["start"] == "2026-10-19" and w["label"] == "Du 19 au 25 octobre" and w["tonight"] == "2026-10-24"
    assert [n["label"] for n in w["nights"]][:2] == ["Lundi 19", "Mardi 20"] and w["empty"] == 2
    assert w["started"] is False and w["child"] == "Bébé"
    w = client.put("/api/nights/2026-10-24", json={"user_id": b}, headers=auth).json()
    assert w["started"] is True
    sat = w["nights"][5]
    assert sat["user_id"] == b and sat["source"] == "set" and sat["tonight"] and w["counts"][str(b)] == 1 and w["empty"] == 1
    assert later == [(b, {"title": "Nuits : nuit de samedi", "body": "Parent A vous a donné la nuit de samedi.", "tag": "duty-2026-10-24"})]
    later.clear()
    client.put("/api/nights/2026-10-24", json={"user_id": a}, headers=auth)
    assert later[0][0] == b and later[0][1]["body"] == "Parent A a pris votre nuit de samedi."
    later.clear()
    client.put("/api/nights/2026-10-24", json={"user_id": a}, headers=auth)
    assert later == []          # rien ne change, personne n'est dérangé
    assert client.put("/api/nights/2027-12-01", json={"user_id": a}, headers=auth).status_code == 422
    assert client.put("/api/nights/2026-10-25", json={"user_id": 999}, headers=auth).status_code == 422


def test_reprendre_la_semaine_derniere(client, auth, ids, later):
    a, b = ids
    assert client.post("/api/nights/copy", json={"start": "2026-10-26"}, headers=auth).status_code == 422
    for d, uid in (("2026-10-19", a), ("2026-10-20", b), ("2026-10-24", b)):
        client.put(f"/api/nights/{d}", json={"user_id": uid}, headers=auth)
    later.clear()
    w = client.post("/api/nights/copy", json={"start": "2026-10-28"}, headers=auth).json()
    assert w["start"] == "2026-10-26"
    assert [n["user_id"] for n in w["nights"]] == [a, b, None, None, None, b, None] and w["empty"] == 4
    assert later == [(b, {"title": "Nuits", "body": "Parent A a prévu les nuits de la semaine du 26 octobre.", "tag": "duty-week-2026-10-26"})]


def test_rythme_jours_attitres_et_nuit_modifiee(client, auth, ids, later):
    a, b = ids
    client.put("/api/nights/2026-10-20", json={"user_id": b}, headers=auth)
    r = client.put("/api/nights/rhythm", json={"mode": "weekdays", "weekdays": [a, b, a, b, a, b, b]}, headers=auth)
    w = r.json()
    # Valable à partir de ce soir : les nuits passées restent comme elles étaient
    assert [n["user_id"] for n in w["nights"]] == [None, b, None, None, None, b, b]
    w = client.get("/api/nights?start=2026-10-26", headers=auth).json()
    assert [n["user_id"] for n in w["nights"]] == [a, b, a, b, a, b, b] and w["empty"] == 0
    w = client.put("/api/nights/2026-10-29", json={"user_id": a}, headers=auth).json()
    assert w["nights"][3]["changed"] and not w["nights"][2]["changed"]
    w = client.put("/api/nights/2026-10-30", json={"user_id": None}, headers=auth).json()
    assert w["nights"][4]["user_id"] is None and w["nights"][4]["source"] == "set" and w["empty"] == 1
    bad = client.put("/api/nights/rhythm", json={"mode": "weekdays", "weekdays": [a] * 6}, headers=auth)
    assert bad.status_code == 422


def test_rythme_alterne_et_changement_qui_fige_le_passe(client, auth, ids, later, clock):
    a, b = ids
    client.put("/api/nights/rhythm", json={"mode": "alternate", "anchor": "2026-10-24", "first": b, "second": a}, headers=auth)
    w = client.get("/api/nights?start=2026-10-26", headers=auth).json()
    assert [n["user_id"] for n in w["nights"]] == [b, a, b, a, b, a, b]
    assert client.put("/api/nights/rhythm", json={"mode": "alternate", "anchor": "2026-10-24", "first": a, "second": a},
                      headers=auth).status_code == 422
    clock.set("2026-10-27 12:00")
    client.put("/api/nights/rhythm", json={"mode": "none"}, headers=auth)
    w = client.get("/api/nights?start=2026-10-26", headers=auth).json()
    # Lundi 26 est passé : il garde le parent que le rythme lui donnait ; mardi 27 (ce soir) et la suite se vident
    assert [n["user_id"] for n in w["nights"]] == [b, None, None, None, None, None, None]


def test_cette_nuit_sur_aujourdhui(client, auth, auth_b, ids, clock):
    a, b = ids
    assert client.get("/api/today", headers=auth).json()["tonight"] is None      # 7 h : pas encore
    clock.set("2026-10-24 17:00")
    t = client.get("/api/today", headers=auth).json()["tonight"]
    assert t["user_id"] is None and t["label"] == "nuit de samedi" and len(t["users"]) == 2
    client.put("/api/nights/2026-10-24", json={"user_id": b}, headers=auth)
    assert client.get("/api/today", headers=auth).json()["tonight"]["me"] is False
    t = client.get("/api/today", headers=auth_b).json()["tonight"]
    assert t["me"] is True and t["name"] == "Parent B"
    clock.set("2026-10-24 19:05")
    act(client, auth, "bed", at="2026-10-24T19:00")
    clock.set("2026-10-25 03:00")
    t = client.get("/api/today", headers=auth_b).json()
    assert t["mode"] == "night" and t["tonight"]["date"] == "2026-10-24" and t["tonight"]["me"] is True


def test_rappels_des_nuits(client, auth, auth_b, ids, clock, later, monkeypatch):
    a, b = ids
    out = []
    monkeypatch.setattr(push, "send", lambda db, sub, payload: out.append((sub.user_id, payload)) or True)
    for h, k in ((auth, "a"), (auth_b, "b")):
        client.post("/api/push/subscribe", json={"endpoint": f"{APPLE}{k}", "keys": KEYS}, headers=h)
    client.put("/api/push/prefs", json={"nap": False, "feed": False}, headers=auth)
    client.put("/api/push/prefs", json={"nap": False, "feed": False}, headers=auth_b)
    act(client, auth, "wake", at="2026-10-24T07:00")
    clock.set("2026-10-24 17:55")
    keys = []
    run_until(clock, "2026-10-24 18:40", keys)
    # 18 h : personne pour ce soir, les deux parents sont prévenus, une seule fois
    assert [(t, k) for t, k in keys] == [("18:00", f"duty|empty|2026-10-24|{a}"), ("18:00", f"duty|empty|2026-10-24|{b}")]
    client.put("/api/nights/2026-10-24", json={"user_id": b}, headers=auth)
    clock.set("2026-10-24 18:52")
    act(client, auth, "bed", at="2026-10-24T18:50")
    keys.clear(); out.clear()
    run_until(clock, "2026-10-24 21:00", keys)
    assert keys == [("18:52", f"duty|eve|2026-10-24|{b}")]
    assert out[0][1]["title"] == "Bébé : cette nuit, c'est vous" and "couchée depuis 18:50" in out[0][1]["body"]
    assert out[0][1]["url"] == "/?tab=nights"


def test_rappel_du_soir_a_20h_et_semaine_a_planifier(client, auth, ids, clock, monkeypatch):
    a, b = ids
    monkeypatch.setattr(push, "send", lambda db, sub, payload: True)
    client.post("/api/push/subscribe", json={"endpoint": f"{APPLE}a", "keys": KEYS}, headers=auth)
    client.put("/api/push/prefs", json={"nap": False, "feed": False, "duty_empty": False}, headers=auth)
    client.put("/api/nights/2026-10-25", json={"user_id": a}, headers=auth)
    clock.set("2026-10-25 18:55")    # dimanche, sans coucher noté
    keys = []
    run_until(clock, "2026-10-25 20:05", keys)
    assert keys == [("19:00", f"duty|week|2026-10-26|{a}"), ("20:00", f"duty|eve|2026-10-25|{a}")]
    client.put("/api/push/prefs", json={"duty_week": False}, headers=auth)
    db = SessionLocal()
    try:
        assert push.prefs(db, a)["duty_week"] is False
    finally:
        db.close()
