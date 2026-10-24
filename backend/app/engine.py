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
# Repère de lait sur une journée, jusqu'à 6 mois : autour de 150 ml par kilo (130 à 170 ici),
# sans dépasser environ un litre. Un ordre de grandeur, jamais une quantité à atteindre.
MILK_PER_KG = (130, 170)
MILK_MAX = 1000
MILK_UNTIL_DAYS = 183


def milk_ref(grams: int, age_days: int) -> dict | None:
    if age_days >= MILK_UNTIL_DAYS:
        return None
    r50 = lambda v: int(round(v / 50) * 50)
    lo, hi = (r50(min(MILK_MAX, k * grams / 1000)) for k in MILK_PER_KG)
    return {"lo": lo, "hi": hi}


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


def evening(age: dict, hab: dict) -> dict:
    """Repères du soir mêlés à ses habitudes : dernier éveil avant le coucher, et plage de coucher
    recentrée sur l'heure où elle est couchée d'habitude (au plus une heure plus tôt ou plus tard)."""
    wl = _blend(age["wl"], hab.get("last"))
    half = (age["bed_max"] - age["bed_min"]) / 2
    center = age["bed_min"] + half
    h = hab.get("bedtime")
    if h:
        med, n = h
        center += max(-60, min(60, (med - center) * n / (n + PRIOR)))
    return {"wl": wl, "bed_min": center - half, "bed_max": center + half}


def plan(day: Day, age: dict, hab: dict | None = None) -> list[dict]:
    """La journée prévue : lever, éveils, siestes (réelles puis prévues), coucher.
    hab : ses habitudes (voir habits), mêlées aux repères de l'âge."""
    hab = hab or {}
    age = age | evening(age, hab)
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

    last, beds = [], []
    for k, d in enumerate(days):
        w = DECAY ** k
        # Le soir : éveil entre la fin de la dernière sieste et le coucher, et l'heure du coucher
        if d.bed is not None and 16 * 60 <= d.bed <= 23 * 60:
            beds.append((d.bed, w))
            ends = [n.end for n in d.naps if n.end is not None and n.end < d.bed]
            if ends and 30 <= d.bed - max(ends) <= 300:
                last.append((d.bed - max(ends), w))
        for i, v in enumerate(stats(d)["wins"]):
            if v is not None:
                add("wins", i, v, w)
        for i, n in enumerate(d.naps):
            if n.start is not None and n.end is not None and NAP_MIN <= n.end - n.start <= NAP_MAX:
                add("naps", i, n.end - n.start, w)
    out = {key: [(round(_wmedian(v)), len(v)) if v else None for v in rows] for key, rows in acc.items()}
    out["last"] = (round(_wmedian(last)), len(last)) if last else None
    out["bedtime"] = (round(_wmedian(beds)), len(beds)) if beds else None
    return out


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


# Courbes de poids de l'OMS (Child Growth Standards 2006), coefficients L, M, S de la naissance à 24 mois,
# un mois par ligne, tirés des tables officielles « Weight-for-age, birth to 5 years ».
WHO_WFA = {
    "f": [[0.3809, 3.2322, 0.14171], [0.1714, 4.1873, 0.13724], [0.0962, 5.1282, 0.13000], [0.0402, 5.8458, 0.12619], [-0.0050, 6.4237, 0.12402], [-0.0430, 6.8985, 0.12274], [-0.0756, 7.2970, 0.12204], [-0.1039, 7.6422, 0.12178], [-0.1288, 7.9487, 0.12181], [-0.1507, 8.2254, 0.12199], [-0.1700, 8.4800, 0.12223], [-0.1872, 8.7192, 0.12247], [-0.2024, 8.9481, 0.12268], [-0.2158, 9.1699, 0.12283], [-0.2278, 9.3870, 0.12294], [-0.2384, 9.6008, 0.12299], [-0.2478, 9.8124, 0.12303], [-0.2562, 10.0226, 0.12306], [-0.2637, 10.2315, 0.12309], [-0.2703, 10.4393, 0.12315], [-0.2762, 10.6464, 0.12323], [-0.2815, 10.8534, 0.12335], [-0.2862, 11.0608, 0.12350], [-0.2903, 11.2688, 0.12369], [-0.2941, 11.4775, 0.12390]],
    "m": [[0.3487, 3.3464, 0.14602], [0.2297, 4.4709, 0.13395], [0.1970, 5.5675, 0.12385], [0.1738, 6.3762, 0.11727], [0.1553, 7.0023, 0.11316], [0.1395, 7.5105, 0.11080], [0.1257, 7.9340, 0.10958], [0.1134, 8.2970, 0.10902], [0.1021, 8.6151, 0.10882], [0.0917, 8.9014, 0.10881], [0.0820, 9.1649, 0.10891], [0.0730, 9.4122, 0.10906], [0.0644, 9.6479, 0.10925], [0.0563, 9.8749, 0.10949], [0.0487, 10.0953, 0.10976], [0.0413, 10.3108, 0.11007], [0.0343, 10.5228, 0.11041], [0.0275, 10.7319, 0.11079], [0.0211, 10.9385, 0.11119], [0.0148, 11.1430, 0.11164], [0.0087, 11.3462, 0.11211], [0.0029, 11.5486, 0.11261], [-0.0028, 11.7504, 0.11314], [-0.0083, 11.9514, 0.11369], [-0.0137, 12.1515, 0.11426]],
}
DAYS_PER_MONTH = 30.4375
PERCENTILES = {"p3": -1.881, "p15": -1.036, "p50": 0.0, "p85": 1.036, "p97": 1.881}


def who_weight(sex: str, days: float, z: float) -> float:
    """Poids (kg) au z-score z pour cet âge, coefficients interpolés entre deux mois."""
    rows = WHO_WFA[sex]
    m = max(0.0, min(len(rows) - 1.0, days / DAYS_PER_MONTH))
    i = min(int(m), len(rows) - 2)
    f = m - i
    L, M, S = (rows[i][k] + (rows[i + 1][k] - rows[i][k]) * f for k in range(3))
    return M * (1 + L * S * z) ** (1 / L) if abs(L) > 1e-9 else M * 2.718281828 ** (S * z)


def who_curves(sex: str, until_days: int, step: int = 7) -> dict:
    days = list(range(0, until_days + 1, step))
    if days[-1] != until_days:
        days.append(until_days)
    return {"days": days} | {k: [round(who_weight(sex, d, z), 3) for d in days] for k, z in PERCENTILES.items()}
