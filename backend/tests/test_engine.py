from datetime import date

from app import engine as E

AGE = E.AGE_BY_ID["3-4"]


def naps(items):
    return [x for x in items if x["type"] == "nap"]


def test_plan_sans_saisie_suit_les_reperes():
    items = E.plan(E.Day(date=date(2026, 10, 24)), AGE)
    assert items[0]["start"] == 7 * 60
    assert naps(items)[0]["start"] == 7 * 60 + AGE["f"]
    bed = items[-1]
    assert bed["type"] == "bed" and AGE["bed_min"] <= bed["start"] <= AGE["bed_max"]


def test_sieste_courte_raccourcit_l_eveil_suivant():
    day = E.Day(date=date(2026, 10, 24), wake=420, wake_real=True, naps=[E.Span(495, 525)])  # 30 min
    second = naps(E.plan(day, AGE))[1]
    assert second["start"] == 525 + E.default_window(AGE, 1) - E.CUT


def test_coucher_reel_remplace_la_prevision():
    day = E.Day(date=date(2026, 10, 24), wake=420, wake_real=True, naps=[E.Span(495, 560)], bed=19 * 60 + 5)
    items = E.plan(day, AGE)
    assert items[-1]["start"] == 19 * 60 + 5 and items[-1]["real"]
    assert len(naps(items)) == 1   # plus de sieste prévue après un coucher


def test_habitudes_prudentes():
    d1 = E.Day(date=date(2026, 10, 23), wake=420, wake_real=True, naps=[E.Span(520, 580)])
    d2 = E.Day(date=date(2026, 10, 22), wake=420, wake_real=True, naps=[E.Span(520, 570), E.Span(700, 949)])  # 4 h 09 : écartée
    hab = E.habits([d1, d2])
    assert hab["wins"][0] == (100, 2) and hab["naps"] == [(60, 2)]
    # 2 journées valent autant que les repères : à mi-chemin entre 1 h 15 et 1 h 40
    assert E.window(AGE, hab, 0) == 87.5
    assert E.nap_length(AGE, hab, 0) == 60
    # sans journée, les repères tels quels ; une valeur extrême est bornée
    assert E.window(AGE, {}, 0) == AGE["f"]
    assert E.window(AGE, {"wins": [(300, 50)]}, 0) == AGE["f"] * 1.4


def test_nuit_retire_les_reveils():
    day = E.Day(date=date(2026, 10, 24), bed=19 * 60 + 30, night=[E.Span(23 * 60, 23 * 60 + 30)])
    info = E.night_info(day, 1440 + 7 * 60)
    assert info["sleep"] == (1440 + 420 - 1170) - 30 and info["count"] == 1


def test_age():
    birth = date(2026, 7, 19)
    assert E.auto_age(birth, date(2026, 10, 24)) == "3-4"
    assert E.age_text(birth, date(2026, 10, 24)) == "3 mois 5 j · 13 semaines"
    assert E.dur(65) == "1 h 05" and E.dur(60) == "1 h" and E.dur(12) == "12 min"


def test_reperes_progressifs_selon_l_age():
    assert E.smooth_age(106)["f"] == 75 and E.smooth_age(152)["f"] == 90
    assert E.smooth_age(115)["f"] == 78 and E.smooth_age(115)["id"] == "3-4"
    # plus de saut le jour où l'on change de tranche
    for d in range(0, 400):
        a, b = E.smooth_age(d), E.smooth_age(d + 1)
        assert all(abs(a[k] - b[k]) <= 2 for k in E.SMOOTH), d


def test_le_soir_s_adapte_a_ses_habitudes():
    # 4 soirs : dernière sieste finie à 17:00, couchée à 19:15, soit 2 h 15 d'éveil
    days = [E.Day(date=date(2026, 10, 20 + k), wake=420, wake_real=True, naps=[E.Span(900, 1020)], bed=19 * 60 + 15)
            for k in range(4)]
    hab = E.habits(days)
    assert hab["last"] == (135, 4) and hab["bedtime"] == (19 * 60 + 15, 4)
    ev = E.evening(AGE, hab)
    # 4 journées pèsent deux tiers : 1 h 45 de repère, 2 h 15 chez elle, environ 2 h 05 retenus
    assert round(ev["wl"]) == 125
    assert ev["bed_min"] > AGE["bed_min"] and ev["bed_max"] - ev["bed_min"] == AGE["bed_max"] - AGE["bed_min"]
    # sans habitudes, les repères de l'âge
    assert E.evening(AGE, {}) == {"wl": AGE["wl"], "bed_min": AGE["bed_min"], "bed_max": AGE["bed_max"]}
