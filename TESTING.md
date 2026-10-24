# Testing

Every function of Kill Sheet, how it was tested and the result. Browser checks ran against the published form of the page: `git archive HEAD`, publish placeholders filled, `docs/` served under `/kill-sheet/` on localhost, headless Chromium at 1280 px and 400 px (touch), light and dark.

## How to rerun

```bash
pip install -e .[dev]
pytest -q                                   # library, parser, CLI
python tests/make_vectors.py && node web/parity.test.mjs   # JS core matches Python
python web/build_pages.py                   # rebuild docs/index.html
pip install playwright && python -m playwright install chromium
pytest -q tests/test_published_browser.py   # published page under /kill-sheet/, main workflows
```

`tests/test_published_browser.py` copies `docs/`, fills the publish placeholders, serves the copy under `/kill-sheet/` and fails on page errors, console errors, CSP violations, sideways scroll or leftover placeholders. It skips itself without Playwright; CI runs it in the `browser` job.

Suite size: 79 pytest + 2,860 parity checks before this pass; 94 pytest (8 browser) + 2,866 parity checks after.

## Function inventory

### Browser page

| Function | What was done | Result |
|---|---|---|
| Page load, published form | Opened `/kill-sheet/` | Pass: example kill sheet, no errors or CSP violations |
| Layout 1280 / 400 px, light and dark | Scroll width | Pass |
| Touch targets | 400 px touch | Pass (the 22 px deviated checkbox sits in a 44 px label) |
| Example select and Load example (vertical, J-type) | Load each | Pass: deviated mode and TVD column for the J well |
| Units Oilfield / Metric | Toggle; form values converted | Pass: KMW 1,270 kg/m3, MD 3048 m |
| Unit round trip | Oilfield, metric, oilfield, then SIDPP = SICP = 0 | Fail before (OMW came back as 9.8000001 and KMW rounded up to 9.9 ppg); pass after fix |
| Units remembered | Reload | Pass (per-browser storage) |
| Scalar inputs (16 boxes) | Negative, text, blank, out of range, 1e400, NaN, full-width digits, `10,5` | Pass: each refused with a specific message, results hidden |
| Thousands comma in a box (`1,200`, `10,000`) | Typed | Fail before (refused as not a number); pass after fix (accepted) |
| LOT/FIT as EMW or as surface pressure plus test MW | Switch, enter 1466.4 psi at 9.8 ppg | Pass: EMW 14.50 ppg |
| KMW basis rounded / exact | Select | Pass: 10.6 / 10.569 |
| Deviated checkbox | Vertical example; blank section TVD | Pass |
| Drill string and annulus tables | Add, remove, cannot remove the last row, length totals flagged when they do not close | Pass |
| Warnings | Tapered string, SIDPP and SICP zero, SICP below SIDPP, pit gain 0, no active volume | Pass |
| Result tiles, volumes, schedule, section points, chart, Driller's method, influx, barite | Read values | Pass: matches the hand calculation below |
| Copy results as CSV | Clipboard | Pass: KMW 10.6, ICP 850.0, FCP 486.7, 1634 strokes |
| Copy with an input error | Click | Pass: "Nothing to copy" |
| Copy fallback | No clipboard | Pass |
| Load a case file: example CSV, empty JSON object, metric JSON | | Pass: metric file switches the units |
| Load a file with `sidpp,1,200` or `omw,9,8` | | Fail before (loaded as SIDPP 1 psi and OMW 9 ppg, kill sheet shown); pass after fix (refused, form unchanged) |
| Load empty, bad JSON, array JSON, unknown field, duplicate field, over 5 MB | | Pass: refused with a message |
| Method and limits | Expand | Pass |
| Network | `fetch` from the page | Pass: blocked by CSP; no network features |
| Print | Print to PDF | Pass |
| `web/app.html` via file:// | Opened directly | Pass |

### CLI

| Command | Result |
|---|---|
| `kill-sheet --example` | Pass |
| `kill-sheet case.csv`, `--exact`, `--json` | Pass |
| No input, missing file, comma-split number | Pass: message and exit 2 |
| Non-UTF-8 case file | Fail before (Python decoding error text); pass after fix (plain "is not UTF-8 text" message, exit 2) |

### Library

`compute`, `to_imperial`, `kmw_round_up`, `influx_fill`, `classify_influx`, `annular_volume_between`, `parse_text`, `EXAMPLE_CASE`: covered by pytest and parity vectors. Pass.

## Correctness checks

Standard surface-stack kill sheet formulas (IADC WellSharp / IWCF), recomputed by hand outside the repo and compared with both cores in the published page (largest relative difference 2.2e-15).

| Case | Hand calculation | Result |
|---|---|---|
| Example vertical well | KMW = 9.8 + 400/(0.052 x 10,000) = 10.569, rounded 10.6; ICP 850; FCP = 450 x 10.6/9.8 = 486.73; 166.68 bbl / 0.102 = 1,634.1 strokes; MAASP = 4.7 x 0.052 x 6,000 = 1,466.4; influx 15/0.02914 = 514.76 ft, 0.5096 - 200/514.76 = 0.1211 psi/ft (gas); barite 1470 x 0.8/24.4 = 48.20 lb/bbl | Pass |
| Influx spilling over two annular sections | 1,090.54 ft, 0.3262 psi/ft | Pass |
| Very deep: 30,000 ft TVD, 16 ppg, SIDPP 1,500 | KMW 16.962, rounded 17.0; FCP 478.12; MAASP 2,600 | Pass |
| SIDPP 0 | KMW = OMW, warning | Pass |
| Deviated J well section points | P = ICP - SIDPP x tvd/TVD + (FCP - SCR) x md/MD: 767.999, 667.219, 522.749 psi | Pass |
| Metric example | KMW 1,270 kg/m3 (10 kg/m3 increment) | Pass |
| Invalid: OMW 4 ppg, negative SIDPP, pump output 0, shoe below TD, LOT = OMW, TVD > MD, pit gain larger than annulus, text, infinity | Refused | Pass |

## Automation audit

| Decision point | Before | After |
|---|---|---|
| Units | Read from the file (`units`), remembered per browser | No change |
| LOT/FIT entry mode | Picked from the file (EMW or pressure) | No change |
| Unit toggle | Converted values drifted on a round trip | Original values restored on the way back |
| Thousands comma in a box | Refused | Accepted (`1,200`); a decimal comma is still refused |
| Deviated mode | Info warning when MD exceeds TVD by more than 2 percent | No change: section TVDs are only known to the user |
| KMW basis | Default rounded up, override select | No change |

## Known limits

- Surface BOP stack only; see README for the full list.
