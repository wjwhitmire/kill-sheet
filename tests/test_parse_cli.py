import json
import os

import pytest

from kill_sheet import EXAMPLE_CASE, InputError, compute, parse_text
from kill_sheet.cli import main

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE_CSV = os.path.join(HERE, "..", "examples", "vertical_land_well.csv")


def test_example_csv_matches_builtin():
    with open(EXAMPLE_CSV, encoding="utf-8") as fh:
        c = parse_text(fh.read())
    a = compute(c)
    b = compute(EXAMPLE_CASE)
    for k in ("kmw", "icp", "fcp", "maasp_omw", "maasp_kmw"):
        assert a[k] == pytest.approx(b[k])
    assert a["strokes"] == pytest.approx(b["strokes"])


def test_parse_json():
    c = parse_text(json.dumps(EXAMPLE_CASE))
    assert c["omw"] == 9.8


def test_parse_tabs_aliases_header_extra_columns():
    text = ("field\tvalue\n# comment\n\nMD\t10000\tft\nTVD\t10000\nshoe_md\t6000\nshoe_tvd\t6000\nMW\t9.8\n"
            "LOT\t14.5\nsidpp\t400\nsicp\t600\ngain\t15\nSCR\t450\nspm\t30\npump\t0.102\n"
            "string\tDP\t9400\t0.01776\nstring\tDC\t600\t0.00768\nannulus\tAll\t10000\t0.05\n")
    c = parse_text(text)
    assert c["well_md"] == 10000 and c["omw"] == 9.8 and len(c["string"]) == 2
    compute(c)


@pytest.mark.parametrize("text,msg", [
    ("", "empty"),
    ("   \n\n", "empty"),
    ("well_md,abc\nstring,a,1,1\nannulus,b,1,1", "not a number"),
    ("well_md,NaN\nstring,a,1,1\nannulus,b,1,1", "finite"),
    ("foo,1\n", "unknown field"),
    ("well_md,1\nwell_md,2\n", "more than once"),
    ("well_md,1\nannulus,b,1,1\n", "No drill string"),
    ("well_md,1\nstring,a,1\n", "needs name"),
    ("[1,2", "JSON"),
    ("[1,2]", "object"),
    ("deviated,maybe\n", "yes or no"),
])
def test_parse_errors(text, msg):
    with pytest.raises(InputError, match=msg):
        parse_text(text)


def test_cli_example(capsys):
    assert main(["--example"]) == 0
    out = capsys.readouterr().out
    assert "ICP" in out and "850 psi" in out and "Training and cross-check aid" in out


def test_cli_file_json(capsys):
    assert main([EXAMPLE_CSV, "--json", "--exact"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["kmw_basis"] == "exact"


def test_cli_error(tmp_path, capsys):
    p = tmp_path / "bad.csv"
    p.write_text("well_md,1000\n", encoding="utf-8")
    assert main([str(p)]) == 2
    assert "error:" in capsys.readouterr().err
