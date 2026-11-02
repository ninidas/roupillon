"""Notifications sur le téléphone : prochaine sieste, prochain biberon, coucher.
Le serveur regarde chaque minute la journée telle que l'app l'affiche et prévient chaque parent
abonné quelques minutes avant, une seule fois par événement. Rien la nuit ni pendant une sieste.
Sur iPhone, il faut ouvrir l'app depuis l'écran d'accueil (iOS 16.4 ou plus) pour s'abonner."""
import base64
import json
import os
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from . import engine as E
from . import models
from . import service as S
from .database import SessionLocal

CHECK_EVERY = 60     # secondes
LATE = 5             # minutes : passé l'heure prévue de plus que ça, on ne prévient plus
LEADS = (5, 10, 15, 20, 30)
DEFAULTS = {"nap": True, "feed": True, "bed": False, "lead": 15}
# Le serveur n'envoie qu'aux services de notification des navigateurs, jamais à une adresse quelconque
PUSH_HOSTS = ("push.apple.com", "fcm.googleapis.com", "push.services.mozilla.com", "notify.windows.com")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def vapid_keys(db: Session) -> tuple[str, str]:
    """(clé privée, clé publique) qui signent les envois, créées au premier besoin et gardées en base."""
    priv, pub = S.get_setting(db, "vapid_private"), S.get_setting(db, "vapid_public")
    if priv and pub:
        return priv, pub
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    priv = _b64(key.private_numbers().private_value.to_bytes(32, "big"))
    pub = _b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    S.set_setting(db, "vapid_private", priv)
    S.set_setting(db, "vapid_public", pub)
    db.commit()
    return priv, pub


def endpoint_ok(url: str) -> bool:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


def prefs(db: Session, user_id: int) -> dict:
    raw = S.get_setting(db, f"notify:{user_id}")
    try:
        saved = json.loads(raw) if raw else {}
    except ValueError:
        saved = {}
    out = DEFAULTS | {k: v for k, v in saved.items() if k in DEFAULTS}
    if out["lead"] not in LEADS:
        out["lead"] = DEFAULTS["lead"]
    return out


def set_prefs(db: Session, user_id: int, values: dict) -> dict:
    p = prefs(db, user_id) | {k: v for k, v in values.items() if k in DEFAULTS and v is not None}
    S.set_setting(db, f"notify:{user_id}", json.dumps(p))
    return p


# ---------- ce qu'il y a à annoncer ----------

def due(view: dict, lead: int, now: datetime) -> list[dict]:
    """Événements dont l'heure prévue tombe dans les `lead` prochaines minutes (ou vient de passer
    de moins de LATE minutes). Chacun a une clé stable : on ne l'annonce qu'une fois."""
    if view["mode"] == "night":
        return []
    dial, d = view["dial"], datetime.strptime(view["date"], "%Y-%m-%d").date()
    nm = dial["now"]
    if any(n["start_real"] and not n["end_real"] for n in dial["naps"]):
        return []      # elle dort : on la laisse dormir
    name = view["child"]["name"]
    soon = lambda m: m - lead <= nm < m + LATE
    out = []
    # Siestes : seulement une fois le lever noté, sinon l'heure part d'un lever supposé à 7 h
    if dial["wake_real"]:
        nxt = next((n for n in dial["naps"] if not n["start_real"]), None)
        if nxt and soon(nxt["start"]):
            ends = [n["end"] for n in dial["naps"] if n["end_real"] and n["end"] <= nm]
            awake = nm - (ends[-1] if ends else dial["wake"])
            out.append({"kind": "nap", "key": f"{d}|nap|{nxt['idx']}",
                        "title": f"{name} : sieste {nxt['idx'] + 1} vers {E.fmt(nxt['start'])}",
                        "body": f"{_in(nxt['start'] - nm)} Éveillée depuis {E.dur(awake)}."})
        if not dial["bed_real"] and soon(_bed(view)):
            later = [n for n in dial["naps"] if not n["start_real"]]
            if not later:
                out.append({"kind": "bed", "key": f"{d}|bed",
                            "title": f"{name} : coucher vers {E.fmt(_bed(view))}",
                            "body": _in(_bed(view) - nm) + " Pensez à noter le coucher."})
    last = view["feed"]["last"]
    if last and last["next"]:
        h, m = (int(x) for x in last["next"].split(":"))
        nxt_dt = datetime(now.year, now.month, now.day, h, m)
        if nxt_dt < now - timedelta(hours=12):
            nxt_dt += timedelta(days=1)
        mins = (nxt_dt - now).total_seconds() / 60
        if -LATE < mins <= lead:
            ml = f" ({last['ml']} ml)" if last["ml"] else ""
            out.append({"kind": "feed", "key": f"feed|{last['id']}",
                        "title": f"{name} : biberon vers {last['next']}",
                        "body": f"{_in(mins)} Le dernier était à {last['time']}{ml}."})
    return out


def _bed(view: dict) -> int:
    h, m = (int(x) for x in view["dial"]["bed_label"].split(":"))
    return h * 60 + m + (1440 if h < 6 else 0)


def _in(mins: float) -> str:
    mins = round(mins)
    return "Dans 1 min environ." if mins == 1 else f"Dans {mins} min environ." if mins > 0 else "C'est l'heure."


# ---------- envoi ----------

def send(db: Session, sub: models.PushSub, payload: dict) -> bool:
    """Un envoi. Abonnement disparu (téléphone désabonné, app supprimée) : on l'oublie."""
    from pywebpush import WebPushException, webpush
    priv, _ = vapid_keys(db)
    origin = S.get_setting(db, "push_origin") or "https://github.com/ninidas/roupillon"
    try:
        webpush({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=json.dumps(payload), vapid_private_key=priv, vapid_claims={"sub": origin},
                ttl=30 * 60, timeout=15, headers={"Urgency": "high"})
        return True
    except WebPushException as e:
        status = e.response.status_code if e.response is not None else None
        if status in (403, 404, 410):
            db.delete(sub)
            db.commit()
        print(f"Notification non envoyée ({status}) : {e}", flush=True)
        return False


def send_user(db: Session, user_id: int, payload: dict) -> int:
    subs = db.query(models.PushSub).filter_by(user_id=user_id).all()
    return sum(send(db, s, payload) for s in subs)


def tick(db: Session, now: datetime | None = None) -> list[str]:
    """Un passage : annonce ce qui arrive, à chaque parent selon ses réglages. Renvoie les clés envoyées."""
    users = {s.user_id for s in db.query(models.PushSub).all()}
    if not users:
        return []
    now = now or S.now_local()
    view = S.today_view(db, now)
    sent = []
    for uid in sorted(users):
        p = prefs(db, uid)
        for ev in due(view, p["lead"], now):
            if not p[ev["kind"]]:
                continue
            key = f"{ev['key']}|{uid}"
            if db.get(models.PushSent, key):
                continue
            db.add(models.PushSent(key=key, at=now))
            db.commit()
            send_user(db, uid, {"title": ev["title"], "body": ev["body"], "tag": ev["kind"]})
            sent.append(key)
    db.query(models.PushSent).filter(models.PushSent.at < now - timedelta(days=3)).delete()
    db.commit()
    return sent


def _loop():
    while True:
        db = SessionLocal()
        try:
            tick(db)
        except Exception as e:  # une notification ratée ne doit jamais faire tomber l'app
            print(f"Notifications : {e}", flush=True)
        finally:
            db.close()
        time.sleep(CHECK_EVERY)


def start():
    if os.environ.get("PUSH_LOOP", "1") != "0":
        threading.Thread(target=_loop, name="push", daemon=True).start()
