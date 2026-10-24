"""Surface-stack kill sheet calculations.

Clean-room implementation of the standard public well-control formulas used on
IADC and IWCF style surface BOP kill sheets. All arithmetic is done in oilfield
units (ft, ppg, psi, bbl, bbl/ft, bbl/stk). Metric input (m, kg/m3, kPa, m3,
m3/m, m3/stk) is converted to oilfield units first.

This is a training and cross-check aid. The rig's approved kill sheet and the
well-site supervisor govern. Every input must be verified.

The JavaScript core in web/app.html mirrors this module line for line and is
checked against tests/vectors.json by web/parity.test.mjs.
"""

from __future__ import annotations

import math
import re

# Hydrostatic constant, psi per ft per ppg. The exact value is 0.051948
# (12 in/ft / 231 in3/gal); 0.052 is the industry kill sheet convention.
G = 0.052
# Barite density used for weight-up: SG 4.2 x 8.33 ppg = 35.0 ppg. 1470 = 35 x 42 gal/bbl.
BARITE_PPG = 35.0
BARITE_LB_PER_BBL = 1470.0
SACK_LB = 100.0

# Metric conversion factors (exact or to the precision of the defining units).
FT_M = 0.3048
PPG_KGM3 = 119.82642731689663
PSI_KPA = 6.894757293168361
BBL_M3 = 0.158987294928
BBLFT_M3M = BBL_M3 / FT_M

# Length sums must close on the well MD within this many feet.
LENGTH_TOL_FT = 1.0
# Plain decimal numbers only (same rule as the JavaScript core): no "1_000", no non-ASCII digits.
_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$", re.ASCII)
_NONFINITE_RE = re.compile(r"^[+-]?(nan|inf|infinity)$", re.I)
MW_MIN_PPG = 5.0
MW_MAX_PPG = 25.0
SCHEDULE_STEPS = 10

WELL_KEYS = (
    "well_md", "well_tvd", "shoe_md", "shoe_tvd", "omw", "sidpp", "sicp",
    "pit_gain", "scr_pressure", "kill_rate_spm", "pump_output",
)


class InputError(ValueError):
    """Raised when an input is missing, impossible, or inconsistent."""


EXAMPLE_CASE = {
    "label": "Example data: vertical land well, 8-1/2 in hole, 9-5/8 in shoe (illustrative values)",
    "units": "imperial",
    "well_md": 10000,
    "well_tvd": 10000,
    "shoe_md": 6000,
    "shoe_tvd": 6000,
    "omw": 9.8,
    "lot_emw": 14.5,
    "sidpp": 400,
    "sicp": 600,
    "pit_gain": 15,
    "scr_pressure": 450,
    "kill_rate_spm": 30,
    "pump_output": 0.102,
    "surface_line_volume": 0,
    "active_volume": 600,
    "deviated": False,
    "kmw_basis": "rounded",
    "string": [
        {"name": "5 in DP 19.5 lb/ft", "length": 8860, "capacity": 0.01776, "bottom_tvd": 8860},
        {"name": "5 in HWDP", "length": 540, "capacity": 0.00874, "bottom_tvd": 9400},
        {"name": "6-1/2 in DC", "length": 600, "capacity": 0.00768, "bottom_tvd": 10000},
    ],
    "annulus": [
        {"name": "DC x open hole", "length": 600, "capacity": 0.02914},
        {"name": "DP/HWDP x open hole", "length": 3400, "capacity": 0.0459},
        {"name": "DP x casing", "length": 6000, "capacity": 0.05154},
    ],
}

LABELS = {
    "well_md": "Well MD", "well_tvd": "Well TVD", "shoe_md": "Shoe MD", "shoe_tvd": "Shoe TVD",
    "omw": "Original mud weight", "lot_emw": "LOT/FIT EMW", "lot_pressure": "LOT/FIT surface pressure",
    "lot_test_mw": "LOT/FIT test mud weight", "sidpp": "SIDPP", "sicp": "SICP", "pit_gain": "Pit gain",
    "scr_pressure": "Slow circulating rate pressure", "kill_rate_spm": "Kill rate",
    "pump_output": "Pump output", "surface_line_volume": "Surface line volume",
    "active_volume": "Active system volume", "kmw_round_increment": "KMW rounding increment",
}


def _num(value, label):
    if isinstance(value, bool) or value is None:
        raise InputError(f"{label} is missing or not a number.")
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            raise InputError(f"{label} is missing.")
        if _NUM_RE.match(s):
            value = float(s)
        elif _NONFINITE_RE.match(s):
            value = float("nan")
        else:
            raise InputError(f"{label} is not a number: '{s}'.")
    if not isinstance(value, (int, float)):
        raise InputError(f"{label} is not a number.")
    v = float(value)
    if not math.isfinite(v):
        raise InputError(f"{label} must be a finite number.")
    return v


def _get(case, key, *, required=True, default=None):
    if key not in case or case[key] is None or (isinstance(case[key], str) and case[key].strip() == ""):
        if required:
            raise InputError(f"{LABELS.get(key, key)} is required.")
        return default
    return _num(case[key], LABELS.get(key, key))


def to_imperial(case):
    """Return a copy of the case in oilfield units. Imperial input is copied as-is."""
    if not isinstance(case, dict):
        raise InputError("Input must be an object of named fields.")
    units = case.get("units", "imperial")
    if units not in ("imperial", "metric"):
        raise InputError("units must be 'imperial' or 'metric'.")
    out = dict(case)
    out["string"] = [dict(s) for s in case.get("string") or []] if isinstance(case.get("string"), list) else case.get("string")
    out["annulus"] = [dict(s) for s in case.get("annulus") or []] if isinstance(case.get("annulus"), list) else case.get("annulus")
    out["units"] = "imperial"
    if units == "imperial":
        return out

    def conv(key, factor):
        if key in case and case[key] is not None and not (isinstance(case[key], str) and case[key].strip() == ""):
            out[key] = _num(case[key], LABELS.get(key, key)) / factor

    for k in ("well_md", "well_tvd", "shoe_md", "shoe_tvd"):
        conv(k, FT_M)
    for k in ("omw", "lot_emw", "lot_test_mw"):
        conv(k, PPG_KGM3)
    for k in ("sidpp", "sicp", "scr_pressure", "lot_pressure"):
        conv(k, PSI_KPA)
    for k in ("pit_gain", "surface_line_volume", "active_volume", "pump_output"):
        conv(k, BBL_M3)
    if "kmw_round_increment" in case and case["kmw_round_increment"] is not None:
        conv("kmw_round_increment", PPG_KGM3)
    else:
        out["kmw_round_increment"] = 10.0 / PPG_KGM3
    for listkey in ("string", "annulus"):
        if isinstance(out[listkey], list):
            for i, sec in enumerate(out[listkey]):
                if not isinstance(sec, dict):
                    continue
                where = f"{listkey} section {i + 1}"
                if sec.get("length") is not None:
                    sec["length"] = _num(sec["length"], f"{where} length") / FT_M
                if sec.get("capacity") is not None:
                    sec["capacity"] = _num(sec["capacity"], f"{where} capacity") / BBLFT_M3M
                if sec.get("bottom_tvd") is not None and not (isinstance(sec["bottom_tvd"], str) and sec["bottom_tvd"].strip() == ""):
                    sec["bottom_tvd"] = _num(sec["bottom_tvd"], f"{where} bottom TVD") / FT_M
    return out


def _sections(raw, kind, deviated):
    label = "Drill string" if kind == "string" else "Annulus"
    if not isinstance(raw, list) or len(raw) == 0:
        raise InputError(f"{label} needs at least one section.")
    out = []
    for i, sec in enumerate(raw):
        where = f"{label} section {i + 1}"
        if not isinstance(sec, dict):
            raise InputError(f"{where} must have a name, length and capacity.")
        name = str(sec.get("name") or f"Section {i + 1}").strip()[:60] or f"Section {i + 1}"
        length = _num(sec.get("length"), f"{where} ({name}) length")
        cap = _num(sec.get("capacity"), f"{where} ({name}) capacity")
        if length <= 0:
            raise InputError(f"{where} ({name}) length must be greater than zero.")
        if cap <= 0:
            raise InputError(f"{where} ({name}) capacity must be greater than zero.")
        item = {"name": name, "length": length, "capacity": cap}
        if kind == "string" and deviated:
            item["bottom_tvd"] = _num(sec.get("bottom_tvd"), f"{where} ({name}) bottom TVD")
        out.append(item)
    return out


def _warn(warnings, code, level, message):
    warnings.append({"code": code, "level": level, "message": message})


def kmw_round_up(kmw, increment):
    """Round a kill mud weight up to the next multiple of increment (exact multiples stay).

    A value within a millionth of an increment above a multiple counts as that multiple, so
    float noise (9.8000001 ppg after a unit round trip) does not add a whole 0.1 ppg.
    """
    n = math.ceil(kmw / increment - 1e-6)
    return round(n * increment, 12)


def influx_fill(pit_gain, annulus):
    """Fill the annulus from the bit upward with the pit gain volume.

    Returns (height_ft, parts) where parts lists the height and volume placed in
    each annular section. Raises InputError if the gain exceeds the annulus.
    """
    remaining = pit_gain
    height = 0.0
    parts = []
    for sec in annulus:
        if remaining <= 0:
            break
        sec_vol = sec["length"] * sec["capacity"]
        if remaining <= sec_vol:
            h = remaining / sec["capacity"]
            parts.append({"name": sec["name"], "height": h, "volume": remaining})
            height += h
            remaining = 0.0
            break
        parts.append({"name": sec["name"], "height": sec["length"], "volume": sec_vol})
        height += sec["length"]
        remaining -= sec_vol
    if remaining > 1e-9:
        raise InputError("Pit gain is larger than the whole annular volume. Check the pit gain and annular capacities.")
    return height, parts


def classify_influx(gradient):
    if gradient < 0.25:
        return "gas"
    if gradient <= 0.4:
        return "oil, condensate or mixed"
    return "water"


def annular_volume_between(annulus, from_bottom, to_bottom):
    """Annular volume between two distances measured upward from the bit (MD, ft)."""
    vol = 0.0
    base = 0.0
    for sec in annulus:
        top = base + sec["length"]
        lo = max(base, from_bottom)
        hi = min(top, to_bottom)
        if hi > lo:
            vol += (hi - lo) * sec["capacity"]
        base = top
    return vol


def compute(case):
    """Compute a full kill sheet. Raises InputError on impossible input."""
    c = to_imperial(case)
    warnings = []
    deviated = c.get("deviated", False)
    if deviated is None:
        deviated = False
    if not isinstance(deviated, bool):
        raise InputError("deviated must be true or false.")
    basis = c.get("kmw_basis", "rounded")
    if basis not in ("rounded", "exact"):
        raise InputError("kmw_basis must be 'rounded' or 'exact'.")

    v = {k: _get(c, k) for k in WELL_KEYS}
    md, tvd = v["well_md"], v["well_tvd"]
    shoe_md, shoe_tvd = v["shoe_md"], v["shoe_tvd"]
    omw = v["omw"]
    sidpp, sicp = v["sidpp"], v["sicp"]
    scr, spm, pump = v["scr_pressure"], v["kill_rate_spm"], v["pump_output"]
    pit_gain = v["pit_gain"]
    line_vol = _get(c, "surface_line_volume", required=False, default=0.0)
    active = _get(c, "active_volume", required=False, default=None)
    inc = _get(c, "kmw_round_increment", required=False, default=0.1)

    # Hard errors: impossible geometry or values.
    for k, val in (("well_md", md), ("well_tvd", tvd), ("shoe_md", shoe_md), ("shoe_tvd", shoe_tvd)):
        if val <= 0:
            raise InputError(f"{LABELS[k]} must be greater than zero.")
    if tvd > md + 1e-6:
        raise InputError("Well TVD cannot be greater than well MD.")
    if shoe_tvd > shoe_md + 1e-6:
        raise InputError("Shoe TVD cannot be greater than shoe MD.")
    if shoe_md > md + 1e-6:
        raise InputError("Shoe MD is deeper than the well MD (TD). Check the shoe and well depths.")
    if shoe_tvd > tvd + 1e-6:
        raise InputError("Shoe TVD is deeper than the well TVD. Check the shoe and well depths.")
    if not (MW_MIN_PPG <= omw <= MW_MAX_PPG):
        raise InputError(f"Original mud weight {omw:.2f} ppg is outside the {MW_MIN_PPG:.0f} to {MW_MAX_PPG:.0f} ppg range this tool accepts.")
    for k, val in (("sidpp", sidpp), ("sicp", sicp), ("pit_gain", pit_gain), ("surface_line_volume", line_vol)):
        if val < 0:
            raise InputError(f"{LABELS[k]} cannot be negative.")
    if scr <= 0:
        raise InputError("Slow circulating rate pressure must be greater than zero.")
    if spm <= 0:
        raise InputError("Kill rate must be greater than zero strokes per minute.")
    if pump <= 0:
        raise InputError("Pump output must be greater than zero. A zero pump output makes every stroke count infinite.")
    if inc <= 0:
        raise InputError("KMW rounding increment must be greater than zero.")
    if active is not None and active < 0:
        raise InputError("Active system volume cannot be negative.")

    # LOT / FIT as an equivalent mud weight at the shoe.
    if c.get("lot_emw") is not None and not (isinstance(c.get("lot_emw"), str) and c["lot_emw"].strip() == ""):
        lot_emw = _get(c, "lot_emw")
        lot_source = "emw"
    else:
        lot_p = _get(c, "lot_pressure", required=False)
        lot_mw = _get(c, "lot_test_mw", required=False)
        if lot_p is None or lot_mw is None:
            raise InputError("Enter the LOT/FIT as an EMW, or as a surface leak-off pressure plus the test mud weight.")
        if lot_p < 0:
            raise InputError("LOT/FIT surface pressure cannot be negative.")
        if not (MW_MIN_PPG <= lot_mw <= MW_MAX_PPG):
            raise InputError(f"LOT/FIT test mud weight {lot_mw:.2f} ppg is outside the {MW_MIN_PPG:.0f} to {MW_MAX_PPG:.0f} ppg range.")
        lot_emw = lot_mw + lot_p / (G * shoe_tvd)
        lot_source = "pressure"
    if lot_emw > MW_MAX_PPG:
        raise InputError(f"LOT/FIT EMW {lot_emw:.2f} ppg is above {MW_MAX_PPG:.0f} ppg. Check the LOT/FIT entry (a misplaced decimal point overstates MAASP).")
    if lot_emw <= omw:
        raise InputError("LOT/FIT EMW must be greater than the original mud weight. As entered the shoe is already at or past leak-off.")

    string = _sections(c.get("string"), "string", deviated)
    annulus = _sections(c.get("annulus"), "annulus", False)
    s_len = sum(s["length"] for s in string)
    a_len = sum(s["length"] for s in annulus)
    if abs(s_len - md) > LENGTH_TOL_FT:
        raise InputError(f"Drill string section lengths add to {s_len:.1f} ft but the well MD is {md:.1f} ft. They must match (bit on bottom).")
    if abs(a_len - md) > LENGTH_TOL_FT:
        raise InputError(f"Annular section lengths add to {a_len:.1f} ft but the well MD is {md:.1f} ft. They must match.")
    if deviated:
        prev_tvd, prev_md, cum = 0.0, 0.0, 0.0
        for s in string:
            cum += s["length"]
            if s["bottom_tvd"] < 0:
                raise InputError(f"{s['name']}: bottom TVD cannot be negative.")
            if s["bottom_tvd"] < prev_tvd - 1e-6:
                raise InputError(f"{s['name']}: bottom TVD is shallower than the section above it.")
            if s["bottom_tvd"] - prev_tvd > (cum - prev_md) + 1e-6:
                raise InputError(f"{s['name']}: TVD gained in the section is more than its length.")
            prev_tvd, prev_md = s["bottom_tvd"], cum
        if abs(string[-1]["bottom_tvd"] - tvd) > LENGTH_TOL_FT:
            raise InputError(f"The last string section bottom TVD ({string[-1]['bottom_tvd']:.1f} ft) must equal the well TVD ({tvd:.1f} ft).")

    # Warnings: possible but suspicious.
    if sicp < sidpp:
        _warn(warnings, "sicp_lt_sidpp", "warn",
              "SICP is lower than SIDPP. This is unusual: check for a float or string influx, a plugged or washed gauge, "
              "trapped pressure, or an influx lighter than the annulus fluid being absent. Verify before using any number here.")
    if sidpp == 0 and sicp == 0:
        _warn(warnings, "no_pressure", "warn",
              "SIDPP and SICP are both zero. KMW equals the original mud weight. Confirm the well is static and the gauges read.")
    elif sidpp == 0:
        _warn(warnings, "sidpp_zero", "warn",
              "SIDPP is zero. If a float is in the string, SIDPP must be read by bumping the float before KMW can be trusted.")
    if not deviated and md - tvd > 0.02 * md:
        _warn(warnings, "consider_deviated", "info",
              "Well MD exceeds TVD by more than 2 percent. The straight-line schedule overstates drill pipe pressure in a deviated well. Consider deviated mode.")
    if pump > 1.0:
        _warn(warnings, "pump_output_large", "warn", "Pump output above 1 bbl/stk is unusual. Check the units.")

    # Kill mud weight.
    kmw_exact = omw + sidpp / (G * tvd)
    kmw_rounded = kmw_round_up(kmw_exact, inc)
    kmw = kmw_rounded if basis == "rounded" else kmw_exact
    if kmw >= BARITE_PPG:
        raise InputError("Kill mud weight is at or above the barite density (35 ppg). Check SIDPP and TVD.")
    if kmw > MW_MAX_PPG:
        _warn(warnings, "kmw_high", "bad", f"Kill mud weight is above {MW_MAX_PPG:.0f} ppg. Check SIDPP and TVD.")

    icp = scr + sidpp
    fcp = scr * kmw / omw

    # Volumes and strokes.
    string_vol = sum(s["length"] * s["capacity"] for s in string)
    ann_vol = sum(s["length"] * s["capacity"] for s in annulus)
    open_hole = md - shoe_md
    bit_to_shoe_vol = annular_volume_between(annulus, 0.0, open_hole)
    surf_to_bit_vol = line_vol + string_vol
    total_vol = surf_to_bit_vol + ann_vol
    volumes = {
        "surface_line": line_vol,
        "string": string_vol,
        "surface_to_bit": surf_to_bit_vol,
        "bit_to_shoe": bit_to_shoe_vol,
        "bit_to_surface": ann_vol,
        "total_circulation": total_vol,
    }
    strokes = {k: val / pump for k, val in volumes.items()}
    minutes = {k: val / spm for k, val in strokes.items()}

    # Wait and Weight step-down schedule.
    line_stk = strokes["surface_line"]
    bit_stk = strokes["surface_to_bit"]
    points = [{"name": "Surface (KMW at drill pipe)", "md": 0.0, "tvd": 0.0, "strokes": line_stk, "pressure": icp}]
    cum_md, cum_vol = 0.0, line_vol
    for s in string:
        cum_md += s["length"]
        cum_vol += s["length"] * s["capacity"]
        if deviated:
            s_tvd = s["bottom_tvd"]
        else:
            s_tvd = cum_md * tvd / md
        p = icp - sidpp * (s_tvd / tvd) + (fcp - scr) * (cum_md / md)
        points.append({"name": "Bottom of " + s["name"], "md": cum_md, "tvd": s_tvd, "strokes": cum_vol / pump, "pressure": p})
    # Force exact closure at the bit (lengths may differ from MD by up to the tolerance).
    points[-1]["pressure"] = fcp
    points[-1]["strokes"] = bit_stk

    def linear_at(stk):
        f = (stk - line_stk) / (bit_stk - line_stk)
        return icp - (icp - fcp) * f

    def curve_at(stk):
        if stk <= points[0]["strokes"]:
            return points[0]["pressure"]
        for a, b in zip(points, points[1:]):
            if stk <= b["strokes"]:
                span = b["strokes"] - a["strokes"]
                if span <= 0:
                    return b["pressure"]
                return a["pressure"] + (b["pressure"] - a["pressure"]) * (stk - a["strokes"]) / span
        return points[-1]["pressure"]

    schedule = []
    for i in range(SCHEDULE_STEPS + 1):
        stk = line_stk + (bit_stk - line_stk) * i / SCHEDULE_STEPS
        p = curve_at(stk) if deviated else linear_at(stk)
        if i == 0:
            p = icp
        if i == SCHEDULE_STEPS:
            p = fcp
            stk = bit_stk
        schedule.append({"step": i, "strokes": stk, "pressure": p})

    section_points = []
    linear_excess_max = 0.0
    linear_excess_min = 0.0
    for pt in points:
        ex = linear_at(pt["strokes"]) - pt["pressure"]
        section_points.append(dict(pt, linear_minus_section=ex))
        linear_excess_max = max(linear_excess_max, ex)
        linear_excess_min = min(linear_excess_min, ex)
    if deviated and linear_excess_max > 5:
        _warn(warnings, "linear_overbalance", "info",
              f"A straight line from ICP to FCP would hold up to {linear_excess_max:.0f} psi more drill pipe pressure than the section schedule. "
              "That adds the same amount to bottom-hole pressure and to the shoe load.")
    if linear_excess_min < -5:
        if deviated:
            _warn(warnings, "linear_underbalance", "bad",
                  f"A straight line from ICP to FCP would run up to {-linear_excess_min:.0f} psi below the section schedule (underbalanced). Use the section schedule.")
        else:
            _warn(warnings, "linear_underbalance", "info",
                  f"The string is tapered: the straight-line schedule runs up to {-linear_excess_min:.0f} psi below the hydrostatic section points "
                  "(bottom-hole pressure dips below formation pressure by that much while KMW goes down the string). Compare with the section points.")

    # Driller's method.
    drillers = {
        "first_hold_dp_pressure": icp,
        "first_strokes": strokes["total_circulation"],
        "first_minutes": minutes["total_circulation"],
        "first_bottoms_up_strokes": strokes["bit_to_surface"],
        "second_hold_casing_pressure": sidpp,
        "second_phase1_strokes": strokes["surface_to_bit"],
        "second_phase1_minutes": minutes["surface_to_bit"],
        "second_hold_dp_pressure": fcp,
        "second_phase2_strokes": strokes["bit_to_surface"],
        "second_phase2_minutes": minutes["bit_to_surface"],
    }

    # MAASP.
    maasp_omw = (lot_emw - omw) * G * shoe_tvd
    maasp_kmw = (lot_emw - kmw) * G * shoe_tvd
    if kmw >= lot_emw:
        _warn(warnings, "kmw_over_lot", "bad",
              "Kill mud weight is at or above the shoe LOT/FIT EMW. Losses at the shoe are expected once KMW is in the annulus above the shoe. Stop and escalate.")
    if sicp >= maasp_omw:
        _warn(warnings, "sicp_over_maasp", "bad",
              "SICP is at or above MAASP for the current mud weight. The shoe may already be at risk. Escalate before circulating.")
    elif sicp >= 0.8 * maasp_omw:
        _warn(warnings, "sicp_near_maasp", "warn", "SICP is within 20 percent of MAASP for the current mud weight.")

    # Influx.
    influx = None
    if pit_gain == 0:
        _warn(warnings, "no_pit_gain", "info", "Pit gain is zero, so influx height and gradient are not calculated.")
    else:
        h, parts = influx_fill(pit_gain, annulus)
        grad = G * omw - (sicp - sidpp) / h
        influx = {"height": h, "gradient": grad, "type": classify_influx(grad), "sections": parts}
        if grad < 0:
            _warn(warnings, "influx_gradient_negative", "warn",
                  "Calculated influx gradient is below zero, which is not physical. Check SICP, SIDPP, pit gain and annular capacity.")
        elif grad > G * omw:
            _warn(warnings, "influx_gradient_heavy", "warn",
                  "Calculated influx gradient is heavier than the mud. Check SICP and SIDPP.")
        if md - tvd > 0.02 * md:
            _warn(warnings, "influx_along_hole", "info",
                  "Influx height is measured along hole. In an inclined bottom section the vertical height is shorter, so the gradient is less reliable.")
        if h > open_hole + 1e-9:
            _warn(warnings, "influx_above_shoe", "warn", "Calculated influx height extends above the shoe.")

    # Barite.
    lb_per_bbl = BARITE_LB_PER_BBL * (kmw - omw) / (BARITE_PPG - kmw)
    vol_inc_per_bbl = (kmw - omw) / (BARITE_PPG - kmw)
    barite = {"lb_per_bbl": lb_per_bbl, "volume_increase_per_bbl": vol_inc_per_bbl,
              "total_lb": None, "sacks": None, "sacks_rounded_up": None, "volume_increase": None, "final_volume": None}
    if active is not None and active > 0:
        total_lb = lb_per_bbl * active
        sacks = total_lb / SACK_LB
        barite.update({"total_lb": total_lb, "sacks": sacks, "sacks_rounded_up": math.ceil(sacks - 1e-9),
                       "volume_increase": vol_inc_per_bbl * active, "final_volume": active * (1 + vol_inc_per_bbl)})

    return {
        "units": "imperial",
        "deviated": deviated,
        "kmw_basis": basis,
        "kmw_exact": kmw_exact,
        "kmw_rounded": kmw_rounded,
        "kmw": kmw,
        "kmw_round_increment": inc,
        "icp": icp,
        "fcp": fcp,
        "lot_emw": lot_emw,
        "lot_source": lot_source,
        "volumes": volumes,
        "strokes": strokes,
        "minutes": minutes,
        "schedule": schedule,
        "section_points": section_points,
        "linear_excess_max": linear_excess_max,
        "linear_excess_min": linear_excess_min,
        "drillers": drillers,
        "maasp_omw": maasp_omw,
        "maasp_kmw": maasp_kmw,
        "influx": influx,
        "barite": barite,
        "warnings": warnings,
    }
