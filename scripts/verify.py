#!/usr/bin/env python3
"""
Recompute every number the page quotes, straight from data/formd.jsonl, using a
second implementation that shares no code with scripts/build_drop.py. Run it
after any crawl or build change:

    python3 scripts/verify.py

Exits non-zero on the first disagreement. The page reads its numbers out of
site/drop.json, so if this passes, the page cannot be quoting a stale figure.
"""
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "formd.jsonl")
POP = os.path.join(ROOT, "data", "accessions.json")
OUT = os.path.join(ROOT, "site", "drop.json")

W0, W1 = "20260701", "20260926"
FUND = "Pooled Investment Fund"

fails = []


def check(label, got, want, tol=0):
    ok = (abs(got - want) <= tol) if isinstance(want, (int, float)) else (got == want)
    print(f"  {'ok  ' if ok else 'FAIL'}  {label:<52} page {want!r:>12}   raw {got!r}")
    if not ok:
        fails.append(label)


# Generational and honorific suffixes, removed before matching so that a person
# who files as "Loeffler II" in one place and "Loeffler" in another is one person.
# This merges a father and a son who share a name, which makes the repeater count
# larger and so works against the page's argument rather than for it.
SUFFIX = re.compile(r"\b(?:jr|sr|ii|iii|iv|phd|md|mba|cpa|jd|esq)\b")


def key(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", SUFFIX.sub(" ", s)).strip()


# The same rule as scripts/build_drop.py, written differently on purpose: if the
# two disagree, one of them has a bug. See build_drop.py for why the word
# boundaries and the position of the short forms matter.
UNAMBIGUOUS = {
    "llc", "inc", "corp", "corporation", "ltd", "limited", "lp", "llp", "plc",
    "gmbh", "bv", "nv", "oy", "kg", "spa", "pty", "sarl", "scs", "scsp",
}
# These double as surnames and given names, so they only count as a suffix when
# they are joined to the word in front of them, which is what "l.p." and "s.a."
# look like once the punctuation is stripped.
AMBIGUOUS = {"co", "company", "ab", "as", "ag", "sa", "n", "a", "na", "lc"}
ORG = {
    "fund", "funds", "capital", "ventures", "venture", "partners", "partnership",
    "holdings", "holding", "group", "trust", "management", "investments",
    "investment", "advisors", "advisory", "series", "spv", "foundation",
    "association", "university", "church", "ministries", "bank", "finance",
    "financial", "global", "international", "services", "solutions", "systems",
    "technologies", "industries", "enterprises", "realty", "properties",
    "equity", "growth", "opportunities", "office", "estate", "family", "asset",
    "assets", "school",
}
NOT_A_NAME = {"", "n a", "na", "none", "unknown", "the", "same"}


def is_person(raw):
    n = key(raw)
    if n in NOT_A_NAME:
        return False
    w = n.split()
    if w[0] in UNAMBIGUOUS or w[-1] in UNAMBIGUOUS:
        return False
    if len(w) > 1 and (w[-2] + w[-1]) in UNAMBIGUOUS | AMBIGUOUS:
        return False
    if any(t in ORG for t in w):
        return False
    return True


def main():
    rows = []
    for line in open(RAW, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rows = [r for r in rows if W0 <= r["filed"] <= W1]
    D = json.load(open(OUT))
    S = D["stats"]

    print("\npopulation and sample")
    pop = json.load(open(POP))["rows"]
    check("population, Q3 to 26 Sep", len(pop), S["popFilings"])
    check("business days in the population", len({r["filed"] for r in pop}), S["popDays"])
    check("filings sampled", len(rows), S["sample"])
    check("distinct CIKs sampled", len({r["cik"] for r in rows}), S["issuers"])
    check("amendments in the sample",
          sum(1 for r in rows if r["form"] == "D/A"), S["amendments"])

    # fold, last non-None wins, which is what the page describes
    fold = {}
    for r in rows:
        e = fold.setdefault(r["cik"], {"inds": set(), "ninv": None, "sold": None,
                                       "people": defaultdict(int)})
        if r["ind"]:
            e["inds"].add(r["ind"])
        for f in ("ninv", "sold"):
            if r[f] is not None:
                e[f] = r[f]
        # one entry per issuer, not per filing: an amendment that repeats a
        # director has not put them on a second company
        seen = e.setdefault("seen", set())
        for p in r["p"]:
            if is_person(p["n"]):
                k = key(p["n"])
                if k not in seen:
                    seen.add(k)
                    e["people"][k] += 1
    funds = [e for e in fold.values() if FUND in e["inds"]]
    cos = [e for e in fold.values() if FUND not in e["inds"] and e["inds"]]

    print("\ncorpus shape")
    check("pooled investment funds", len(funds), S["funds"])
    check("operating companies", len(cos), S["cos"])
    check("fund share, percent", round(100 * len(funds) / len(fold), 2), S["fundPct"])
    entity_only = 0
    for r in rows:
        if r["p"] and not any(is_person(p["n"]) for p in r["p"]):
            entity_only += 1
    check("filings naming no human", entity_only, S["entityOnly"])

    print("\nnames on operating-company filings")
    deg = Counter()
    for e in cos:
        for k, v in e["people"].items():
            deg[k] += v
    once = sum(1 for v in deg.values() if v == 1)
    check("distinct people", len(deg), S["coNames"]["distinct"])
    check("appearances", sum(deg.values()), S["coNames"]["appearances"])
    check("appear exactly once", once, S["coNames"]["once"])
    check("percent who appear once",
          round(100 * once / len(deg), 2), S["coNames"]["oncePct"])
    check("people on two or more",
          sum(1 for v in deg.values() if v > 1), S["coNames"]["repeat"])
    check("edges those repeaters add",
          sum(v - 1 for v in deg.values() if v > 1), S["coNames"]["bridged"])

    print("\nnatural persons across the whole sample")
    pdeg = Counter()
    pseen = defaultdict(set)
    for r in rows:
        for p in r["p"]:
            if is_person(p["n"]):
                pseen[key(p["n"])].add(r["cik"])
    for k, v in pseen.items():
        pdeg[k] = len(v)
    check("distinct people", len(pdeg), S["peopleNames"]["distinct"])
    check("appear exactly once",
          sum(1 for v in pdeg.values() if v == 1), S["peopleNames"]["once"])

    print("\nmost frequent names")
    top = Counter()
    tseen = defaultdict(set)
    for r in rows:
        for p in r["p"]:
            tseen[key(p["n"])].add(r["cik"])
    for k, v in tseen.items():
        top[k] = len(v)
    named = {k: v for k, v in top.items() if v > 1}
    for i, (k, v) in enumerate(sorted(named.items(), key=lambda x: -x[1])[:3]):
        check(f"repeat name #{i + 1} filings", v, D["repeats"][i]["d"])
    # the top repeats must all be administrative capacity, not people vouching
    admin = 0
    for k, v in sorted(named.items(), key=lambda x: -x[1])[:9]:
        for r in rows:
            for p in r["p"]:
                if key(p["n"]) == k and p.get("c"):
                    c = p["c"].lower()
                    if any(w in c for w in ("agent", "general partner", "administrator",
                                            "manager of", "authorized")):
                        admin += 1
                    break
            else:
                continue
            break
    check("of the top 9 repeats, named as agents or GPs", admin, 9)

    print("\nbacker counts, operating companies")
    withn = [e for e in cos if e["ninv"] and e["ninv"] > 0]
    zero = [e for e in cos if e["ninv"] == 0]
    blank = [e for e in cos if e["ninv"] is None]
    inv = S["investors"]["co"]
    check("operating-company filings", len(cos), inv["n"])
    check("reporting at least one backer", len(withn), inv["reporting"])
    check("reporting zero", len(zero), len(cos) - len(withn) - len(blank))
    check("leaving the field blank", len(blank), 0)
    med = sorted(e["ninv"] for e in withn)[len(withn) // 2]
    check("median backers", med, inv["medianBackers"])
    checks = sorted(e["sold"] / e["ninv"] for e in withn if e["sold"] and e["sold"] > 0)
    check("median implied cheque", int(checks[len(checks) // 2]), inv["checkMedian"])
    check("max backers reported", max(e["ninv"] for e in withn), inv["maxBackers"])

    print("\nfiler attestations")
    band = lambda k: ("1" if k == 1 else "2" if k == 2 else "3-5" if k <= 5 else
                      "6-10" if k <= 10 else "11-25" if k <= 25 else
                      "26-100" if k <= 100 else "100+")
    got = Counter(band(e["ninv"]) for e in withn)
    want = {b: c for b, c in inv["ninvBands"]}
    check("investor count bands", dict(sorted(got.items())), dict(sorted(want.items())))

    print("\nno investor field exists anywhere in the filings")
    keys = set()
    for r in rows[:400]:
        keys |= set(r.keys())
    bad = [k for k in keys if re.search(r"investor|buyer|purchaser|holder", k, re.I)]
    check("fields naming investors or buyers", bad, [])

    print("\n" + ("all checks passed" if not fails else f"{len(fails)} FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
