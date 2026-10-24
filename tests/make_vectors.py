"""Generate tests/vectors.json from the Python library. Run: python tests/make_vectors.py"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from kill_sheet import EXAMPLE_CASE, InputError, compute  # noqa: E402
from kill_sheet.core import BBL_M3, BBLFT_M3M, FT_M, PPG_KGM3, PSI_KPA  # noqa: E402


def base(**over):
    c = copy.deepcopy(EXAMPLE_CASE)
    c.pop("label", None)
    c.update(over)
    return c


def with_string(c, i, **over):
    c["string"][i].update(over)
    return c


def metric(c):
    m = {"units": "metric", "kill_rate_spm": c["kill_rate_spm"], "kmw_basis": c.get("kmw_basis", "rounded"),
         "deviated": c.get("deviated", False)}
    for k in ("well_md", "well_tvd", "shoe_md", "shoe_tvd"):
        m[k] = c[k] * FT_M
    for k in ("omw", "lot_emw"):
        m[k] = c[k] * PPG_KGM3
    for k in ("sidpp", "sicp", "scr_pressure"):
        m[k] = c[k] * PSI_KPA
    for k in ("pit_gain", "surface_line_volume", "active_volume", "pump_output"):
        m[k] = c[k] * BBL_M3
    m["string"] = [{"name": s["name"], "length": s["length"] * FT_M, "capacity": s["capacity"] * BBLFT_M3M,
                    "bottom_tvd": s["bottom_tvd"] * FT_M} for s in c["string"]]
    m["annulus"] = [{"name": s["name"], "length": s["length"] * FT_M, "capacity": s["capacity"] * BBLFT_M3M}
                    for s in c["annulus"]]
    return m


J_WELL = base(
    well_md=12000, well_tvd=9000, shoe_md=7000, shoe_tvd=6000, deviated=True,
    string=[{"name": "DP vertical", "length": 2000, "capacity": 0.01776, "bottom_tvd": 2000},
            {"name": "DP build", "length": 3000, "capacity": 0.01776, "bottom_tvd": 4500},
            {"name": "DP tangent", "length": 5800, "capacity": 0.01776, "bottom_tvd": 8200},
            {"name": "HWDP", "length": 600, "capacity": 0.00874, "bottom_tvd": 8600},
            {"name": "DC", "length": 600, "capacity": 0.00768, "bottom_tvd": 9000}],
    annulus=[{"name": "DC x OH", "length": 600, "capacity": 0.02914},
             {"name": "DP x OH", "length": 4400, "capacity": 0.0459},
             {"name": "DP x csg", "length": 7000, "capacity": 0.05154}],
    surface_line_volume=4.0,
)

CASES = [
    ("example", base()),
    ("example_exact", base(kmw_basis="exact")),
    ("example_deviated_flag", base(deviated=True)),
    ("example_surface_lines", base(surface_line_volume=6.5)),
    ("lot_from_pressure", base(lot_emw=None, lot_pressure=1400, lot_test_mw=9.5)),
    ("influx_spill", base(pit_gain=40, sicp=780)),
    ("influx_three_sections", base(pit_gain=200, sicp=900)),
    ("heavy_influx_water", base(sicp=420)),
    ("sicp_lt_sidpp", base(sicp=300)),
    ("zero_gain", base(pit_gain=0)),
    ("zero_sidpp", base(sidpp=0, sicp=150)),
    ("kmw_over_lot", base(lot_emw=10.5)),
    ("no_active_volume", base(active_volume=None)),
    ("round_increment_half", base(kmw_round_increment=0.5)),
    ("j_well_deviated", J_WELL),
    ("j_well_linear", dict(copy.deepcopy(J_WELL), deviated=False)),
    ("metric_example", metric(base())),
    ("metric_j_well", metric(J_WELL)),
    ("err_shoe_below_td", base(shoe_md=10500, shoe_tvd=9500)),
    ("err_zero_pump", base(pump_output=0)),
    ("err_negative_sidpp", base(sidpp=-50)),
    ("err_negative_sicp", base(sicp=-1)),
    ("err_string_length", with_string(base(), 0, length=8000)),
    ("err_tvd_gt_md", base(well_tvd=10500)),
    ("err_gain_too_big", base(pit_gain=900)),
    ("err_no_lot", base(lot_emw=None)),
    ("err_lot_below_mw", base(lot_emw=9.0)),
    ("err_dev_missing_tvd", with_string(base(deviated=True), 1, bottom_tvd=None)),
    ("err_dev_tvd_reverse", with_string(base(deviated=True), 1, bottom_tvd=8000)),
    ("err_nan", base(sidpp="abc")),
    ("err_bad_basis", base(kmw_basis="nearest")),
    ("err_mw_range", base(omw=30)),
    ("err_deviated_string", base(deviated="no")),
    ("err_lot_emw_typo", base(lot_emw=145)),
    ("err_underscore_number", base(well_md="10_000")),
]


def main():
    out = {"generator": "tests/make_vectors.py", "cases": []}
    for name, case in CASES:
        try:
            res = compute(case)
        except InputError as exc:
            out["cases"].append({"name": name, "input": case, "error": str(exc)})
            continue
        out["cases"].append({"name": name, "input": case, "result": res})
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {len(out['cases'])} vectors to tests/vectors.json")


if __name__ == "__main__":
    main()
