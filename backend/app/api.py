import secrets
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session

from . import actions as A
from . import engine as E
from . import models
from . import service as S
from .auth import (burn_password_check, create_token, current_user, hash_password, key_hash, new_widget_key,
                   password_problem, verify_password, widget_user)
from .database import get_db
from .limiter import limiter

router = APIRouter(prefix="/api")
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Hhmm = Annotated[str, StringConstraints(pattern=r"^\d{2}:\d{2}$")]
Stamp = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")]
Ml = Annotated[int, Field(ge=0, le=400)]


def fail(e: A.ActionError):
    raise HTTPException(status_code=e.status, detail=e.message)


def user_out(u: models.User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "has_widget_key": bool(u.widget_key_hash)}


# ---------- installation et connexion ----------

class Account(BaseModel):
    display_name: Name
    username: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=2, max_length=30, pattern=r"^[a-z0-9._-]+$")]
    password: Annotated[str, Field(max_length=200)]


class SetupBody(BaseModel):
    child_name: Name
    birth_date: date
    accounts: Annotated[list[Account], Field(min_length=1, max_length=2)]


def check_birth(d: date) -> None:
    today = S.now_local().date()
    if d > today or d < today - timedelta(days=4 * 365):
        raise HTTPException(status_code=422, detail="Date de naissance invalide")


@router.get("/setup")
def setup_status(db: Session = Depends(get_db)):
    return {"needs_setup": db.query(models.User).count() == 0}


@router.post("/setup")
@limiter.limit("5/minute")
def setup(request: Request, body: SetupBody, db: Session = Depends(get_db)):
    if db.query(models.User).count():
        raise HTTPException(status_code=409, detail="L'app est déjà installée")
    check_birth(body.birth_date)
    if len({a.username for a in body.accounts}) != len(body.accounts):
        raise HTTPException(status_code=422, detail="Les deux identifiants doivent être différents")
    for a in body.accounts:
        if problem := password_problem(a.password):
            raise HTTPException(status_code=422, detail=f"{a.display_name} : {problem}")
    users = [models.User(username=a.username, display_name=a.display_name, password_hash=hash_password(a.password))
             for a in body.accounts]
    db.add_all(users)
    S.set_setting(db, "child_name", body.child_name)
    S.set_setting(db, "birth_date", body.birth_date.isoformat())
    db.commit()
    return {"token": create_token(users[0]), "user": user_out(users[0])}


class LoginBody(BaseModel):
    username: Annotated[str, Field(max_length=60)]
    password: Annotated[str, Field(max_length=200)]


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, body: LoginBody, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(username=body.username.strip().lower()).first()
    if not user:
        burn_password_check(body.password)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")
    return {"token": create_token(user), "user": user_out(user)}


@router.get("/me")
def me(user: models.User = Depends(current_user)):
    return user_out(user)


class PasswordBody(BaseModel):
    current: Annotated[str, Field(max_length=200)]
    new: Annotated[str, Field(max_length=200)]


@router.post("/me/password")
@limiter.limit("5/minute")
def change_password(request: Request, body: PasswordBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current, user.password_hash):
        raise HTTPException(status_code=403, detail="Mot de passe actuel incorrect")
    if problem := password_problem(body.new):
        raise HTTPException(status_code=422, detail=problem)
    user.password_hash = hash_password(body.new)
    user.session_key = secrets.token_hex(16)   # les autres appareils sont déconnectés
    db.commit()
    return {"token": create_token(user)}


@router.post("/me/widget-key")
def make_widget_key(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Nouvelle clé : l'ancienne cesse de marcher. Montrée une seule fois."""
    key = new_widget_key()
    user.widget_key_hash = key_hash(key)
    db.commit()
    return {"key": key}


@router.delete("/me/widget-key")
def drop_widget_key(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    user.widget_key_hash = None
    db.commit()
    return {"ok": True}


# ---------- la journée ----------

@router.get("/today")
def today(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return S.today_view(db)


class ActionBody(BaseModel):
    act: Literal["wake", "nap_start", "nap_end", "bed", "night_start", "night_end", "feed"]
    at: Stamp | None = None     # heure du geste sur le téléphone (envoi différé hors connexion)
    ml: Ml | None = None


def parse_at(value: str | None, now: datetime) -> datetime:
    if not value:
        return now
    return datetime.fromisoformat(value).replace(second=0, microsecond=0)


@router.post("/actions")
def action(body: ActionBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    now = S.now_local()
    t = parse_at(body.at, now)
    try:
        A.check_time(t, now)
        res = A.do(db, user, body.act, t, body.ml)
    except A.ActionError as e:
        fail(e)
    return res | {"today": S.today_view(db, now)}


class EventPatch(BaseModel):
    start: Hhmm | Stamp | None = None
    end: Hhmm | Stamp | None = None
    ml: Ml | None = None
    day: date | None = None     # journée de référence d'une heure « HH:MM »


class EventNew(BaseModel):
    kind: Literal["wake", "nap", "bed", "night", "feed"]
    day: date
    start: Hhmm
    end: Hhmm | None = None
    ml: Ml | None = None


def to_dt(value: str, kind: str, day: date) -> datetime:
    try:
        if len(value) == 5:
            return S.resolve(day, kind, value)
        return datetime.fromisoformat(value).replace(second=0, microsecond=0)
    except ValueError:
        raise HTTPException(status_code=422, detail="Heure invalide")


def check_span(kind: str, start: datetime, end: datetime | None) -> None:
    if end is None:
        return
    if end <= start:
        raise HTTPException(status_code=422, detail="L'heure de fin doit être après celle du début")
    if end - start > timedelta(hours=8):
        raise HTTPException(status_code=422, detail="Plus de 8 heures : vérifiez les heures")


def event_day(ev: models.Event) -> date:
    t = S.parse(ev.start)
    return S.bed_day(t) if ev.kind in ("bed", "night") else t.date()


def single_per_day(db: Session, kind: str, d: date):
    """Un seul lever et un seul coucher par journée : une nouvelle saisie remplace l'ancienne."""
    m0 = S.midnight(d)
    if kind == "wake":
        return next(iter(S.events_between(db, m0, m0 + timedelta(days=1), ("wake",))), None)
    if kind == "bed":
        return next(iter(S.events_between(db, m0 + timedelta(hours=12), m0 + timedelta(hours=30), ("bed",))), None)
    return None


@router.post("/events")
def add_event(body: EventNew, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    start = to_dt(body.start, body.kind, body.day)
    end = to_dt(body.end, body.kind, body.day) if body.end and body.kind in ("nap", "night") else None
    check_span(body.kind, start, end)
    if start > S.now_local() + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Cette heure n'est pas encore passée")
    ev = single_per_day(db, body.kind, body.day)
    if ev:
        ev.start, ev.updated_by = S.stamp(start), user.id
    else:
        ev = models.Event(kind=body.kind, start=S.stamp(start), end=S.stamp(end) if end else None,
                          ml=body.ml if body.kind == "feed" else None, created_by=user.id, updated_by=user.id)
        db.add(ev)
    db.commit()
    return {"id": ev.id}


@router.patch("/events/{event_id}")
def edit_event(event_id: int, body: EventPatch, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ev = db.get(models.Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Introuvable : déjà supprimé ?")
    day = body.day or event_day(ev)
    fields = body.model_fields_set
    start = to_dt(body.start, ev.kind, day) if "start" in fields and body.start else S.parse(ev.start)
    end = S.parse(ev.end) if ev.end else None
    if "end" in fields:
        end = to_dt(body.end, ev.kind, day) if body.end and ev.kind in ("nap", "night") else None
    check_span(ev.kind, start, end)
    if start > S.now_local() + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Cette heure n'est pas encore passée")
    ev.start, ev.end = S.stamp(start), S.stamp(end) if end else None
    if "ml" in fields and ev.kind == "feed":
        ev.ml = body.ml
    ev.updated_by = user.id
    db.commit()
    return {"id": ev.id}


@router.delete("/events/{event_id}")
def delete_event(event_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ev = db.get(models.Event, event_id)
    if ev:
        db.delete(ev)
        db.commit()
    return {"ok": True}


@router.get("/days/{d}/view")
def get_day_view(d: date, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return S.day_view(db, d, S.now_local())


@router.get("/days/{d}")
def get_day(d: date, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return S.day_detail(db, d)


@router.delete("/days/{d}")
def clear_day(d: date, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Efface siestes, coucher, nuit et biberons de la journée. Le lever reste."""
    day, feeds = S.build_day(db, d)
    ids = [n.id for n in day.naps] + [w.id for w in day.night] + [f["id"] for f in feeds] + ([day.bed_id] if day.bed_id else [])
    if ids:
        db.query(models.Event).filter(models.Event.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    return {"deleted": len(ids)}


@router.get("/history")
def history(days: int = 30, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    now = S.now_local()
    _, d0 = S.current(db, now)
    days = max(1, min(days, 120))
    out = [s for i in range(days)
           if (s := S.day_summary(db, d0 - timedelta(days=i), d0, E.minutes(now, d0) if i == 0 else None))]
    cfg = S.settings(db)
    age = S.age_params(cfg, now.date())
    lo, hi = S.REF_24H_RANGE[S.age_for(cfg, now.date())]
    hab = S.habits(db, d0)
    n = min(5, max(len(age["naps"]), len(hab["wins"]), len(hab["naps"])))
    her = lambda key, i: E.dur(h[0]) if (h := E._hab(hab, key, i)) else None
    rows = [{"label": f"Sieste {i + 1}",
             "win": E.dur(E.window(age, hab, i)), "win_ref": E.dur(E.default_window(age, i)), "win_her": her("wins", i),
             "nap": E.dur(E.nap_length(age, hab, i)), "nap_ref": E.dur(age["naps"][min(i, len(age["naps"]) - 1)]),
             "nap_her": her("naps", i)} for i in range(n)]
    learned = max([h[1] for key in ("wins", "naps") for h in hab[key] if h] or [0])
    ev = E.evening(age, hab)
    evening = {"win": E.dur(ev["wl"]), "win_ref": E.dur(age["wl"]),
               "bed": f"{E.fmt(ev['bed_min'])} à {E.fmt(ev['bed_max'])}",
               "bed_ref": f"{E.fmt(age['bed_min'])} à {E.fmt(age['bed_max'])}",
               "usual": E.fmt(hab["bedtime"][0]) if hab.get("bedtime") else None}
    return {"days": out, "rhythm": rows, "learned_days": learned, "evening": evening,
            "ref_24h": {"lo": lo * 60, "hi": hi * 60, "label": S.REF_24H[S.age_for(cfg, now.date())]}}


# ---------- poids ----------

class WeightNew(BaseModel):
    day: date
    kg: float = Field(ge=1.5, le=25)


def weight_out(w: models.Weight) -> dict:
    return {"id": w.id, "day": w.day, "label": S.date_label(date.fromisoformat(w.day)),
            "kg": S.kg_text(w.grams)}


@router.get("/growth")
def get_growth(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return S.growth(db, S.now_local().date())


@router.post("/weights")
def add_weight(body: WeightNew, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if body.day > S.now_local().date():
        raise HTTPException(status_code=422, detail="Cette date est dans le futur")
    w = models.Weight(day=body.day.isoformat(), grams=round(body.kg * 1000), created_by=user.id)
    db.add(w)
    db.commit()
    return weight_out(w)


@router.delete("/weights/{wid}")
def delete_weight(wid: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.get(models.Weight, wid)
    if not w:
        raise HTTPException(status_code=404, detail="Pesée introuvable")
    db.delete(w)
    db.commit()
    return {"deleted": 1}


# ---------- réglages ----------

@router.get("/settings")
def get_settings(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    cfg = S.settings(db)
    today = S.now_local().date()
    auto = E.auto_age(date.fromisoformat(cfg["birth_date"]), today) if cfg["birth_date"] else None
    return cfg | {"ages": [{"id": a["id"], "name": a["name"]} for a in E.AGES], "auto_age": auto,
                  "child": S.child_info(cfg, S.age_for(cfg, today), today),
                  "users": [{"id": u.id, "display_name": u.display_name} for u in db.query(models.User).all()]}


class SettingsBody(BaseModel):
    child_name: Name | None = None
    birth_date: date | None = None
    manual_age: str | None = None
    sex: Literal["f", "m"] | None = None


@router.put("/settings")
def put_settings(body: SettingsBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    fields = body.model_fields_set
    if "child_name" in fields and body.child_name:
        S.set_setting(db, "child_name", body.child_name)
    if "birth_date" in fields and body.birth_date:
        check_birth(body.birth_date)
        S.set_setting(db, "birth_date", body.birth_date.isoformat())
    if "manual_age" in fields:
        if body.manual_age is not None and body.manual_age not in E.AGE_BY_ID:
            raise HTTPException(status_code=422, detail="Âge inconnu")
        S.set_setting(db, "manual_age", body.manual_age)
    if "sex" in fields and body.sex:
        S.set_setting(db, "sex", body.sex)
    db.commit()
    return get_settings(user, db)


# ---------- widget Scriptable et Raccourcis iPhone ----------

@router.get("/quick/status")
@limiter.limit("60/minute")
def quick_status(request: Request, user: models.User = Depends(widget_user), db: Session = Depends(get_db)):
    v = S.today_view(db)
    return v["widget"] | {"child": v["child"]["name"], "now": v["now_iso"], "headline": v["headline"],
                          "feed": v["feed"]["last"]}


def quick_reply(request: Request, message: str):
    """Les Raccourcis affichent tel quel ce qu'on leur renvoie : ?text=1 donne la phrase seule."""
    if request.query_params.get("text"):
        return PlainTextResponse(message)
    return {"message": message}


@router.post("/quick/toggle")
@limiter.limit("20/minute")
def quick_toggle(request: Request, user: models.User = Depends(widget_user), db: Session = Depends(get_db)):
    try:
        return quick_reply(request, A.toggle(db, user, S.now_local())["message"])
    except A.ActionError as e:
        return quick_reply(request, e.message) if request.query_params.get("text") else fail(e)


class QuickFeed(BaseModel):
    ml: Ml | None = None


@router.post("/quick/feed")
@limiter.limit("20/minute")
def quick_feed(request: Request, body: QuickFeed | None = None, user: models.User = Depends(widget_user), db: Session = Depends(get_db)):
    return quick_reply(request, A.do(db, user, "feed", S.now_local(), body.ml if body else None)["message"])
