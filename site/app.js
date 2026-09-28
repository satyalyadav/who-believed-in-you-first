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
const investorCountHtml = n => {
  if (n === null || n === undefined) return `<span class="nodata">not recorded</span>`;
  if (n === 0) return `<span title="Cached zero may be an explicit zero or a blank collapsed by the earlier parser">0*</span>`;
  return fmt(n);
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
  ["s5", "Investor count"],
  ["s6", "Model"],
  ["s7", "Receipts"],
];

function buildChrome() {
  $("#rail-list").innerHTML = ITEMS.map(([id, label], i) =>
    `<li><a href="#${id}" data-id="${id}"><span class="bx" aria-hidden="true"></span>${i + 1}. ${label}</a></li>`
  ).join("");

  const links = $$("#rail-list a");
  const onScroll = () => {
    let cur = ITEMS[0][0];
    for (const [id] of ITEMS) {
      const el = document.getElementById(id);
      if (el && el.getBoundingClientRect().top < 140) cur = id;
    }
    links.forEach(a => {
      const active = a.dataset.id === cur;
      a.classList.toggle("on", active);
      if (active) a.setAttribute("aria-current", "location");
      else a.removeAttribute("aria-current");
    });
    const n = ITEMS.findIndex(i => i[0] === cur) + 1;
    $("#chrome-idx").textContent = `Section ${n} of ${ITEMS.length}`;
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
  const detail = !!opts.detail;
  const persons = f.p.map(p => `<div class="frow blk">
      <span class="k">Name of related person</span>
      <span class="v"><button type="button" class="person" data-person="${esc(p.n)}" data-person-type="${p.e ? "entity" : "person"}" aria-pressed="${isPersonActive(p.n, p.e ? "entity" : "person")}">${esc(p.n)}</button>
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
      <span class="mid">Selected fields excerpt</span>
      <span class="sp"></span>
      <span class="acc">${f.acc}</span>
      ${detail ? '<button type="button" class="close" data-close aria-label="Close filing details">close</button>' : ""}
    </div>
    ${f.sharedAcc ? `<p class="small shared-note">This accession appears under multiple issuer CIKs in the local EDGAR index (${f.sharedCiks.map(esc).join(", ")}). XML Item 1 names the primary issuer ${esc(f.name)}; this selected index row is CIK ${esc(f.cik)}${f.cikName ? `, labeled ${esc(f.cikName)}${f.nameTruncated ? "…" : ""}` : ""}${f.nameFromIndex ? " (EDGAR index name, may be truncated)" : f.nameUnresolvedShared ? " (issuer label unresolved)" : ""}. Offering amounts and the investor total are joint-offering values. Item 3 lists related persons for any issuer on the notice, so the names are not assigned to each CIK.</p>` : ""}

    <div class="fsec">Item 1. Issuer identity</div>
    <div class="frow"><span class="k">Name of issuer in XML Item 1</span><span class="v">${esc(f.name)}</span></div>
    ${f.sharedAcc ? `<div class="frow"><span class="k">CIK in selected EDGAR index row</span><span class="v">${esc(f.cik)}</span></div>
    <div class="frow"><span class="k">Selected row's issuer label</span><span class="v">${esc(f.cikName || "")}${f.nameTruncated ? "…" : ""}${f.nameFromIndex ? ` <span class="tag">EDGAR index name, may be truncated</span>` : f.nameUnresolvedShared ? ` <span class="tag">issuer label unresolved</span>` : ""}</span></div>`
      : `<div class="frow"><span class="k">CIK</span><span class="v">${f.cik}</span></div>`}
    ${compact ? "" : `<div class="frow"><span class="k">Entity type</span><span class="v">${nd(f.etype)}</span></div>
    <div class="frow"><span class="k">Jurisdiction</span><span class="v">${nd(f.juris)}</span></div>
    <div class="frow"><span class="k">Year formed</span><span class="v">${nd(f.yinc)}</span></div>`}
    ${(!compact && f.prev.length) ? `<div class="frow"><span class="k">Previous names</span><span class="v">${esc(f.prev.join("; "))}</span></div>` : ""}

    <div class="fsec">Item 2. Principal place of business and contact information</div>
    <div class="frow"><span class="k">City</span><span class="v">${nd(f.city)}</span></div>
    <div class="frow"><span class="k">State</span><span class="v">${nd(f.state)}</span></div>

    <div class="fsec">Item 3. Related persons <span style="font-weight:400;color:var(--ink-3)">${f.sharedAcc ? "joint offering list; may relate to any issuer" : "the complete list the issuer gave"}</span></div>
    ${persons || `<div class="frow"><span class="k">related persons</span><span class="v"><span class="nodata">&nbsp;</span></span></div>`}

    <div class="fsec">Item 4. Industry group</div>
    <div class="frow"><span class="k">Industry group</span><span class="v">${nd(f.ind)}</span></div>
    ${f.ftype ? `<div class="frow"><span class="k">Fund type</span><span class="v">${nd(f.ftype)}</span></div>` : ""}
    ${compact ? "" : `<div class="fsec">Item 5. Issuer size</div>
    <div class="frow"><span class="k">Revenue range</span><span class="v">${nd(f.rev)}</span></div>
    ${f.nav ? `<div class="frow"><span class="k">Net asset value</span><span class="v">${nd(f.nav)}</span></div>` : ""}

    <div class="fsec">Item 6. Federal exemptions and exclusions</div>
    <div class="frow"><span class="k">Rule</span><span class="v">${exempt.map(e => `<span class="tag">${esc(e)}</span>`).join(" ") || nd(false)}</span></div>

    <div class="fsec">Item 7. Filing type</div>
    <div class="frow"><span class="k">New notice or amendment</span>
      <span class="v">${xrow(!f.amend, true)} ${xrow(!!f.amend)} ${f.amend && f.prevAcc ? "amends " + f.prevAcc : ""}</span></div>
    <div class="frow"><span class="k">Date of first sale</span>
      <span class="v">${f.yet ? xrow(true, true) + " first sale reported as yet to occur" : f.sale0 ? esc(f.sale0) : "date not verified in current cache"}</span></div>

    <div class="fsec">Item 9. Securities offered</div>
    <div class="frow"><span class="k">Securities offered</span>
      <span class="v">${(f.secs || []).map(s => `<span class="tag">${esc(secName(s))}</span>`).join(" ") || nd(false)}</span></div>
`}

    <div class="fsec">Item 13. Offering and sales amounts</div>
    <div class="frow hi"><span class="k">Total offering amount</span>
      <span class="v">${moneyCell(f.offer, f.offerInd)}</span></div>
    <div class="frow hi"><span class="k">Total amount sold</span>
      <span class="v">${moneyCell(f.sold, false)}</span></div>
    <div class="frow"><span class="k">Remaining to be sold</span>
      <span class="v">${moneyCell(f.rem, f.remInd)}</span></div>

    <div class="fsec">Item 14. Investor count</div>
    <div class="frow hi"><span class="k">Investor count in this filing</span>
      <span class="v">${investorCountHtml(f.ninv)}
        <span style="color:var(--ink-3)">${f.ninv == null ? "" : f.ninv === 0 ? "cached 0; explicit zero or prior blank unknown" : "aggregate count; no investor names"}</span></span></div>

    ${compact ? "" : `<div class="fsec">Item 15. Sales Commission and Finders' Fees Expenses</div>
    <div class="frow"><span class="k">Sales commissions</span><span class="v">${moneyCell(f.comm, false)}</span></div>
    <div class="frow"><span class="k">Finders' fees</span><span class="v">${moneyCell(f.fees, false)}</span></div>
    <div class="fsec">Item 16. Use of proceeds</div>
    ${(f.proceeds !== null && f.proceeds !== undefined) ? `<div class="frow"><span class="k">Gross proceeds used for payments to Item 3 related persons</span><span class="v">${moneyCell(f.proceeds, false)}</span></div>` : ""}

    <div class="fsec">Signature</div>
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

function issuerKey(i) {
  return `${i.c}:${i.i}`;
}

function dirRows() {
  const q = norm(dirState.q);
  const qPerson = personKey(dirState.q);
  let rows = D.issuers.filter(i => {
    if (dirState.kind === "co" && i.g === FUND) return false;
    if (dirState.kind === "fund" && i.g !== FUND) return false;
    if (dirState.ind && i.g !== dirState.ind) return false;
    if (dirState.people && !i.P.length) return false;
    if (dirState.person) {
      const hit = dirState.person.type === "entity"
        ? i.E.some(p => nameKey(p, "entity") === dirState.person.key)
        : i.P.some(p => nameKey(p, "person") === dirState.person.key);
      if (!hit) return false;
    }
    if (q) {
      const otherFields = norm([i.n, i.i, i.g || "", i.s || ""].join(" "));
      const personMatch = i.P.some(p => {
        const key = personKey(p);
        return key.includes(q) || (qPerson && key === qPerson);
      });
      const entityMatch = i.E.some(p => norm(p).includes(q));
      if (!otherFields.includes(q) && !personMatch && !entityMatch) return false;
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
  if (s === "k-asc") rows.sort((a, b) => num(a.k) - num(b.k));
  if (s === "n") rows.sort((a, b) => a.n.localeCompare(b.n));
  if (s === "n-desc") rows.sort((a, b) => b.n.localeCompare(a.n));
  return rows;
}

function norm(s) {
  return String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

const PERSON_SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "phd", "md", "mba", "cpa", "jd", "esq"]);
function personKey(s) {
  const words = norm(s).split(" ").filter(Boolean);
  while (words.length && PERSON_SUFFIXES.has(words[words.length - 1])) words.pop();
  return words.join(" ");
}

function nameKey(s, type) {
  return `${type}:${type === "entity" ? norm(s) : personKey(s)}`;
}

function isPersonActive(s, type) {
  return !!dirState.person && dirState.person.key === nameKey(s, type);
}

const CAP = 400;
const FUND = "Pooled Investment Fund";

function renderDir() {
  const rows = dirRows();
  const body = $("#dir-body");
  const shown = rows.slice(0, CAP);
  body.innerHTML = shown.map(i => `
    <tr data-profile="${esc(issuerKey(i))}"${dirState.sel === issuerKey(i) ? ' class="sel"' : ""}>
      <td class="acc">${dstr(i.f)}</td>
      <td class="nm"><a href="${edgar(i.c, i.i)}" target="_blank" rel="noopener">${esc(i.n)}${i.nameTruncated ? "…" : ""}</a>
        ${i.N > 1 ? `<span class="tag">${fmt(i.N)} sampled index rows</span>` : ""}
        ${i.nameFromIndex ? `<span class="tag">EDGAR index issuer name${i.nameTruncated ? " · may be truncated" : ""}</span>` : ""}
        ${i.nameUnresolvedShared ? `<span class="tag">EDGAR index issuer label unresolved</span>` : ""}
        ${i.sharedLatest ? `<span class="tag">joint-offering values</span>` : ""}</td>
      <td>${i.g ? `<span class="tag${i["6"] ? " c" : ""}">${esc(i.g)}</span>` : ""}
        ${i["6"] ? `<span class="tag c">506(c)</span>` : ""}</td>
      <td class="pp">${i.P.length
        ? i.P.slice(0, 3).map(p => `<button type="button" class="person" data-person="${esc(p)}" data-person-type="person" aria-pressed="${isPersonActive(p, "person")}">${esc(p)}</button>`).join("") +
          (i.P.length > 3 ? ` <span style="color:var(--ink-3)">+${i.P.length - 3} more names</span>` : "") +
          (i.E.length ? ` <span style="color:var(--ink-3)">${i.E.length} related ${i.E.length === 1 ? "entity" : "entities"}</span>` : "")
        : i.E.length
          ? `<button type="button" class="person" data-person="${esc(i.E[0])}" data-person-type="entity" aria-pressed="${isPersonActive(i.E[0], "entity")}">${esc(i.E[0])}</button> (entity)` +
            (i.E.length > 1 ? ` <span style="color:var(--ink-3)">+${i.E.length - 1} more entities</span>` : "")
          : i.J.length ? `<span style="color:var(--ink-3)">no CIK-assigned names</span>`
            : `<span style="color:var(--ink-3)">none named</span>`}
        ${i.J.length ? `<span class="tag">${i.J.length} shared Item 3 list${i.J.length === 1 ? "" : "s"} · not CIK-assigned</span>` : ""}</td>
      <td class="num">${i.d == null ? `<span style="color:var(--ink-3)">${i.I ? "indefinite" : "—"}</span>` : usd(i.d)}</td>
      <td class="num">${investorCountHtml(i.k)}</td>
      <td class="acc">${i.i}<br><button type="button" class="link row-detail" data-detail-cik="${esc(i.c)}" data-detail-acc="${esc(i.i)}" aria-expanded="${dirState.sel === issuerKey(i)}" aria-label="Show details for ${esc(i.n)} (CIK ${esc(i.c)})">details</button></td>
    </tr>`).join("");

  $("#dir-empty").hidden = rows.length > 0;
  const pool = dirState.kind === "co" ? D.stats.cos : D.stats.funds;
  const noun = dirState.kind === "co" ? "non-fund issuer profiles" : "pooled fund profiles";
  $("#dir-count").textContent = `${fmt(rows.length)} of ${fmt(pool)} ${noun}` +
    (rows.length > CAP ? `, showing the first ${CAP}` : "");
  if (dirState.person) {
    $("#dir-count").textContent = `Filtered to ${dirState.person.label} (${dirState.person.type}). ` + $("#dir-count").textContent;
  }
  syncSortHeaders();
}

function syncSortHeaders() {
  const map = { "d-asc": ["d", "ascending"], d: ["d", "descending"],
    n: ["n", "ascending"], "n-desc": ["n", "descending"],
    "d$": ["d$", "descending"], "d$-asc": ["d$", "ascending"],
    k: ["k", "descending"], "k-asc": ["k", "ascending"] };
  const [key, direction] = map[dirState.sort] || [];
  $$(".dirwrap .sort").forEach(button => {
    const th = button.closest("th");
    if (button.dataset.sort === key) th.setAttribute("aria-sort", direction);
    else th.removeAttribute("aria-sort");
  });
}

function showDetail(cik, acc) {
  const f = D.forms.find(x => x.cik === cik && x.acc === acc);
  const i = D.issuers.find(x => x.c === cik && x.i === acc);
  if (!i) return;
  dirState.sel = issuerKey(i);
  renderDir();
  const host = $("#dir-detail");
  if (f) {
    host.innerHTML = renderForm(f, { detail: true });
  } else {
    host.innerHTML = `<div class="detail">
      <div class="top"><span>${esc(i.n)}${i.nameTruncated ? "…" : ""}</span><span class="sp"></span>
        <a class="src" style="color:var(--paper)" href="${edgar(i.c, i.i)}" target="_blank" rel="noopener">EDGAR</a>
        <button class="close" data-close>close</button></div>
      <div class="body">
        <div class="frow"><span class="k">accession</span><span class="v">${i.i}</span></div>
        <div class="frow"><span class="k">filed</span><span class="v">${i.f}</span></div>
        <div class="frow"><span class="k">industry</span><span class="v">${nd(i.g)}</span></div>
        <div class="frow"><span class="k">amount sold</span><span class="v">${i.d == null ? nd(false) : usd(i.d)}</span></div>
        <div class="frow"><span class="k">investor count in latest sampled filing</span><span class="v">${investorCountHtml(i.k)}${i.k === 0 ? " · explicit zero or prior blank unknown" : ""}</span></div>
        <div class="frow"><span class="k">issuer-related person-name matches</span><span class="v">${i.P.map(p =>
          `<button type="button" class="person" data-person="${esc(p)}" data-person-type="person" aria-pressed="${isPersonActive(p, "person")}">${esc(p)}</button>`).join("") || nd(false)}</span></div>
        <div class="frow"><span class="k">issuer-related entities</span><span class="v">${i.E.map(p =>
          `<button type="button" class="person" data-person="${esc(p)}" data-person-type="entity" aria-pressed="${isPersonActive(p, "entity")}">${esc(p)}</button>`).join("") || nd(false)}</span></div>
        ${i.nameFromIndex ? `<div class="frow"><span class="k">issuer name source</span><span class="v">EDGAR daily-index row${i.nameTruncated ? "; name may be truncated at 55 characters" : ""}.</span></div>` : ""}
        ${i.nameUnresolvedShared ? `<div class="frow"><span class="k">issuer name source</span><span class="v">The selected CIK's issuer label could not be resolved from its local EDGAR index row.</span></div>` : ""}
        ${i.sharedLatest ? `<div class="frow"><span class="k">latest filing values</span><span class="v">Joint-offering XML from an accession shared across CIK rows; offering amounts and the investor total may repeat for co-issuers.</span></div>` : ""}
        ${i.J.length ? `<div class="frow"><span class="k">Joint Item 3 names, not CIK-assigned</span><div class="v">${i.J.map(group => `<div><span class="mono">${esc(group.acc)}</span><div><strong>XML Item 1 primary issuer name:</strong> ${group.xmlName ? esc(group.xmlName) : "unavailable in cached XML"}${group.primaryCik ? ` (XML primary CIK ${esc(group.primaryCik)})` : " (primary CIK unresolved)"}</div><div><strong>Full-window EDGAR index CIKs on this accession:</strong> ${group.ciks.map(esc).join(", ")}. The selected profile label and its source are shown separately in this detail panel.</div><div><strong>Related persons on the joint notice, not assigned to an individual CIK:</strong> ${group.p.map(p => `${esc(p.n)}${p.r.length ? ` (${p.r.map(esc).join(", ")})` : ""}`).join("; ")}</div></div>`).join("")}</div></div>` : ""}
      </div></div>`;
  }
  wirePersons(host);
  host.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function clearDetail() {
  const selected = dirState.sel;
  dirState.sel = null;
  $("#dir-detail").innerHTML = "";
  renderDir();
  const button = selected && $$("[data-detail-cik]").find(el =>
    issuerKey({ c: el.dataset.detailCik, i: el.dataset.detailAcc }) === selected);
  if (button) button.focus();
}

let personDelegationInstalled = false;
function wirePersons() {
  if (personDelegationInstalled) return;
  personDelegationInstalled = true;
  document.addEventListener("click", ev => {
    const button = ev.target.closest("button.person[data-person]");
    if (!button) return;
    ev.preventDefault();
    ev.stopPropagation();
    const type = button.dataset.personType === "entity" ? "entity" : "person";
    const key = nameKey(button.dataset.person, type);
    dirState.person = dirState.person?.key === key ? null : {
      key, type, label: button.dataset.person,
    };
    dirState.sel = null;
    $("#dir-detail").innerHTML = "";
    renderDir();
    if (dirState.person) $("#s3").scrollIntoView({ behavior: "smooth", block: "start" });
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
      ? "non-fund issuer profiles only" : "pooled-fund profiles only";
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
  $$(".dirwrap .sort").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.sort;
      if (key === "d") dirState.sort = dirState.sort === "d" ? "d-asc" : "d";
      else if (key === "d$") dirState.sort = dirState.sort === "d$" ? "d$-asc" : "d$";
      else if (key === "k") dirState.sort = dirState.sort === "k" ? "k-asc" : "k";
      else dirState.sort = dirState.sort === "n" ? "n-desc" : "n";
      $("#f-sort").value = dirState.sort;
      renderDir();
    });
  });
  $("#dir-body").addEventListener("click", e => {
    const detail = e.target.closest("[data-detail-cik][data-detail-acc]");
    if (detail) showDetail(detail.dataset.detailCik, detail.dataset.detailAcc);
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
      font-family="IBM Plex Mono, monospace" fill="#5f6975">${esc(label)}</text>`;
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
      font-family="IBM Plex Mono, monospace" fill="#5f6975">${fmt(v)}</text>`;
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
      <span>${humans} names match the script's person-name heuristic${
        f.p.length > humans ? `, ${f.p.length - humans} named entities` : ""}</span>
      <span>${f.ninv == null ? "investor count unavailable" : f.ninv === 0 ? "cached investor count 0*; explicit zero or prior blank unknown" : `${fmt(f.ninv)} investors reported`}</span>
    </div>
    ${renderForm(f)}
    <div class="acts" style="margin:12px 0 0">
      <button class="b" data-form-step="-1">previous filing</button>
      <button class="b" data-form-step="1">next filing</button>
      <span class="note" style="margin-left:4px">Five sampled filings, rendered from their parsed fields.</span>
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
  const add = (map, name, idx, roles, month, issuer, type) => {
    const k = nameKey(name, type);
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
      add(PERSON_IDX.all, name, idx, i.R, i.f.slice(0, 6), i.n, "person");
      if (i.g !== FUND) add(PERSON_IDX.co, name, idx, i.R, i.f.slice(0, 6), i.n, "person");
    });
    i.E.forEach(name => add(PERSON_IDX.all, name, idx, ["entity"], i.f.slice(0, 6), i.n, "entity"));
  });
  for (const map of [PERSON_IDX.all, PERSON_IDX.co]) {
    map.forEach(e => (e.roles = [...e.roles].slice(0, 3).join(", ")));
  }
}

function renderGraph() {
  const st = D.stats;
  const co = st.coNames;

  const nodes = co.distinct + st.cos;
  const edges = co.appearances;
  $("#graphverdict").innerHTML =
    `Across ${fmt(st.cos)} non-fund issuer CIK profiles, this name-to-issuer
     graph has ${fmt(nodes)} nodes: ${fmt(co.distinct)} normalized name keys
     classified by the script's person-name heuristic and ${fmt(st.cos)} issuers. It has ${fmt(edges)} links. ${co.oncePct}%
     of the name keys appear on one issuer profile; ${fmt(co.repeat)} keys
     appear on more than one. A repeated normalized name is a match made by the
     stated rules, not a confirmed identity. Form D's investor total is a
     separate field, so these links do not show who invested or endorsed whom.`;

  // the same histogram twice: once for non-fund issuers, then for all profiles
  hbars($("#deg-chart"), st.degCo, { rowH: 24, padL: 104 });
  const co1 = (st.degCo[0] || [])[1] || 0;
  $("#deg-legend").innerHTML =
    `${fmt(co1)} of ${fmt(co.distinct)} normalized names occur on one non-fund CIK profile. ` +
    `The bars count issuer profiles, not confirmed people.`;

  hbars($("#deg-all-chart"), st.degAll, { rowH: 24, padL: 104, color: "#5f6975" });
  const all1 = (st.degAll[0] || [])[1] || 0;
  const allTot = st.degAll.reduce((a, r) => a + r[1], 0);
  const six = (st.degAll[st.degAll.length - 1] || [])[1] || 0;
  $("#deg-all-legend").innerHTML =
    `Including ${fmt(st.funds)} pooled-fund CIK profiles, ${fmt(all1)} of ` +
    `${fmt(allTot)} normalized names still appear once, and ${fmt(six)} appear on six or more. ` +
    `These are issuer-reported names and roles.`;

  // who repeats, and in what capacity
  const rep = D.repeatsCo.slice(0, 220);
  $("#rep-body").innerHTML = rep.map(r => `<tr>
      <td class="nm"><button type="button" class="person" data-person="${esc(r.n)}" data-person-type="person" aria-pressed="${isPersonActive(r.n, "person")}">${esc(r.n)}</button></td>
      <td class="num">${r.d}</td>
      <td class="pp">${esc(r.r.slice(0, 2).join(", "))}</td>
      <td class="pp" style="color:var(--ink-3)">${esc(r.ex[0] || "")}</td>
    </tr>`).join("")
    || `<tr><td colspan="4" class="empty">No normalized name appears on two non-fund CIK profiles in this sample.</td></tr>`;
  wirePersons($("#rep-body"));

  // what the repeaters actually do, read off the filings rather than asserted
  const ind = st.repeatInd || [];
  $("#rep-ind").innerHTML = ind.map(([k, v]) =>
    `<tr><td>${esc(k)}</td><td class="num">${fmt(v)}</td></tr>`).join("")
    || `<tr><td colspan="2" class="empty">no repeat names in the sample</td></tr>`;

  const top = D.repeats.slice(0, 12);
  const el = $("#agent-chart");
  const AW = chartW(el), RH = 36;
  el.setAttribute("viewBox", `0 0 ${AW} ${top.length * RH + 4}`);
  el.setAttribute("width", AW);
  el.setAttribute("height", top.length * RH + 4);
  const chartSummary = top.map(r => {
    const role = r.r.filter(x => x !== "not stated")[0] || "role not stated";
    return `${r.n}, ${r.d} issuer profiles, role ${role}`;
  }).join("; ");
  const accessibleName = `Most frequently named parties across the sample: ${chartSummary}.`;
  el.setAttribute("aria-label", accessibleName);
  el.setAttribute("title", accessibleName);
  el.innerHTML = `<title>${esc(accessibleName)}</title>` + top.map((r, i) => {
    const y = i * RH;
    const name = r.n.length > 24
      ? `${r.n.slice(0, 15)}\u2026${r.n.slice(-8)}` : r.n;
    const role = r.r.filter(x => x !== "not stated")[0] || "role not stated";
    return `<text x="0" y="${y + 12}" font-size="11.5" font-family="IBM Plex Mono, monospace"
        fill="#0e1319" title="${esc(r.n)}"><title>${esc(r.n)}</title>${esc(name)}</text>
      <rect x="0" y="${y + 17}" width="${(r.d / top[0].d * (AW * 0.5)).toFixed(1)}" height="3" fill="#b3271d"></rect>
      <text x="0" y="${y + 33}" font-size="11.5" font-family="IBM Plex Mono, monospace"
        fill="#5f6975" title="${esc(r.n)}; ${r.d} issuer profiles; role: ${esc(role)}">${r.d} issuer profiles, as ${esc(role)}</text>`;
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
      ${fmt(st.cos)} non-fund issuer CIKs, ${st.coPct}%</text>
    <text x="${W}" y="43" font-size="11.5" font-family="IBM Plex Mono, monospace" fill="#b3271d" text-anchor="end">
      ${fmt(st.funds)} pooled funds, ${st.fundPct}%</text>`;
}

function renderBlank() {
  const st = D.stats;
  const co = st.investors.co;
  const all = st.investors.all;

  bars($("#ninv-chart"), co.ninvBands, { h: 210, padL: 44 });
  /* The band sentence is assembled from positive EDGAR index-row counts. */
  const bands = co.ninvBands;
  const at = label => (bands.find(b => b[0] === label) || ["", 0])[1];
  const bandsTotal = bands.reduce((s, b) => s + b[1], 0);
  const biggest = bands.reduce((a, b) => (b[1] > a[1] ? b : a), ["", -1]);
  const low = at("1") + at("2");
  const high = at("11-25") + at("26-100") + at("100+");
  const pc = n => Math.round(100 * n / bandsTotal) + "%";
  const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  set("#bk-report", `${fmt(co.reporting)} of ${fmt(co.n)} non-fund EDGAR index rows have a positive investor count; the other ${fmt(co.cachedZeroOrLegacyBlank + co.unreported)} have no positive count. ${fmt(co.cachedZeroOrLegacyBlank)} cached values are zero and may be explicit zeroes or blanks collapsed by an earlier parser; the exact split is unknown.`);
  set("#bk-bands",
    `The largest single band is ${biggest[0] === "1" ? "one investor" : biggest[0]}, ` +
    `with ${fmt(biggest[1])} of the ${fmt(bandsTotal)}. ${pc(low)} report one or two. ` +
    `${pc(high)} report eleven or more.`);

  $("#ninv-sub").textContent =
    `${fmt(co.reporting)} of ${fmt(co.n)} non-fund EDGAR index rows report at least one investor`;

  $("#blank-note").innerHTML =
    `Among the ${fmt(co.reporting)} non-fund EDGAR index rows with a positive
     reported investor count, the median is <b>${fmt(co.medianBackers)}</b>.
     Among the ${fmt(co.checkN)} rows
     with positive reported count and amount sold, the median aggregate amount
     sold divided by the count is <b>${bytes(co.checkMedian)}</b> (Gini
     ${co.checkGini}). This ratio is not an observed individual allocation. The cache's
     zero values may be explicit or may come from blank fields an earlier parser
     stored as zero, so the exact zero-versus-blank split is unknown.`;
  $("#check-sub").textContent =
    `Reported amount sold divided by the reported investor count, for the ` +
    `${fmt(co.checkN)} of ${fmt(co.n)} non-fund EDGAR index rows with a positive ` +
    `reported count and positive amount sold. This does not estimate individual check sizes.`;
  hbars($("#check-chart"), co.checkBands, { rowH: 20, padL: 88, color: "#b3271d" });
  $("#check-legend").innerHTML =
    `Among ${fmt(all.checkN)} of ${fmt(all.n)} EDGAR index rows including funds, with ` +
    `a positive reported count and positive amount sold, the median aggregate-per-investor ratio is ` +
    `${bytes(all.checkMedian)} and the Gini is ${all.checkGini}. Pooled-fund rows ` +
    `include some very high reported sale amounts.`;
}

function renderReceipts() {
  const st = D.stats;
  const co = st.investors.co;
  const lineage = st.amendLineage;
  const matchCount = lineage.complete ? fmt(lineage.exactLinksInSample) : "unknown";
  const lowerBoundText = `At least ${fmt(lineage.lowerBound)} source-confirmed ` +
    `D/A-to-declared-previous-filing link${lineage.lowerBound === 1 ? " is" : "s are"} in this sample.`;
  const rows = [
    ["Population", `${fmt(st.popFilings)} Form D and Form D/A EDGAR index rows from 1 July through 26 September 2026, across ${fmt(st.popDays)} business days. This is a partial-quarter window.`],
    ["Sample", `${fmt(st.sample)} EDGAR index rows representing ${fmt(st.uniqueAccessions)} unique accession numbers, selected with seed ${st.seed} (${st.sampleRate}% of the population).`],
    ["Index rows by type", `${fmt(st.fundFilings)} pooled-fund rows and ${fmt(st.coFilings)} non-fund rows.`],
    ["Issuer profiles", `${fmt(st.issuers)} distinct CIKs: ${fmt(st.funds)} pooled funds and ${fmt(st.cos)} non-fund issuer profiles. ${fmt(st.multiFilingIssuers)} CIKs have multiple sampled index rows.`],
    ["Shared accession rows", `${fmt(st.sharedRows)} sampled rows across ${fmt(st.sharedAccInPopulation)} accessions appear under multiple CIKs in the full local index. ${fmt(st.sharedRowsSampleMultiCik)} rows across ${fmt(st.sharedAccSampleMultiCik)} accessions are repeated under multiple CIKs in this sample. These rows remain in row-based summaries; offering amounts and investor counts can repeat. Joint Item 3 names are shown unassigned and omitted from CIK-level name metrics.`],
    ["Amendment lineage", `${fmt(st.amendments)} sampled rows are Form D/A. ${fmt(lineage.reparsed)} cached D/A rows have been re-fetched and re-parsed; ${fmt(lineage.checked)} have a prior-accession value, ${fmt(lineage.missingField)} parsed without that required value, ${fmt(lineage.fetchFailed)} fetches returned no document, and ${fmt(lineage.parseFailed)} fetched XML documents could not be parsed. ${fmt(lineage.unverified)} legacy cached rows have no recorded lineage inspection. ${lowerBoundText} The source fixture and sampled target record confirm one D/A-to-D pair in the sample (<a class="src" href="${lineage.fixture.source}" target="_blank" rel="noopener">SEC filing</a>). The exact number of in-sample D/A-to-declared-previous-filing links is ${matchCount}.`],
    ["Non-US issuers", `${fmt(st.nonUsTotal)} distinct non-US issuer CIKs are represented.`],
    ["Issuer-related names", `${fmt(st.coNames.distinct)} normalized name keys classified by the script's person-name heuristic across non-fund CIK profiles; ${st.coNames.oncePct}% appear on one profile. These are name matches, not verified identities.`],
    ["Index rows with no heuristic person-name match", `${fmt(st.entityOnlyFilings)} of ${fmt(st.sample)} sampled rows have no name matching the script's person-name heuristic.`],
    ["Investor counts, non-fund EDGAR index rows", `${fmt(co.reporting)} of ${fmt(co.n)} have a positive count. The other ${fmt(co.cachedZeroOrLegacyBlank + co.unreported)} rows have no positive count; ${fmt(co.cachedZeroOrLegacyBlank)} cached values are zero, but may be explicit zeros or blanks collapsed by the earlier parser. The exact split is unknown. Median positive count: ${fmt(co.medianBackers)}.`],
    ["Investor counts, latest sampled profile per non-fund CIK", `${fmt(st.investors.coIssuers.reporting)} of ${fmt(st.investors.coIssuers.n)} profiles have a positive count. The other ${fmt(st.investors.coIssuers.cachedZeroOrLegacyBlank + st.investors.coIssuers.unreported)} include ${fmt(st.investors.coIssuers.cachedZeroOrLegacyBlank)} cached zero values that may be explicit zeros or legacy collapsed blanks; the exact split is unknown.`],
    ["First-sale dates", `${st.firstSaleDatesParsed ? `${fmt(st.firstSaleDatesParsed)} sample rows have a parsed first-sale date.` : "No first-sale date values were captured in the current cache; historical dates are unverified."} ${fmt(st.yetToOccur)} sampled index rows explicitly mark the first sale as yet to occur.`],
    ["Aggregate sold-per-investor ratio", `Among ${fmt(co.checkN)} of ${fmt(co.n)} non-fund EDGAR index rows with both a positive reported investor count and positive amount sold, the median ratio is ${bytes(co.checkMedian)} (Gini ${co.checkGini}). This is an aggregate ratio, not an individual allocation.`],
    ["New Form D deadline", `The SEC says a new Form D notice is due within 15 calendar days after the first sale, when the first investor is irrevocably contractually committed; a Saturday, Sunday, or holiday due date moves to the next business day. Amendments may be required for specific changes or annually while the offering continues. SEC staff says filing is not a condition to Rule 504 or 506 exemption availability; Rule 507 describes potential consequences. See the <a class="src" href="https://www.sec.gov/resources-small-businesses/exempt-offerings/filing-form-d-notice" target="_blank" rel="noopener">SEC filing guide</a>, the <a class="src" href="https://www.sec.gov/about/divisions-offices/division-corporation-finance/frequently-asked-questions-answers-form-d" target="_blank" rel="noopener">Form D FAQ</a>, and <a class="src" href="https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/securities-act-rules" target="_blank" rel="noopener">SEC interpretations</a>.`],
    ["Rule 506", `Rule 506(b) prohibits general solicitation or general advertising. It permits sales to any number of accredited investors and up to 35 non-accredited purchasers in any 90-calendar-day period who can evaluate the merits and risks, alone or with a purchaser representative; the issuer may reasonably believe this condition is met. Rule 506(c) permits general solicitation when every purchaser is accredited and the issuer takes reasonable steps to verify accredited status. See the <a class="src" href="https://www.sec.gov/resources-small-businesses/exempt-offerings/private-placements-rule-506b" target="_blank" rel="noopener">SEC Rule 506 guidance</a> and <a class="src" href="https://www.ecfr.gov/current/title-17/chapter-II/part-230/section-230.506" target="_blank" rel="noopener">17 CFR 230.506</a>.`],
    ["Local cache", `The parsed data file was last modified ${D.meta && D.meta.cacheModified || "date unavailable"}. This is a local file date, not an EDGAR retrieval date.`],
    ["Source", `The cache contains parsed SEC EDGAR <span class="mono">primary_doc.xml</span> records. No enrichment layer is used.`],
    ["Verification", `scripts/verify.py recomputes data-derived counts from <span class="mono">data/formd.jsonl</span> and checks them against this generated file. It also tests the corrected previous-accession XML path against the linked SEC source fixture.`],
    ["Cosign launch copy", `The public endorsements and early-discovery descriptions are attributed in section 1 of this page. The launch copy does not establish the hypothetical threshold, weighting, ranking, or amplification settings used in section 6 of this page.`],
  ];
  $("#receipts").innerHTML = rows.map(([k, v]) =>
    `<tr><th scope="row">${k}</th><td>${v}</td></tr>`).join("");
}

/* ------------------------------------------------------------ the model */

const sim = {
  n: 2000, seed: 20, boost: 1.5, vis: 3, w: 0.85, eff: 0.06, reach: 0.3, noise: 0.5, cohort: 0.25,
  series: [], last: null, flat: null, lock: null, lockFlat: null,
  capLow: null, capHigh: null, capThin: null, capFat: null, capAmpLo: null, capAmpHi: null,
  axis: null, queued: null, dragging: false, extremesFresh: false,
};

/* Two workers. The first draws the curve and streams it back while it computes.
   The second recomputes the all-discovery comparison, which is what the dashed
   line sits at, so that line moves with the knob instead of jumping when the
   pointer is released. The six numbers the paragraph quotes cost six more full
   runs, so those are only asked for once the drag has settled.
   Splitting them across two workers is what keeps a slider tick at about 35ms
   instead of the 65ms it would take to run both in one. */
let wA = null, wB = null, busyB = false, activeB = null;
let pendingControl = null, pendingExtremes = null, pendingA = false;
let runSeq = 0;
let drawQueued = false;

function startWorkers() {
  if (wA) return;
  wA = new Worker("model-worker.js");
  wA.onmessage = e => {
    const d = e.data;
    if (d.id !== runSeq) return;              // a newer run superseded this one
    if (d.stage === 1) {
      sim.series = d.series;
      scheduleDraw();
      return;
    }
    sim.series = d.series;
    sim.last = d.last;
    sim.lock = d.lock;
    pendingA = false;
    scheduleDraw();
    if (sim.queued) { const q = sim.queued; sim.queued = null; sendA(q); }
    else if (!sim.dragging) requestExtremes();
  };
  wA.onerror = () => { pendingA = false; };

  wB = new Worker("model-worker.js");
  wB.onmessage = e => {
    const d = e.data;
    busyB = false;
    activeB = null;
    if (d.id === runSeq) {
      if (d.kind === "control") {
        sim.flat = d.flat;
        sim.lockFlat = d.lockFlat;
        scheduleDraw();
      } else {
        sim.capLow = d.capLow;
        sim.capHigh = d.capHigh;
        sim.capThin = d.capThin;
        sim.capFat = d.capFat;
        sim.capAmpLo = d.capAmpLo;
        sim.capAmpHi = d.capAmpHi;
        sim.extremesFresh = true;
        scheduleDraw();
      }
    }
    drainB();
  };
  wB.onerror = () => { busyB = false; activeB = null; drainB(); };
}

/* The second worker takes one job at a time and always prefers the newest, so
   dragging a knob never queues up a backlog of stale comparison runs. */
function askB(kind, cfg) {
  const job = { kind, cfg, id: runSeq };
  if (kind === "control") pendingControl = job;
  else pendingExtremes = job;
  drainB();
}

function drainB() {
  if (busyB) return;
  // A current run's control line is needed for the readout. Keep it ahead of
  // the optional extremes sweep if both accumulated while this worker was busy.
  const job = pendingControl || pendingExtremes;
  if (!job) return;
  if (job.kind === "control") pendingControl = null;
  else pendingExtremes = null;
  busyB = true;
  activeB = job;
  wB.postMessage({ ...job.cfg, kind: job.kind, id: job.id });
}

function sendA(cfg) {
  startWorkers();
  pendingA = true;
  const id = ++runSeq;
  pendingControl = null;
  pendingExtremes = null;
  // Each configuration gets its own vertical scale. Clear prior-run points
  // before either worker can reply, so an early control reply cannot pin the
  // next run to the old curve's range.
  sim.series = [];
  sim.last = null;
  sim.flat = null;
  sim.lock = null;
  sim.lockFlat = null;
  sim.axis = null;
  sim.extremesFresh = false;                  // the paragraph quotes the old run
  $("#sim-verdict").textContent = "";
  $("#sim-readout").innerHTML = "";
  $("#sim-legend").textContent = "";
  $("#sim-status").textContent = "simulating";
  $("#sim-prose-status").textContent = "computing this run";
  scheduleDraw();
  wA.postMessage({ ...cfg, kind: "main", id });
  askB("control", cfg);
}

/* One curve run at a time. A knob move during a run replaces the queued one
   rather than adding to it. */
function runModel() {
  const cfg = { ...sim };
  if (pendingA) { sim.queued = cfg; return; }
  sendA(cfg);
}

/* Called when the reader stops moving a knob. The six numbers the paragraph
   quotes cost six more runs, so they wait for this. */
function requestExtremes() {
  if (sim.extremesFresh ||
      pendingExtremes && pendingExtremes.id === runSeq ||
      activeB && activeB.kind === "extremes" && activeB.id === runSeq) return;
  askB("extremes", { ...sim });
}

function markSettled() {
  sim.dragging = false;
  if (!pendingA && !sim.queued) requestExtremes();
}

function scheduleDraw() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => { drawQueued = false; drawSim(); });
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
  if (!series.length && !last) {
    sim.axis = null;
    $("#sim-legend").textContent = "";
    $("#sim-status").textContent = "simulating";
    return;
  }

  /* The capture ratio is at its maximum at round zero, when the day-one cohort
     holds everything, so the first point of a run is its peak. Pinning the axis
     to that point means the line grows into a stable frame instead of rescaling
     under itself on every streamed batch. */
  const tMax = last ? Math.max(1, last.t) : 1000;
  if (sim.axis == null && series.length) sim.axis = Math.max(2, Math.ceil(series[0][1] * 2) / 2);
  if (flat) sim.axis = Math.max(sim.axis || 2, Math.ceil(flat.capture * 2) / 2);
  const yMax = sim.axis || 4;

  const iw = W - padL - padR, ih = H - padT - padB;
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
    ctx.fillText(parity ? "1x" : v.toFixed(1) + "x", padL - 7, y + 4);
  }
  ctx.textAlign = "center";
  ctx.fillStyle = "#7d8894";
  for (let g = 0; g <= 5; g++) {
    const x = padL + (g / 5) * iw;
    const label = g === 5 ? `${Math.round((g / 5) * tMax)} rounds`
      : String(Math.round((g / 5) * tMax));
    // the last tick carries a unit, so it is flush with the plot edge rather
    // than centred on it, which would push it off the canvas
    ctx.textAlign = g === 5 ? "right" : "center";
    ctx.fillText(label, g === 5 ? W - padR : x, H - 10);
  }

  // The five regular ticks can skip 1x when the initial-cohort ratio is large.
  // Keep parity visible as its own reference on every vertical scale.
  const parityIsTick = Array.from({ length: 5 }, (_, g) => (g / 4) * yMax)
    .some(v => Math.abs(v - 1) < 0.01);
  if (!parityIsTick) {
    const y = Math.round(yOf(1)) + 0.5;
    ctx.strokeStyle = "#3d4a56";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.fillStyle = "#aab4bf";
    ctx.textAlign = "right";
    ctx.fillText("1x", padL - 7, y + 4);
  }

  if (flat) {
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "#6b7885";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(padL, yOf(flat.capture));
    ctx.lineTo(W - padR, yOf(flat.capture));
    ctx.stroke();
    ctx.restore();
  }

  if (series.length) {
    ctx.strokeStyle = "#7fd1b4";
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    for (let i = 0; i < series.length; i++) {
      const x = padL + (series[i][0] / tMax) * iw;
      const y = yOf(series[i][1]);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke();
    // the head of the line, so a run still in flight looks in flight
    const head = series[series.length - 1];
    if (!last || head[0] < tMax) {
      ctx.fillStyle = "#7fd1b4";
      ctx.beginPath();
      ctx.arc(padL + (head[0] / tMax) * iw, yOf(head[1]), 2.6, 0, 6.284);
      ctx.fill();
    }
  }

  const headCap = last ? last.capture : (series.length ? series[series.length - 1][1] : null);
  $("#sim-legend").innerHTML = [
    ["#7fd1b4", headCap == null ? "starting cohort" : `starting cohort, ${headCap.toFixed(2)}x its share`],
    ["#6b7885", flat ? `all discovery, ${flat.capture.toFixed(2)}x` : "all discovery"],
  ].map(([col, l]) => `<span><i style="background:${col}"></i>${l}</span>`).join("");
  $("#sim-status").textContent = last
    ? `${fmt(last.t)} rounds · ${fmt(last.visible)} visible`
    : "simulating";

  const cards = [
    [last ? fmt(last.visible) : "\u2026", "profiles visible after the run"],
    [last ? last.capture.toFixed(2) + "x" : "\u2026",
     "how much more modeled score the starting cohort holds than its share of profiles"],
    [flat ? flat.capture.toFixed(2) + "x" : "\u2026",
     "the same, with every endorsement arriving through discovery"],
    [sim.lock == null ? "\u2026" : (sim.lock * 100).toFixed(0) + "%",
     `of the top 1% after 20 rounds are still in the top 1% after ${last ? fmt(last.t) : "the run"} rounds`],
    [sim.lockFlat == null ? "\u2026" : (sim.lockFlat * 100).toFixed(0) + "%",
     "the same, with every endorsement arriving through discovery"],
  ];
  $("#sim-readout").innerHTML = cards.map(([n, l], i) =>
    `<div><span class="n${i === 0 ? "" : " warn"}">${n}</span><span class="l">${l}</span></div>`).join("");

  if (last && flat && sim.extremesFresh) $("#sim-verdict").innerHTML = verdictHtml(last, flat);
  const pend = $("#sim-prose-status");
  if (pend) {
    pend.textContent = sim.extremesFresh ? ""
      : (last && flat ? "recomputing the ranges this paragraph quotes" : "");
    $("#sim-verdict").classList.toggle("pending", !sim.extremesFresh);
  }
}

function verdictHtml(last, flat) {
  const x = v => (v == null ? "?" : v.toFixed(2) + "x");
  const cohortSize = last.cohortCount;
  const cohortFraction = last.cohortFraction;
  const lock = sim.lock == null ? null : (sim.lock * 100).toFixed(0) + "%";
  const lockF = sim.lockFlat == null ? null : (sim.lockFlat * 100).toFixed(0) + "%";
  const ampSpread = sim.capAmpLo != null && sim.capAmpHi != null
    ? Math.abs(100 * (sim.capAmpHi - sim.capAmpLo) / sim.capAmpLo) : null;

  return `The modeled starting cohort is
    <span class="mono">${fmt(cohortSize)}</span> of <span class="mono">${fmt(sim.n)}</span> profiles,
    or ${(cohortFraction * 100).toFixed(1)}% of the network. At the model's
    ${fmt(last.t)}-round endpoint they hold
    <b>${last.capture.toFixed(2)}x</b> their share of the total modeled score, and the
    model stops here. In the all-discovery control,
    the same cohort lands at <b>${flat ? flat.capture.toFixed(2) : "?"}x</b>.
    ${lock === null || lockF === null ? "" : `Rank order is the other half of it.
     <b>${lock}</b> of the profiles in the top 1% after twenty rounds are still in
    the top 1% after ${fmt(last.t)} rounds; the all-discovery run gets ${lockF}.`}

    These are outcomes under the selected model assumptions, not measurements of
    Cosign behavior. At everything else held fixed, moving the starting-cohort
    share from 2% of the network to 60%
    moves the capture ratio from ${x(sim.capThin)} to ${x(sim.capFat)}. Moving
    the visibility threshold from one
    endorsement to twelve moves it from ${x(sim.capLow)} to ${x(sim.capHigh)}.
    The discovery share is one of the model assumptions. The day-one cohort
    endorsement boost moves it from
    ${x(sim.capAmpLo)} to ${x(sim.capAmpHi)}, a spread of about
    ${ampSpread == null ? "?" : ampSpread.toFixed(0) + "%"}. These are outcomes of
    this simulation's assumptions. Cosign's launch copy mentions discovery, but
    does not document any of these settings.`;
}

function wireSim() {
  const map = [["n", "n"], ["seed", "seed"], ["boost", "boost"], ["vis", "vis"], ["w", "w"],
               ["eff", "eff"], ["rr", "reach"], ["noise", "noise"], ["co", "cohort"]];
  map.forEach(([id, key]) => {
    const el = $("#k-" + id);
    const out = $("#v-" + id);
    if (!el || !out) throw new Error("sim knob #" + id + " is not in the page");
    const readKnob = () => {
      sim[key] = key === "cohort" ? Number(el.value) / 100 : parseFloat(el.value);
      out.textContent = key === "cohort" ? Math.round(sim.cohort * 100) + "%"
        : key === "boost" ? Number(sim.boost).toFixed(2) + "×"
        : ["w", "eff", "reach", "noise"].includes(key) ? Number(sim[key]).toFixed(2)
        : fmt(el.value);
    };
    // A range input fires `input` continuously while the thumb is held, so the
    // curve redraws as it moves. While a drag is in progress the worker is told
    // to skip the six comparison runs, which is the difference between a redraw
    // costing about 30ms and about 250ms.
    el.addEventListener("pointerdown", () => { sim.dragging = true; });
    el.addEventListener("input", () => { readKnob(); runModel(); });
    for (const done of ["pointerup", "pointercancel", "change", "blur"]) {
      el.addEventListener(done, () => { if (sim.dragging) markSettled(); });
    }
    // keyboard moves are discrete, so each one settles immediately
    el.addEventListener("keydown", () => { sim.dragging = false; markSettled(); });
    readKnob();
  });
  $("#sim-run").addEventListener("click", () => {
    sim.seed = sim.seed >= 300 ? 1 : sim.seed + 1;
    $("#k-seed").value = sim.seed;
    $("#v-seed").textContent = sim.seed;
    markSettled();
    runModel();
  });
  $("#sim-shuffle").addEventListener("click", () => {
    sim.seed = 1 + Math.floor(Math.random() * 300);
    $("#k-seed").value = sim.seed;
    $("#v-seed").textContent = sim.seed;
    markSettled();
    runModel();
  });
  runModel();
}

/* Charts are sized from their container, so a width change means redrawing them.
   The model does not need re-running, only its canvas does. */
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
  $("#kicker-n").textContent = `${fmt(st.sample)} of ${fmt(st.popFilings)} EDGAR index rows · ${fmt(st.popDays)} business days`;
  $("#by-f").textContent = fmt(st.sample);
  $("#by-acc").textContent = fmt(st.uniqueAccessions);
  $("#chrome-stat").textContent = "Sample ends 26 Sep 2026 · partial quarter";
  $("#rail-n").textContent = `${fmt(st.sample)} EDGAR index rows · ${fmt(st.cos)} non-fund CIK profiles`;
  $("#foot-date").textContent = "Sample window: 1 July–26 September 2026 (partial quarter)";

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
    `The ${fmt(st.sample)} sampled EDGAR index rows cover <span class="mono">${fmt(st.uniqueAccessions)}</span>
     unique accession numbers and represent <span class="mono">${fmt(st.issuers)}</span>
     distinct issuer CIK profiles. Across those profiles, the name rules produce
     <span class="mono">${fmt(people.appearances)}</span> name matches under the person-name heuristic.
     The script's name heuristic finds no person-like name in <span class="mono">${fmt(st.entityOnlyFilings)}</span>
     EDGAR index rows. Some latest filing values are joint-offering fields repeated under co-issuer CIKs;
     the directory labels those rows. Shared Item 3 names are displayed separately without CIK attribution
     and are omitted from the profile name graph.`;

  const yetSaleCount = $("#yet-sale-n");
  if (yetSaleCount) yetSaleCount.textContent = fmt(st.yetToOccur);

  $("#fund-n").textContent = fmt(st.funds);
  $("#iss-n").textContent = fmt(st.issuers);
  const nu = $("#nonus");
  if (nu) nu.textContent = fmt(st.nonUsTotal);
  const noamt = $("#noamount");
  if (noamt) noamt.textContent = fmt(st.fundsNoAmount);
  for (const [id, v] of [["#co-tech", fmt(st.coTech)], ["#co-n", fmt(st.cos)],
                         ["#co-other", fmt(st.coOther)]]) {
    const e = $(id); if (e) e.textContent = v;
  }

  $("#graphtext").innerHTML =
    `This graph links normalized name keys classified by the script's person-name
     heuristic from Form D's related-person lists to the issuer CIKs that report them. It is a graph of issuer-side
     filing roles, not endorsements or investor identities. Among
     <span class="mono">${fmt(st.cos)}</span> non-fund issuer profiles, the name
     rules yield <span class="mono">${fmt(st.coNames.appearances)}</span>
     appearance links across <span class="mono">${fmt(st.coNames.distinct)}</span>
     distinct name keys.`;

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
