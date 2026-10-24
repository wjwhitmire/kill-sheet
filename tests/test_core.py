"""Kill sheet tests. Hand-computed values are worked in the comments."""

import copy
import math

import pytest

from kill_sheet import EXAMPLE_CASE, InputError, classify_influx, compute, influx_fill, kmw_round_up, to_imperial


def case(**over):
    c = copy.deepcopy(EXAMPLE_CASE)
    c.update(over)
    return c


def codes(r):
    return {w["code"] for w in r["warnings"]}


# ---------------------------------------------------------------------------
# Textbook example, worked by hand.
#
# Vertical well, TD 10,000 ft MD = TVD. Shoe 6,000 ft. OMW 9.8 ppg. LOT EMW 14.5 ppg.
# SIDPP 400 psi, SICP 600 psi, pit gain 15 bbl. SCR 450 psi at 30 spm. Pump 0.102 bbl/stk.
#
# KMW   = 9.8 + 400 / (0.052 x 10,000) = 9.8 + 400 / 520 = 9.8 + 0.769231 = 10.569231 ppg
#         rounded up to next 0.1 ppg = 10.6 ppg
# ICP   = 450 + 400 = 850 psi
# FCP   = 450 x 10.6 / 9.8 = 486.7347 psi
#
# String:  DP   8,860 x 0.01776 = 157.3536 bbl
#          HWDP   540 x 0.00874 =   4.7196 bbl
#          DC     600 x 0.00768 =   4.6080 bbl
#          surface to bit       = 166.6812 bbl  / 0.102 = 1,634.13 stk  / 30 = 54.47 min
# Annulus: DC x OH    600 x 0.02914 =  17.484 bbl
#          DP x OH  3,400 x 0.0459  = 156.060 bbl
#          DP x csg 6,000 x 0.05154 = 309.240 bbl
#          bit to surface           = 482.784 bbl / 0.102 = 4,733.18 stk
#          bit to shoe (4,000 ft OH)= 173.544 bbl / 0.102 = 1,701.41 stk
# Total circulation = 166.6812 + 482.784 = 649.4652 bbl = 6,367.31 stk
#
# MAASP at OMW = (14.5 - 9.8) x 0.052 x 6,000 = 1,466.4 psi
# MAASP at KMW = (14.5 - 10.6) x 0.052 x 6,000 = 1,216.8 psi
#
# Influx: 15 bbl fits in DC x OH (17.484 bbl). Height = 15 / 0.02914 = 514.76 ft
#         gradient = 0.052 x 9.8 - (600 - 400) / 514.76 = 0.5096 - 0.38853 = 0.12107 psi/ft -> gas
#
# Barite: 1470 x (10.6 - 9.8) / (35 - 10.6) = 1176 / 24.4 = 48.197 lb/bbl
#         600 bbl active: 28,918 lb = 289.18 sacks -> 290 sacks; volume increase 600 x 0.8/24.4 = 19.672 bbl
# ---------------------------------------------------------------------------


def test_textbook_example():
    r = compute(case())
    assert r["kmw_exact"] == pytest.approx(10.569231, abs=1e-6)
    assert r["kmw_rounded"] == pytest.approx(10.6)
    assert r["kmw"] == pytest.approx(10.6)
    assert r["icp"] == pytest.approx(850)
    assert r["fcp"] == pytest.approx(486.7347, abs=1e-4)
    v, s, m = r["volumes"], r["strokes"], r["minutes"]
    assert v["surface_to_bit"] == pytest.approx(166.6812)
    assert s["surface_to_bit"] == pytest.approx(1634.1294, abs=1e-3)
    assert m["surface_to_bit"] == pytest.approx(54.471, abs=1e-3)
    assert v["bit_to_surface"] == pytest.approx(482.784)
    assert v["bit_to_shoe"] == pytest.approx(173.544)
    assert s["bit_to_shoe"] == pytest.approx(1701.412, abs=1e-3)
    assert v["total_circulation"] == pytest.approx(649.4652)
    assert s["total_circulation"] == pytest.approx(6367.306, abs=1e-3)
    assert r["maasp_omw"] == pytest.approx(1466.4)
    assert r["maasp_kmw"] == pytest.approx(1216.8)
    inf = r["influx"]
    assert inf["height"] == pytest.approx(514.756, abs=1e-3)
    assert inf["gradient"] == pytest.approx(0.12107, abs=1e-5)
    assert inf["type"] == "gas"
    b = r["barite"]
    assert b["lb_per_bbl"] == pytest.approx(48.1967, abs=1e-4)
    assert b["total_lb"] == pytest.approx(28918.03, abs=1e-2)
    assert b["sacks_rounded_up"] == 290
    assert b["volume_increase"] == pytest.approx(19.672, abs=1e-3)


def test_drillers_summary():
    r = compute(case())
    d = r["drillers"]
    assert d["first_hold_dp_pressure"] == pytest.approx(850)
    assert d["second_hold_casing_pressure"] == pytest.approx(400)  # casing equals SIDPP after first circulation
    assert d["second_hold_dp_pressure"] == pytest.approx(r["fcp"])
    assert d["second_phase1_strokes"] == pytest.approx(r["strokes"]["surface_to_bit"])
    assert d["first_strokes"] == pytest.approx(r["strokes"]["total_circulation"])


# --- KMW rounding ---------------------------------------------------------

def test_kmw_round_up_basic():
    assert kmw_round_up(10.5692, 0.1) == pytest.approx(10.6)
    assert kmw_round_up(10.01, 0.1) == pytest.approx(10.1)
    # Exact multiples stay put (no spurious step from float error).
    assert kmw_round_up(10.6, 0.1) == pytest.approx(10.6)
    assert kmw_round_up(10.3, 0.1) == pytest.approx(10.3)
    assert kmw_round_up(10.51, 0.5) == pytest.approx(11.0)


def test_kmw_exact_basis():
    r = compute(case(kmw_basis="exact"))
    assert r["kmw"] == pytest.approx(r["kmw_exact"])
    assert r["fcp"] == pytest.approx(450 * r["kmw_exact"] / 9.8)


def test_kmw_rounded_never_below_exact():
    for sidpp in (0, 1, 52, 100, 333, 520, 777, 1234):
        r = compute(case(sidpp=sidpp, sicp=sidpp + 100))
        assert r["kmw_rounded"] >= r["kmw_exact"] - 1e-12
        assert r["kmw_rounded"] - r["kmw_exact"] < 0.1 + 1e-9


def test_bad_kmw_basis():
    with pytest.raises(InputError):
        compute(case(kmw_basis="nearest"))


# --- Schedule --------------------------------------------------------------

@pytest.mark.parametrize("dev", [False, True])
def test_schedule_endpoints_and_monotonic(dev):
    r = compute(case(deviated=dev))
    sch = r["schedule"]
    assert len(sch) == 11
    assert sch[0]["pressure"] == pytest.approx(r["icp"])
    assert sch[-1]["pressure"] == pytest.approx(r["fcp"])
    assert sch[0]["strokes"] == pytest.approx(0)
    assert sch[-1]["strokes"] == pytest.approx(r["strokes"]["surface_to_bit"])
    for a, b in zip(sch, sch[1:]):
        assert b["strokes"] > a["strokes"]
        assert b["pressure"] <= a["pressure"] + 1e-9


def test_schedule_linear_steps_equal():
    r = compute(case())
    sch = r["schedule"]
    step = (r["icp"] - r["fcp"]) / 10
    for i, row in enumerate(sch):
        assert row["pressure"] == pytest.approx(r["icp"] - step * i)


def test_schedule_with_surface_lines_starts_after_lines():
    r = compute(case(surface_line_volume=5.1))
    # 5.1 bbl / 0.102 = 50 strokes held at ICP before the step-down begins.
    assert r["schedule"][0]["strokes"] == pytest.approx(50)
    assert r["schedule"][0]["pressure"] == pytest.approx(r["icp"])
    assert r["volumes"]["surface_to_bit"] == pytest.approx(166.6812 + 5.1)


def test_deviated_reduces_to_vertical_when_tvd_equals_md():
    # Vertical well: bottom TVD of each section equals its bottom MD.
    vert = compute(case(deviated=False))
    dev = compute(case(deviated=True))
    for a, b in zip(vert["section_points"], dev["section_points"]):
        assert a["pressure"] == pytest.approx(b["pressure"], abs=1e-9)
    for k in ("kmw", "icp", "fcp", "maasp_omw"):
        assert vert[k] == pytest.approx(dev[k])
    # Uniform string capacity: section points fall exactly on the straight line.
    uni = case(string=[{"name": "DP", "length": 6000, "capacity": 0.01776, "bottom_tvd": 6000},
                       {"name": "DP2", "length": 4000, "capacity": 0.01776, "bottom_tvd": 10000}])
    v2 = compute(dict(uni, deviated=False))
    d2 = compute(dict(uni, deviated=True))
    for a, b in zip(v2["schedule"], d2["schedule"]):
        assert a["pressure"] == pytest.approx(b["pressure"], abs=1e-9)
        assert a["strokes"] == pytest.approx(b["strokes"], abs=1e-9)


def test_deviated_hand_example():
    # J-type well: MD 12,000, TVD 9,000. Vertical to 2,000 ft, build to 5,000 MD (4,500 TVD),
    # tangent to 11,400 MD (8,600 TVD), then 600 ft of DC to TD.
    # Point at bottom of the build:
    #   P = ICP - SIDPP x (4,500/9,000) + (FCP - SCR) x (5,000/12,000)
    #   KMW exact = 9.8 + 400/(0.052 x 9,000) = 10.654701 ppg, FCP = 450 x 10.654701/9.8 = 489.2465 psi
    #   P = 850 - 200 + 39.2465 x 0.416667 = 666.353 psi
    # Straight line at the same strokes (88.8 of 207.072 bbl, fraction 0.428836):
    #   850 - (850 - 489.2465) x 0.428836 = 695.296 psi, about 29 psi above the section schedule.
    c = case(well_md=12000, well_tvd=9000, shoe_md=7000, shoe_tvd=6000, deviated=True, kmw_basis="exact",
             string=[{"name": "DP vertical", "length": 2000, "capacity": 0.01776, "bottom_tvd": 2000},
                     {"name": "DP build", "length": 3000, "capacity": 0.01776, "bottom_tvd": 4500},
                     {"name": "DP tangent", "length": 6400, "capacity": 0.01776, "bottom_tvd": 8600},
                     {"name": "DC", "length": 600, "capacity": 0.00768, "bottom_tvd": 9000}],
             annulus=[{"name": "DC x OH", "length": 600, "capacity": 0.02914},
                      {"name": "DP x OH", "length": 4400, "capacity": 0.0459},
                      {"name": "DP x csg", "length": 7000, "capacity": 0.05154}])
    r = compute(c)
    kmw = 9.8 + 400 / (0.052 * 9000)
    fcp = 450 * kmw / 9.8
    p_build = 850 - 400 * 4500 / 9000 + (fcp - 450) * 5000 / 12000
    assert p_build == pytest.approx(666.353, abs=1e-3)
    assert r["section_points"][2]["pressure"] == pytest.approx(p_build)
    assert r["section_points"][2]["linear_minus_section"] == pytest.approx(695.296 - 666.353, abs=2e-3)
    assert "linear_overbalance" in codes(r)
    assert "consider_deviated" not in codes(r)


def test_deviated_requires_tvd():
    c = case(deviated=True)
    del c["string"][0]["bottom_tvd"]
    with pytest.raises(InputError, match="bottom TVD"):
        compute(c)


def test_deviated_tvd_errors():
    c = case(deviated=True)
    c["string"][1]["bottom_tvd"] = 8000  # shallower than section above
    with pytest.raises(InputError, match="shallower"):
        compute(c)
    c = case(deviated=True)
    c["string"][2]["bottom_tvd"] = 9900  # last section must land on well TVD
    with pytest.raises(InputError, match="well TVD"):
        compute(c)


# --- Influx ------------------------------------------------------------------

def test_influx_spill_over():
    ann = EXAMPLE_CASE["annulus"]
    # 25 bbl: fills DC x OH (600 ft, 17.484 bbl), remaining 7.516 bbl in DP x OH: 7.516 / 0.0459 = 163.747 ft
    h, parts = influx_fill(25, ann)
    assert len(parts) == 2
    assert parts[0]["height"] == pytest.approx(600)
    assert parts[1]["height"] == pytest.approx(7.516 / 0.0459)
    assert h == pytest.approx(600 + 7.516 / 0.0459)


def test_influx_spill_two_sections():
    ann = EXAMPLE_CASE["annulus"]
    # 200 bbl: 17.484 + 156.06 = 173.544 in open hole, 26.456 bbl in casing: 26.456 / 0.05154 = 513.31 ft
    h, parts = influx_fill(200, ann)
    assert len(parts) == 3
    assert h == pytest.approx(4000 + 26.456 / 0.05154)
    r = compute(case(pit_gain=200, sicp=900))
    assert "influx_above_shoe" in codes(r)


def test_influx_larger_than_annulus():
    with pytest.raises(InputError, match="annular volume"):
        compute(case(pit_gain=600))


def test_influx_classification():
    assert classify_influx(0.1) == "gas"
    assert classify_influx(0.2499) == "gas"
    assert classify_influx(0.25) == "oil, condensate or mixed"
    assert classify_influx(0.4) == "oil, condensate or mixed"
    assert classify_influx(0.41) == "water"
    # SICP - SIDPP small -> heavy influx. 15 bbl, height 514.76 ft, 0.5096 - 20/514.76 = 0.4707 -> water
    r = compute(case(sicp=420))
    assert r["influx"]["type"] == "water"


def test_zero_pit_gain():
    r = compute(case(pit_gain=0))
    assert r["influx"] is None
    assert "no_pit_gain" in codes(r)


# --- Barite --------------------------------------------------------------------

def test_barite_formula():
    # 12.0 -> 14.0 ppg: 1470 x 2 / 21 = 140 lb/bbl exactly.
    r = compute(case(omw=12.0, sidpp=1040, sicp=1200, lot_emw=17, kmw_basis="exact", active_volume=1000))
    assert r["kmw"] == pytest.approx(14.0)
    b = r["barite"]
    assert b["lb_per_bbl"] == pytest.approx(140.0)
    assert b["total_lb"] == pytest.approx(140000.0)
    assert b["sacks"] == pytest.approx(1400.0)
    assert b["sacks_rounded_up"] == 1400
    assert b["volume_increase"] == pytest.approx(1000 * 2 / 21)
    # Mass balance check: (V x 12 + Vb x 35) / (V + Vb) = 14.
    vb = b["volume_increase"]
    assert (1000 * 12 + vb * 35) / (1000 + vb) == pytest.approx(14.0)


def test_barite_without_active_volume():
    c = case()
    del c["active_volume"]
    r = compute(c)
    assert r["barite"]["lb_per_bbl"] > 0
    assert r["barite"]["sacks"] is None


# --- LOT input -----------------------------------------------------------------

def test_lot_from_surface_pressure():
    # Leak-off 1,400 psi with 9.5 ppg test mud at 6,000 ft TVD: EMW = 9.5 + 1400/312 = 13.98718 ppg
    c = case(lot_emw=None, lot_pressure=1400, lot_test_mw=9.5)
    r = compute(c)
    assert r["lot_emw"] == pytest.approx(9.5 + 1400 / 312)
    assert r["lot_source"] == "pressure"
    assert r["maasp_omw"] == pytest.approx((r["lot_emw"] - 9.8) * 312)


def test_lot_missing():
    with pytest.raises(InputError, match="LOT"):
        compute(case(lot_emw=None))


def test_lot_below_mw():
    with pytest.raises(InputError, match="LOT"):
        compute(case(lot_emw=9.5))


def test_kmw_over_lot_warns():
    r = compute(case(lot_emw=10.5))
    assert "kmw_over_lot" in codes(r)
    assert r["maasp_kmw"] < 0


# --- Validation ----------------------------------------------------------------

def test_sicp_less_than_sidpp_warns():
    r = compute(case(sicp=300))
    assert "sicp_lt_sidpp" in codes(r)


def test_shoe_deeper_than_td_errors():
    with pytest.raises(InputError, match="Shoe MD is deeper"):
        compute(case(shoe_md=10500, shoe_tvd=9000))
    with pytest.raises(InputError, match="Shoe TVD is deeper"):
        compute(case(well_tvd=9000, shoe_md=9500, shoe_tvd=9200))


def test_zero_pump_output_errors():
    with pytest.raises(InputError, match="Pump output"):
        compute(case(pump_output=0))


@pytest.mark.parametrize("key", ["sidpp", "sicp", "pit_gain", "surface_line_volume"])
def test_negative_pressures_and_volumes_error(key):
    with pytest.raises(InputError, match="negative"):
        compute(case(**{key: -1}))


@pytest.mark.parametrize("key,val", [
    ("scr_pressure", 0), ("scr_pressure", -10), ("kill_rate_spm", 0), ("well_tvd", 0), ("well_md", -5),
    ("omw", 0), ("omw", 30), ("pump_output", -0.1), ("active_volume", -1),
])
def test_impossible_values_error(key, val):
    with pytest.raises(InputError):
        compute(case(**{key: val}))


@pytest.mark.parametrize("val", [None, "", "abc", float("nan"), float("inf"), True])
def test_non_numbers_error(val):
    with pytest.raises(InputError):
        compute(case(sidpp=val))


def test_tvd_greater_than_md_errors():
    with pytest.raises(InputError, match="TVD cannot be greater"):
        compute(case(well_tvd=10100))


def test_section_lengths_must_close():
    c = case()
    c["string"][0]["length"] = 8800
    with pytest.raises(InputError, match="Drill string section lengths"):
        compute(c)
    c = case()
    c["annulus"][2]["length"] = 5000
    with pytest.raises(InputError, match="Annular section lengths"):
        compute(c)


def test_section_bad_values():
    c = case()
    c["annulus"][0]["capacity"] = 0
    with pytest.raises(InputError, match="capacity"):
        compute(c)
    c = case(string=[])
    with pytest.raises(InputError, match="at least one"):
        compute(c)


def test_zero_sidpp_warns():
    r = compute(case(sidpp=0, sicp=100))
    assert r["kmw_exact"] == pytest.approx(9.8)
    assert "sidpp_zero" in codes(r)


def test_sicp_near_maasp():
    r = compute(case(sicp=1500))
    assert "sicp_over_maasp" in codes(r)


# --- Metric ----------------------------------------------------------------

def test_metric_matches_imperial():
    from kill_sheet.core import BBL_M3, BBLFT_M3M, FT_M, PPG_KGM3, PSI_KPA
    c = case()
    m = {"units": "metric"}
    for k in ("well_md", "well_tvd", "shoe_md", "shoe_tvd"):
        m[k] = c[k] * FT_M
    for k in ("omw", "lot_emw"):
        m[k] = c[k] * PPG_KGM3
    for k in ("sidpp", "sicp", "scr_pressure"):
        m[k] = c[k] * PSI_KPA
    for k in ("pit_gain", "surface_line_volume", "active_volume", "pump_output"):
        m[k] = c[k] * BBL_M3
    m["kill_rate_spm"] = c["kill_rate_spm"]
    m["string"] = [{"name": s["name"], "length": s["length"] * FT_M, "capacity": s["capacity"] * BBLFT_M3M,
                    "bottom_tvd": s["bottom_tvd"] * FT_M} for s in c["string"]]
    m["annulus"] = [{"name": s["name"], "length": s["length"] * FT_M, "capacity": s["capacity"] * BBLFT_M3M}
                    for s in c["annulus"]]
    m["kmw_basis"] = "exact"
    ri = compute(dict(c, kmw_basis="exact"))
    rm = compute(m)
    for k in ("kmw", "icp", "fcp", "maasp_omw"):
        assert rm[k] == pytest.approx(ri[k], rel=1e-9)
    assert rm["strokes"]["total_circulation"] == pytest.approx(ri["strokes"]["total_circulation"], rel=1e-9)
    # Metric rounding default is 10 kg/m3.
    rr = compute(dict(m, kmw_basis="rounded"))
    assert rr["kmw_rounded"] * PPG_KGM3 == pytest.approx(math.ceil(ri["kmw_exact"] * PPG_KGM3 / 10) * 10)


def test_to_imperial_rejects_bad_units():
    with pytest.raises(InputError):
        to_imperial(case(units="si"))
