# Kill Sheet

A free, open surface-stack kill sheet calculator for the Wait and Weight and Driller's methods. It gives kill mud weight, ICP and FCP, volumes and strokes, the drill pipe pressure step-down schedule (vertical or deviated), MAASP, influx height and type, and barite for the weight-up.

Live tool: https://wjwhitmire.github.io/kill-sheet/

The browser tool runs entirely on your device. Nothing you enter is uploaded. The Python library has no runtime dependencies.

> **Training and cross-check aid only.** The rig's approved kill sheet and the well-site supervisor govern. Verify every input against the rig's own records and gauges before relying on any number. This tool does not replace well-control training or certification, and it is not affiliated with IADC, IWCF, any operator, or any app vendor.

It is a clean-room implementation written from the public, standard well-control formulas taught on IADC WellSharp and IWCF surface-stack courses. It refuses impossible inputs with a specific message instead of computing with them.

## Quick start

```
pip install -e .[dev]
pytest -q
kill-sheet --example
kill-sheet examples/vertical_land_well.csv
kill-sheet examples/vertical_land_well.csv --exact --json
```

Python:

```python
from kill_sheet import compute, EXAMPLE_CASE
r = compute(EXAMPLE_CASE)
r["kmw"], r["icp"], r["fcp"], r["schedule"]
```

### Input file

Key/value CSV (comma, tab or semicolon separated; `#` lines and blank lines skipped; an optional `field,value` header; extra columns ignored), or a JSON object with the same keys. See `examples/vertical_land_well.csv`. Numbers in a file use a decimal point and no thousands comma: a row such as `sidpp,1,200` or `omw,10,5` is refused with a message instead of being read as 1 psi or 10 ppg. In the browser form a thousands comma in a box (`1,200`) is accepted; a decimal comma (`10,5`) is refused.

| Key | Meaning | Unit (oilfield / metric) |
|---|---|---|
| `units` | `imperial` (default) or `metric` | |
| `well_md`, `well_tvd` | Bit depth, bit on bottom | ft / m |
| `shoe_md`, `shoe_tvd` | Last casing shoe | ft / m |
| `omw` | Original mud weight | ppg / kg/m3 |
| `lot_emw` | LOT/FIT as equivalent mud weight | ppg / kg/m3 |
| `lot_pressure`, `lot_test_mw` | Or: surface leak-off pressure plus test mud weight | psi, ppg / kPa, kg/m3 |
| `sidpp`, `sicp` | Stabilized shut-in pressures | psi / kPa |
| `pit_gain` | Pit gain | bbl / m3 |
| `scr_pressure`, `kill_rate_spm` | Slow circulating rate pressure at the kill rate, and the kill rate | psi / kPa, spm |
| `pump_output` | Pump output | bbl/stk / m3/stk |
| `surface_line_volume` | Optional, surface lines to the rig floor | bbl / m3 |
| `active_volume` | Optional, active system volume for barite totals | bbl / m3 |
| `deviated` | `yes`/`no`; deviated schedule mode | |
| `kmw_basis` | `rounded` (default) or `exact` | |
| `kmw_round_increment` | Default 0.1 ppg (10 kg/m3 in metric) | ppg / kg/m3 |
| `string,name,length,capacity[,bottom_tvd]` | Drill string sections, surface to bit | ft, bbl/ft / m, m3/m |
| `annulus,name,length,capacity` | Annular sections, bit upward | ft, bbl/ft / m, m3/m |

String and annular lengths must each add to the well MD within 1 ft. In deviated mode every string section needs the TVD at its bottom.

## Method

Oilfield units throughout. Metric input is converted to oilfield units first and results are converted back for display. 0.052 is the hydrostatic constant in psi/ft per ppg (exact value 12/231 = 0.051948; 0.052 is the kill sheet convention).

**Kill mud weight.** Shown exact and rounded up to the next 0.1 ppg (a value within a millionth of an increment above a multiple counts as that multiple, so float noise never adds 0.1 ppg). You choose which one drives FCP, MAASP at KMW, and barite; the default is rounded up. An exact multiple of the increment stays where it is.

```
KMW = OMW + SIDPP / (0.052 x TVD)
```

**Circulating pressures.**

```
ICP = SCR pressure + SIDPP
FCP = SCR pressure x KMW / OMW
```

**Volumes and strokes.** Each section volume is length x capacity.

```
surface to bit    = surface lines + sum(string length x capacity)
bit to shoe       = annular volume over the open hole (well MD - shoe MD), from the bit up
bit to surface    = sum(annular length x capacity)
total circulation = surface to bit + bit to surface
strokes = volume / pump output        minutes = strokes / kill rate
```

**Wait and Weight schedule, vertical.** A straight line from ICP (after the surface lines are filled) to FCP at surface-to-bit strokes, in 10 equal stroke steps:

```
P(i) = ICP - (ICP - FCP) x i / 10,   strokes(i) = lines + (bit - lines) x i / 10
```

**Wait and Weight schedule, deviated.** At the bottom of each drill string section, measured depth `md` and true vertical depth `tvd`, with KMW filling the string down to that point:

```
P = ICP - SIDPP x (tvd / TVD) + (FCP - SCR) x (md / MD)
```

The first term takes away the static overbalance as the KMW column gains vertical height. The second adds the extra friction pressure of the heavier mud in proportion to the string length it fills. The 10-step table is read off straight lines between these section points by stroke count. When each section TVD equals its MD the formula reduces exactly to the vertical straight line for a uniform string (tested). Split long sections at the kickoff point and the end of the build so the points follow the well profile.

The section points are reported for vertical wells too. With a tapered string (DP, HWDP, DC of different capacities) they sit off the straight line; the tool reports the difference and flags it. In deviated mode the tool warns when the straight line would hold more than 5 psi over the section schedule (extra bottom-hole pressure and shoe load) or run below it (underbalanced).

**Driller's method.** First circulation: original mud at the kill rate, drill pipe pressure held at ICP until the influx is out (one full circulation). Shut in; SICP should be close to SIDPP. Second circulation: pump KMW holding casing pressure constant at the shut-in value until KMW reaches the bit (surface-to-bit strokes), then hold drill pipe pressure at FCP until KMW is at surface (bit-to-surface strokes).

**MAASP.** For the current mud weight and for KMW:

```
MAASP = (LOT EMW - MW) x 0.052 x shoe TVD
LOT EMW from a test = test MW + surface leak-off pressure / (0.052 x shoe TVD)
```

**Influx.** Height comes from filling the annulus from the bit upward with the pit gain. When a section fills, the rest spills into the next one up.

```
height   = sum over filled sections, partial section height = remaining volume / capacity
gradient = 0.052 x OMW - (SICP - SIDPP) / height       (psi/ft)
gas < 0.25 psi/ft;  oil, condensate or mixed 0.25 to 0.40;  water > 0.40
```

**Barite.** Barite SG 4.2 (35.0 ppg; 1470 = 35 x 42 gal/bbl), 100 lb sacks:

```
barite (lb per bbl of starting mud) = 1470 x (KMW - OMW) / (35 - KMW)
volume increase per bbl            = (KMW - OMW) / (35 - KMW)
sacks = lb per bbl x active volume / 100, rounded up
```

### Sources

All formulas are the standard public well-control relations found in:

- IADC WellSharp Drilling (surface stack) syllabus and kill sheet; IWCF Drilling Well Control Level 3 and 4 formula sheet (surface BOP kill sheet). KMW, ICP, FCP, strokes, MAASP, influx gradient, barite.
- IADC Drilling Manual, well control chapter. Wait and Weight and Driller's method procedures.
- IWCF surface BOP deviated well kill sheet. The deviated well drill pipe pressure schedule (dynamic pressure at KOP, end of build and section points).
- API RP 59, Recommended Practice for Well Control Operations. Method descriptions.
- Grace, R. D., *Advanced Blowout and Well Control*, Gulf Publishing, 1994; Watson, D., Brittenham, T., Moore, P., *Advanced Well Control*, SPE Textbook Series Vol. 10, 2003. Deviated well step-down (hydrostatic at section TVD, friction by MD fraction) and influx gradient.
- Barite weight-up from the mass balance `V1 x W1 + Vb x 35 = (V1 + Vb) x W2`; same form as API RP 13B and every mud engineering handbook.

## Limits

- Surface BOP stack only. No subsea choke line friction and no riser margin.
- Single-bubble static view. Gas expansion, migration, temperature and compressibility are not modeled. MAASP is a static figure at the shoe and changes as soon as KMW passes the shoe.
- Influx type is indicative only. It is distorted by pit gain error, washed-out hole, a mixed influx, a float in the string, influx inside the string, and inclination near bottom (height here is measured along hole; the tool flags it when MD exceeds TVD by more than 2 percent).
- FCP = SCR x KMW / OMW assumes friction scales with density only. Rheology changes and SCR taken at a different depth or with different mud are not corrected.
- Bit on bottom: string and annular lengths must each add to the well MD within 1 ft.
- Barite figures cover the active volume only. No dilution, no trip margin and no safety margin are added to KMW.
- Metric output is a conversion of the oilfield calculation. The 0.052 constant is kept, so metric results match oilfield kill sheets, not an SI sheet using 0.00981 exactly (difference about 0.1 percent).
- Hard errors (refused): blank or non-numeric values, negative SIDPP, SICP, pit gain or line volume; zero or negative SCR pressure, kill rate or pump output; mud weights outside 5 to 25 ppg; LOT/FIT EMW above 25 ppg; TVD greater than MD; shoe deeper than TD; LOT/FIT EMW at or below OMW; section lengths that do not close on MD; pit gain larger than the annulus; deviated section TVDs that go backward or gain more TVD than length.
- Warnings (computed but flagged): SICP lower than SIDPP; SIDPP zero; KMW at or above the LOT EMW; SICP at or near MAASP; influx gradient below zero or above the mud gradient; influx above the shoe; straight-line schedule above or below the section points.

## Validation

- `tests/test_core.py` works a textbook example by hand in the comments (KMW 10.569 rounded to 10.6 ppg, ICP 850, FCP 486.7 psi, 1,634 strokes to the bit, MAASP 1,466 psi, 515 ft gas influx at 0.121 psi/ft, 48.2 lb/bbl barite) and checks each value. It also covers KMW rounding, schedule endpoints equal to ICP and FCP with monotonic steps, deviated mode reducing to vertical mode when TVD equals MD, a hand-worked J-type well point, influx spill-over across two and three sections, the barite formula and its mass balance, metric/oilfield agreement, and every validation rule above.
- `tests/vectors.json` holds 33 reference cases produced by the Python library. `web/parity.test.mjs` runs the JavaScript core from `web/app.html` against them (relative tolerance 1e-9) and also checks error messages and the file parser.

```
python tests/make_vectors.py && node web/parity.test.mjs
python web/build_pages.py        # writes docs/index.html for GitHub Pages
```

## License

MIT. Copyright 2026 Will Whitmire.
