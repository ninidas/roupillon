"""Les gestes du quotidien (boutons de l'app, widget, Raccourcis) : un seul endroit pour les règles."""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import engine as E
from . import models
from . import service as S


class ActionError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


ACTS = ("wake", "nap_start", "nap_end", "bed", "night_start", "night_end", "feed")


def _open(db: Session, kind: str, t: datetime, hours: int = 14):
    return (db.query(models.Event).filter(models.Event.kind == kind, models.Event.end.is_(None),
                                          models.Event.start >= S.stamp(t - timedelta(hours=hours)),
                                          models.Event.start <= S.stamp(t))
            .order_by(models.Event.start.desc()).first())


def _nap_number(db: Session, ev: models.Event) -> int:
    start = S.parse(ev.start)
    day, _ = S.build_day(db, start.date())
    ids = [n.id for n in day.naps]
    return ids.index(ev.id) + 1 if ev.id in ids else len(ids) or 1


def _add(db: Session, user, kind: str, t: datetime, **kw) -> models.Event:
    ev = models.Event(kind=kind, start=S.stamp(t), created_by=user.id, updated_by=user.id, **kw)
    db.add(ev)
    db.flush()
    return ev


def _planned(db: Session, t: datetime, kind: str):
    """Heure prévue pour la prochaine sieste (ou le coucher) de la journée en cours, avant le geste."""
    mode, d = S.current(db, t)
    if mode != "day":
        return None, d
    _, _, items = S.forecast(db, d, t.date())
    if kind == "bed":
        x = items[-1]
    else:
        x = next((i for i in items if i["type"] == "nap" and not i["start_real"]), None)
    return (S.stamp(S.at(d, x["start"])) if x else None), d


def check_time(t: datetime, now: datetime) -> None:
    if t > now + timedelta(minutes=5) or t < now - timedelta(hours=24):
        raise ActionError(422, "Heure hors de la journée en cours")


def do(db: Session, user, act: str, t: datetime, ml: int | None = None) -> dict:
    """Applique le geste à l'heure t. Renvoie le message à afficher et de quoi l'annuler."""
    hm = t.strftime("%H:%M")
    if act == "wake":
        ev = next((e for e in S.events_between(db, S.midnight(t.date()), S.midnight(t.date()) + timedelta(days=1), ("wake",))), None)
        # Levée pendant un réveil nocturne : le réveil s'arrête là
        nw = _open(db, "night", t)
        if nw:
            nw.end, nw.updated_by = S.stamp(t), user.id
        if ev:
            undo = {"op": "patch", "id": ev.id, "body": {"start": ev.start.replace(" ", "T")}}
            ev.start, ev.updated_by = S.stamp(t), user.id
        else:
            ev = _add(db, user, "wake", t)
            undo = {"op": "delete", "id": ev.id}
        db.commit()
        return {"event_id": ev.id, "field": "start", "at": S.iso(t), "undo": undo, "message": f"Levée à {hm}"}

    if act == "nap_start":
        cur = _open(db, "nap", t)
        if cur:
            raise ActionError(409, f"Une sieste est déjà en cours depuis {cur.start[-5:]}")
        planned, d = _planned(db, t, "nap")
        ev = _add(db, user, "nap", t, planned_start=planned)
        # Fin estimée maintenant que l'heure réelle d'endormissement est connue
        _, _, items = S.forecast(db, d, t.date())
        x = next((i for i in items if i["type"] == "nap" and i["id"] == ev.id), None)
        if x:
            ev.planned_end = S.stamp(S.at(d, x["end"]))
        db.commit()
        return {"event_id": ev.id, "field": "start", "at": S.iso(t), "undo": {"op": "delete", "id": ev.id},
                "message": f"Sieste {_nap_number(db, ev)} commencée à {hm}"}

    if act == "nap_end":
        ev = _open(db, "nap", t)
        if not ev:
            raise ActionError(409, "Aucune sieste en cours")
        start = S.parse(ev.start)
        end = max(t, start + timedelta(minutes=1))
        ev.end, ev.updated_by = S.stamp(end), user.id
        db.commit()
        return {"event_id": ev.id, "field": "end", "at": S.iso(end), "undo": {"op": "patch", "id": ev.id, "body": {"end": None}},
                "message": f"Sieste {_nap_number(db, ev)} terminée à {end.strftime('%H:%M')} · {E.dur((end - start).total_seconds() / 60)}"}

    if act == "bed":
        d = S.bed_day(t)
        m0 = S.midnight(d)
        ev = next(iter(S.events_between(db, m0 + timedelta(hours=12), m0 + timedelta(hours=30), ("bed",))), None)
        if ev:
            undo = {"op": "patch", "id": ev.id, "body": {"start": ev.start.replace(" ", "T")}}
            ev.start, ev.updated_by = S.stamp(t), user.id
        else:
            ev = _add(db, user, "bed", t, planned_start=_planned(db, t, "bed")[0])
            undo = {"op": "delete", "id": ev.id}
        db.commit()
        return {"event_id": ev.id, "field": "start", "at": S.iso(t), "undo": undo, "message": f"Couchée à {hm}, bonne nuit"}

    if act in ("night_start", "night_end"):
        mode, _ = S.current(db, t)
        if mode != "night":
            raise ActionError(409, "Pas de nuit en cours : notez d'abord le coucher")
        cur = _open(db, "night", t)
        if act == "night_start":
            if cur:
                raise ActionError(409, f"Un réveil est déjà en cours depuis {cur.start[-5:]}")
            ev = _add(db, user, "night", t)
            db.commit()
            return {"event_id": ev.id, "field": "start", "at": S.iso(t), "undo": {"op": "delete", "id": ev.id},
                    "message": f"Réveil nocturne à {hm}"}
        if not cur:
            raise ActionError(409, "Aucun réveil nocturne en cours")
        start = S.parse(cur.start)
        end = max(t, start + timedelta(minutes=1))
        cur.end, cur.updated_by = S.stamp(end), user.id
        db.commit()
        return {"event_id": cur.id, "field": "end", "at": S.iso(end), "undo": {"op": "patch", "id": cur.id, "body": {"end": None}},
                "message": f"Rendormie à {end.strftime('%H:%M')} · {E.dur((end - start).total_seconds() / 60)}"}

    if act == "feed":
        ev = _add(db, user, "feed", t, ml=ml)
        db.commit()
        return {"event_id": ev.id, "field": "start", "at": S.iso(t), "undo": {"op": "delete", "id": ev.id},
                "message": f"Biberon à {hm}" + (f", {ml} ml" if ml else "")}

    raise ActionError(400, "Action inconnue")


def toggle(db: Session, user, t: datetime) -> dict:
    """Raccourci « dort / réveillée » : sieste le jour, réveil nocturne la nuit."""
    mode, _ = S.current(db, t)
    if mode == "night":
        return do(db, user, "night_end" if _open(db, "night", t) else "night_start", t)
    return do(db, user, "nap_end" if _open(db, "nap", t) else "nap_start", t)
