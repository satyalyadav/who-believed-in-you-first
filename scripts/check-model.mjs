/* Checks the worker's numbers against a deliberately naive reference
   implementation. Run with: node scripts/check-model.mjs */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const workerPath = join(here, "..", "site", "model-worker.js");
const src = readFileSync(workerPath, "utf8")
  .replace(/self\.onmessage[\s\S]*$/, "");
const mod = {};
new Function("self", "module", src + "\nmodule.exports = { simulate, simulateControl: typeof simulateControl === 'function' ? simulateControl : null };")(null, mod);
const simulate = mod.exports.simulate;
const simulateControl = mod.exports.simulateControl;
const appSrc = readFileSync(join(here, "..", "site", "app.js"), "utf8");

// the straightforward version, written to be obviously correct rather than fast
function reference(cfg) {
  const { n, seed, boost, vis, w, eff, reach, noise, cohort } = cfg;
  let a = (0x9e3779b9 ^ Math.imul(Math.round(seed * 2654435761), 2654435761)) >>> 0;
  const rnd = () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const rep = new Array(n).fill(0);
  const nend = new Array(n).fill(0);
  const q = new Array(n).fill(0);
  const amp = new Array(n).fill(1);
  const day1 = new Array(n).fill(false);
  for (let i = 0; i < n; i++) q[i] = rnd();
  for (let i = 0; i < n; i++) if (rnd() < cohort) { nend[i] = vis; day1[i] = true; }
  if (!day1.some(Boolean)) { nend[0] = vis; day1[0] = true; }
  for (let i = 0; i < n; i++) if (day1[i]) amp[i] = boost;
  for (let t = 0; t < 1000; t++) {
    const active = [];
    for (let i = 0; i < n; i++) if (nend[i] >= vis) active.push(i);
    if (active.length < 3) break;
    for (let e = 0; e < Math.floor(n * eff); e++) {
      const en = active[Math.floor(rnd() * active.length)];
      let tg;
      if (rnd() < reach) tg = Math.floor(rnd() * n);
      else {
        let best = active[Math.floor(rnd() * active.length)];
        for (let g = 0; g < 5; g++) {
          const c = active[Math.floor(rnd() * active.length)];
          if (rep[c] > rep[best]) best = c;
        }
        tg = best;
      }
      const wgt = (1 - w + w * Math.min(4, rep[en] * 0.5)) * amp[en];
      nend[tg]++;
      if (rnd() >= noise ? rnd() < q[tg] : rnd() < 0.33) rep[tg] += wgt;
    }
  }
  const live = [];
  for (let i = 0; i < n; i++) if (nend[i] >= vis) live.push(rep[i] + nend[i] * 0.01);
  live.sort((x, y) => y - x);
  const total = live.reduce((x, y) => x + y, 0) || 1;
  let cr = 0, cn = 0;
  for (let i = 0; i < n; i++) if (day1[i] && nend[i] >= vis) { cr += rep[i] + nend[i] * 0.01; cn = cn; }
  for (let i = 0; i < n; i++) if (day1[i]) cn++;
  return {
    visible: live.length,
    capture: (cr / total) / (cn / n),
    cohort: cr / total,
  };
}

let bad = 0;

function invariant(label, ok) {
  if (!ok) bad++;
  console.log(`${ok ? "ok  " : "FAIL"}  invariant: ${label}`);
}

const base = { n: 2000, seed: 20, boost: 1.5, vis: 3, w: 0.85, eff: 0.06,
               reach: 0.3, noise: 0.5, cohort: 0.25 };

// Exact semantic checks for the initial draw, cohort boost, visibility counts,
// and the comparison run. These do not depend on the approximate reference
// comparison below.
const semanticCfg = { ...base, n: 40, seed: 17, eff: 0.2, cohort: 0.35 };
const boostedRun = simulate(semanticCfg, false, null, true);
const neutralRun = simulate({ ...semanticCfg, boost: 1 }, false, null, true);
const controlRun = simulateControl ? simulateControl(semanticCfg, true) : null;
const initial = boostedRun.diagnostics?.initial;
const same = (a, b) => Array.isArray(a) && Array.isArray(b) &&
  a.length === b.length && a.every((value, i) => value === b[i]);

const boostAssignedOnlyToDayOne = !!initial &&
  initial.firstDay.some(Boolean) &&
  initial.amplification.every((value, i) =>
    value === (initial.firstDay[i] ? semanticCfg.boost : 1));
invariant("boost is above one and assigned only to day-one cohort members",
  semanticCfg.boost > 1 && boostAssignedOnlyToDayOne);
invariant("changing boost leaves initial quality and cohort draws unchanged",
  !!initial && !!neutralRun.diagnostics?.initial &&
  same(initial.quality, neutralRun.diagnostics.initial.quality) &&
  same(initial.firstDay, neutralRun.diagnostics.initial.firstDay));
invariant("all-discovery control reuses initial quality and cohort draws",
  !!initial && !!controlRun?.diagnostics?.initial &&
  same(initial.quality, controlRun.diagnostics.initial.quality) &&
  same(initial.firstDay, controlRun.diagnostics.initial.firstDay));

const eventCfg = { ...semanticCfg, n: 40, cohort: 1, noise: 0.5 };
const eventRun = simulate(eventCfg, false, null, true);
const quietRun = simulate({ ...eventCfg, noise: 0 }, false, null, true);
const noisyRun = simulate({ ...eventCfg, noise: 1 }, false, null, true);
const eventDebug = eventRun.diagnostics;
const initialCount = eventDebug?.initial?.firstDay.filter(Boolean).length;
const eventN = Math.floor(eventCfg.n * eventCfg.eff);
const countTotal = eventDebug?.nend.reduce((sum, value) => sum + value, 0);
const exactVisibilityCount = !!eventDebug &&
  countTotal === initialCount * eventCfg.vis + eventRun.last.t * eventN &&
  eventDebug.nend.every(Number.isInteger);
invariant("every modeled endorsement increments visibility by exactly one",
  exactVisibilityCount);
const repTotal = eventDebug?.rep.reduce((sum, value) => sum + value, 0);
invariant("successful endorsement weights sum to the reputation added",
  !!eventDebug && eventDebug.successCount > 0 && eventDebug.failureCount > 0 &&
  Math.abs(repTotal - eventDebug.successfulWeight) <=
    Number.EPSILON * eventDebug.successCount * eventDebug.successfulWeight * 2);
invariant("noise changes reputation outcomes but never the total endorsement count",
  quietRun.diagnostics?.nend.reduce((sum, value) => sum + value, 0) === countTotal &&
  noisyRun.diagnostics?.nend.reduce((sum, value) => sum + value, 0) === countTotal &&
  !same(quietRun.diagnostics?.rep, noisyRun.diagnostics?.rep));
invariant("reported starting cohort count and share match the actual draw",
  !!eventDebug && eventRun.last.cohortCount === initialCount &&
  eventRun.last.cohortFraction === initialCount / eventCfg.n &&
  eventRun.last.capture === eventRun.last.cohortShare / (initialCount / eventCfg.n));

const verdict = appSrc.match(/function verdictHtml\([\s\S]*?\n\}/)?.[0] || "";
invariant("verdict uses measured cohort count and fraction",
  /last\.cohortCount/.test(verdict) && /last\.cohortFraction/.test(verdict) &&
  !/Math\.round\(sim\.cohort\s*\*\s*sim\.n\)/.test(verdict));

for (const cfg of [
  base,
  { ...base, vis: 1 },
  { ...base, vis: 12 },
  { ...base, reach: 1 },
  { ...base, cohort: 0.02 },
  { ...base, cohort: 0.6 },
  { ...base, w: 0 },
  { ...base, n: 900, eff: 0.2 },
]) {
  const run = simulate(cfg, cfg === base);
  const fast = run.last;
  const slow = reference(cfg);
  const row = {
    cfg: Object.entries(cfg).map(([k, v]) => `${k}=${v}`).join(" "),
    fastVisible: fast.visible, refVisible: slow.visible,
    fastCapture: +fast.capture.toFixed(4), refCapture: +slow.capture.toFixed(4),
  };
  // the two implementations order the active list differently, which consumes
  // the shared RNG stream in a different order, so they are two independent
  // draws from the same distribution rather than the same draw. Compare the
  // shape with a relative tolerance.
  const vOK = Math.abs(fast.visible - slow.visible) / Math.max(1, slow.visible) < 0.06;
  const cOK = Math.abs(fast.capture - slow.capture) / Math.max(1, slow.capture) < 0.20;
  if (!vOK || !cOK) { bad++; row.FAIL = `visible ${vOK} capture ${cOK}`; }
  console.log((vOK && cOK ? "ok  " : "FAIL") + "  " + row.cfg);
  console.log(`      visible ${row.fastVisible} vs ${row.refVisible}   ` +
              `capture ${row.fastCapture} vs ${row.refCapture}`);
  if (cfg === base) {
    const first = run.series[0]?.t;
    const last = run.series.at(-1)?.t;
    const roundsOK = fast.t === 1000 && first === 0 && last === 1000;
    if (!roundsOK) bad++;
    console.log((roundsOK ? "ok  " : "FAIL") +
      `  completed-round labels ${first}..${last}; final reported ${fast.t}`);
  }
}

console.log(bad ? `\n${bad} mismatch(es)` : "\nall within tolerance");
process.exit(bad ? 1 : 0);
