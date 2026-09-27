/* Checks the worker's numbers against a deliberately naive reference
   implementation. Run with: node scripts/check-model.mjs */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "site", "model-worker.js"), "utf8")
  .replace(/self\.onmessage[\s\S]*$/, "");
const mod = {};
new Function("self", "module", src + "\nmodule.exports = { simulate };")(null, mod);
const simulate = mod.exports.simulate;

// the straightforward version, written to be obviously correct rather than fast
function reference(cfg) {
  const { n, seed, vis, w, eff, reach, noise, cohort } = cfg;
  let a = (seed * 2654435761) >>> 0;
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
  for (let i = 0; i < Math.min(seed, n); i++) amp[i] = 0.35 + rnd() * 0.65;
  for (let i = 0; i < n; i++) if (rnd() < cohort) { nend[i] = vis; day1[i] = true; }
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
      if (rnd() >= noise ? rnd() < q[tg] : rnd() < 0.33) rep[tg] += wgt;
      else nend[tg] += wgt * 0.2;
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

const base = { n: 2000, seed: 20, vis: 3, w: 0.85, eff: 0.06, reach: 0.3, noise: 0.5, cohort: 0.25 };
let bad = 0;

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
  const fast = simulate(cfg, false).last;
  const slow = reference(cfg);
  const row = {
    cfg: Object.entries(cfg).filter(([k]) => k !== "w" || true)
      .map(([k, v]) => `${k}=${v}`).join(" "),
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
}

console.log(bad ? `\n${bad} mismatch(es)` : "\nall within tolerance");
process.exit(bad ? 1 : 0);
