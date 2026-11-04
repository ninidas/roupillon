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
    # couchée : l'app attend « Endormie », puis propose le réveil nocturne
    assert [a["act"] for a in r.json()["today"]["actions"]] == ["asleep"]
    clock.set("2026-10-24 19:45")
    r = act(client, auth, "asleep")
    assert [a["act"] for a in r.json()["today"]["actions"]] == ["night_start"]

    clock.set("2026-10-24 23:10")
    act(client, auth, "night_start")
    clock.set("2026-10-24 23:40")
    assert act(client, auth, "night_end").json()["message"] == "Rendormie à 23:40 · 30 min"

    clock.set("2026-10-25 06:50")
    t = client.get("/api/today", headers=auth).json()
    assert t["mode"] == "night" and t["date"] == "2026-10-24"
    assert [a["act"] for a in t["actions"]] == ["night_start", "wake"]
    # la nuit : réveil estimé au centre, cadran de la nuit en premier, la journée en second
    assert t["headline"]["cap"] == "Réveil estimé" and t["headline"]["big"] == "07:03"   # lever de la veille à 07:10, rapproché de 7 h
    nd = t["night_dial"]
    assert nd["head"] == t["headline"] and not nd["wake_real"] and nd["wake_label"] == "07:03"
    assert [(w["start_hm"], w["end_hm"]) for w in nd["wakes"]] == [("23:10", "23:40")]
    assert t["day_head"]["cap"] == "Siestes"

    clock.set("2026-10-25 07:00")
    t = act(client, auth, "wake").json()["today"]
    assert t["mode"] == "day" and t["date"] == "2026-10-25"
    assert t["night_dial"]["head"]["cap"] == "Nuit dernière" and t["night_dial"]["wake_real"]
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
    assert t["feed"]["ask_id"] == fid and t["feed"]["last"]["next"] == "12:00"
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
    # premier toucher : au lit ; deuxième : endormie
    assert client.post("/api/quick/toggle", headers=k).json()["message"].startswith("Au lit à 08:00")
    assert client.get("/api/quick/status", headers=k).json()["state"] == "settling"
    clock.set("2026-10-24 08:10")
    assert client.post("/api/quick/toggle", headers=k).json()["message"] == "Endormie à 08:10, en 10 min"
    clock.set("2026-10-24 08:45")
    s = client.get("/api/quick/status", headers=k).json()
    # l'app met « Réveil estimé » au-dessus de l'heure ; le menu du widget garde l'heure dans son message
    assert s["state"] == "nap" and s["headline"]["sub"].startswith("Réveil estimé vers ") and "message" not in s
    assert client.get("/api/today", headers=auth).json()["headline"]["cap"] == "Réveil estimé"
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
    assert r.text == "Au lit à 08:00. Touchez « Endormie » quand elle dort"
    r = client.post("/api/quick/feed?text=1", headers={"X-Roupillon-Key": key})
    assert r.text == "Biberon à 08:00"


def test_reprise_de_l_ancien_oracle(client, auth, clock):
    from datetime import date
    from app import import_oracle
    from app.database import SessionLocal
    db = SessionLocal()
    n = import_oracle.import_day(db, date(2026, 3, 2), {
        "wake": "07:00", "wakeSet": False, "feeds": [{"t": "08:00", "ml": 120}],
        "naps": {"1": {"start": "12:40", "end": "13:30"}, "0": {"start": "09:05", "end": "10:20"}},
        "bed": "19:30", "night": [{"start": "02:10", "end": "02:30"}]})
    db.commit()
    assert n == 5   # lever non noté : pas repris
    assert import_oracle.import_day(db, date(2026, 3, 2), {"naps": {"0": {"start": "09:00"}}}) == 0
    db.close()
    d = client.get("/api/days/2026-03-02", headers=auth).json()
    assert [x["start"] for x in d["naps"]] == ["09:05", "12:40"] and d["bed"]["time"] == "19:30"
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


def test_cadran_apres_l_heure_du_coucher_prevu(client, auth, clock):
    clock.set("2026-10-24 07:00")
    act(client, auth, "wake")
    clock.set("2026-10-24 22:00")
    t = act(client, auth, "feed").json()["today"]
    d = t["dial"]
    # coucher prévu largement dépassé : le biberon de 22:00 et « maintenant » restent sur le cadran
    assert d["bed"] >= 22 * 60 and any(f["t"] == 22 * 60 for f in d["feeds"]) and d["bed_label"] != "22:10"


def test_pas_de_biberon_annonce_apres_le_coucher(client, auth, clock):
    clock.set("2026-10-24 07:00")
    act(client, auth, "wake")
    clock.set("2026-10-24 10:00")
    assert act(client, auth, "feed").json()["today"]["feed"]["last"]["next_label"] == "prochain vers 13:00"
    clock.set("2026-10-24 17:30")
    t = act(client, auth, "feed").json()["today"]
    assert t["feed"]["last"]["next_label"] == "prochain au lever"   # 21:00 tomberait après le coucher prévu
    clock.set("2026-10-24 19:00")
    assert act(client, auth, "bed").json()["today"]["feed"]["last"]["next_label"] == "prochain au lever"


def test_poids_et_repere_de_lait(client, auth, clock):
    clock.set("2026-10-24 10:00")
    assert client.get("/api/today", headers=auth).json()["feed"]["ref"] is None
    assert client.post("/api/weights", json={"day": "2026-10-30", "kg": 5.5}, headers=auth).status_code == 422
    w = client.post("/api/weights", json={"day": "2026-10-20", "kg": 5.5}, headers=auth).json()
    assert w["kg"] == "5,5"
    ref = client.get("/api/today", headers=auth).json()["feed"]["ref"]
    assert (ref["lo"], ref["hi"], ref["kg"]) == (700, 950, "5,5")
    assert client.get("/api/growth", headers=auth).json()["weights"][0]["id"] == w["id"]
    client.delete(f"/api/weights/{w['id']}", headers=auth)
    assert client.get("/api/today", headers=auth).json()["feed"]["ref"] is None



def test_courbe_de_poids(client, auth, clock):
    from app import engine as E
    # Valeurs des tables OMS : médiane d'une fille à 3 mois 5,85 kg, 3e percentile 4,6, 97e 7,4
    assert round(E.who_weight("f", 3 * E.DAYS_PER_MONTH, 0), 2) == 5.85
    assert round(E.who_weight("f", 3 * E.DAYS_PER_MONTH, -1.881), 1) == 4.6
    assert round(E.who_weight("f", 3 * E.DAYS_PER_MONTH, 1.881), 1) == 7.4
    clock.set("2026-10-24 10:00")
    for day, kg in (("2026-10-02", 5.4), ("2026-10-09", 5.62)):
        client.post("/api/weights", json={"day": day, "kg": kg}, headers=auth)
    g = client.get("/api/growth", headers=auth).json()
    assert g["curves"] is None   # sexe pas encore indiqué
    assert g["weights"][0]["kg"] == "5,62" and g["weights"][0]["gain"] == "+220 g en 7 jours"
    client.put("/api/settings", json={"sex": "f"}, headers=auth)
    g = client.get("/api/growth", headers=auth).json()
    assert g["curves"]["days"][0] == 0 and g["curves"]["days"][-1] == g["span_days"] and len(g["curves"]["p50"]) == len(g["curves"]["days"])


def test_taille(client, auth, clock):
    from app import engine as E
    # Tables OMS de la taille : fille de 3 mois, médiane 59,8 cm, 3e percentile 55,8 ; garçon de 6 mois, médiane 67,6
    assert round(E.who_length("f", 3 * E.DAYS_PER_MONTH, 0), 1) == 59.8
    assert round(E.who_length("f", 3 * E.DAYS_PER_MONTH, -1.881), 1) == 55.8
    assert round(E.who_length("m", 6 * E.DAYS_PER_MONTH, 0), 1) == 67.6
    clock.set("2026-10-24 10:00")
    assert client.post("/api/heights", json={"day": "2026-10-30", "cm": 60}, headers=auth).status_code == 422
    assert client.post("/api/heights", json={"day": "2026-10-02", "cm": 12}, headers=auth).status_code == 422
    client.post("/api/heights", json={"day": "2026-09-02", "cm": 57}, headers=auth)
    h = client.post("/api/heights", json={"day": "2026-10-02", "cm": 59.5}, headers=auth).json()
    client.put("/api/settings", json={"sex": "f"}, headers=auth)
    g = client.get("/api/growth", headers=auth).json()
    assert g["heights"][0]["cm"] == "59,5" and g["heights"][0]["gain"] == "+2,5 cm en 30 jours"
    assert len(g["height_curves"]["p50"]) == len(g["height_curves"]["days"])
    assert client.delete(f"/api/heights/{h['id']}", headers=auth).json() == {"deleted": 1}
    assert len(client.get("/api/growth", headers=auth).json()["heights"]) == 1


def test_endormissement(client, auth, clock):
    act = lambda a: client.post("/api/actions", headers=auth, json={"act": a})
    clock.set("2026-10-24 07:00")
    act("wake")
    clock.set("2026-10-24 08:30")
    r = act("nap_lay").json()
    assert r["field"] == "laid" and r["today"]["settling"] and r["today"]["headline"]["cap"] == "S'endort depuis"
    assert [a["act"] for a in r["today"]["actions"]] == ["asleep", "nap_end"]
    # au lit n'est pas encore une sieste : la prévision attend l'endormissement
    assert not any(n["start_real"] for n in r["today"]["dial"]["naps"])
    assert act("nap_lay").status_code == 409
    # « Elle dort » pendant la mise au lit = l'endormissement
    clock.set("2026-10-24 08:42")
    r = act("nap_start").json()
    assert r["message"] == "Endormie à 08:42, en 12 min"
    nap = next(x for x in r["today"]["timeline"] if x["type"] == "nap")
    assert nap["start"] == "08:42" and nap["settle"] == "endormie en 12 min" and nap["start_real"]
    # Annuler remet au lit
    ev = r["event_id"]
    client.patch(f"/api/events/{ev}", headers=auth, json={"start": "2026-10-24T08:30", "settling": True})
    assert client.get("/api/today", headers=auth).json()["settling"]
    # réveillée sans « Endormie » : l'app demande l'heure d'endormissement
    clock.set("2026-10-24 09:40")
    r = act("nap_end").json()
    assert r["ask_asleep"] == {"id": ev, "laid": "08:30", "end": "09:40"}
    assert client.patch(f"/api/events/{ev}", headers=auth, json={"start": "08:50", "day": "2026-10-24"}).status_code == 200
    t = client.get("/api/today", headers=auth).json()
    nap = next(x for x in t["timeline"] if x["type"] == "nap")
    assert (nap["start"], nap["end"], nap["settle"]) == ("08:50", "09:40", "endormie en 20 min") and not t["settling"]
    # au lit après l'endormissement : refusé
    assert client.patch(f"/api/events/{ev}", headers=auth, json={"laid": "09:00", "day": "2026-10-24"}).status_code == 422
    # le soir : couchée, puis endormie ; le coucher reste compté à la mise au lit
    clock.set("2026-10-24 19:00")
    r = act("bed").json()
    assert r["today"]["mode"] == "night" and r["today"]["settling"] and r["today"]["actions"][0]["act"] == "asleep"
    clock.set("2026-10-24 19:25")
    assert act("asleep").json()["message"] == "Endormie à 19:25, en 25 min"
    t = client.get("/api/today", headers=auth).json()
    bed = next(x for x in t["timeline"] if x["type"] == "bed")
    assert bed["time"] == "19:00" and bed["settle"] == "endormie en 25 min" and not t["settling"]
    h = client.get("/api/history", headers=auth).json()["settle"]
    assert [(r["label"], r["mean"]) for r in h["rows"]] == [("Sieste 1", "20 min"), ("Coucher", "25 min")]


def test_endormissement_du_soir_oublie(client, auth, clock):
    act = lambda a: client.post("/api/actions", headers=auth, json={"act": a})
    clock.set("2026-10-24 07:00")
    act("wake")
    clock.set("2026-10-24 19:00")
    act("bed")
    # 90 minutes plus tard, l'attente est oubliée : le raccourci note un réveil nocturne comme avant
    clock.set("2026-10-24 23:00")
    t = client.get("/api/today", headers=auth).json()
    assert not t["settling"] and t["actions"][0]["act"] == "night_start"
    key = client.post("/api/me/widget-key", headers=auth).json()["key"]
    assert client.post("/api/quick/toggle", headers={"X-Roupillon-Key": key}).json()["message"] == "Réveil nocturne à 23:00"


def test_mise_au_lit_sans_sieste(client, auth, clock):
    act = lambda a: client.post("/api/actions", headers=auth, json={"act": a})
    clock.set("2026-10-24 07:00")
    act("wake")
    clock.set("2026-10-24 17:00")
    act("nap_lay")
    # elle ne s'est pas endormie, on passe au coucher : la mise au lit disparaît
    clock.set("2026-10-24 19:00")
    act("bed")
    assert client.get("/api/days/2026-10-24", headers=auth).json()["naps"] == []
