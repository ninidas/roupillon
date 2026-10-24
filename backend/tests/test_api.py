from conftest import PASSWORD


def act(client, auth, a, **kw):
    return client.post("/api/actions", json={"act": a, **kw}, headers=auth)


def test_installation_unique_et_connexion(client, auth):
    assert client.get("/api/setup").json() == {"needs_setup": False}
    r = client.post("/api/setup", json={"child_name": "X", "birth_date": "2026-07-01",
                                        "accounts": [{"display_name": "Z", "username": "zz", "password": PASSWORD}]})
    assert r.status_code == 409
    assert client.post("/api/login", json={"username": "pb", "password": "mauvais-mot-de-passe"}).status_code == 401
    r = client.post("/api/login", json={"username": "PB", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"]["display_name"] == "Parent B"
    assert client.get("/api/today").status_code == 401


def test_mot_de_passe_court_refuse(client):
    r = client.post("/api/setup", json={"child_name": "X", "birth_date": "2026-07-01",
                                        "accounts": [{"display_name": "Z", "username": "zz", "password": "court"}]})
    assert r.status_code == 422


def test_journee_complete(client, auth, clock):
    clock.set("2026-10-24 07:10")
    r = act(client, auth, "wake")
    assert r.json()["message"] == "Levée à 07:10"
    assert r.json()["today"]["headline"]["cap"] == "Sieste 1 dans"

    clock.set("2026-10-24 08:30")
    r = act(client, auth, "nap_start")
    assert r.json()["message"] == "Sieste 1 commencée à 08:30"
    assert r.json()["today"]["actions"][0]["act"] == "nap_end"
    assert act(client, auth, "nap_start").status_code == 409

    clock.set("2026-10-24 09:30")
    r = act(client, auth, "nap_end")
    assert r.json()["message"] == "Sieste 1 terminée à 09:30 · 1 h"
    t = r.json()["today"]
    assert t["headline"]["cap"] == "Sieste 2 dans" and t["totals"]["slept"] == "1 h"

    clock.set("2026-10-24 19:30")
    r = act(client, auth, "bed")
    assert r.json()["today"]["mode"] == "night"
    assert [a["act"] for a in r.json()["today"]["actions"]] == ["night_start"]

    clock.set("2026-10-24 23:10")
    act(client, auth, "night_start")
    clock.set("2026-10-24 23:40")
    assert act(client, auth, "night_end").json()["message"] == "Rendormie à 23:40 · 30 min"

    clock.set("2026-10-25 06:50")
    t = client.get("/api/today", headers=auth).json()
    assert t["mode"] == "night" and t["date"] == "2026-10-24"
    assert [a["act"] for a in t["actions"]] == ["night_start", "wake"]

    clock.set("2026-10-25 07:00")
    t = act(client, auth, "wake").json()["today"]
    assert t["mode"] == "day" and t["date"] == "2026-10-25"
    # nuit du changement d'heure : 11 h à l'horloge, 12 h réelles
    assert t["totals"]["last_night"]["sleep"] == "12 h" and t["totals"]["last_night"]["count"] == 1

    h = client.get("/api/history", headers=auth).json()
    day = next(d for d in h["days"] if d["date"] == "2026-10-24")
    assert day["naps"] == 1 and day["bed"] == "19:30" and day["night"]["sleep"] == "12 h"


def test_correction_et_annulation(client, auth, clock):
    clock.set("2026-10-24 10:00")
    r = act(client, auth, "nap_start").json()
    nid = r["event_id"]
    # « c'était il y a 10 min »
    assert client.patch(f"/api/events/{nid}", json={"start": "2026-10-24T09:50"}, headers=auth).status_code == 200
    clock.set("2026-10-24 11:00")
    r = act(client, auth, "nap_end").json()
    assert r["message"].endswith("1 h 10")
    # annuler le réveil rouvre la sieste
    client.patch(f"/api/events/{nid}", json=r["undo"]["body"], headers=auth)
    assert client.get("/api/today", headers=auth).json()["actions"][0]["act"] == "nap_end"
    # fin avant le début : refusé
    assert client.patch(f"/api/events/{nid}", json={"end": "09:00"}, headers=auth).status_code == 422
    # ajout d'une sieste oubliée, puis effacement de la journée
    assert client.post("/api/events", json={"kind": "nap", "day": "2026-10-24", "start": "07:30", "end": "08:00"},
                       headers=auth).status_code == 200
    d = client.get("/api/days/2026-10-24", headers=auth).json()
    assert [n["start"] for n in d["naps"]] == ["07:30", "09:50"]
    assert client.delete("/api/days/2026-10-24", headers=auth).json()["deleted"] == 2


def test_un_seul_lever_par_jour(client, auth, clock):
    clock.set("2026-10-24 07:00")
    act(client, auth, "wake")
    client.post("/api/events", json={"kind": "wake", "day": "2026-10-24", "start": "06:40"}, headers=auth)
    assert client.get("/api/days/2026-10-24", headers=auth).json()["wake"]["time"] == "06:40"


def test_biberon(client, auth, clock):
    clock.set("2026-10-24 09:00")
    fid = act(client, auth, "feed").json()["event_id"]
    t = client.get("/api/today", headers=auth).json()
    assert t["feed"]["ask_id"] == fid and t["feed"]["last"]["next"] == "12:30"
    client.patch(f"/api/events/{fid}", json={"ml": 120}, headers=auth)
    t = client.get("/api/today", headers=auth).json()
    assert t["feed"]["ask_id"] is None and t["feed"]["ml"] == 120


def test_widget_et_raccourcis(client, auth, clock):
    assert client.get("/api/quick/status").status_code == 401
    assert client.get("/api/quick/status", headers={"X-Roupillon-Key": "rp_faux"}).status_code == 401
    key = client.post("/api/me/widget-key", headers=auth).json()["key"]
    k = {"X-Roupillon-Key": key}
    clock.set("2026-10-24 08:00")
    s = client.get("/api/quick/status", headers=k).json()
    assert s["state"] == "awake" and s["target"].startswith("2026-10-24T")
    assert client.post("/api/quick/toggle", headers=k).json()["message"] == "Sieste 1 commencée à 08:00"
    clock.set("2026-10-24 08:45")
    assert client.get("/api/quick/status", headers=k).json()["state"] == "nap"
    assert client.post("/api/quick/toggle", headers=k).json()["message"].startswith("Sieste 1 terminée")
    # une nouvelle clé remplace l'ancienne
    client.post("/api/me/widget-key", headers=auth)
    assert client.get("/api/quick/status", headers=k).status_code == 401


def test_changer_le_mot_de_passe_deconnecte_les_autres(client, auth):
    r = client.post("/api/me/password", json={"current": PASSWORD, "new": "nouveau-mot-de-passe"}, headers=auth)
    assert r.status_code == 200
    assert client.get("/api/me", headers=auth).status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).status_code == 200


def test_reglages(client, auth):
    r = client.put("/api/settings", json={"manual_age": "4-6", "child_name": "Bébé 2"}, headers=auth).json()
    assert r["child"]["age_id"] == "4-6" and r["child"]["age_manual"] and r["child_name"] == "Bébé 2"
    r = client.put("/api/settings", json={"manual_age": None}, headers=auth).json()
    assert not r["child"]["age_manual"]
    assert client.put("/api/settings", json={"manual_age": "99"}, headers=auth).status_code == 422
    assert client.put("/api/settings", json={"birth_date": "2030-01-01"}, headers=auth).status_code == 422


def test_api_inconnue_et_heure_hors_journee(client, auth, clock):
    assert client.get("/api/nope").status_code == 404
    clock.set("2026-10-24 10:00")
    assert act(client, auth, "nap_start", at="2026-10-22T10:00").status_code == 422


def test_raccourci_en_texte(client, auth, clock):
    key = client.post("/api/me/widget-key", headers=auth).json()["key"]
    clock.set("2026-10-24 08:00")
    r = client.post("/api/quick/toggle?text=1", headers={"X-Roupillon-Key": key})
    assert r.text == "Sieste 1 commencée à 08:00"
    r = client.post("/api/quick/feed?text=1", headers={"X-Roupillon-Key": key})
    assert r.text == "Biberon à 08:00"


def test_reprise_de_l_ancien_oracle(client, auth, clock):
    from datetime import date
    from app import import_oracle
    from app.database import SessionLocal
    db = SessionLocal()
    n = import_oracle.import_day(db, date(2026, 10, 17), {
        "wake": "07:00", "wakeSet": False, "feeds": [{"t": "08:00", "ml": 120}],
        "naps": {"1": {"start": "12:18", "end": "13:10"}, "0": {"start": "09:18", "end": "10:34"}},
        "bed": "19:30", "night": [{"start": "02:10", "end": "02:30"}]})
    db.commit()
    assert n == 5   # lever non noté : pas repris
    assert import_oracle.import_day(db, date(2026, 10, 17), {"naps": {"0": {"start": "09:00"}}}) == 0
    db.close()
    d = client.get("/api/days/2026-10-17", headers=auth).json()
    assert [x["start"] for x in d["naps"]] == ["09:18", "12:18"] and d["bed"]["time"] == "19:30"
    assert d["night"][0]["dur"] == "20 min" and d["feeds"][0]["ml"] == 120


def test_releve_des_heures_prevues(client, auth, clock):
    from app import models
    from app.database import SessionLocal
    clock.set("2026-10-24 07:00")
    act(client, auth, "wake")
    clock.set("2026-10-24 08:30")
    nid = act(client, auth, "nap_start").json()["event_id"]
    clock.set("2026-10-24 09:20")
    act(client, auth, "nap_end")
    clock.set("2026-10-24 19:00")
    bid = act(client, auth, "bed").json()["event_id"]
    db = SessionLocal()
    nap, bed = db.get(models.Event, nid), db.get(models.Event, bid)
    # 115 jours : premier éveil de 78 min, première sieste prévue d'une heure
    assert (nap.planned_start, nap.planned_end) == ("2026-10-24 08:18", "2026-10-24 09:30")
    assert bed.planned_start and bed.planned_start.startswith("2026-10-24 ")
    db.close()


def test_copie_de_nuit(client, auth):
    import os
    from datetime import datetime, timedelta
    from app import backup
    for k in range(9):
        backup.backup_now(datetime(2026, 10, 1) + timedelta(days=k))
    files = sorted(os.listdir(backup.folder()))
    assert len(files) == backup.KEEP and files[-1] == "roupillon-2026-10-09.db"
    import sqlite3
    assert sqlite3.connect(os.path.join(backup.folder(), files[-1])).execute("select count(*) from users").fetchone()[0] == 2


def test_changement_d_heure_et_vue_d_un_jour(client, auth, clock):
    # Nuit du 24 au 25 octobre 2026 : 3 h devient 2 h, la nuit dure une heure de plus qu'à l'horloge
    clock.set("2026-10-24 07:00")
    act(client, auth, "wake")
    clock.set("2026-10-24 09:00")
    act(client, auth, "nap_start")
    clock.set("2026-10-24 10:00")
    act(client, auth, "nap_end")
    clock.set("2026-10-24 19:00")
    act(client, auth, "bed")
    clock.set("2026-10-25 07:00")
    t = act(client, auth, "wake").json()["today"]
    assert t["totals"]["last_night"]["sleep"] == "13 h"
    v = client.get("/api/days/2026-10-24/view", headers=auth).json()
    assert [x["type"] for x in v["timeline"]] == ["wake", "gap", "nap", "gap", "bed"]
    assert v["dial"]["bed_real"] and v["summary"]["night"]["sleep"] == "13 h"


def test_ancien_nom_d_en_tete_accepte_si_configure(client, auth, monkeypatch):
    from app import auth as A
    key = client.post("/api/me/widget-key", headers=auth).json()["key"]
    assert client.get("/api/quick/status", headers={"X-Ancienne-Key": key}).status_code == 401
    monkeypatch.setattr(A, "EXTRA_KEY_HEADER", "X-Ancienne-Key")
    assert client.get("/api/quick/status", headers={"X-Ancienne-Key": key}).status_code == 200
