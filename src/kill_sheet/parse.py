"""Read a kill sheet case from JSON or a simple key/value text file.

Text format (comma, tab or semicolon separated; blank lines and lines starting
with # are skipped; an optional header row "field,value" is ignored):

    units,imperial
    well_md,10000
    well_tvd,10000
    ...
    string,5 in DP,8860,0.01776[,bottom_tvd]
    annulus,DC x open hole,600,0.02914

Scalar rows take the first value after the key; extra columns are ignored.
"""

from __future__ import annotations

import json
import re

from .core import _NONFINITE_RE, _NUM_RE, InputError

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50_000

SCALAR_KEYS = {
    "units", "well_md", "well_tvd", "shoe_md", "shoe_tvd", "omw", "lot_emw", "lot_pressure", "lot_test_mw",
    "sidpp", "sicp", "pit_gain", "scr_pressure", "kill_rate_spm", "pump_output", "surface_line_volume",
    "active_volume", "deviated", "kmw_basis", "kmw_round_increment", "label",
}
ALIASES = {
    "md": "well_md", "tvd": "well_tvd", "mw": "omw", "mud_weight": "omw", "original_mud_weight": "omw",
    "scr": "scr_pressure", "scrp": "scr_pressure", "spm": "kill_rate_spm", "kill_rate": "kill_rate_spm",
    "pump": "pump_output", "lot": "lot_emw", "fit": "lot_emw", "gain": "pit_gain",
    "surface_lines": "surface_line_volume", "active": "active_volume",
}
TEXT_KEYS = {"units", "kmw_basis", "label"}
_INT_RE = re.compile(r"^[+-]?\d+$", re.ASCII)
_DIGITS_RE = re.compile(r"^\d+(\.\d*)?$", re.ASCII)


def _norm_key(k):
    k = re.sub(r"[^a-z0-9]+", "_", k.strip().lower()).strip("_")
    return ALIASES.get(k, k)


def _split(line):
    if "\t" in line:
        parts = line.split("\t")
    elif "," in line:
        parts = line.split(",")
    elif ";" in line:
        parts = line.split(";")
    else:
        parts = line.split()
    return [p.strip() for p in parts]


def _to_num(s, where):
    if s == "":
        raise InputError(f"{where}: value is blank.")
    if _NUM_RE.match(s):
        v = float(s)
    elif _NONFINITE_RE.match(s):
        v = float("nan")
    else:
        raise InputError(f"{where}: '{s}' is not a number.")
    if v != v or v in (float("inf"), float("-inf")):
        raise InputError(f"{where}: value must be a finite number.")
    return v


def _bool(s, where):
    t = s.strip().lower()
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off", ""):
        return False
    raise InputError(f"{where}: expected yes or no, got {s!r}.")


def parse_text(text):
    """Parse JSON or key/value text into a case dict. Raises InputError with a specific message."""
    if not isinstance(text, str):
        raise InputError("Input must be text.")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise InputError("File is larger than 5 MB.")
    stripped = text.lstrip("﻿").strip()
    if stripped == "":
        raise InputError("File is empty.")
    if stripped[0] in "{[":
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InputError(f"JSON could not be read (line {exc.lineno}, column {exc.colno}).") from None
        except RecursionError:
            raise InputError("JSON could not be read (nested too deeply).") from None
        if not isinstance(data, dict):
            raise InputError("JSON input must be an object of named fields.")
        return data

    lines = stripped.splitlines()
    if len(lines) > MAX_ROWS:
        raise InputError("File has more than 50,000 rows.")
    case = {"string": [], "annulus": []}
    seen = set()
    for n, raw in enumerate(lines, start=1):
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        parts = _split(line)
        key = _norm_key(parts[0])
        where = f"Line {n} ({parts[0]})"
        if n == 1 and key in ("field", "key", "parameter", "name") and len(parts) >= 2:
            continue
        if key in ("string", "annulus"):
            if len(parts) < 4:
                raise InputError(f"{where}: a {key} row needs name, length and capacity.")
            sec = {"name": parts[1][:60], "length": _to_num(parts[2], where + " length"),
                   "capacity": _to_num(parts[3], where + " capacity")}
            if key == "string" and len(parts) >= 5 and parts[4] != "":
                sec["bottom_tvd"] = _to_num(parts[4], where + " bottom TVD")
            case[key].append(sec)
            continue
        if key not in SCALAR_KEYS:
            raise InputError(f"{where}: unknown field.")
        if key in seen:
            raise InputError(f"{where}: field appears more than once.")
        seen.add(key)
        if len(parts) < 2:
            raise InputError(f"{where}: value is missing.")
        val = parts[1]
        if key in TEXT_KEYS:
            case[key] = val.lower() if key != "label" else val[:200]
        elif key == "deviated":
            case[key] = _bool(val, where)
        else:
            if len(parts) > 2 and _INT_RE.match(val) and _DIGITS_RE.match(parts[2]):
                # "sidpp,1,200" splits into 1 and 200: refuse it rather than read 1 psi.
                raise InputError(
                    f"{where}: '{val},{parts[2]}' looks like one number split by a comma. "
                    "Write it without the thousands comma (1200) and with a decimal point (10.5)."
                )
            case[key] = _to_num(val, where)
    if not case["string"]:
        raise InputError("No drill string rows found (rows starting with 'string').")
    if not case["annulus"]:
        raise InputError("No annulus rows found (rows starting with 'annulus').")
    return case
