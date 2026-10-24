"""Lecture de la base et mise en forme de ce qu'affichent l'app, le widget et les Raccourcis."""
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from . import engine as E
from . import models

TZ = ZoneInfo(os.environ.get("APP_TZ", "Europe/Paris"))
FMT = "%Y-%m-%d %H:%M"
WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
          "octobre", "novembre", "décembre"]
MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
# Repères donnés à titre indicatif, comme dans l'oracle d'origine
DAY_REF = {"2.5-3": "Repère vers 3 mois : 4 à 5 h de siestes par jour",
           "3-4": "Repère vers 3 mois : 4 à 5 h de siestes par jour"}
REF_24H_RANGE = {a: (14, 17) for a in ("0-6s", "6-10s", "2.5-3", "3-4")} | {a: (12, 15) for a in ("4-6", "6-9", "9-12")}
REF_24H = {a: f"{lo} à {hi} h" for a, (lo, hi) in REF_24H_RANGE.items()}


def now_local() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def parse(s: str) -> datetime:
    return datetime.strptime(s, FMT)


def stamp(dt: datetime) -> str:
    return dt.strftime(FMT)


def midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def at(d: date, m: float) -> datetime:
    return midnight(d) + timedelta(minutes=round(m))


def real_dur(d: date, a: float, b: float) -> float:
    """Minutes réellement écoulées entre les minutes a et b du jour d, heures locales.
    La nuit d'un changement d'heure compte une heure de plus (octobre) ou de moins (mars).
    Une heure qui existe deux fois (2 h à 3 h en octobre) est prise à sa première occurrence."""
    utc = lambda m: at(d, m).replace(tzinfo=TZ).astimezone(ZoneInfo("UTC"))
    return (utc(b) - utc(a)).total_seconds() / 60


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:00")


def date_label(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def short_label(d: date, today: date) -> str:
    if d == today:
        return "Aujourd'hui"
    if d == today - timedelta(days=1):
        return "Hier"
    return f"{WEEKDAYS[d.weekday()][:3]}. {d.day} {MONTHS_SHORT[d.month - 1]}"


def bed_day(dt: datetime) -> date:
    """Un coucher après minuit appartient encore à la veille."""
    return dt.date() if dt.hour >= 6 else dt.date() - timedelta(days=1)


def resolve(d: date, kind: str, hhmm: str) -> datetime:
    """Heure saisie « HH:MM » sur la journée d : la nuit déborde sur le lendemain."""
    h, m = (int(x) for x in hhmm.split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("heure invalide")
    dt = midnight(d) + timedelta(hours=h, minutes=m)
    if (kind == "bed" and h < 6) or (kind == "night" and h < 12):
        dt += timedelta(days=1)
    return dt


# ---------- réglages ----------

def get_setting(db: Session, key: str, default=None):
    row = db.get(models.AppConfig, key)
    return row.value if row and row.value is not None else default


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(models.AppConfig, key)
    if row is None:
        db.add(models.AppConfig(key=key, value=value))
    else:
        row.value = value


def settings(db: Session) -> dict:
    birth = get_setting(db, "birth_date")
    return {
        "child_name": get_setting(db, "child_name", "Bébé"),
        "birth_date": birth,
        "manual_age": get_setting(db, "manual_age"),
        "sex": get_setting(db, "sex"),
    }


def weight_on(db: Session, d: date):
    """Dernière pesée faite au plus tard le jour d."""
    return (db.query(models.Weight).filter(models.Weight.day <= d.isoformat())
            .order_by(models.Weight.day.desc(), models.Weight.id.desc()).first())


def milk_info(db: Session, cfg: dict, d: date) -> dict | None:
    w = weight_on(db, d)
    if not w or not cfg["birth_date"]:
        return None
    ref = E.milk_ref(w.grams, (d - date.fromisoformat(cfg["birth_date"])).days)
    if not ref:
        return None
    return ref | {"kg": kg_text(w.grams), "weighed": short_label(date.fromisoformat(w.day), d).lower(),
                  "label": f"souvent {ref['lo']} à {ref['hi']} ml par jour"}


def kg_text(grams: int) -> str:
    return f"{grams / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def growth(db: Session, today: date) -> dict:
    """Pesées, gain depuis la précédente, et courbes OMS jusqu'un peu après l'âge actuel."""
    cfg = settings(db)
    birth = date.fromisoformat(cfg["birth_date"]) if cfg["birth_date"] else None
    ws = db.query(models.Weight).order_by(models.Weight.day, models.Weight.id).all()
    out, prev = [], None
    for w in ws:
        d = date.fromisoformat(w.day)
        gain = None
        if prev:
            g, n = w.grams - prev.grams, (d - date.fromisoformat(prev.day)).days
            gain = f"{'+' if g >= 0 else '−'}{abs(g)} g" + (f" en {E.plural(n, 'jour')}" if n else " le même jour")
        out.append({"id": w.id, "day": w.day, "label": date_label(d), "kg": kg_text(w.grams), "grams": w.grams,
                    "age_days": (d - birth).days if birth else None, "gain": gain})
        prev = w
    age = (today - birth).days if birth else None
    span = None
    if age is not None:
        last = max([x["age_days"] for x in out if x["age_days"] is not None] or [0])
        span = min(730, max(183, max(age, last) + 45))
    curves = E.who_curves(cfg["sex"], span) if cfg["sex"] in E.WHO_WFA and span else None
    return {"sex": cfg["sex"], "age_days": age, "span_days": span, "weights": out[::-1], "curves": curves,
            "milk": milk_info(db, cfg, today)}


def age_for(cfg: dict, today: date) -> str:
    if cfg["manual_age"] in E.AGE_BY_ID:
        return cfg["manual_age"]
    if cfg["birth_date"]:
        return E.auto_age(date.fromisoformat(cfg["birth_date"]), today)
    return "2.5-3"


def age_params(cfg: dict, today: date) -> dict:
    """Repères utilisés par les prévisions : la tranche choisie à la main telle quelle,
    sinon ceux de l'âge exact d'après la date de naissance."""
    if cfg["manual_age"] not in E.AGE_BY_ID and cfg["birth_date"]:
        return E.smooth_age((today - date.fromisoformat(cfg["birth_date"])).days)
    return E.AGE_BY_ID[age_for(cfg, today)]


# ---------- journées ----------

def events_between(db: Session, a: datetime, b: datetime, kinds: tuple | None = None):
    q = db.query(models.Event).filter(models.Event.start >= stamp(a), models.Event.start < stamp(b))
    if kinds:
        q = q.filter(models.Event.kind.in_(kinds))
    return q.order_by(models.Event.start, models.Event.id).all()


def build_day(db: Session, d: date, evs: list | None = None) -> tuple[E.Day, list[dict]]:
    """evs : événements déjà chargés couvrant au moins d et d+1 (sinon lus ici)."""
    m0 = midnight(d)
    if evs is None:
        evs = events_between(db, m0, m0 + timedelta(days=2))
    mins = lambda s: E.minutes(parse(s), d) if s else None
    day = E.Day(date=d)
    wakes = [e for e in evs if e.kind == "wake" and parse(e.start).date() == d]
    if wakes:
        day.wake, day.wake_real, day.wake_id = mins(wakes[0].start), True, wakes[0].id
    beds = [e for e in evs if e.kind == "bed" and m0 + timedelta(hours=12) <= parse(e.start) < m0 + timedelta(hours=30)]
    bed_dt = parse(beds[0].start) if beds else None
    if beds:
        day.bed, day.bed_id = mins(beds[0].start), beds[0].id
    nap_end = bed_dt or m0 + timedelta(days=1)
    day.naps = [E.Span(mins(e.start), mins(e.end), e.id) for e in evs
                if e.kind == "nap" and m0 + timedelta(hours=4) <= parse(e.start) < nap_end]
    if bed_dt:
        next_wake = [e for e in evs if e.kind == "wake" and parse(e.start) > bed_dt]
        limit = parse(next_wake[0].start) if next_wake else bed_dt + timedelta(hours=18)
        day.night = [E.Span(mins(e.start), mins(e.end), e.id) for e in evs
                     if e.kind == "night" and bed_dt <= parse(e.start) < limit]
    feeds = [{"id": e.id, "t": mins(e.start), "ml": e.ml} for e in evs
             if e.kind == "feed" and parse(e.start).date() == d]
    return day, feeds


def current(db: Session, now: datetime) -> tuple[str, date]:
    """« night » si un coucher des 18 dernières heures n'a été suivi ni d'un lever ni d'une sieste."""
    beds = events_between(db, now - timedelta(hours=18), now + timedelta(minutes=1), ("bed",))
    if beds:
        bed = beds[-1]
        after = events_between(db, parse(bed.start) + timedelta(minutes=1), now + timedelta(minutes=1), ("wake", "nap"))
        if not after:
            return "night", bed_day(parse(bed.start))
    d = now.date()
    if now.hour < 4 and not events_between(db, midnight(d), now + timedelta(minutes=1), ("wake",)):
        d -= timedelta(days=1)
    return "day", d


def habits(db: Session, d: date) -> dict:
    """Ses habitudes sur les jours qui précèdent d (la journée en cours n'est pas finie)."""
    first = d - timedelta(days=E.LEARN_DAYS)
    evs = events_between(db, midnight(first), midnight(d) + timedelta(days=1))
    return E.habits([build_day(db, d - timedelta(days=k), evs)[0] for k in range(1, E.LEARN_DAYS + 1)])


def forecast(db: Session, d: date, today: date):
    """Journée d, ses biberons et sa prévision, telle que l'app l'affiche."""
    day, feeds = build_day(db, d)
    return day, feeds, E.plan(day, age_params(settings(db), today), habits(db, d))


def last_night(db: Session, d: date, day: E.Day) -> dict | None:
    """Nuit qui s'est terminée au lever (réel) du jour d."""
    if not day.wake_real:
        return None
    prev, _ = build_day(db, d - timedelta(days=1))
    info = E.night_info(prev, day.wake + 1440, lambda a, b: real_dur(prev.date, a, b))
    return {"sleep": info["sleep"], "count": info["count"]} if info else None


def last_feed(db: Session, now: datetime):
    evs = events_between(db, now - timedelta(days=2), now + timedelta(minutes=1), ("feed",))
    return evs[-1] if evs else None


# ---------- vue « Aujourd'hui » ----------

def btn(act: str, label: str, style: str = "nap", time: str | None = None) -> dict:
    return {"act": act, "label": label, "style": style, "time": time}


def today_view(db: Session, now: datetime | None = None) -> dict:
    now = now or now_local()
    mode, d = current(db, now)
    cfg = settings(db)
    age_id = age_for(cfg, now.date())
    day, feeds, items = forecast(db, d, now.date())
    nm = E.minutes(now, d)
    hm = E.fmt(nm)
    hi = None
    widget: dict

    if mode == "night":
        info = E.night_info(day, nm, lambda a, b: real_dur(d, a, b))
        open_w = next((w for w in day.night if w.end is None), None)
        if open_w:
            headline = {"cap": "Réveil nocturne", "big": E.dur(real_dur(d, open_w.start, nm)), "icon": "eye",
                        "sub": f"Réveillée à {E.fmt(open_w.start)} · nuit commencée à {E.fmt(day.bed)}"}
            actions = [btn("night_end", "Rendormie", "nap", hm)]
            widget = {"state": "night_awake", "title": "Réveil nocturne", "line": f"depuis {E.fmt(open_w.start)}",
                      "since": iso(at(d, open_w.start))}
        else:
            headline = {"cap": "Nuit en cours", "big": E.dur(info["sleep"]), "icon": "moon",
                        "sub": f"Couchée à {E.fmt(day.bed)} · {E.plural(info['count'], 'réveil') if info['count'] else 'aucun réveil'}"}
            actions = [btn("night_start", "Réveil nocturne", "night", hm)]
            widget = {"state": "night", "title": "Nuit en cours", "line": f"couchée à {E.fmt(day.bed)}",
                      "since": iso(at(d, day.bed))}
        if nm >= 1440:
            actions.append(btn("wake", "Levée", "awake", hm))
    else:
        open_nap = next((x for x in items if x["type"] == "nap" and x["start_real"] and not x["end_real"]), None)
        done = [x for x in items if x["type"] == "nap" and x["end_real"] and x["end"] <= nm]
        awake_from = done[-1]["end"] if done else day.wake
        awake_txt = f"éveillée depuis {E.dur(nm - awake_from)}" if nm >= awake_from else "pas encore levée"
        due = next((x for x in items if x["type"] == "nap" and not x["start_real"] and x["start"] <= nm < x["end"]), None)
        up = next((x for x in items if x["type"] in ("nap", "bed") and not x.get("start_real") and x["start"] > nm), None)
        if open_nap:
            hi = open_nap
            p = (nm - open_nap["start"]) / max(1, open_nap["end"] - open_nap["start"])
            label = f"Sieste {open_nap['idx'] + 1}"
            headline = {"cap": f"{label} en cours", "big": E.fmt(open_nap["end"]), "icon": "moon", "progress": min(1, p),
                        "sub": f"Réveil estimé · endormie à {E.fmt(open_nap['start'])}, il y a {E.dur(nm - open_nap['start'])}"}
            widget = {"state": "nap", "title": f"{label} en cours", "line": f"réveil vers {E.fmt(open_nap['end'])}",
                      "since": iso(at(d, open_nap["start"])), "target": iso(at(d, open_nap["end"])), "progress": min(1, p)}
        elif due:
            hi = due
            label = f"Sieste {due['idx'] + 1}"
            headline = {"cap": label, "big": "Maintenant", "icon": "moon",
                        "sub": f"Prévue vers {E.fmt(due['start'])} · {awake_txt}"}
            widget = {"state": "due", "title": f"{label} maintenant", "line": f"prévue vers {E.fmt(due['start'])}",
                      "since": iso(at(d, awake_from))}
        elif up:
            hi = up
            label = "Coucher" if up["type"] == "bed" else f"Sieste {up['idx'] + 1}"
            p = (nm - awake_from) / max(1, up["start"] - awake_from)
            headline = {"cap": f"{label} dans", "big": E.dur(up["start"] - nm), "progress": max(0, min(1, p)),
                        "sub": f"Vers {E.fmt(up['start'])} · {awake_txt}"}
            widget = {"state": "awake", "title": f"{label} vers {E.fmt(up['start'])}", "line": awake_txt,
                      "target": iso(at(d, up["start"])), "since": iso(at(d, awake_from)), "progress": max(0, min(1, p))}
        else:
            hi = items[-1]
            headline = {"cap": "Coucher", "big": "Maintenant", "icon": "moon",
                        "sub": f"Prévu vers {E.fmt(items[-1]['start'])} · {awake_txt}"}
            widget = {"state": "bed", "title": "Coucher maintenant", "line": f"prévu vers {E.fmt(items[-1]['start'])}",
                      "since": iso(at(d, awake_from))}
        bed_item = items[-1]
        if open_nap:
            actions = [btn("nap_end", "Elle est réveillée", "awake", hm)]
        elif not day.wake_real and not day.naps and nm < 12 * 60:
            actions = [btn("wake", "Elle est levée", "awake", hm), btn("nap_start", "Elle dort", "ghost")]
        elif nm >= bed_item["start"] - 60 or nm >= 17 * 60 + 30:
            actions = [btn("bed", "Elle est couchée", "night", hm), btn("nap_start", "Sieste", "ghost")]
        else:
            actions = [btn("nap_start", "Elle dort", "nap", hm)]

    # Totaux
    slept = 0
    for x in items:
        if x["type"] == "nap" and x["start_real"]:
            e = x["end"] if x["end_real"] else max(x["start"], nm)
            slept += max(0, e - x["start"])
    planned = sum(x["end"] - x["start"] for x in items if x["type"] == "nap")
    ln = last_night(db, d, day)
    totals = {"slept": E.dur(slept), "planned": E.dur(planned), "pct": min(1, slept / planned) if planned else 0,
              "day_ref": DAY_REF.get(age_id), "ref_24h": REF_24H.get(age_id),
              "last_night": {"sleep": E.dur(ln["sleep"]), "count": ln["count"],
                             "wakes": (E.plural(ln["count"], "réveil") + (" nocturnes" if ln["count"] > 1 else " nocturne")) if ln["count"] else "Aucun réveil nocturne",
                             "total_24h": E.dur(ln["sleep"] + slept)} if ln and ln["sleep"] is not None else None}

    # Biberons
    lf = last_feed(db, now)
    feed = {"count": len(feeds), "ml": sum(f["ml"] or 0 for f in feeds), "last": None, "ask_id": None,
            "ref": milk_info(db, cfg, d)}
    if lf:
        t = parse(lf.start)
        ago = int((now - t).total_seconds() // 60)
        nxt = t + timedelta(minutes=E.FEED_INTERVAL)
        # Après le coucher, pas de biberon prévu : ils reprennent au lever (un réveil nocturne peut
        # en amener un, il se note alors comme d'habitude, sans être annoncé)
        after_bed = mode == "night" or (items[-1]["type"] == "bed" and nxt >= at(d, items[-1]["start"]))
        feed["last"] = {"id": lf.id, "time": t.strftime("%H:%M"), "ml": lf.ml, "ago": E.dur(ago),
                        "next": None if after_bed else nxt.strftime("%H:%M"),
                        "next_label": "prochain au lever" if after_bed else f"prochain vers {nxt:%H:%M}"}
        if lf.ml is None and 0 <= ago < 30:
            feed["ask_id"] = lf.id

    return {
        "now": hm, "now_iso": iso(now), "date": d.isoformat(), "date_label": date_label(now.date()), "mode": mode,
        "child": child_info(cfg, age_id, now.date()),
        "headline": headline, "actions": actions, "widget": widget,
        "dial": dial(items, day, feeds, nm, mode),
        "timeline": timeline(items, day, hi, nm),
        "totals": totals, "feed": feed,
        "feeds": [{"id": f["id"], "time": E.fmt(f["t"]), "ml": f["ml"]} for f in feeds],
    }


def child_info(cfg: dict, age_id: str, today: date) -> dict:
    birth = cfg["birth_date"]
    return {"name": cfg["child_name"], "age_id": age_id, "age_name": E.AGE_BY_ID[age_id]["name"],
            "age_manual": cfg["manual_age"] in E.AGE_BY_ID,
            "age_text": E.age_text(date.fromisoformat(birth), today) if birth else None}


def dial(items, day, feeds, nm, mode) -> dict:
    wake, bed = items[0]["start"], items[-1]["start"]
    bed_real = items[-1]["type"] == "bed" and items[-1]["real"]
    # Coucher prévu dépassé sans être noté : le cadran s'étire jusqu'à maintenant,
    # pour que le point « maintenant » et les derniers biberons restent visibles
    end = max(bed, nm + 10, *[f["t"] + 10 for f in feeds if f["t"] is not None]) if not bed_real and mode == "day" and nm >= 0 else bed
    return {
        "wake": wake, "bed": end, "now": nm, "night": mode == "night",
        "wake_real": items[0]["real"], "bed_real": bed_real,
        "wake_label": E.fmt(wake), "bed_label": E.fmt(bed),
        "naps": [{"idx": x["idx"], "start": x["start"], "end": x["end"], "start_real": x["start_real"], "end_real": x["end_real"],
                  "label": E.fmt(x["start"])} for x in items if x["type"] == "nap"],
        "feeds": [{"t": f["t"], "id": f["id"]} for f in feeds if f["t"] is not None],
    }


def timeline(items, day, hi, nm) -> list[dict]:
    out = []
    for x in items:
        if x["type"] == "gap":
            out.append({"type": "gap", "text": f"{E.dur(x['len'])} d'éveil" + (" · raccourci après une sieste courte" if x["cut"] else "")})
        elif x["type"] == "sun":
            out.append({"type": "wake", "id": x["id"], "time": E.fmt(x["start"]), "real": x["real"]})
        elif x["type"] == "nap":
            out.append({"type": "nap", "id": x["id"], "idx": x["idx"], "label": f"Sieste {x['idx'] + 1}",
                        "start": E.fmt(x["start"]), "end": E.fmt(x["end"]), "dur": E.dur(x["end"] - x["start"]),
                        "start_real": x["start_real"], "end_real": x["end_real"], "now": x is hi,
                        "past": not x["start_real"] and x["end"] <= nm})
        elif x["type"] == "bed":
            out.append({"type": "bed", "id": x["id"], "time": E.fmt(x["start"]), "real": x["real"], "late": x["late"],
                        "now": x is hi,
                        "night": [{"id": w.id, "start": E.fmt(w.start), "end": E.fmt(w.end) if w.end is not None else None,
                                   "dur": E.dur(real_dur(day.date, w.start, w.end)) if w.end is not None else None} for w in day.night]})
    return out


# ---------- historique ----------

def day_summary(db: Session, d: date, today: date, now_min: int | None = None) -> dict | None:
    """now_min : minute actuelle si d est la journée en cours (la sieste en cours s'arrête là sur la frise)."""
    day, feeds = build_day(db, d)
    if not (day.wake_real or day.naps or day.bed is not None or feeds):
        return None
    s = E.stats(day)
    wins = [w for w in s["wins"] if w is not None]
    nxt, _ = build_day(db, d + timedelta(days=1))
    night = None
    if day.bed is not None and nxt.wake_real:
        info = E.night_info(day, nxt.wake + 1440, lambda a, b: real_dur(d, a, b))
        night = {"sleep": E.dur(info["sleep"]), "count": info["count"], "min": info["sleep"]}
    ml = sum(f["ml"] or 0 for f in feeds)
    return {
        "date": d.isoformat(), "label": short_label(d, today),
        "wake": E.fmt(day.wake) if day.wake_real else None,
        "naps": s["count"], "day_sleep": E.dur(s["total"]), "day_sleep_min": s["total"],
        "mean_window": E.dur(sum(wins) / len(wins)) if wins else None,
        "bed": E.fmt(day.bed) if day.bed is not None else None, "night": night,
        "feeds": len(feeds), "ml": ml,
        # Frise de la journée, en minutes depuis minuit
        "strip": {"wake": day.wake if day.wake_real else None, "bed": day.bed, "now": now_min,
                  "naps": [[n.start, n.end if n.end is not None else now_min] for n in day.naps
                           if n.start is not None and (n.end is not None or now_min is not None)]},
    }


def day_view(db: Session, d: date, now: datetime) -> dict:
    """Une journée passée telle que l'écran Aujourd'hui la montre, sans les prévisions."""
    day, feeds, items = forecast(db, d, now.date())
    kept = []
    for x in items:
        if (x["type"] == "nap" and not x["start_real"]) or (x["type"] == "bed" and not x["real"]):
            break
        kept.append(x)
    while kept and kept[-1]["type"] == "gap":
        kept.pop()
    if kept[-1]["type"] != "bed":
        # Coucher non noté : le cadran s'arrête un peu après la dernière sieste
        last = max([x["end"] for x in kept if x["type"] == "nap"] or [day.wake + 600])
        kept.append({"type": "bed", "start": last + 90, "real": False, "id": None, "late": False})
    return {"date": d.isoformat(), "label": date_label(d), "summary": day_summary(db, d, now.date()),
            "dial": dial(kept, day, feeds, -1, "day"), "timeline": timeline(kept, day, None, -1),
            "feeds": [{"id": f["id"], "time": E.fmt(f["t"]), "ml": f["ml"]} for f in feeds]}


def day_detail(db: Session, d: date) -> dict:
    day, feeds = build_day(db, d)
    s = E.stats(day)
    return {
        "date": d.isoformat(), "label": date_label(d),
        "wake": {"id": day.wake_id, "time": E.fmt(day.wake), "real": day.wake_real},
        "naps": [{"id": n.id, "label": f"Sieste {i + 1}", "start": E.fmt(n.start),
                  "end": E.fmt(n.end) if n.end is not None else None,
                  "dur": E.dur(n.end - n.start) if n.end is not None else None} for i, n in enumerate(day.naps)],
        "bed": {"id": day.bed_id, "time": E.fmt(day.bed)} if day.bed is not None else None,
        "night": [{"id": w.id, "start": E.fmt(w.start), "end": E.fmt(w.end) if w.end is not None else None,
                   "dur": E.dur(real_dur(d, w.start, w.end)) if w.end is not None else None} for w in day.night],
        "feeds": [{"id": f["id"], "time": E.fmt(f["t"]), "ml": f["ml"]} for f in feeds],
        "day_sleep": E.dur(s["total"]),
    }
