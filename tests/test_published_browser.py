"""Browser test of the page exactly as GitHub Pages serves it.

docs/ is copied to a temporary folder, the publish placeholders are filled
the way the release script fills them, and the copy is served under
/kill-sheet/ on localhost. Headless Chromium then runs the main workflows and
fails on any page error, console error or Content-Security-Policy violation.

Needs the playwright package and its Chromium; skipped when they are missing.
"""

import functools
import http.server
import shutil
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
NAME = "kill-sheet"
FILL = {
    "https://wjwhitmire.github.io/kill-sheet/": f"https://wjwhitmire.github.io/{NAME}/",
    "wjwhitmire": "wjwhitmire",
    "https://github.com/wjwhitmire/kill-sheet": f"https://github.com/wjwhitmire/{NAME}",
}
WATCH = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("pages")
    dest = root / NAME
    shutil.copytree(ROOT / "docs", dest)
    for f in dest.rglob("*"):
        if f.suffix in (".html", ".js", ".json", ".webmanifest", ".css", ".txt", ".xml"):
            text = f.read_text(encoding="utf-8")
            for k, v in FILL.items():
                text = text.replace(k, v)
            f.write_text(text, encoding="utf-8")
    handler = functools.partial(QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/{NAME}/"
    server.shutdown()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


def open_page(browser, url, width=1280, **ctx):
    context = browser.new_context(viewport={"width": width, "height": 900}, **ctx)
    context.route("https://fonts.googleapis.com/**", lambda r: r.abort())
    context.route("https://fonts.gstatic.com/**", lambda r: r.abort())
    context.add_init_script(WATCH)
    page = context.new_page()
    page.problems = []
    page.on("pageerror", lambda e: page.problems.append(f"pageerror: {e}"))
    page.on(
        "console",
        lambda m: page.problems.append(f"console: {m.text}")
        if m.type == "error" and "fonts.g" not in m.text and "ERR_FAILED" not in m.text
        and not (m.location or {}).get("url", "").endswith("/favicon.ico")
        else None,
    )
    page.goto(url)
    return page


def assert_clean(page):
    csp = page.evaluate("window.__csp")
    assert not csp, csp
    assert not page.problems, page.problems
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
    for placeholder in FILL:
        assert placeholder not in page.content()


EXAMPLE_CSV = (ROOT / "examples" / "vertical_land_well.csv").read_text()


def error_text(page):
    return "" if page.is_hidden("#error") else page.text_content("#error")


def edit(page, box, value):
    page.fill(f"#{box}", value)
    page.wait_for_timeout(50)


def test_example_kill_sheet(site, browser):
    page = open_page(browser, site)
    assert page.text_content("#t-kmw").startswith("10.6")
    assert page.text_content("#t-icp").startswith("850")
    assert page.text_content("#t-fcp").startswith("487")
    assert page.text_content("#t-maasp").startswith("1,466")
    assert page.locator("#tbl-sched tbody tr").count() == 11
    assert "gas" in page.text_content("#influx")
    assert_clean(page)


def test_unit_round_trip_is_exact(site, browser):
    page = open_page(browser, site)
    page.click("#units-metric")
    assert "1,270" in page.text_content("#t-kmw")
    page.click("#units-imperial")
    assert page.input_value("#in-omw") == "9.8"
    edit(page, "in-sidpp", "0")
    edit(page, "in-sicp", "0")
    # KMW equals OMW when SIDPP is zero; float drift used to round it up to 9.9
    assert page.text_content("#t-kmw").startswith("9.8")


def test_thousands_comma_in_a_box(site, browser):
    page = open_page(browser, site)
    edit(page, "in-sidpp", "1,200")
    assert error_text(page) == ""
    assert page.text_content("#t-icp").startswith("1,650")
    edit(page, "in-omw", "10,5")
    assert "not a number" in error_text(page)


def test_file_with_comma_split_number_is_refused(site, browser, tmp_path):
    f = tmp_path / "case.csv"
    f.write_text(EXAMPLE_CSV.replace("sidpp,400", "sidpp,1,200"))
    page = open_page(browser, site)
    page.set_input_files("#file-input", str(f))
    page.wait_for_function("document.getElementById('file-status').textContent.includes('Nothing was loaded')")
    assert "split by a comma" in page.text_content("#file-status")
    assert page.text_content("#t-icp").startswith("850")  # the form was left alone


def test_example_file_loads(site, browser, tmp_path):
    f = tmp_path / "case.csv"
    f.write_text(EXAMPLE_CSV)
    page = open_page(browser, site)
    page.set_input_files("#file-input", str(f))
    page.wait_for_function("document.getElementById('file-status').textContent.startsWith('Loaded case.csv')")
    assert page.text_content("#t-kmw").startswith("10.6")


def test_deviated_example_and_copy(site, browser):
    page = open_page(browser, site)
    page.select_option("#example-select", "jwell")
    page.click("#load-example")
    assert page.is_checked("#deviated")
    assert error_text(page) == ""
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined})")
    page.click("#copy-csv")
    assert page.input_value("#csv-fallback").startswith("item,value,unit")


def test_bad_input_hides_results(site, browser):
    page = open_page(browser, site)
    edit(page, "in-pump_output", "0")
    assert "Pump output must be greater than zero" in error_text(page)
    assert page.is_hidden("#results")


def test_phone_width(site, browser):
    page = open_page(browser, site, width=400, has_touch=True, is_mobile=True)
    assert page.text_content("#t-kmw").startswith("10.6")
    assert_clean(page)
