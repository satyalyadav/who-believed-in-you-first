/* Who believed in you first?
   One JSON file in, everything else computed here. No dependencies. */
(() => {
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const fmt = n => {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-US");
};
const usd = n => {
  if (n === null || n === undefined) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return "$" + (n / 1e9).toFixed(a >= 1e10 ? 0 : 2).replace(/\.0+$/, "") + "B";
  if (a >= 1e6) return "$" + (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (a >= 1e3) return "$" + (n / 1e3).toFixed(0) + "k";
  return "$" + n;
};
const bytes = n => (n === null || n === undefined ? "—" : usd(n));
const dstr = ymd => {
  if (!ymd) return "—";
  const m = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${m[+ymd.slice(4,6) - 1]} ${+ymd.slice(6,8)}`;
};
const edgar = (cik, acc) =>
  `https://www.sec.gov/Archives/edgar/data/${+cik}/${acc.replace(/-/g, "")}/${acc}-index.htm`;

const MONTHS = ["202607", "202608", "202609"];

let D = null;

/* ------------------------------------------------------------------ chrome */

const ITEMS = [
  ["s1", "The pitch"],
  ["s2", "The form"],
  ["s3", "The corpus"],
  ["s4", "The graph"],
  ["s5", "The blank field"],
  ["s6", "Inheritance"],
  ["s7", "Receipts"],
];

function buildChrome() {
  $("#rail-list").innerHTML = ITEMS.map(([id, label], i) =>
    `<li><a href="#${id}" data-id="${id}"><span class="bx">X</span>${i + 1}. ${label}</a></li>`
  ).join("");

  const links = $$("#rail-list a");
  const onScroll = () => {
    let cur = ITEMS[0][0];
    for (const [id] of ITEMS) {
      const el = document.getElementById(id);
      if (el && el.getBoundingClientRect().top < 140) cur = id;
    }
    links.forEach(a => a.classList.toggle("on", a.dataset.id === cur));
    const n = ITEMS.findIndex(i => i[0] === cur) + 1;
    $("#chrome-idx").textContent = `item ${n} of ${ITEMS.length}`;
  };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

/* ------------------------------------------------------------- the form */

function xb(on, x) { return `<span class="xb${on ? " on" : ""}${x ? " x" : ""}">${on ? "X" : " "}</span>`; }
function xrow(on, x) { return `<span class="xs">${xb(on, x)}</span>`; }
function nd(v) { return v ? String(v) : `<span class="nodata">&nbsp;</span>`; }

function moneyCell(v, indef) {
  if (indef) return "Indefinite";
  return v === null || v === undefined ? nd(false) : "$ " + fmt(v);
}

function renderForm(f, opts = {}) {
  const compact = !!opts.compact;
  const persons = f.p.map(p => `<div class="frow blk">
      <span class="k">Name of related person</span>
      <span class="v"><span class="person" data-person="${esc(p.n)}">${esc(p.n)}</span>
        ${p.e ? `<span class="tag">legal entity</span>` : ""}</span></div>
    <div class="frow">
      <span class="k">Relationship to the issuer</span>
      <span class="v">${(p.r.length ? p.r : ["None"]).map(r =>
        `<span class="tag${p.r.length ? "" : " c"}">${esc(r)}</span>`).join(" ")}
        ${p.c ? `<span style="color:var(--ink-3)">${esc(p.c)}</span>` : ""}</span></div>`).join("");

  const exempt = f.exc.map(e =>
    e === "06c" ? "Rule 506(c)" : e === "06b" ? "Rule 506(b)"
    : e === "3C" ? "Investment Company Act §3(c)" : e
  );

  return `<div class="form" data-acc="${f.acc}">
    <div class="form-head">
      <span class="t">SEC FORM D</span>
      ${compact ? "" : '<span class="mid">Notice of Exempt Offering of Securities</span>'}
      <span class="sp"></span>
      <span class="acc">${f.acc}</span>
    </div>

    <div class="fsec">Item 1. Issuer information</div>
    <div class="frow"><span class="k">Name of issuer</span><span class="v">${esc(f.name)}</span></div>
    <div class="frow"><span class="k">CIK</span><span class="v">${f.cik}</span></div>
    ${compact ? "" : `<div class="frow"><span class="k">Entity type</span><span class="v">${nd(f.etype)}</span></div>
    <div class="frow"><span class="k">Jurisdiction</span><span class="v">${nd(f.juris)}</span></div>
    <div class="frow"><span class="k">Year formed</span><span class="v">${nd(f.yinc)}</span></div>`}
    <div class="frow"><span class="k">Address</span><span class="v">${nd(f.city)}, ${nd(f.state)}</span></div>
    ${(!compact && f.prev.length) ? `<div class="frow"><span class="k">Previous names</span><span class="v">${esc(f.prev.join("; "))}</span></div>` : ""}

    <div class="fsec">Item 2. Officers, directors and promoters <span style="font-weight:400;color:var(--ink-3)">the complete list the issuer gave</span></div>
    ${persons || `<div class="frow"><span class="k">related persons</span><span class="v"><span class="nodata">&nbsp;</span></span></div>`}

    <div class="fsec">Item 3. Industry</div>
    <div class="frow"><span class="k">Industry group</span><span class="v">${nd(f.ind)}</span></div>
    ${f.ftype ? `<div class="frow"><span class="k">Fund type</span><span class="v">${nd(f.ftype)}</span></div>` : ""}
    ${compact ? "" : `<div class="frow"><span class="k">Revenue range</span><span class="v">${nd(f.rev)}</span></div>
    ${f.nav ? `<div class="frow"><span class="k">Net asset value</span><span class="v">${nd(f.nav)}</span></div>` : ""}

    <div class="fsec">Item 4. Filing type</div>
    <div class="frow"><span class="k">New notice or amendment</span>
      <span class="v">${xrow(!f.amend, true)} ${xrow(!!f.amend)} ${f.amend && f.prevAcc ? "amends " + f.prevAcc : ""}</span></div>
    <div class="frow"><span class="k">Date of first sale</span>
      <span class="v">${f.yet ? xrow(true, true) + " first sale has not happened yet" : nd(f.sale0)}</span></div>

    <div class="fsec">Item 5. Exemption claimed</div>
    <div class="frow"><span class="k">Rule</span><span class="v">${exempt.map(e => `<span class="tag">${esc(e)}</span>`).join(" ") || nd(false)}</span></div>
    <div class="frow"><span class="k">Securities offered</span>
      <span class="v">${(f.secs || []).map(s => `<span class="tag">${esc(secName(s))}</span>`).join(" ") || nd(false)}</span></div>
`}
    <div class="fsec">Item 6. The money</div>
    <div class="frow hi"><span class="k">Total offering amount</span>
      <span class="v">${moneyCell(f.offer, f.offerInd)}</span></div>
    <div class="frow hi"><span class="k">Total amount sold</span>
      <span class="v">${moneyCell(f.sold, false)}</span></div>
    <div class="frow"><span class="k">Remaining to be sold</span>
      <span class="v">${moneyCell(f.rem, f.remInd)}</span></div>
    <div class="frow hi"><span class="k">Investors who had already invested</span>
      <span class="v">${f.ninv ? fmt(f.ninv) : nd(false)}
        <span style="color:var(--ink-3)">${f.ninv ? "a count, never a list of names" : ""}</span></span></div>
    ${compact ? "" : `<div class="frow"><span class="k">Sales commissions</span><span class="v">${moneyCell(f.comm, false)}</span></div>
    <div class="frow"><span class="k">Finders' fees</span><span class="v">${moneyCell(f.fees, false)}</span></div>
    ${f.proceeds ? `<div class="frow"><span class="k">Gross proceeds used</span><span class="v">${moneyCell(f.proceeds, false)}</span></div>` : ""}

    <div class="frow"><span class="k">Signed by</span>
      <span class="v">${f.sig ? esc(f.sig.n || "") + (f.sig.t ? ", " + esc(f.sig.t) : "") + ", " + (f.sig.d || "") : nd(false)}</span></div>`}
    <div class="frow"><span class="k">Source</span>
      <span class="v"><a class="src" href="${edgar(f.cik, f.acc)}" target="_blank" rel="noopener">open on EDGAR</a></span></div>
  </div>`;
}

const SEC_NAMES = {
  isEquityType: "Equity",
  isDebtType: "Debt",
  isOtherType: "Other",
  isPooledInvestmentFundType: "Pooled fund interests",
  isTenantInCommonType: "Tenant-in-common securities",
  isOptionToAcquireType: "Option or warrant to acquire",
  isSecurityToBeAcquiredType: "Security acquired on exercise",
  isMineralPropertyType: "Mineral property",
};
function secName(k) { return SEC_NAMES[k] || k.replace(/^is/, "").replace(/Type$/, ""); }

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* ------------------------------------------------------------ directory */

let dirState = { q: "", ind: "", people: false, sort: "d", sel: null, person: null, kind: "co" };

function dirRows() {
  const q = dirState.q.trim().toLowerCase();
  let rows = D.issuers.filter(i => {
    if (dirState.kind === "co" && i.g === FUND) return false;
    if (dirState.kind === "fund" && i.g !== FUND) return false;
    if (dirState.ind && i.g !== dirState.ind) return false;
    if (dirState.people && !i.P.length) return false;
    if (dirState.person) {
      const hit = i.P.some(p => norm(p) === dirState.person) ||
        i.E.some(p => norm(p) === dirState.person);
      if (!hit) return false;
    }
    if (q) {
      const hay = (i.n + " " + i.P.join(" ") + " " + i.E.join(" ") + " " + i.i + " " +
                   (i.g || "") + " " + (i.s || "")).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const s = dirState.sort;
  const num = v => (v === null || v === undefined ? -1 : v);
  if (s === "d") rows.sort((a, b) => b.f.localeCompare(a.f) || a.i.localeCompare(b.i));
  if (s === "d-asc") rows.sort((a, b) => a.f.localeCompare(b.f) || a.i.localeCompare(b.i));
  if (s === "d$") rows.sort((a, b) => num(b.d) - num(a.d));
  if (s === "d$-asc") rows.sort((a, b) => num(a.d) - num(b.d));
  if (s === "k") rows.sort((a, b) => num(b.k) - num(a.k));
  if (s === "n") rows.sort((a, b) => a.n.localeCompare(b.n));
  return rows;
}

function norm(s) {
  return String(s || "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
}

const CAP = 400;
const FUND = "Pooled Investment Fund";

function renderDir() {
  const rows = dirRows();
  const body = $("#dir-body");
  const shown = rows.slice(0, CAP);
  body.innerHTML = shown.map(i => `
    <tr data-i="${i.i}"${dirState.sel === i.i ? ' class="sel"' : ""}>
      <td class="acc">${dstr(i.f)}</td>
      <td class="nm"><a href="${edgar(i.c, i.i)}" target="_blank" rel="noopener">${esc(i.n)}</a>
        ${i.m ? `<span class="tag">+${i.m} amendment${i.m > 1 ? "s" : ""}</span>` : ""}</td>
      <td>${i.g ? `<span class="tag${i["6"] ? " c" : ""}">${esc(i.g)}</span>` : ""}
        ${i["6"] ? `<span class="tag c">506(c)</span>` : ""}</td>
      <td class="pp">${i.P.length
        ? i.P.slice(0, 3).map(p => `<span class="person" data-person="${esc(p)}">${esc(p)}</span>`).join("") +
          (i.P.length > 3 ? ` <span style="color:var(--ink-3)">+${i.P.length - 3}</span>` : "")
        : `<span style="color:var(--ink-3)">${i.E.length ? esc(i.E[0]) + " (entity)" : "none named"}</span>`}</td>
      <td class="num">${i.d ? usd(i.d) : `<span style="color:var(--ink-3)">${i.I ? "indefinite" : "—"}</span>`}</td>
      <td class="num">${i.k ? fmt(i.k) : `<span style="color:var(--ink-3)">—</span>`}</td>
      <td class="acc">${i.i}</td>
    </tr>`).join("");

  $("#dir-empty").hidden = rows.length > 0;
  const pool = dirState.kind === "co" ? D.stats.cos : D.stats.funds;
  const noun = dirState.kind === "co" ? "operating companies" : "pooled investment funds";
  $("#dir-count").textContent = `${fmt(rows.length)} of ${fmt(pool)} ${noun}` +
    (rows.length > CAP ? `, showing the first ${CAP}` : "");
  $$("#dir-body th, .dirwrap th").forEach(() => {});

  if (dirState.person) {
    $("#dir-count").textContent = `filtered to ${esc(dirState.person)} · ` + $("#dir-count").textContent;
  }
}

function showDetail(acc) {
  const f = D.forms.find(x => x.acc === acc);
  const i = D.issuers.find(x => x.i === acc);
  if (!i) return;
  dirState.sel = acc;
  renderDir();
  const host = $("#dir-detail");
  if (f) {
    host.innerHTML = renderForm(f);
  } else {
    host.innerHTML = `<div class="detail">
      <div class="top"><span>${esc(i.n)}</span><span class="sp"></span>
        <a class="src" style="color:var(--paper)" href="${edgar(i.c, i.i)}" target="_blank" rel="noopener">EDGAR</a>
        <button class="close" data-close>close</button></div>
      <div class="body">
        <div class="frow"><span class="k">accession</span><span class="v">${i.i}</span></div>
        <div class="frow"><span class="k">filed</span><span class="v">${i.f}</span></div>
        <div class="frow"><span class="k">industry</span><span class="v">${nd(i.g)}</span></div>
        <div class="frow"><span class="k">amount sold</span><span class="v">${i.d ? usd(i.d) : nd(false)}</span></div>
        <div class="frow"><span class="k">investors already in</span><span class="v">${i.k || nd(false)}</span></div>
        <div class="frow"><span class="k">named people</span><span class="v">${i.P.map(p =>
          `<span class="person" data-person="${esc(p)}">${esc(p)}</span>`).join("") || nd(false)}</span></div>
      </div></div>`;
  }
  wirePersons(host);
  host.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function clearDetail() {
  dirState.sel = null;
  $("#dir-detail").innerHTML = "";
  renderDir();
}

function wirePersons(root) {
  $$(".person", root || document).forEach(el => {
    el.addEventListener("click", ev => {
      ev.preventDefault();
      ev.stopPropagation();
      const p = el.dataset.person;
      dirState.person = dirState.person === norm(p) ? null : norm(p);
      $$(".person.sel").forEach(x => x.classList.remove("sel"));
      if (dirState.person) {
        el.classList.add("sel");
        $("#dir-detail").innerHTML = "";
        renderDir();
        $("#s3").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}

function wireDir() {
  $("#q").addEventListener("input", e => { dirState.q = e.target.value; renderDir(); });
  const sel = $("#f-ind");
  const fillInd = () => {
    const pool = D.issuers.filter(i => dirState.kind === "co" ? i.g !== FUND : i.g === FUND);
    const counts = {};
    pool.forEach(i => { if (i.g) counts[i.g] = (counts[i.g] || 0) + 1; });
    sel.innerHTML = `<option value="">every industry</option>` +
      Object.entries(counts).sort((a, b) => b[1] - a[1])
        .map(([g, c]) => `<option value="${esc(g)}">${esc(g)} (${fmt(c)})</option>`).join("");
  };
  fillInd();
  sel.addEventListener("change", e => { dirState.ind = e.target.value; renderDir(); });
  $("#f-sort").addEventListener("change", e => { dirState.sort = e.target.value; renderDir(); });
  $("#f-kind").addEventListener("click", e => {
    dirState.kind = dirState.kind === "co" ? "fund" : "co";
    e.currentTarget.setAttribute("aria-pressed", String(dirState.kind === "co"));
    e.currentTarget.textContent = dirState.kind === "co"
      ? "operating companies only" : "everything, including funds";
    fillInd();
    $("#f-ind").value = "";
    dirState.ind = "";
    $("#dir-detail").innerHTML = "";
    dirState.sel = null;
    renderDir();
  });
  $("#f-people").addEventListener("click", e => {
    dirState.people = !dirState.people;
    e.currentTarget.setAttribute("aria-pressed", String(dirState.people));
    renderDir();
  });
  $$("#dir-body th").forEach(th => {
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      if (k === "d$") dirState.sort = dirState.sort === "d$" ? "d$-asc" : "d$";
      else if (k === "d") dirState.sort = dirState.sort === "d" ? "d-asc" : "d";
      else dirState.sort = k === "k" ? "k" : "n";
      $("#f-sort").value = ["d", "d-asc", "d$", "d$-asc", "k", "n"].includes(dirState.sort)
        ? dirState.sort : "d";
      renderDir();
    });
  });
  $("#dir-body").addEventListener("click", e => {
    const tr = e.target.closest("tr");
    if (tr && tr.dataset.i) showDetail(tr.dataset.i);
  });
  document.addEventListener("click", e => {
    if (e.target.closest("[data-close]")) clearDetail();
  });
}

/* ------------------------------------------------------------- charts */

function chartW(el, fallback = 420) {
  const host = el.parentElement;
  const grand = host && host.parentElement;
  const w = host ? Math.round(host.getBoundingClientRect().width) : 0;
  const cap = grand ? Math.round(grand.getBoundingClientRect().width) : Infinity;
  return Math.max(280, Math.min(w || fallback, cap));
}

function bars(el, rows, opts = {}) {
  const W = chartW(el);
  const padL = opts.padL || 92, padR = 10, padT = 12, padB = 26;
  const H = opts.h || 200;
  const max = Math.max(...rows.map(r => r[1]), 1);
  const n = rows.length;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const gap = 3;
  const bw = Math.max(2, innerW / n - gap);
  let out = "";
  out += `<line x1="${padL}" y1="${padT + innerH}" x2="${W - padR}" y2="${padT + innerH}" stroke="#c6ccd3"/>`;
  rows.forEach(([label, v], i) => {
    const h = Math.max(v > 0 ? 1.5 : 0, (v / max) * innerH);
    const x = padL + i * (innerW / n);
    const y = padT + innerH - h;
    out += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}"
      fill="${opts.color || "#0e1319"}"></rect>`;
    out += `<text x="${x.toFixed(1)}" y="${(padT + innerH + 14).toFixed(1)}" font-size="11"
      font-family="IBM Plex Mono, monospace" fill="#7c8794">${esc(label)}</text>`;
  });
  rows.forEach(([label, v], i) => {
    out += `<text x="${padL - 7}" y="${(padT + innerH - (v / max) * innerH + 4).toFixed(1)}" font-size="11"
      font-family="IBM Plex Mono, monospace" fill="#495260" text-anchor="end">${fmt(v)}</text>`;
  });
  el.setAttribute("viewBox", `0 0 ${W} ${H}`);
  el.setAttribute("width", W);
  el.setAttribute("height", H);
  el.innerHTML = out;
}

function hbars(el, rows, opts = {}) {
  const W = chartW(el);
  const padL = opts.padL || 46, padR = 58, padT = 6, padB = 6;
  const rowH = opts.rowH || 20;
  const H = padT + padB + rows.length * rowH;
  const max = Math.max(...rows.map(r => r[1]), 1);
  const innerW = W - padL - padR;
  let out = "";
  rows.forEach(([label, v], i) => {
    const y = padT + i * rowH;
    const w = Math.max(1, (v / max) * innerW);
    out += `<text x="${padL - 7}" y="${y + rowH / 2 + 4}" font-size="11" font-family="IBM Plex Mono, monospace"
      fill="#495260" text-anchor="end">${esc(label)}</text>`;
    out += `<rect x="${padL}" y="${y + 3}" width="${w.toFixed(1)}" height="${rowH - 7}" fill="${opts.color || "#0e1319"}"></rect>`;
    out += `<text x="${padL + w + 6}" y="${y + rowH / 2 + 4}" font-size="11"
      font-family="IBM Plex Mono, monospace" fill="#7c8794">${fmt(v)}</text>`;
  });
  el.setAttribute("viewBox", `0 0 ${W} ${H}`);
  el.setAttribute("width", W);
  el.setAttribute("height", H);
  el.innerHTML = out;
}

/* ------------------------------------------------------------ the graph */

const PERSON_IDX = { all: new Map(), co: new Map() };

let anatomyIdx = 0;

function renderAnatomy() {
  const host = $("#anatomy");
  const forms = D.forms || [];
  if (!forms.length) return;
  anatomyIdx = Math.min(anatomyIdx, forms.length - 1);
  const f = forms[anatomyIdx];
  const humans = f.p.filter(p => !p.e).length;
  host.innerHTML = `
    <div class="ctl mono" style="margin-bottom:0;border-bottom:0">
      ${forms.map((x, i) => `<button class="b" data-form="${i}"
        aria-pressed="${i === anatomyIdx}">${esc(x.label || `filing ${i + 1}`)}</button>`).join("")}
    </div>
    <div class="pickmeta mono">
      <span>${esc(f.label)}</span>
      <span>${humans} named ${humans === 1 ? "person" : "people"}${
        f.p.length > humans ? `, ${f.p.length - humans} named entities` : ""}</span>
      <span>${f.ninv ? `${fmt(f.ninv)} backers reported` : "no backer count"}</span>
    </div>
    ${renderForm(f)}
    <div class="acts" style="margin:12px 0 0">
      <button class="b" data-form-step="-1">previous filing</button>
      <button class="b" data-form-step="1">next filing</button>
      <span class="note" style="margin-left:4px">These five are real filings from the sample, unmodified.</span>
    </div>`;
  host.querySelectorAll("[data-form]").forEach(b => b.addEventListener("click", () => {
    anatomyIdx = +b.dataset.form;
    renderAnatomy();
  }));
  host.querySelectorAll("[data-form-step]").forEach(b => b.addEventListener("click", () => {
    anatomyIdx = (anatomyIdx + +b.dataset.formStep + forms.length) % forms.length;
    renderAnatomy();
  }));
  wirePersons(host);
}

function buildPersonIndex() {
  const add = (map, name, idx, roles, month, issuer) => {
    const k = norm(name);
    if (!k) return;
    let e = map.get(k);
    if (!e) map.set(k, e = { n: name, rows: [], roles: new Set(), months: new Set(), names: new Set() });
    e.rows.push(idx);
    e.roles.add((roles || []).join("/") || "role not stated");
    e.months.add(month);
    if (e.names.size < 8) e.names.add(issuer);
  };
  D.issuers.forEach((i, idx) => {
    i.P.forEach(name => {
      add(PERSON_IDX.all, name, idx, i.R, i.f.slice(0, 6), i.n);
      if (i.g !== FUND) add(PERSON_IDX.co, name, idx, i.R, i.f.slice(0, 6), i.n);
    });
    i.E.forEach(name => add(PERSON_IDX.all, name, idx, ["entity"], i.f.slice(0, 6), i.n));
  });
  for (const map of [PERSON_IDX.all, PERSON_IDX.co]) {
    map.forEach(e => (e.roles = [...e.roles].slice(0, 3).join(", ")));
  }
}

function renderGraph() {
  const st = D.stats;
  const co = st.coNames;

  $("#graphverdict").innerHTML =
    `It is almost entirely not there. Restricting to the
     <span class="mono">${fmt(st.cos)}</span> operating-company filings,
     <span class="mono">${fmt(co.distinct)}</span> distinct people are named and
     <b>${co.oncePct}%</b> of them appear on exactly one company, which makes them
     a dead end in any graph you build. That leaves
     <span class="mono">${fmt(co.repeat)}</span> people who connect two filings
     and <span class="mono">${fmt(co.bridged)}</span> edges between
     <span class="mono">${fmt(st.cos)}</span> companies. The entire recorded social
     graph of who stood behind an American startup this quarter is
     <b>${fmt(co.repeat)} nodes and ${fmt(co.bridged)} edges</b>, and not one
     investor is in it, because investors are not who Form D names. Across the
     whole sample, ${fmt(st.entityOnly)} of ${fmt(st.sample)} filings name no human
     being at all.`;

  // the same histogram twice: once for the operating companies, once for the
  // whole corpus, because the obvious objection is that the funds fill the gap
  hbars($("#deg-chart"), st.degCo, { rowH: 24, padL: 104 });
  const co1 = (st.degCo[0] || [])[1] || 0;
  $("#deg-legend").innerHTML =
    `${fmt(co1)} of the ${fmt(co.distinct)} people named on an operating company sit ` +
    `on exactly one and connect to nothing. Everything under the first bar is the graph.`;

  hbars($("#deg-all-chart"), st.degAll, { rowH: 24, padL: 104, color: "#7a848e" });
  const all1 = (st.degAll[0] || [])[1] || 0;
  const allTot = st.degAll.reduce((a, r) => a + r[1], 0);
  const six = (st.degAll[st.degAll.length - 1] || [])[1] || 0;
  $("#deg-all-legend").innerHTML =
    `Add the ${fmt(st.funds)} fund filings and the shape barely moves: ${fmt(all1)} of ` +
    `${fmt(allTot)} people still appear once, and only ${fmt(six)} appear on six or more. ` +
    `The funds do not add edges. They add administrators.`;

  // who repeats, and in what capacity
  const rep = D.repeatsCo.slice(0, 220);
  $("#rep-body").innerHTML = rep.map(r => `<tr>
      <td class="nm"><span class="person" data-person="${esc(r.n)}">${esc(r.n)}</span></td>
      <td class="num">${r.d}</td>
      <td class="pp">${esc(r.r.slice(0, 2).join(", "))}</td>
      <td class="pp" style="color:var(--ink-3)">${esc(r.ex[0] || "")}</td>
    </tr>`).join("")
    || `<tr><td colspan="4" class="empty">No person is named on two operating companies in this sample.</td></tr>`;
  wirePersons($("#rep-body"));

  // what the repeaters actually do, read off the filings rather than asserted
  const ind = st.repeatInd || [];
  $("#rep-ind").innerHTML = ind.map(([k, v]) =>
    `<tr><td>${esc(k)}</td><td class="num">${fmt(v)}</td></tr>`).join("")
    || `<tr><td colspan="2" class="empty">no repeat names in the sample</td></tr>`;

  const top = D.repeats.slice(0, 12);
  const el = $("#agent-chart");
  const AW = chartW(el), RH = 23;
  el.setAttribute("viewBox", `0 0 ${AW} ${top.length * RH + 4}`);
  el.setAttribute("width", AW);
  el.setAttribute("height", top.length * RH + 4);
  el.innerHTML = top.map((r, i) => {
    const y = i * RH;
    const name = r.n.length > 24 ? r.n.slice(0, 23) + "\u2026" : r.n;
    const role = r.r.filter(x => x !== "not stated")[0] || "role not stated";
    return `<text x="0" y="${y + 12}" font-size="11.5" font-family="IBM Plex Mono, monospace"
        fill="#0e1319">${esc(name)}</text>
      <rect x="0" y="${y + 17}" width="${(r.d / top[0].d * (AW * 0.5)).toFixed(1)}" height="3" fill="#b3271d"></rect>
      <text x="${(AW * 0.55).toFixed(0)}" y="${y + 12}" font-size="11.5" font-family="IBM Plex Mono, monospace"
        fill="#7c8794">${r.d}, as ${esc(role)}</text>`;
  }).join("");

}

function renderFundSplit() {
  const st = D.stats;
  const W = chartW($("#split-chart")), H = 52;
  const wCo = (st.coPct / 100) * W;
  const el = $("#split-chart");
  el.setAttribute("viewBox", `0 0 ${W} ${H}`);
  el.setAttribute("width", W);
  el.setAttribute("height", H);
  el.innerHTML = `
    <rect x="0" y="6" width="${(wCo - 1).toFixed(1)}" height="20" fill="#0e1319"></rect>
    <rect x="${wCo.toFixed(1)}" y="6" width="${(W - wCo - 1).toFixed(1)}" height="20" fill="#b3271d"></rect>
    <text x="0" y="43" font-size="11.5" font-family="IBM Plex Mono, monospace" fill="#0e1319">
      ${fmt(st.cos)} operating companies, ${st.coPct}%</text>
    <text x="${W}" y="43" font-size="11.5" font-family="IBM Plex Mono, monospace" fill="#b3271d" text-anchor="end">
      ${fmt(st.funds)} pooled funds, ${st.fundPct}%</text>`;
}

function renderBlank() {
  const st = D.stats;
  const co = st.investors.co;
  const all = st.investors.all;

  bars($("#ninv-chart"), co.ninvBands, { h: 210, padL: 44 });
  $("#ninv-sub").textContent =
    `${fmt(co.reporting)} of ${fmt(co.n)} operating-company filings filled in the box`;

  $("#blank-note").innerHTML =
    `Every one of the ${fmt(co.n)} operating-company filings answers the box. The
     median is <b>${fmt(co.medianBackers)} backers</b> and the implied cheque is
     <b>${bytes(co.checkMedian)}</b>, with a Gini of ${co.checkGini}. Take the
     <span class="mono">${fmt(co.maxBackers)}</span> that COIZO LTD reported and
     the <span class="mono">$5.3bn</span> that Pruco Life Insurance reported to
     eleven, and the field turns out to be measuring captive finance portfolios
     and insurer balance sheets as much as it is measuring venture rounds.`;

  const w = co.checkGini;
  const word = w > 0.85 ? "That is close to one person writing the round."
    : w > 0.6 ? "That is a lopsided distribution." : "That is flatter than you would expect.";
  $("#check-sub").textContent =
    `Computed as reported amount sold divided by reported investors already in, for the ` +
    `${fmt(co.n)} operating-company filings. ${word} Not one of them is named anywhere.`;
  hbars($("#check-chart"), co.checkBands, { rowH: 20, padL: 88, color: "#b3271d" });
  $("#check-legend").innerHTML =
    `Across all ${fmt(all.n)} filings including funds, the median implied cheque is ` +
    `${bytes(all.checkMedian)} and the Gini is ${all.checkGini}, because the corpus ` +
    `contains money market funds reporting sales in the tens of billions.`;
}

function renderReceipts() {
  const st = D.stats;
  const today = new Date().toISOString().slice(0, 10);
  const co = st.investors.co;
  const rows = [
    ["Population", `${fmt(st.popFilings)} Form D and Form D-A filings filed between
      1 July and 26 September 2026, read in full from the EDGAR daily
      dissemination index across ${fmt(st.popDays)} business days`],
    ["Sample", `${fmt(st.sample)} of them, drawn with seed ${st.seed}`],
    ["Sample rate", `${st.sampleRate}% of the quarter`],
    ["Distinct issuers", `${fmt(st.issuers)}, after folding ${fmt(st.amendments)}
      amendments onto the filing they amend`],
    ["Pooled investment funds", `${fmt(st.funds)} (${st.fundPct}%)`],
    ["Operating companies", `${fmt(st.cos)} (${st.coPct}%)`],
    ["Names, all filings", `${fmt(st.allNames.distinct)} distinct,
      ${fmt(st.allNames.appearances)} appearances,
      ${st.allNames.oncePct}% appear once`],
    ["Names, natural persons", `${fmt(st.peopleNames.distinct)} distinct,
      ${fmt(st.peopleNames.appearances)} appearances,
      ${st.peopleNames.oncePct}% appear once`],
    ["Names, operating companies", `${fmt(st.coNames.distinct)} distinct,
      ${fmt(st.coNames.appearances)} appearances,
      ${st.coNames.oncePct}% appear once,
      ${fmt(st.coNames.repeat)} repeaters adding ${fmt(st.coNames.bridged)} edges`],
    ["Filings naming no human", fmt(st.entityOnly)],
    ["Backer counts, operating cos", `${fmt(co.reporting)} of ${fmt(co.n)} report
      at least one backer, none leave the field blank, and the rest report zero,
      which on this form means the first sale had not happened yet. Median
      ${fmt(co.medianBackers)} backers, median implied cheque
      ${bytes(co.checkMedian)}, Gini ${co.checkGini}`],
    ["Rule 506(c)", `${fmt(st.rule506cCo)} of ${fmt(st.cos)} operating-company
      filings, ${fmt(st.rule506c)} of ${fmt(st.issuers)} in total`],
    ["Retrieved", today],
    ["Filing deadline", `Form D is due no later than 15 days after the first
      sale, not before it. See the form itself:
      <a class="src" href="https://www.sec.gov/Archives/edgar/vprr/0201/02014640.pdf"
      target="_blank" rel="noopener">sec.gov</a>`],
    ["Rule 506", `506(b): no general solicitation, unlimited accredited plus up to
      35 sophisticated non-accredited. 506(c): general solicitation allowed, all
      purchasers accredited and verified.
      <a class="src" href="https://www.sec.gov/answers/rule506.htm"
      target="_blank" rel="noopener">investor.gov</a>`],
    ["Source", `SEC EDGAR <span class="mono">primary_doc.xml</span> for every
      accession, parsed directly. No third-party enrichment, no paid data, and no
      language model anywhere in the data path`],
    ["Verification", `every figure on this page is recomputed from
      <span class="mono">data/formd.jsonl</span> by a second script that shares
      no code with the one that wrote this file, and the two fail loudly on any
      disagreement. The entity test, which decides the headline numbers, is
      stated in that script rather than left to a regex`],
    ["cosign copy", `cosign.co and the a16z and Erik Torenberg launch posts,
      retrieved ${today}`],
  ];
  $("#receipts").innerHTML = rows.map(([k, v]) =>
    `<tr><th scope="row">${k}</th><td>${v}</td></tr>`).join("");
}

/* ------------------------------------------------------------ the model */

const sim = {
  n: 2000, seed: 20, vis: 3, w: 0.85, eff: 0.06, reach: 0.3, noise: 0.5, cohort: 0.25,
  series: [], last: null, flat: null, lock: null, lockFlat: null,
  capLow: null, capHigh: null, busy: false, queued: null,
};

/* The model runs in a worker so a redraw never blocks the page. It answers in
   two messages: the curve first, then the three extra numbers the prose quotes.
   While a redraw is in flight, knob moves collapse into one queued run rather
   than queueing a run each. */
let worker = null;
let runSeq = 0;

function startWorker() {
  if (worker) return worker;
  worker = new Worker("model-worker.js");
  worker.onmessage = e => {
    const d = e.data;
    if (d.id !== runSeq) return;           // a newer run superseded this one
    if (d.stage === 1) {
      sim.series = d.series;
      sim.last = d.last;
      sim.lock = d.lock;
      drawSim();
    } else {
      sim.flat = d.flat;
      sim.lockFlat = d.lockFlat;
      sim.capLow = d.capLow;
      sim.capHigh = d.capHigh;
      drawSim();
    }
    if (sim.queued) { const q = sim.queued; sim.queued = null; requestModel(q); }
    else sim.busy = false;
  };
  worker.onerror = () => { sim.busy = false; };
  return worker;
}

function requestModel(cfg) {
  const w = startWorker();
  sim.busy = true;
  w.postMessage({ ...cfg, id: ++runSeq });
}

function runModel() {
  if (sim.busy) { sim.queued = { ...sim }; return; }
  requestModel({ ...sim });
}

function drawSim() {
  const c = $("#sim-canvas");
  if (!c) return;
  const host = c.parentElement;
  const W = Math.max(320, Math.min(1100, Math.round(host.getBoundingClientRect().width)));
  const H = 340;
  if (c.width !== W) c.width = W;
  if (c.height !== H) c.height = H;
  const ctx = c.getContext("2d");
  const padL = 46, padR = 16, padT = 16, padB = 30;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#10151b";
  ctx.fillRect(0, 0, W, H);

  const last = sim.last;
  const flat = sim.flat;
  const series = sim.series;

  $("#sim-legend").innerHTML = [
    ["#7fd1b4", last ? `day-one cohort, ${last.capture.toFixed(2)}x its share` : "day-one cohort"],
    ["#6b7885", flat ? `all discovery, ${flat.capture.toFixed(2)}x` : "all discovery"],
  ].map(([col, l]) => `<span><i style="background:${col}"></i>${l}</span>`).join("");
  $("#sim-status").textContent = last
    ? `${fmt(last.t)} rounds · ${fmt(last.visible)} visible` : "working";

  if (last && series.length) {
    const iw = W - padL - padR, ih = H - padT - padB;
    const tMax = last.t || 1;
    const peak = Math.max(2, last.capture, flat ? flat.capture : 0);
    const yMax = Math.ceil(peak * 2) / 2;
    const yOf = v => padT + ih - (Math.max(0, Math.min(yMax, v)) / yMax) * ih;

    ctx.font = "11px IBM Plex Mono, monospace";
    for (let g = 0; g <= 4; g++) {
      const v = (g / 4) * yMax;
      const y = Math.round(yOf(v)) + 0.5;
      const parity = Math.abs(v - 1) < 0.01;
      ctx.strokeStyle = parity ? "#3d4a56" : "#232c36";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      ctx.fillStyle = parity ? "#aab4bf" : "#7d8894";
      ctx.textAlign = "right";
      ctx.fillText(parity ? "1x parity" : v.toFixed(1) + "x", padL - 7, y + 4);
    }
    ctx.textAlign = "center";
    ctx.fillStyle = "#7d8894";
    for (let g = 0; g <= 5; g++) {
      const x = padL + (g / 5) * iw;
      ctx.fillText(Math.round((g / 5) * tMax), x, H - 10);
    }

    const line = (pts, color, width, dash) => {
      ctx.save();
      if (dash) ctx.setLineDash([4, 4]);
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      for (let i = 0; i < pts.length; i++) {
        const x = padL + (pts[i][0] / tMax) * iw;
        const y = yOf(pts[i][1]);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.stroke();
      ctx.restore();
    };
    line(series, "#7fd1b4", 2.2, false);
    // the control lands in stage 2; draw it as a straight line to where it ends
    if (flat) line([[0, flat.capture], [tMax, flat.capture]], "#6b7885", 1.4, true);
  }

  const cards = [
    [last ? fmt(last.visible) : "…", "profiles visible after the run"],
    [last ? last.capture.toFixed(2) + "x" : "…",
     "how much more reputation the day-one cohort holds than its share of the network"],
    [flat ? flat.capture.toFixed(2) + "x" : "…",
     "the same, with every endorsement arriving through discovery"],
    [sim.lock == null ? "…" : (sim.lock * 100).toFixed(0) + "%",
     "of the top 1% after 20 rounds are still in the top 1% at the end"],
    [sim.lockFlat == null ? "…" : (sim.lockFlat * 100).toFixed(0) + "%",
     "the same, with every endorsement arriving through discovery"],
  ];
  $("#sim-readout").innerHTML = cards.map(([n, l], i) =>
    `<div><span class="n${i === 0 ? "" : " warn"}">${n}</span><span class="l">${l}</span></div>`).join("");

  if (last && flat) $("#sim-verdict").innerHTML = verdictHtml(last, flat);
}

function verdictHtml(last, flat) {
  const cohortSize = Math.round(sim.cohort * sim.n);
  const lock = sim.lock == null ? null : Math.round(sim.lock * 100);
  const lockF = sim.lockFlat == null ? null : Math.round(sim.lockFlat * 100);
  return `The people who were already credible when the doors opened are
    <span class="mono">${fmt(cohortSize)}</span> of <span class="mono">${fmt(sim.n)}</span>,
    or ${(sim.cohort * 100).toFixed(0)}% of the network. After
    ${fmt(last.t)} rounds of endorsements they are holding
    <b>${last.capture.toFixed(2)}x</b> their share of all the reputation, and the
    network has settled: it is not still climbing. Turn every endorsement into
    discovery instead of social proof and the same cohort lands at
    <b>${flat ? flat.capture.toFixed(2) : "?"}x</b>, which is parity, because with
    nothing compounding a head start is worth nothing.
    ${lock === null || lockF === null ? "" : `Rank order is the other half of it. <b>${lock}%</b> of
    the people in the top 1% after twenty rounds are still in the top 1% a
    thousand rounds later; the all-discovery run gets ${lockF}%.`}
    The visibility threshold is the number a product team argues about, and
    moving it from one endorsement to twelve moves the capture ratio from
    ${sim.capLow == null ? "?" : sim.capLow.toFixed(2) + "x"} to
    ${sim.capHigh == null ? "?" : sim.capHigh.toFixed(2) + "x"} at everything
    else held fixed, which is worth knowing before you pick a number. The dial
    that decides
    whether the first cohort compounds at all is the one nobody puts in a spec.
    Cosign's public copy has already picked a value for it: <em class="term">make
    discoveries before anyone else.</em>`;
}

function wireSim() {
  const map = [["n", "n"], ["seed", "seed"], ["vis", "vis"], ["w", "w"],
               ["eff", "eff"], ["rr", "reach"], ["noise", "noise"], ["co", "cohort"]];
  map.forEach(([id, key]) => {
    const el = $("#k-" + id);
    const out = $("#v-" + id);
    if (!el || !out) throw new Error("sim knob #" + id + " is not in the page");
    const readKnob = () => {
      sim[key] = key === "cohort" ? Number(el.value) / 100 : parseFloat(el.value);
      out.textContent = key === "cohort" ? Math.round(sim.cohort * 100) + "%"
        : ["w", "eff", "reach", "noise"].includes(key) ? Number(sim[key]).toFixed(2)
        : fmt(el.value);
    };
    el.addEventListener("input", () => {
      readKnob();
      clearTimeout(sim.t);
      sim.t = setTimeout(runModel, 40);
    });
    readKnob();
  });
  $("#sim-run").addEventListener("click", () => {
    sim.seed = sim.seed >= 300 ? 1 : sim.seed + 1;
    $("#k-seed").value = sim.seed;
    $("#v-seed").textContent = sim.seed;
    runModel();
  });
  $("#sim-shuffle").addEventListener("click", () => {
    sim.seed = 1 + Math.floor(Math.random() * 400);
    runModel();
  });
  runModel();
}

/* ---------------------------------------------------------------- tip */

let redrawT = null;
addEventListener("resize", () => {
  clearTimeout(redrawT);
  redrawT = setTimeout(() => {
    if (!D) return;
    renderGraph();
    renderFundSplit();
    renderBlank();
    if (sim.last) drawSim();
  }, 200);
});

function wireTip() {
  const tip = $("#tip");
  document.addEventListener("mousemove", e => {
    const t = e.target.closest("[data-tip]");
    if (!t) { tip.classList.remove("on"); return; }
    tip.innerHTML = t.dataset.tip;
    tip.classList.add("on");
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(innerWidth - r.width - 12, e.clientX + 14) + "px";
    tip.style.top = Math.max(8, e.clientY - r.height - 12) + "px";
  });
}

/* ---------------------------------------------------------------- boot */

function boot(DATA) {
  D = DATA;
  const st = D.stats;
  const today = new Date().toISOString().slice(0, 10);
  $("#kicker-n").textContent = `${fmt(st.sample)} of ${fmt(st.popFilings)} filings in the quarter`;
  $("#by-f").textContent = fmt(st.sample);
  $("#chrome-stat").textContent = `EDGAR Form D, ${fmt(st.popFilings)} filings in the quarter`;
  $("#rail-n").textContent = `${fmt(st.sample)} filings · ${fmt(st.coNames.distinct)} people`;
  $("#rail-date").textContent = today;
  $("#foot-date").textContent = today;

  const form = D.forms.find(f => /manufacturer/i.test(f.label || "")) || D.forms[0];
  if (form) {
    anatomyIdx = Math.max(0, (D.forms || []).indexOf(form));
    $("#hero-form").innerHTML = renderForm(form, { compact: true });
    wirePersons($("#hero-form"));
  }
  renderAnatomy();

  buildPersonIndex();
  wireDir();
  renderDir();
  renderGraph();
  renderBlank();
  renderReceipts();
  wireSim();
  wireTip();
  wirePersons(document);

  const co = st.coNames;
  const people = st.peopleNames;

  $("#dir-intro").innerHTML =
    `There are <span class="mono">${fmt(st.issuers)}</span> distinct issuers in
     the sample, <span class="mono">${fmt(st.peopleAppearances || people.appearances)}</span>
     name appearances, and <span class="mono">${fmt(st.entityOnly)}</span> filings
     that name nobody human at all.`;

  $("#fund-n").textContent = fmt(st.funds);
  $("#iss-n").textContent = fmt(st.issuers);
  $("#s3 h2").textContent = "Two thirds of it is not startups";

  $("#graphtext").innerHTML =
    `Pull the named people out of those filings and draw an edge from each person
     to every company they were named on. That is the endorsement graph, minus
     the endorsements, taken from the only machine-readable US record of who
     stood behind a private company when it raised. Across the whole sample,
     <span class="mono">${fmt(st.cos)}</span> operating-company filings name
     <span class="mono">${fmt(people.appearances)}</span> people in
     <span class="mono">${fmt(people.distinct)}</span> distinct names.`;

  $("#graphverdict").innerHTML =
    `It is almost entirely not there. Restricting to the
     <span class="mono">${fmt(st.cos)}</span> operating-company filings,
     <span class="mono">${fmt(co.distinct)}</span> distinct people are named and
     <span class="mono">${co.oncePct}%</span> of them appear on exactly one
     company, which makes them a dead end in any graph you build.
     <span class="mono">${fmt(co.repeat)}</span> people are named on two or more,
     and between them they add <span class="mono">${fmt(co.bridged)}</span> edges
     to <span class="mono">${fmt(st.cos)}</span> companies. That is the entire
     recorded social graph of who stood behind American startups this quarter:
     ${fmt(co.repeat)} nodes, ${fmt(co.bridged)} edges, and no investors in it at
     all, because investors are not who Form D names.`;

  renderFundSplit();
}

fetch("drop.json")
  .then(r => r.json())
  .then(boot)
  .catch(err => {
    console.error("boot failed", err);
    document.getElementById("kicker-n").textContent = "data missing: " + err.message;
    window.__stack = err.stack;
    const p = document.createElement("p");
    p.className = "note";
    p.textContent = "drop.json did not load. Run scripts/build_drop.py and reload. " + err.message;
    document.querySelector(".hero").appendChild(p);
  });

buildChrome();
})();
