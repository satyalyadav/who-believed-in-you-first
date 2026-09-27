/* The endorsement model, off the main thread.
   Four runs happen per redraw: the one you see, an all-discovery control, and
   two probes at the ends of the visibility slider. Only the first needs a
   series; the other three need one number, so they skip snapshotting entirely. */

"use strict";

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* One run. `series` controls whether the time series is recorded; when it is
   false the run still measures the final state, which is all the control and
   the threshold probes are asked for. */
function simulate(cfg, series) {
  const { n, seed, vis, w, eff, reach, noise, cohort } = cfg;
  const rnd = mulberry32((0x9e3779b9 ^ Math.imul(Math.round(seed * 2654435761), 2654435761)) >>> 0);
  const rep = new Float64Array(n);
  const nend = new Float64Array(n);
  const quality = new Float64Array(n);
  const amp = new Float64Array(n).fill(1);
  const firstDay = new Uint8Array(n);
  for (let i = 0; i < n; i++) quality[i] = rnd();
  // the first arrivals are drawn at random, not on quality
  for (let i = 0; i < (seed < n ? seed : n); i++) amp[i] = 0.35 + rnd() * 0.65;
  let cohortN = 0;
  for (let i = 0; i < n; i++) {
    if (rnd() < cohort) { nend[i] = vis; firstDay[i] = 1; cohortN++; }
  }
  if (!cohortN) { nend[0] = vis; firstDay[0] = 1; cohortN = 1; }

  const out = [];
  let top20 = null;
  let last = null;

  /* nend only ever grows, so once somebody clears the visibility threshold they
     stay visible forever. That makes the set of people who can endorse into the
     network grow monotonically, so it is maintained by appending the names that
     cross the line rather than rescanning all n of them every round. */
  const active = new Int32Array(n);
  let activeN = 0;
  const inActive = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    if (nend[i] >= vis) { active[activeN++] = i; inActive[i] = 1; }
  }
  const crossing = new Int32Array(n);
  let pending = 0;

  for (let t = 0; t < 1000; t++) {
    if (activeN < 3) break;

    const events = n * eff | 0;
    for (let e = 0; e < events; e++) {
      const endorser = active[(rnd() * activeN) | 0];

      // where an endorsement comes from decides everything. A share of the flow
      // is discovery: you get looked at because somebody is browsing. The rest is
      // social proof: you get looked at because you already look worth it.
      let target;
      if (rnd() < reach) {
        target = (rnd() * n) | 0;
      } else {
        // nobody reads the whole list, you glance at a handful of names
        let best = active[(rnd() * activeN) | 0];
        let bv = rep[best];
        for (let g = 0; g < 5; g++) {
          const c = active[(rnd() * activeN) | 0];
          if (rep[c] > bv) { bv = rep[c]; best = c; }
        }
        target = best;
      }

      const sawTheRealThing = rnd() >= noise;
      const hit = sawTheRealThing ? rnd() < quality[target] : rnd() < 0.33;
      const weight = (1 - w + w * (rep[endorser] * 0.5 < 4 ? rep[endorser] * 0.5 : 4)) * amp[endorser];
      if (hit) {
        rep[target] += weight;
      } else {
        nend[target] += weight * 0.2;
        // did that push them over the line? nobody is added twice
        if (!inActive[target] && nend[target] >= vis) { crossing[pending++] = target; inActive[target] = 1; }
      }
    }
    for (let c = 0; c < pending; c++) active[activeN++] = crossing[c];
    pending = 0;

    if (t === 19) top20 = topOf(rep, nend, vis, n, 0.01);
    if (series && t % 5 === 0 && t !== 999) out.push(snapshot(t, rep, nend, vis, n, firstDay, cohortN));
  }

  last = snapshot(999, rep, nend, vis, n, firstDay, cohortN);
  if (series) out.push(last);

  const end = topOf(rep, nend, vis, n, 0.01);
  const keep = top20 && top20.length ? end.filter(i => top20.includes(i)).length / top20.length : null;
  return { series: out, last, lock: keep };
}

/* The top slice of the visible set, by reputation then by endorsements. */
function topOf(rep, nend, vis, n, frac) {
  const idx = [];
  for (let i = 0; i < n; i++) if (nend[i] >= vis) idx.push(i);
  idx.sort((a, b) => (rep[b] + nend[b] * 0.01) - (rep[a] + nend[a] * 0.01));
  return idx.slice(0, Math.max(1, Math.round(idx.length * frac)));
}

/* The shape of the network at one moment. Sorting a typed array rather than
   spreading a Float64Array into a JS array and sorting that is about five times
   faster, which matters because this runs a few hundred times per redraw. */
function snapshot(t, rep, nend, vis, n, firstDay, cohortN) {
  const live = new Float64Array(n);
  let m = 0;
  for (let i = 0; i < n; i++) {
    if (nend[i] >= vis) live[m++] = rep[i] + nend[i] * 0.01;
  }
  const visible = m;
  const sorted = live.subarray(0, m).slice().sort();
  sorted.reverse();
  let total = 0;
  for (let i = 0; i < m; i++) total += sorted[i];
  if (!total) total = 1;

  let c = 0, p50 = m, p90 = m;
  for (let i = 0; i < m; i++) {
    c += sorted[i];
    if (p50 === m && c / total >= 0.5) p50 = i + 1;
    if (c / total >= 0.9) { p90 = i + 1; break; }
  }
  const share = k => {
    let s = 0;
    const m2 = Math.min(k, m);
    for (let i = 0; i < m2; i++) s += sorted[i];
    return s / total;
  };

  // what share of everything accumulated belongs to the people who were already
  // visible on the day the network opened, and how that compares with the share
  // of the network they were to begin with. 1.0 is parity.
  let cohortRep = 0;
  for (let i = 0; i < n; i++) {
    if (firstDay[i] && nend[i] >= vis) cohortRep += rep[i] + nend[i] * 0.01;
  }
  const cohortShare = cohortRep / total;
  return {
    t, visible,
    share: m ? sorted[0] / total : 0,
    p50, p90,
    top1share: share(Math.max(1, Math.round(m * 0.01))),
    top10share: share(Math.max(1, Math.round(m * 0.1))),
    cohortShare,
    capture: cohortShare / (cohortN / n),
    gini: giniOf(sorted, total, m),
  };
}

function giniOf(desc, total, m) {
  if (!m || !total) return 0;
  let cum = 0;
  for (let i = 0; i < m; i++) cum += (i + 1) * desc[m - 1 - i];
  return (2 * cum) / (m * total) - (m + 1) / m;
}

self.onmessage = e => {
  const cfg = e.data;
  const id = cfg.id;
  const main = simulate(cfg, true);
  // ship the curve the reader is looking at before spending time on the numbers
  // the prose quotes
  self.postMessage({
    id, stage: 1,
    series: main.series.map(p => [p.t, p.capture]),
    last: main.last,
    lock: main.lock,
  });
  const ctl = simulate({ ...cfg, reach: 1, seed: cfg.seed + 7919 }, false);
  // the threshold is the dial product teams argue about, so measure it rather
  // than assert it
  const low = simulate({ ...cfg, vis: 1 }, false);
  const high = simulate({ ...cfg, vis: 12 }, false);
  self.postMessage({
    id, stage: 2,
    flat: { capture: ctl.last.capture, visible: ctl.last.visible },
    lockFlat: ctl.lock,
    capLow: low.last.capture,
    capHigh: high.last.capture,
  });
};
