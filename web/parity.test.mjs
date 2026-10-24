// Parity test: run the JavaScript core from web/app.html against tests/vectors.json.
// Usage: node web/parity.test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "app.html"), "utf8");
const m = html.match(/<script id="core">([\s\S]*?)<\/script>/);
if (!m) {
  console.error('Could not find <script id="core"> in app.html');
  process.exit(1);
}
const ctx = vm.createContext({ Math, Number, String, Object, Array, Error, JSON, isFinite });
vm.runInContext(m[1] + "\n;globalThis.KillSheetCore = KillSheetCore;", ctx);
const C = ctx.KillSheetCore;
const vectors = JSON.parse(readFileSync(join(here, "..", "tests", "vectors.json"), "utf8"));

// Relative tolerance 1e-9 with an absolute floor of 1e-9 for values near zero.
const REL = 1e-9;
const ABS = 1e-9;
const near = (a, b) => Math.abs(a - b) <= Math.max(ABS, REL * Math.max(Math.abs(a), Math.abs(b)));

let checks = 0;
let failures = 0;
const fail = (msg) => {
  failures++;
  console.error("FAIL " + msg);
};

// Deep compare: numbers within tolerance, everything else exact, same keys.
function cmp(path, got, want) {
  checks++;
  if (typeof want === "number") {
    if (typeof got !== "number" || !near(got, want)) fail(`${path}: got ${got}, want ${want}`);
    return;
  }
  if (want === null || typeof want !== "object") {
    if (got !== want) fail(`${path}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
    return;
  }
  if (Array.isArray(want)) {
    if (!Array.isArray(got) || got.length !== want.length) {
      fail(`${path}: array length ${got && got.length}, want ${want.length}`);
      return;
    }
    want.forEach((w, i) => cmp(`${path}[${i}]`, got[i], w));
    return;
  }
  if (got === null || typeof got !== "object") {
    fail(`${path}: got ${JSON.stringify(got)}, want object`);
    return;
  }
  const gk = Object.keys(got).sort().join(",");
  const wk = Object.keys(want).sort().join(",");
  if (gk !== wk) fail(`${path}: keys ${gk} != ${wk}`);
  for (const k of Object.keys(want)) cmp(`${path}.${k}`, got[k], want[k]);
}

for (const c of vectors.cases) {
  let res;
  try {
    res = C.compute(JSON.parse(JSON.stringify(c.input)));
  } catch (e) {
    checks++;
    if (!("error" in c)) fail(`${c.name}: unexpected error ${e.message}`);
    else if (!e.isInputError) fail(`${c.name}: non-input error ${e.message}`);
    else if (e.message !== c.error) fail(`${c.name}: error text "${e.message}" != "${c.error}"`);
    continue;
  }
  if ("error" in c) {
    checks++;
    fail(`${c.name}: expected error "${c.error}", got a result`);
    continue;
  }
  cmp(c.name, res, c.result);
}

// Parser parity: the example CSV must parse to the same case as the Python parser
// (checked through compute, which the vectors pin), and bad inputs must be rejected.
const exampleCsv = readFileSync(join(here, "..", "examples", "vertical_land_well.csv"), "utf8");
const parsed = C.parseText(exampleCsv);
const ex = vectors.cases.find((c) => c.name === "example");
cmp("parseText(example csv)", C.compute(parsed), ex.result);
checks++;
if (parsed.string.length !== 3 || parsed.annulus.length !== 3) fail("parseText example section counts");

const okInputs = [
  "field\tvalue\nMD\t10000\tft\nTVD\t10000\nshoe_md\t6000\nshoe_tvd\t6000\nMW\t9.8\nLOT\t14.5\nsidpp\t400\nsicp\t600\ngain\t15\nSCR\t450\nspm\t30\npump\t0.102\nstring\tDP\t9400\t0.01776\nstring\tDC\t600\t0.00768\nannulus\tAll\t10000\t0.05\n",
];
for (const t of okInputs) {
  checks++;
  try {
    const r = C.compute(C.parseText(t));
    if (!near(r.icp, 850)) fail("ok input ICP");
  } catch (e) {
    fail(`ok input rejected: ${e.message}`);
  }
}
for (const [v, want] of [[9.8000001, 9.8], [9.80001, 9.9], [10.569, 10.6], [10.6, 10.6]]) {
  checks++;
  if (C.kmwRoundUp(v, 0.1) !== want) fail(`kmwRoundUp(${v}) = ${C.kmwRoundUp(v, 0.1)}, want ${want}`);
}
const badInputs = [
  "", "   \n\n", "well_md,abc\nstring,a,1,1\nannulus,b,1,1", "well_md,NaN\nstring,a,1,1\nannulus,b,1,1",
  "foo,1\n", "well_md,1\nwell_md,2\n", "well_md,1\nannulus,b,1,1\n", "well_md,1\nstring,a,1\n",
  "[1,2", "[1,2]", "deviated,maybe\n",
  "sidpp,1,200\nstring,a,1,1\nannulus,b,1,1\n", "omw,10,5\nstring,a,1,1\nannulus,b,1,1\n",
];
for (const t of badInputs) {
  checks++;
  try {
    C.parseText(t);
    fail(`parseText should reject ${JSON.stringify(t)}`);
  } catch (e) {
    if (!e.isInputError) fail(`parseText ${JSON.stringify(t)} threw non-input error ${e.message}`);
  }
}

if (failures) {
  console.error(`${failures} of ${checks} checks failed`);
  process.exit(1);
}
console.log(`parity ok: ${checks} checks across ${vectors.cases.length} vector cases (tolerance rel 1e-9, abs 1e-9)`);
