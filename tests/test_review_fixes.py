"""Regression tests for defects found in independent review."""

import copy

import pytest

from kill_sheet import EXAMPLE_CASE, InputError, compute, parse_text
from kill_sheet.cli import main


def case(**over):
    c = copy.deepcopy(EXAMPLE_CASE)
    c.update(over)
    return c


def test_lot_emw_decimal_typo_refused():
    # 145 entered for 14.5 ppg gave MAASP 42,182 psi with no warning.
    with pytest.raises(InputError, match="LOT/FIT EMW .* above 25 ppg"):
        compute(case(lot_emw=145))


def test_lot_from_pressure_typo_refused():
    with pytest.raises(InputError, match="above 25 ppg"):
        compute(case(lot_emw=None, lot_pressure=14000, lot_test_mw=9.5))


@pytest.mark.parametrize("val", ["10_000", "\u0661\u0660\u0660\u0660\u0660", " 1 0 "])
def test_numbers_must_be_plain_decimal(val):
    # Python float() accepts underscores and non-ASCII digits; the JS core does not.
    with pytest.raises(InputError, match="not a number"):
        compute(case(well_md=val))


def test_parser_rejects_underscore_digits():
    with pytest.raises(InputError, match="not a number"):
        parse_text("well_md,10_000\nstring,a,1,1\nannulus,b,1,1\n")


def test_deeply_nested_json_is_an_input_error():
    with pytest.raises(InputError, match="nested too deeply"):
        parse_text("[" * 100000 + "]" * 100000)


def test_cli_strips_control_characters_from_label(tmp_path, capsys):
    import json
    p = tmp_path / "c.json"
    p.write_text(json.dumps(case(label="Well A\x1b[2J\x1b[31mX")), encoding="utf-8")
    assert main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and "Well A[2J[31mX" in out


@pytest.mark.parametrize("row", ["sidpp,1,200", "omw,10,5", "pit_gain,1,5", "active_volume,1,200.5"])
def test_comma_split_numbers_are_refused(row):
    # these used to be read as SIDPP 1 psi, OMW 10 ppg, ... with the rest dropped as an extra column
    text = row + "\nstring,a,1,1\nannulus,b,1,1\n"
    with pytest.raises(InputError, match="split by a comma"):
        parse_text(text)


def test_text_extra_column_still_ignored():
    assert parse_text("omw,9.8,ppg\nstring,a,1,1\nannulus,b,1,1\n")["omw"] == 9.8


def test_kmw_round_up_ignores_float_noise():
    from kill_sheet.core import kmw_round_up

    # 9.8 ppg after an oilfield -> metric -> oilfield round trip used to round up to 9.9
    assert kmw_round_up(9.8000001, 0.1) == 9.8
    assert kmw_round_up(9.80001, 0.1) == 9.9
    assert kmw_round_up(10.569, 0.1) == 10.6
    assert kmw_round_up(10.6, 0.1) == 10.6


def test_cli_non_utf8_file_has_a_plain_message(tmp_path, capsys):
    f = tmp_path / "case.csv"
    f.write_bytes(b"omw,9.8\n# caf\xe9\n")
    assert main([str(f)]) == 2
    err = capsys.readouterr().err
    assert "is not UTF-8 text" in err
    assert "codec" not in err
