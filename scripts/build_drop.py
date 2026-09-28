#!/usr/bin/env python3
"""
Turn the raw Form D crawl into the one JSON file the drop reads.

Everything the page shows is computed here so the numbers on screen can be
reproduced by re-running this file. Run it after scripts/fetch_formd.py.
"""
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "formd.jsonl")
OUT = os.path.join(ROOT, "site", "drop.json")
ACCESSIONS = os.path.join(ROOT, "data", "accessions.json")

WINDOW = ("20260701", "20260926")
SAMPLE_SEED = 20260926

# The single largest slice of Form D. Anything filed under this industry group is
# an asset manager or a fund vehicle rather than an operating company, and the
# page reports the corpus both ways because the two stories are different.
FUND = "Pooled Investment Fund"

# A related person on Form D is often a legal entity, and telling those two apart
# decides the headline numbers, so the rule is written down rather than
# improvised. Five tests, in order:
#
#   1. nothing usable, or a placeholder such as "n/a", is not a person
#   2. an unambiguous legal form anywhere in the name, whole word, is not a person
#      (llc, inc, lp, gmbh and so on; these cannot be surnames)
#   3. an ambiguous short form only counts at the end of the name, or as the last
#      two words joined, because "sa" and "as" are surnames and "l p" is a
#      suffix that normalises into two tokens
#   4. an organisation word used as a whole word is not a person
#   5. anything else is a person
#
# Word boundaries are not optional. An earlier version had none, which quietly
# filed "Salene Hitchcock-Gear" as a company because "hitchcock" contains "co",
# and "Reshma Abraham" likewise on "ab". It moved 1,251 names to 1,508 and the
# repeater count from 31 to 36. The all-caps test that used to be rule 5 never
# fired on this corpus and has been dropped rather than left to misfire on the
# next one.
# Generational and honorific suffixes, dropped before matching so that
# "Loeffler II" and "Loeffler" are the same person.
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|phd|md|mba|cpa|jd|esq)\b", re.I)

FORMS_UNAMBIGUOUS = {
    "llc", "inc", "corp", "corporation", "ltd", "limited", "lp", "llp", "plc",
    "gmbh", "bv", "nv", "oy", "kg", "spa", "pty", "sarl", "scs", "scsp",
}
FORMS_AMBIGUOUS = {"co", "company", "ab", "as", "ag", "sa", "n", "a", "na", "lc"}
ORG_WORDS = {
    "fund", "funds", "capital", "ventures", "venture", "partners", "partnership",
    "holdings", "holding", "group", "trust", "management", "investments",
    "investment", "advisors", "advisory", "series", "spv", "foundation",
    "association", "university", "church", "ministries", "bank", "finance",
    "financial", "global", "international", "services", "solutions", "systems",
    "technologies", "industries", "enterprises", "realty", "properties",
    "equity", "growth", "opportunities", "office", "estate", "family", "asset",
    "assets", "school",
}
PLACEHOLDERS = {"n a", "na", "none", "unknown", "the", "same"}


def norm(s):
    """Fold a name down to comparable words: strip accents, drop punctuation and
    case, collapse whitespace. "L.P." and "L P" have to land on the same string
    for the suffix tests to work."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace(".", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_entity(name):
    """Is this related person a legal entity rather than a human?"""
    n = norm(name)
    if not n or n in PLACEHOLDERS:
        return True
    words = n.split()
    if words[0] in FORMS_UNAMBIGUOUS or words[-1] in FORMS_UNAMBIGUOUS:
        return True
    if len(words) > 1:
        # "l p" and "s a" arrive as two tokens because the periods are stripped,
        # so the suffix tests run against the joined tail as well as the whole word
        tail = words[-2] + words[-1]
        if tail in FORMS_UNAMBIGUOUS or tail in FORMS_AMBIGUOUS:
            return True
    if ORG_WORDS.intersection(words):
        return True
    return False


def person_key(name):
    return re.sub(r"\s+", " ", SUFFIX.sub("", norm(name))).strip()


def pct(n, d):
    return round(100.0 * n / d, 2) if d else 0.0


def gini(values):
    xs = sorted(v for v in values if v is not None and v >= 0)
    n = len(xs)
    total = sum(xs)
    if n == 0 or total == 0:
        return None
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return round((2.0 * cum) / (n * total) - (n + 1.0) / n, 3)


def deg_hist(idx, cap=5):
    """How many issuers each named person appears on, as a histogram."""
    d = Counter(v["d"] for v in idx.values())
    out = []
    for k in range(1, cap + 1):
        if d.get(k):
            out.append([f"{k} compan" + ("y" if k == 1 else "ies"), d[k]])
    over = sum(c for k, c in d.items() if k > cap)
    if over:
        out.append([f"{cap + 1}+ companies", over])
    return out


def repeat_industries(idx, by_name):
    """What sort of business are the repeat names on? The index carries example
    issuer names, so the lookup goes through the name rather than a row number."""
    c = Counter()
    for v in idx.values():
        if v["d"] < 2:
            continue
        for nm in v["ex"]:
            c[by_name.get(nm, "unclassified")] += 1
    return c.most_common(8)


def band_counts(vals, bands):
    out = []
    for lo, hi, label in bands:
        c = sum(1 for v in vals if lo <= v <= hi)
        if c or label:
            out.append([label, c])
    return out


def load():
    recs = []
    for line in open(SRC, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if WINDOW[0] <= r["filed"] <= WINDOW[1]:
            recs.append(r)
    recs.sort(key=lambda r: r["acc"])
    return recs


def fold(recs):
    """One record per issuer, with amendments merged onto the original."""
    issuers = {}
    for r in recs:
        cur = issuers.get(r["cik"])
        if cur is None:
            cur = {
                "acc": r["acc"], "cik": r["cik"], "name": r["name"], "form": r["form"],
                "filed": r["filed"], "ind": r["ind"], "ftype": r["ftype"],
                "etype": r["etype"], "juris": r["juris"], "state": r["state"],
                "offer": r["offer"], "offerInd": r["offerIndef"], "sold": r["sold"],
                "ninv": r["ninv"], "c506": r["506c"], "amends": 0, "p": {},
                "proceeds": r["proceeds"], "fees": r["fees"], "comm": r["comm"],
                "secs": r["secs"], "yet": r["yet"], "bcombo": r["bcombo"],
                "prev": r["prev"], "sale0": r["sale0"], "sig": r["sig"],
            }
            issuers[r["cik"]] = cur
        else:
            cur["amends"] += 1
            for f in ("sold", "ninv", "offer", "proceeds"):
                if r[f] is not None:
                    cur[f] = r[f]
        for p in r["p"]:
            k = person_key(p["n"])
            if not k:
                continue
            slot = cur["p"].setdefault(k, {
                "n": p["n"], "r": [], "e": is_entity(p["n"]), "c": p.get("c"),
            })
            for rel in p["r"]:
                if rel not in slot["r"]:
                    slot["r"].append(rel)
    return issuers


def main():
    recs = load()
    issuers = fold(recs)

    # the directory carries only what the page reads. Everything else a filing
    # holds stays in the raw crawl, and the handful of complete filings rendered
    # as forms keep their full record.
    out_issuers = []
    for cur in issuers.values():
        people = [p for p in cur["p"].values() if not p["e"]]
        ents = [p for p in cur["p"].values() if p["e"]]
        out_issuers.append({
            "i": cur["acc"], "c": cur["cik"], "n": cur["name"], "f": cur["filed"],
            "m": cur["amends"], "g": cur["ind"], "s": cur["state"],
            "I": cur["offerInd"], "d": cur["sold"], "k": cur["ninv"],
            "6": cur["c506"], "R": sorted({r for p in people for r in p["r"]}),
            "P": [p["n"] for p in people][:8], "E": [p["n"] for p in ents][:4],
        })

    funds = [i for i in out_issuers if i["g"] == FUND]
    cos = [i for i in out_issuers if i["g"] != FUND]

    # ---- who is named, and how often
    def index(rows, want_people):
        """rows: list of (name, entity_flag, roles, filed, issuer_name) tuples"""
        out = defaultdict(lambda: {"d": 0, "r": Counter(), "m": Counter(), "ex": []})
        for name, ent, roles, filed, iname in rows:
            if want_people and ent:
                continue
            k = person_key(name)
            if not k:
                continue
            s = out[k]
            s["d"] += 1
            for r in roles or ["not stated"]:
                s["r"][r] += 1
            s["m"][filed[:6]] += 1
            if len(s["ex"]) < 6:
                s["ex"].append(iname)
        return out

    def tuples(rows):
        for cur in rows:
            for slot in cur["p"].values():
                yield (slot["n"], slot["e"], slot["r"], cur["filed"], cur["name"])

    cos_folded = [c for c in issuers.values() if c["ind"] != FUND]
    idx_all = index(tuples(issuers.values()), False)
    idx_people = index(tuples(issuers.values()), True)
    idx_named_all = index(tuples(issuers.values()), True)   # people, every filing
    idx_cos = index(tuples(cos_folded), True)
    idx_entities = index(tuples(issuers.values()), None)
    ent_only = index(tuples(issuers.values()), "entity")

    def profile(m):
        return {
            "distinct": len(m),
            "appearances": sum(v["d"] for v in m.values()),
            "once": sum(1 for v in m.values() if v["d"] == 1),
            "oncePct": pct(sum(1 for v in m.values() if v["d"] == 1), len(m)),
            "repeat": sum(1 for v in m.values() if v["d"] > 1),
            "bridged": sum(v["d"] - 1 for v in m.values() if v["d"] > 1),
        }

    display = {}
    for cur in issuers.values():
        for slot in cur["p"].values():
            display.setdefault(person_key(slot["n"]), slot["n"])

    def people_list(m, limit=400):
        rows = []
        for k, v in m.items():
            if v["d"] < 2:
                continue
            rows.append({
                "n": display.get(k, k), "d": v["d"],
                "r": [r for r, _ in v["r"].most_common(3)],
                "m": dict(v["m"]), "ex": v["ex"],
            })
        rows.sort(key=lambda r: (-r["d"], r["n"]))
        return rows[:limit]

    repeats_all = people_list(idx_all)
    repeats_cos = people_list(idx_cos)

    # ---- the one field that counts backers
    def investor_stats(rows, label):
        with_n = [i for i in rows if i["k"] and i["k"] > 0]
        checks = [i["d"] / i["k"] for i in with_n if i["d"] and i["d"] > 0]
        checks.sort()
        return {
            "label": label,
            "n": len(rows),
            "reporting": len(with_n),
            "reportingPct": pct(len(with_n), len(rows)),
            "medianBackers": int(sorted(i["k"] for i in with_n)[len(with_n) // 2]) if with_n else 0,
            "maxBackers": max((i["k"] for i in with_n), default=0),
            "checkMedian": int(checks[len(checks) // 2]) if checks else 0,
            "checkGini": gini(checks),
            "checks": checks,
            "ninvBands": band_counts(
                [i["k"] for i in with_n],
                [(1, 1, "1"), (2, 2, "2"), (3, 5, "3-5"), (6, 10, "6-10"),
                 (11, 25, "11-25"), (26, 100, "26-100"), (101, 10**9, "100+")]),
            "checkBands": band_counts(checks, [
                (0, 25_000, "under $25k"), (25_001, 100_000, "$25k to $100k"),
                (100_001, 500_000, "$100k to $500k"), (500_001, 2_000_000, "$500k to $2M"),
                (2_000_001, 10_000_000, "$2M to $10M"), (10_000_001, 10**15, "over $10M")]),
        }

    inv_all = investor_stats(out_issuers, "every filing in the sample")
    inv_cos = investor_stats(cos, "operating companies only")

    # ---- a few complete filings, rendered as the actual form
    def full(r):
        return {
            "acc": r["acc"], "cik": r["cik"], "name": r["name"], "form": r["form"],
            "filed": r["filed"], "juris": r["juris"], "etype": r["etype"],
            "yinc": r["yinc"], "city": r["city"], "state": r["state"], "prev": r["prev"],
            "p": [{"n": p["n"], "r": p["r"], "c": p["c"], "st": p["st"],
                   "e": is_entity(p["n"])} for p in r["p"]],
            "ind": r["ind"], "ftype": r["ftype"], "rev": r["rev"], "nav": r["nav"],
            "exc": r["exc"], "c506": r["506c"], "amend": r["amend"],
            "prevAcc": r["prevAcc"], "sale0": r["sale0"], "yet": r["yet"],
            "offer": r["offer"], "offerInd": r["offerIndef"], "sold": r["sold"],
            "rem": r["rem"], "remInd": r["remIndef"], "ninv": r["ninv"],
            "comm": r["comm"], "fees": r["fees"], "proceeds": r["proceeds"],
            "secs": r["secs"], "bcombo": r["bcombo"], "sig": r["sig"],
        }

    def score(r):
        s = 0
        if r["ind"] == "Technology":
            s += 5
        if r["ind"] == FUND:
            s -= 6
        humans = [p for p in r["p"] if not is_entity(p["n"])]
        if 1 <= len(humans) <= 4:
            s += 4
        if any("Director" in p["r"] or "Executive Officer" in p["r"] for p in humans):
            s += 3
        if r["sold"] and 1_000_000 <= r["sold"] <= 40_000_000:
            s += 4
        if r["ninv"] and 3 <= r["ninv"] <= 60:
            s += 2
        if r["sig"] and r["sig"].get("t"):
            s += 1
        if not r["amend"] and r["offer"] and not r["offerIndef"]:
            s += 2
        return s

    people_of = lambda f: [p for p in f["p"] if not is_entity(p["n"])]

    ranked = sorted(recs, key=score, reverse=True)
    picks = []

    def want(label, test, order=ranked):
        for r in order:
            f = full(r)
            if test(f):
                f["label"] = label
                picks.append(f)
                return f
        return None

    def money(v):
        v = v or 0
        return f"${v/1e6:.1f}m" if v < 1e9 else f"${v/1e9:.1f}bn"

    want("A biotech company, {} raised, {} backers".format(
             money(next((r["sold"] for r in recs if r["ind"] == "Biotechnology"
                         and 500_000 < (r["sold"] or 0) < 5_000_000
                         and (r["ninv"] or 0) >= 5
                         and 2 <= len([p for p in r["p"] if not is_entity(p["n"])]) <= 4), 0)),
             str(next((r["ninv"] for r in recs if r["ind"] == "Biotechnology"
                         and 500_000 < (r["sold"] or 0) < 5_000_000
                         and (r["ninv"] or 0) >= 5
                         and 2 <= len([p for p in r["p"] if not is_entity(p["n"])]) <= 4), 0))),
         lambda f: f["ind"] == "Biotechnology" and 500_000 < (f["sold"] or 0) < 5_000_000
         and (f["ninv"] or 0) >= 5 and 2 <= len(people_of(f)) <= 4)
    ins = next((r for r in recs if r["ind"] == "Insurance" and (r["sold"] or 0) > 1_000_000_000), None)
    want(f"An insurer offering {money(ins['sold'] if ins else 0)} to {ins['ninv'] if ins else 0} investors",
         lambda f: f["ind"] == "Insurance" and (f["sold"] or 0) > 1_000_000_000)
    re_ = next((r for r in recs if "Real Estate" in (r["ind"] or "")
                and (r["ninv"] or 0) >= 40 and (r["sold"] or 0) > 1_000_000), None)
    want(f"A real estate vehicle with {re_['ninv'] if re_ else 0} backers",
         lambda f: "Real Estate" in (f["ind"] or "") and (f["ninv"] or 0) >= 40
         and (f["sold"] or 0) > 1_000_000)
    fd = next((r for r in recs if r["ind"] == FUND
               and len([p for p in r["p"] if not is_entity(p["n"])]) >= 8), None)
    want(f"A fund, {len([p for p in fd['p'] if not is_entity(p['n'])]) if fd else 0} names deep",
         lambda f: f["ind"] == FUND and len(people_of(f)) >= 8)
    mf = next((r for r in recs if r["ind"] == "Manufacturing"
               and 5_000_000 < (r["sold"] or 0) < 30_000_000), None)
    want(f"A manufacturer, {money(mf['sold'] if mf else 0)} sold, {mf['ninv'] if mf else 0} backers",
         lambda f: f["ind"] == "Manufacturing" and 5_000_000 < (f["sold"] or 0) < 30_000_000)

    if not picks and ranked:
        f = full(ranked[0])
        f["label"] = "A filing from the quarter"
        picks.append(f)

    forms, seen = [], set()
    for f in picks:
        if f["acc"] not in seen:
            seen.add(f["acc"])
            forms.append(f)

    # ---- population, from the daily index we read in full
    pop = {"filings": None, "byMonth": [], "days": 0, "peak": None}
    if os.path.exists(ACCESSIONS):
        rows = json.load(open(ACCESSIONS))["rows"]
        pop["filings"] = len(rows)
        pop["days"] = len({r["filed"] for r in rows})
        mc = Counter(r["filed"][:6] for r in rows)
        pop["byMonth"] = [[k, v] for k, v in sorted(mc.items())]
        dc = Counter(r["filed"] for r in rows)
        pop["peak"] = dc.most_common(1)[0]

    by_ind = Counter(i["g"] or "Unclassified" for i in out_issuers)
    by_state = Counter(i["s"] or "--" for i in out_issuers)
    by_state_co = Counter(i["s"] or "--" for i in cos)
    by_month = Counter(i["f"][:6] for i in out_issuers)
    US = {
        "DELAWARE", "CALIFORNIA", "TEXAS", "NEW YORK", "NEVADA", "COLORADO",
        "OHIO", "FLORIDA", "MASSACHUSETTS", "ILLINOIS", "WASHINGTON", "GEORGIA",
        "VIRGINIA", "MARYLAND", "UTAH", "ARIZONA", "OREGON", "PENNSYLVANIA",
        "NEW JERSEY", "NORTH CAROLINA", "MINNESOTA", "MISSOURI", "TENNESSEE",
        "WISCONSIN", "INDIANA", "MICHIGAN", "CONNECTICUT", "ALABAMA", "LOUISIANA",
        "KENTUCKY", "OKLAHOMA", "SOUTH CAROLINA", "KANSAS", "IOWA", "ARKANSAS",
        "IDAHO", "MONTANA", "NEBRASKA", "NEW MEXICO", "HAWAII", "ALASKA",
        "RHODE ISLAND", "VERMONT", "WYOMING", "MAINE", "NEW HAMPSHIRE",
        "MISSISSIPPI", "WEST VIRGINIA", "NORTH DAKOTA", "SOUTH DAKOTA",
        "DISTRICT OF COLUMBIA", "PUERTO RICO", "GUAM", "VIRGIN ISLANDS",
    }
    non_us = Counter(c["juris"] for c in issuers.values()
                     if c["juris"] and c["juris"].upper() not in US)

    stats = {
        "window": f"{WINDOW[0]}-{WINDOW[1]}",
        "seed": SAMPLE_SEED,
        "sample": len(recs),
        "popFilings": pop["filings"],
        "popDays": pop["days"],
        "popByMonth": pop["byMonth"],
        "popPeak": pop["peak"],
        "sampleRate": pct(len(recs), pop["filings"]) if pop["filings"] else None,
        "issuers": len(out_issuers),
        "amendments": sum(1 for r in recs if r["form"] == "D/A"),
        "amendOrigInSample": sum(1 for r in recs
                                 if r["form"] == "D/A" and r["prevAcc"]
                                 and r["prevAcc"] in {x["acc"] for x in recs}),
        "multiFilingIssuers": sum(1 for v in issuers.values() if v["amends"] > 0),
        "days": len({i["f"] for i in out_issuers}),
        "funds": len(funds),
        "fundPct": pct(len(funds), len(out_issuers)),
        "cos": len(cos),
        "coPct": pct(len(cos), len(out_issuers)),
        "allNames": profile(idx_all),
        "peopleNames": profile(idx_people),
        "entityNames": {"entities": profile(ent_only)},
        "coNames": profile(idx_cos),
        "cosWithPeople": sum(1 for i in cos if i["P"]),
        "cosWithPeoplePct": pct(sum(1 for i in cos if i["P"]), len(cos)),
        "entityOnly": sum(1 for i in out_issuers if i["E"] and not i["P"]),
        "byInd": by_ind.most_common(),
        "byState": by_state_co.most_common(12),
        "byStateAll": by_state.most_common(12),
        "byMonth": [[k, v] for k, v in sorted(by_month.items())],
        "degCo": deg_hist(idx_cos),
        "degAll": deg_hist(idx_named_all),
        "repeatInd": repeat_industries(idx_cos,
                                      {c["name"]: (c["ind"] or "unclassified")
                                       for c in issuers.values()}),
        "nonUs": non_us.most_common(6),
        "nonUsTotal": sum(non_us.values()),
        "amendOrigInSample": 0,
        "mergedIssuers": sum(1 for v in issuers.values() if v["amends"] > 0),
        "rule506c": sum(1 for i in out_issuers if i["6"]),
        "rule506cCo": sum(1 for i in cos if i["6"]),
        "fundsNoAmount": sum(1 for i in funds if not i["d"]),
        "cosNoAmount": sum(1 for i in cos if not i["d"]),
        "indefiniteOfferings": sum(1 for i in out_issuers if i["I"]),
        "investors": {"all": inv_all, "co": inv_cos},
        "soldBandsCo": band_counts(
            [i["d"] for i in cos if i["d"]],
            [(0, 100_000, "under $100k"), (100_001, 500_000, "$100k to $500k"),
             (500_001, 1_000_000, "$500k to $1M"), (1_000_001, 5_000_000, "$1M to $5M"),
             (5_000_001, 20_000_000, "$5M to $20M"), (20_000_001, 100_000_000, "$20M to $100M"),
             (100_000_001, 10**15, "over $100M")]),
    }

    payload = {
        "meta": {"window": stats["window"], "seed": SAMPLE_SEED,
                 "source": "SEC EDGAR Form D and Form D-A, primary_doc.xml"},
        "stats": stats,
        "issuers": out_issuers,
        "repeats": repeats_all,
        "repeatsCo": repeats_cos,
        "forms": forms,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))

    print(f"wrote {OUT}  {os.path.getsize(OUT)/1e6:.2f} MB")
    for k in ("sample", "popFilings", "issuers", "amendments", "funds", "fundPct",
              "cos", "entityOnly", "rule506c", "rule506cCo"):
        print(f"  {k}: {stats[k]}")
    print("  names(all):", json.dumps(stats["allNames"]))
    print("  people only:", json.dumps(stats["peopleNames"]))
    print("  companies:  ", json.dumps(stats["coNames"]))
    print("  investors all:", {k: v for k, v in inv_all.items() if k not in ("checks", "ninvBands", "checkBands")})
    print("  investors co: ", {k: v for k, v in inv_cos.items() if k not in ("checks", "ninvBands", "checkBands")})
    print("  top repeats:  ", [(r["n"], r["d"], r["r"][:2]) for r in repeats_all[:10]])
    print("  co repeats:   ", [(r["n"], r["d"], r["r"][:2]) for r in repeats_cos[:6]])


if __name__ == "__main__":
    main()
