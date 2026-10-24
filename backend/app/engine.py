"""Calcul des prévisions, sans base de données : tout est en minutes depuis minuit du jour étudié
(une heure après minuit vaut donc plus de 1440). Reprise fidèle de l'oracle d'origine."""
from dataclasses import dataclass, field
from datetime import date, datetime

AGES = [
    {"id": "0-6s", "name": "0-6 sem.", "f": 45, "l": 60, "wl": 60, "naps": [60, 60, 60, 60, 45, 30], "bed_min": 19 * 60, "bed_max": 21 * 60},
    {"id": "6-10s", "name": "1,5-2,5 m", "f": 60, "l": 75, "wl": 80, "naps": [60, 75, 60, 45, 30], "bed_min": 18 * 60 + 30, "bed_max": 20 * 60},
    {"id": "2.5-3", "name": "2,5-3 m", "f": 70, "l": 85, "wl": 90, "naps": [50, 90, 60, 40, 30], "bed_min": 18 * 60 + 30, "bed_max": 19 * 60 + 30},
    {"id": "3-4", "name": "3-4 m", "f": 75, "l": 100, "wl": 105, "naps": [60, 90, 60, 30], "bed_min": 18 * 60 + 30, "bed_max": 19 * 60 + 30},
    {"id": "4-6", "name": "4-6 m", "f": 90, "l": 120, "wl": 135, "naps": [60, 90, 40], "bed_min": 18 * 60 + 30, "bed_max": 19 * 60 + 30},
    {"id": "6-9", "name": "6-9 m", "f": 120, "l": 150, "wl": 180, "naps": [75, 90, 30], "bed_min": 18 * 60 + 30, "bed_max": 19 * 60 + 30},
    {"id": "9-12", "name": "9-12 m", "f": 150, "l": 180, "wl": 225, "naps": [60, 90], "bed_min": 18 * 60 + 30, "bed_max": 19 * 60 + 30},
]
AGE_BY_ID = {a["id"]: a for a in AGES}
DEFAULT_WAKE = 7 * 60
SHORT_NAP = 45      # en dessous, l'éveil suivant est raccourci
CUT = 12            # de combien
FEED_INTERVAL = 210  # écart habituel entre deux biberons


def fmt(m: float) -> str:
    m = round(m)
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def dur(m: float) -> str:
    m = max(0, round(m))
    h, r = divmod(m, 60)
    if not h:
        return f"{r} min"
    return f"{h} h {r:02d}" if r else f"{h} h"


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def auto_age(birth: date, today: date) -> str:
    return band((today - birth).days)


def band(d: int) -> str:
    if d < 42: return "0-6s"
    if d < 76: return "6-10s"
    if d < 91: return "2.5-3"
    if d < 122: return "3-4"
    if d < 183: return "4-6"
    if d < 274: return "6-9"
    return "9-12"


# Âge en jours au milieu de chaque tranche. Entre deux milieux, les temps d'éveil et les heures
# de coucher glissent jour après jour au lieu de sauter le jour où l'on change de tranche.
MIDS = {"0-6s": 21, "6-10s": 59, "2.5-3": 83, "3-4": 106, "4-6": 152, "6-9": 228, "9-12": 320}
SMOOTH = ("f", "l", "wl", "bed_min", "bed_max")


def smooth_age(days: int) -> dict:
    """Repères pour un âge exact : ceux de la tranche, avec les valeurs de SMOOTH interpolées."""
    age = dict(AGE_BY_ID[band(days)])
    for a0, a1 in zip(AGES, AGES[1:]):
        m0, m1 = MIDS[a0["id"]], MIDS[a1["id"]]
        if m0 <= days < m1:
            x = (days - m0) / (m1 - m0)
            for k in SMOOTH:
                age[k] = round(a0[k] + (a1[k] - a0[k]) * x)
            break
    return age


def age_text(birth: date, today: date) -> str:
    months = (today.year - birth.year) * 12 + today.month - birth.month
    if today.day < birth.day:
        months -= 1
    y, mo = divmod(birth.month - 1 + months, 12)
    try:
        ref = date(birth.year + y, mo + 1, birth.day)
    except ValueError:      # né un 31 : le mois suivant n'a pas de 31
        ref = date(birth.year + y, mo + 2, 1) if mo < 11 else date(birth.year + y + 1, 1, 1)
    days = (today - ref).days
    weeks = (today - birth).days // 7
    return f"{months} mois" + (f" {days} j" if days else "") + f" · {weeks} semaines"


def default_window(age: dict, i: int) -> float:
    return age["f"] if i == 0 else min(age["l"], age["f"] + (age["l"] - age["f"]) * i / 3)


@dataclass
class Span:
    start: int | None
    end: int | None = None
    id: int | None = None


@dataclass
class Day:
    date: date
    wake: int = DEFAULT_WAKE
    wake_real: bool = False
    wake_id: int | None = None
    naps: list[Span] = field(default_factory=list)
    bed: int | None = None
    bed_id: int | None = None
    night: list[Span] = field(default_factory=list)


def plan(day: Day, age: dict, hab: dict | None = None) -> list[dict]:
    """La journée prévue : lever, éveils, siestes (réelles puis prévues), coucher.
    hab : ses habitudes (voir habits), mêlées aux repères de l'âge."""
    hab = hab or {}
    items = [{"type": "sun", "start": day.wake, "real": day.wake_real, "id": day.wake_id}]
    t, short = day.wake, False
    for i in range(max(8, len(day.naps))):
        cut = CUT if short else 0
        w = window(age, hab, i) - cut
        o = day.naps[i] if i < len(day.naps) else None
        if o is None:
            if day.bed is not None:
                break
            if t + age["wl"] - cut >= age["bed_min"]:
                break
        start = o.start if o is not None else t + w
        if o is None and start + 20 + age["wl"] > age["bed_max"]:
            break
        d = nap_length(age, hab, i)
        if (o is None or o.end is None) and start + d + age["wl"] > age["bed_max"]:
            d = max(20, age["bed_max"] - age["wl"] - start)
        end = o.end if o is not None and o.end is not None else start + d
        items.append({"type": "gap", "len": start - t, "cut": bool(cut) and o is None})
        items.append({"type": "nap", "idx": i, "start": start, "end": end,
                      "start_real": o is not None, "end_real": o is not None and o.end is not None,
                      "id": o.id if o else None})
        short = o is not None and o.end is not None and (end - start) < SHORT_NAP
        t = end
    wl = age["wl"] - (CUT if short else 0)
    bed = t + wl
    if bed < age["bed_min"]:
        bed = min(age["bed_min"], t + wl * 1.25)
    if day.bed is not None:
        bed = day.bed
    items.append({"type": "gap", "len": bed - t, "cut": day.bed is None and short and bed == t + wl})
    items.append({"type": "bed", "start": bed, "real": day.bed is not None, "id": day.bed_id,
                  "late": day.bed is None and bed > age["bed_max"] + 15})
    return items


def stats(day: Day) -> dict:
    """Éveils réels avant chaque sieste (20 min à 5 h, sinon ignorés), sommeil de jour terminé."""
    prev = day.wake if day.wake_real else None
    wins, total, count = [], 0, 0
    for n in day.naps:
        w = n.start - prev if prev is not None and n.start is not None else None
        wins.append(w if w is not None and 20 <= w <= 300 else None)
        if n.start is not None and n.end is not None and n.end > n.start:
            total += n.end - n.start
            count += 1
        prev = n.end
    return {"wins": wins, "total": total, "count": count}


# Apprentissage de ses habitudes, prudent : une médiane (une journée bizarre ne pèse rien),
# les jours récents comptent davantage, et tant qu'il y a peu de journées on reste près des repères.
LEARN_DAYS = 14
DECAY = 0.85        # poids d'une journée : x0,85 par jour d'ancienneté
PRIOR = 2           # les repères valent 2 journées : 1 journée réelle pèse 1/3, 4 en pèsent 2/3
NAP_MIN, NAP_MAX = 10, 240   # durées retenues pour apprendre (hors oublis et erreurs de saisie)


def _wmedian(vals: list[tuple[float, float]]) -> float:
    vals = sorted(vals)
    half, acc = sum(w for _, w in vals) / 2, 0.0
    for v, w in vals:
        acc += w
        if acc >= half:
            return v
    return vals[-1][0]


def habits(days: list[Day]) -> dict:
    """Par rang de sieste : (médiane pondérée, nombre de journées) de l'éveil qui précède et de la durée.
    days[0] est la journée la plus récente."""
    acc: dict[str, list[list]] = {"wins": [], "naps": []}

    def add(key, i, v, w):
        while len(acc[key]) <= i:
            acc[key].append([])
        acc[key][i].append((v, w))

    for k, d in enumerate(days):
        w = DECAY ** k
        for i, v in enumerate(stats(d)["wins"]):
            if v is not None:
                add("wins", i, v, w)
        for i, n in enumerate(d.naps):
            if n.start is not None and n.end is not None and NAP_MIN <= n.end - n.start <= NAP_MAX:
                add("naps", i, n.end - n.start, w)
    return {key: [(round(_wmedian(v)), len(v)) if v else None for v in rows] for key, rows in acc.items()}


def _blend(ref: float, h) -> float:
    if not h:
        return ref
    med, n = h
    v = ref + (med - ref) * n / (n + PRIOR)
    return max(ref * 0.7, min(ref * 1.4, v))


def _hab(hab: dict, key: str, i: int):
    rows = hab.get(key) or []
    return rows[i] if i < len(rows) else None


def window(age: dict, hab: dict, i: int) -> float:
    """Éveil prévu avant la sieste i (rang 0 = première)."""
    return _blend(default_window(age, i), _hab(hab, "wins", i))


def nap_length(age: dict, hab: dict, i: int) -> float:
    return _blend(age["naps"][min(i, len(age["naps"]) - 1)], _hab(hab, "naps", i))


def night_info(day: Day, end: int | None, dur=None) -> dict | None:
    """Nuit commencée au coucher de ce jour. end : minute du lever (ou de maintenant), None si inconnue.
    dur(a, b) : minutes écoulées entre deux minutes du jour (le service y fait entrer le changement d'heure)."""
    if day.bed is None:
        return None
    dur = dur or (lambda a, b: b - a)
    awake, open_at = 0, None
    for w in day.night:
        if w.start is None:
            continue
        if w.end is not None:
            awake += max(0, dur(w.start, w.end))
        else:
            open_at = w.start
    sleep = None
    if end is not None:
        sleep = max(0, dur(day.bed, end) - awake - (dur(open_at, end) if open_at is not None else 0))
    return {"bed": day.bed, "awake": awake, "open": open_at, "count": len(day.night), "sleep": sleep}


def minutes(dt: datetime, d: date) -> int:
    return int((dt - datetime(d.year, d.month, d.day)).total_seconds() // 60)
