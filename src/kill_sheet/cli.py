"""Command line: kill-sheet CASE_FILE [--json] [--exact]

CASE_FILE is JSON or key/value CSV (see kill_sheet.parse). Use --example to
print the built-in example. Training and cross-check aid only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from .core import EXAMPLE_CASE, InputError, compute
from .parse import MAX_BYTES, parse_text

NOTICE = ("Training and cross-check aid only. The rig's approved kill sheet and the "
          "well-site supervisor govern. Verify every input.")


# Control characters (terminal escape sequences) are stripped from the free-text label.
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _report(case, r):
    out = []
    w = out.append
    w(NOTICE)
    if case.get("label"):
        w(_CTRL.sub("", str(case["label"])))
    w("")
    w(f"Kill mud weight   exact {r['kmw_exact']:.3f} ppg   rounded up {r['kmw_rounded']:.2f} ppg   using {r['kmw']:.3f} ppg ({r['kmw_basis']})")
    w(f"ICP               {r['icp']:.0f} psi")
    w(f"FCP               {r['fcp']:.0f} psi")
    w(f"MAASP             {r['maasp_omw']:.0f} psi at OMW, {r['maasp_kmw']:.0f} psi at KMW (LOT/FIT EMW {r['lot_emw']:.2f} ppg)")
    w("")
    w(f"{'Volume':<20}{'bbl':>10}{'strokes':>10}{'min':>8}")
    for k, lab in (("surface_to_bit", "Surface to bit"), ("bit_to_shoe", "Bit to shoe"),
                   ("bit_to_surface", "Bit to surface"), ("total_circulation", "Total circulation")):
        w(f"{lab:<20}{r['volumes'][k]:>10.1f}{r['strokes'][k]:>10.0f}{r['minutes'][k]:>8.1f}")
    w("")
    w("Wait and Weight drill pipe schedule")
    w(f"{'Step':<6}{'Strokes':>10}{'psi':>8}")
    for row in r["schedule"]:
        w(f"{row['step']:<6}{row['strokes']:>10.0f}{row['pressure']:>8.0f}")
    if r["influx"]:
        inf = r["influx"]
        w("")
        w(f"Influx height {inf['height']:.0f} ft, gradient {inf['gradient']:.3f} psi/ft, likely {inf['type']} (indicative only)")
    b = r["barite"]
    w("")
    w(f"Barite (SG 4.2) {b['lb_per_bbl']:.1f} lb/bbl")
    if b["total_lb"] is not None:
        w(f"  {b['total_lb']:.0f} lb = {b['sacks_rounded_up']} sacks of 100 lb, volume increase {b['volume_increase']:.1f} bbl")
    for wn in r["warnings"]:
        w(f"[{wn['level'].upper()}] {wn['message']}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kill-sheet", description="Surface-stack kill sheet calculator. " + NOTICE)
    ap.add_argument("case_file", nargs="?", help="JSON or key/value CSV case file")
    ap.add_argument("--example", action="store_true", help="run the built-in example data")
    ap.add_argument("--exact", action="store_true", help="use the exact KMW instead of rounded up")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = ap.parse_args(argv)
    try:
        if args.example:
            case = dict(EXAMPLE_CASE)
        elif args.case_file:
            with open(args.case_file, "rb") as fh:
                data = fh.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise InputError("File is larger than 5 MB.")
            try:
                text = data.decode("utf-8-sig", errors="strict")
            except UnicodeDecodeError:
                raise InputError(
                    f"{args.case_file} is not UTF-8 text. Save it as UTF-8 CSV or JSON (in Excel: Save As, CSV UTF-8) and try again."
                ) from None
            case = parse_text(text)
        else:
            ap.error("give a case file or --example")
        if args.exact:
            case["kmw_basis"] = "exact"
        r = compute(case)
    except (InputError, UnicodeDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(r, indent=1))
    else:
        print(_report(case, r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
