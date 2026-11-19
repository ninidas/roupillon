"""Qui se lève la nuit : un parent par nuit, choisi semaine par semaine ou par un rythme par défaut.
Une nuit porte la date du soir : la « nuit de lundi » va du coucher du lundi au lever du mardi.
Un choix fait à la main l'emporte toujours sur le rythme, « personne » compris."""
import json
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from . import models
from . import service as S

MODES = ("none", "alternate", "weekdays")
DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
KEEP_PAST = 14     # jours : changer de rythme fige d'abord les nuits passées qu'il avait remplies


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def users(db: Session) -> list[models.User]:
    return db.query(models.User).order_by(models.User.id).all()


def names(db: Session) -> dict[int, str]:
    return {u.id: u.display_name for u in users(db)}


# ---------- rythme par défaut ----------

def rhythm(db: Session) -> dict:
    try:
        r = json.loads(S.get_setting(db, "night_rhythm") or "{}")
    except ValueError:
        r = {}
    return r if r.get("mode") in MODES else {"mode": "none"}


def from_rhythm(r: dict, d: date) -> int | None:
    """Parent que le rythme donne pour la nuit d (rien avant le jour où il a été choisi)."""
    if r["mode"] == "none" or d.isoformat() < r.get("since", ""):
        return None
    if r["mode"] == "weekdays":
        return r["weekdays"][d.weekday()]
    gap = (d - date.fromisoformat(r["anchor"])).days
    return r["first"] if gap % 2 == 0 else r["second"]


def set_rhythm(db: Session, value: dict, today: date) -> dict:
    """Nouveau rythme, valable à partir de ce soir. Les nuits passées que l'ancien remplissait
    sont d'abord notées telles quelles, pour que l'historique ne change pas."""
    old = rhythm(db)
    if old["mode"] != "none":
        d = max(date.fromisoformat(old["since"]), today - timedelta(days=KEEP_PAST))
        while d < today:
            if db.get(models.NightDuty, d.isoformat()) is None and from_rhythm(old, d) is not None:
                db.add(models.NightDuty(day=d.isoformat(), user_id=from_rhythm(old, d)))
            d += timedelta(days=1)
    r = {"mode": value["mode"]}
    if r["mode"] != "none":
        r["since"] = today.isoformat()
    if r["mode"] == "weekdays":
        r["weekdays"] = value["weekdays"]
    elif r["mode"] == "alternate":
        r |= {"anchor": value["anchor"], "first": value["first"], "second": value["second"]}
    S.set_setting(db, "night_rhythm", json.dumps(r))
    return r


# ---------- nuits ----------

def assigned(db: Session, d: date, r: dict | None = None) -> tuple[int | None, str | None]:
    """(parent, d'où il vient : « set » choisi à la main, « rhythm » rythme par défaut, None personne)."""
    row = db.get(models.NightDuty, d.isoformat())
    if row is not None:
        return row.user_id, "set"
    uid = from_rhythm(r or rhythm(db), d)
    return uid, "rhythm" if uid is not None else None


def set_night(db: Session, d: date, user_id: int | None, actor: models.User) -> tuple[int | None, int | None]:
    """Choix à la main pour la nuit d. Renvoie (avant, après)."""
    old, _ = assigned(db, d)
    row = db.get(models.NightDuty, d.isoformat())
    if row is None:
        row = models.NightDuty(day=d.isoformat())
        db.add(row)
    row.user_id, row.set_by = user_id, actor.id
    return old, user_id


def copy_last(db: Session, start: date, actor: models.User) -> int:
    """La semaine qui commence à start reprend la précédente ; les nuits vides la semaine dernière
    ne vident rien. Renvoie le nombre de nuits remplies."""
    r, n = rhythm(db), 0
    for i in range(7):
        src, _ = assigned(db, start - timedelta(days=7 - i), r)
        if src is not None:
            set_night(db, start + timedelta(days=i), src, actor)
            n += 1
    return n


def night_label(d: date) -> str:
    return f"nuit de {S.WEEKDAYS[d.weekday()]}"


def week_label(start: date) -> str:
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"Du {start.day} au {end.day} {S.MONTHS[end.month - 1]}"
    return f"Du {start.day} {S.MONTHS[start.month - 1]} au {end.day} {S.MONTHS[end.month - 1]}"


def tonight_date(view: dict) -> date:
    """La nuit qui vient ou qui est en cours : celle du jour affiché par l'app."""
    return date.fromisoformat(view["date"])


def week(db: Session, start: date, me: models.User, tonight: date) -> dict:
    start, r, who = monday(start), rhythm(db), names(db)
    nights, counts = [], {uid: 0 for uid in who}
    for i in range(7):
        d = start + timedelta(days=i)
        uid, source = assigned(db, d, r)
        planned = from_rhythm(r, d)
        if uid in counts:
            counts[uid] += 1
        nights.append({"date": d.isoformat(), "label": f"{DAYS[i]} {d.day}", "user_id": uid, "source": source,
                       "changed": source == "set" and planned is not None and planned != uid,
                       "tonight": d == tonight, "past": d < tonight})
    return {
        "start": start.isoformat(), "label": week_label(start), "this_week": monday(tonight).isoformat(),
        "tonight": tonight.isoformat(), "me": me.id,
        "users": [{"id": uid, "name": n} for uid, n in who.items()],
        "nights": nights, "counts": counts,
        "empty": sum(1 for n in nights if n["user_id"] is None and not n["past"]),
        "rhythm": r,
    }


def tonight(db: Session, view: dict, me: models.User, now: datetime) -> dict | None:
    """Ligne « Cette nuit » de l'écran Aujourd'hui : le soir à partir de 16 h, et toute la nuit."""
    if view["mode"] != "night" and 6 <= now.hour < 16:
        return None
    d = tonight_date(view)
    uid, _ = assigned(db, d)
    who = names(db)
    return {"date": d.isoformat(), "label": night_label(d), "user_id": uid, "name": who.get(uid),
            "me": uid == me.id, "me_id": me.id, "users": [{"id": i, "name": n} for i, n in who.items()]}


def bed_time(db: Session, d: date) -> datetime | None:
    beds = S.events_between(db, S.midnight(d) + timedelta(hours=12), S.midnight(d) + timedelta(hours=30), ("bed",))
    return S.parse(beds[-1].start) if beds else None


# ---------- textes des notifications ----------

def change_notices(db: Session, d: date, old: int | None, new: int | None, actor: models.User) -> list[tuple[int, dict]]:
    """Qui prévenir quand un parent change une nuit, et quoi lui dire. Jamais celui qui a fait le changement."""
    if old == new:
        return []
    when, out = night_label(d), []
    name = actor.display_name
    if new is not None and new != actor.id:
        body = f"{name} vous a donné la {when}." if old != actor.id else f"{name} vous a passé sa {when}."
        out.append((new, {"title": f"Nuits : {when}", "body": body, "tag": f"duty-{d}"}))
    if old is not None and old != actor.id and old != new:
        body = (f"{name} a pris votre {when}." if new == actor.id
                else f"{name} a retiré votre {when} : personne n'est prévu." if new is None
                else f"Votre {when} a été donnée à quelqu'un d'autre par {name}.")
        out.append((old, {"title": f"Nuits : {when}", "body": body, "tag": f"duty-{d}"}))
    return out


def week_notices(db: Session, start: date, actor: models.User, what: str) -> list[tuple[int, dict]]:
    return [(u.id, {"title": "Nuits", "body": f"{actor.display_name} {what}", "tag": f"duty-week-{start}"})
            for u in users(db) if u.id != actor.id]


def due(db: Session, view: dict, now: datetime) -> list[tuple[int | None, dict]]:
    """Rappels du jour, chacun avec une clé stable. (None, …) = pour tous les parents."""
    d, child = tonight_date(view), view["child"]["name"]
    out = []
    if now.date() == d:
        uid, _ = assigned(db, d)
        bed = bed_time(db, d)
        # Rappel du soir : au coucher noté, sinon à 20 h
        if uid is not None and 17 <= now.hour and (bed is not None or now.hour >= 20):
            body = (f"{child} est couchée depuis {bed:%H:%M}. C'est vous qui vous levez cette nuit."
                    if bed else "C'est vous qui vous levez cette nuit.")
            out.append((uid, {"kind": "duty_eve", "key": f"duty|eve|{d}",
                              "title": f"{child} : cette nuit, c'est vous", "body": body}))
        if uid is None and now.hour == 18 and now.minute < 30:
            out.append((None, {"kind": "duty_empty", "key": f"duty|empty|{d}", "title": f"{child} : nuit de ce soir",
                               "body": "Personne n'est prévu pour la nuit de ce soir. Touchez pour choisir."}))
    if now.weekday() == 6 and now.hour == 19 and now.minute < 30:
        start, r = now.date() + timedelta(days=1), rhythm(db)
        empty = sum(1 for i in range(7) if assigned(db, start + timedelta(days=i), r)[0] is None)
        if empty:
            s = "s" if empty > 1 else ""
            out.append((None, {"kind": "duty_week", "key": f"duty|week|{start}", "title": "Nuits de la semaine prochaine",
                               "body": f"{empty} nuit{s} à attribuer pour la semaine du {start.day} {S.MONTHS[start.month - 1]}. Touchez pour planifier."}))
    return out
