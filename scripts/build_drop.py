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

ENTITY_TAIL = re.compile(
    r"(llc|l l c|l p|lp|llp|inc|corp|corporation|co|company|partners|partnership|"
    r"holdings|holding|group|ventures|venture|capital|fund|trust|estate|family|"
    r"office|advisors|advisory|management|investments|investment|asset|assets|"
    r"series|spv|limited|association|gmbh|sa r l|sarl|plc|ab|as|oy|ag|bv|nv|"
    r"university|church|ministries|foundation|school|church)",
    re.I,
)
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v|phd|md|mba|cpa|jd|esq)\b", re.I)
FUND = "Pooled Investment Fund"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace(".", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_entity(name):
    n = norm(name)
    if not n or n in ("n a", "na", "none", "unknown", "the"):
        return True
    if ENTITY_TAIL.search(n):
        return True
    words = n.split()
    # a lone token with no letters, or an all-caps style acronym, is not a person
    if len(words) == 1 and (len(words[0]) <= 2 or not re.fullmatch(r"[a-z]+", words[0])):
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

    out_issuers = []
    for cur in issuers.values():
        people = [p for p in cur["p"].values() if not p["e"]]
        ents = [p for p in cur["p"].values() if p["e"]]
        out_issuers.append({
            "i": cur["acc"], "c": cur["cik"], "n": cur["name"], "f": cur["filed"],
            "m": cur["amends"], "g": cur["ind"], "t": cur["ftype"],
            "y": cur["etype"], "j": cur["juris"], "s": cur["state"],
            "o": cur["offer"], "I": cur["offerInd"], "d": cur["sold"],
            "k": cur["ninv"], "6": cur["c506"],
            "P": [p["n"] for p in people][:8], "R": sorted({r for p in people for r in p["r"]}),
            "E": [p["n"] for p in ents][:4],
            "C": next((p["c"] for p in people if p["c"]), None),
            "F": cur["sale0"], "B": cur["bcombo"], "X": cur["prev"],
            "G": cur["sig"],
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
        "rule506c": sum(1 for i in out_issuers if i["6"]),
        "rule506cCo": sum(1 for i in cos if i["6"]),
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
