#!/usr/bin/env python3
"""
Turn the raw Form D crawl into the one JSON file the drop reads.

Everything the page shows is computed here so the numbers on screen can be
reproduced by re-running this file. Run it after scripts/fetch_formd.py.
"""
import datetime
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "formd.jsonl")
OUT = os.path.join(ROOT, "site", "drop.json")
ACCESSIONS = os.path.join(ROOT, "data", "accessions.json")
LINEAGE_FIXTURE = os.path.join(ROOT, "data", "fixtures", "formd-amendment-000878.xml")

WINDOW = ("20260701", "20260926")
SAMPLE_SEED = 20260926

# The single largest slice of Form D. The other issuer types include both
# operating businesses and vehicles, so the page keeps the formal category name.
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
# Person suffixes are removed only from the end of a name. Roman numerals inside
# an entity name identify part of its legal name and stay in the key.
PERSON_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "mba", "cpa", "jd", "esq"}

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
    words = norm(name).split()
    while words and words[-1] in PERSON_SUFFIXES:
        words.pop()
    return " ".join(words)


def person_display(name):
    """Show the same terminal-suffix-free form used by person filters."""
    words = (name or "").strip().split()
    while words and norm(words[-1]) in PERSON_SUFFIXES:
        words.pop()
    return re.sub(r"[\s,]+$", "", " ".join(words))


def entity_key(name):
    """Normalize formatting while preserving all legal-name tokens."""
    return norm(name)


def cik_identity(value):
    return str(value).lstrip("0") or "0"


def annotate_accession_rows(recs, index_rows):
    """Label CIK rows from a shared accession using their local index metadata.

    Form D's structured Item 3 list is tied to the offering and may apply to any
    issuer on the notice. It is not assigned to each continuation-page issuer.
    Keep the full XML name only for a uniquely matched primary CIK. Use an
    unambiguous (accession, CIK) index name for other rows, or an explicit
    unresolved label when that pair has conflicting names.
    """
    by_acc = defaultdict(list)
    by_pair = defaultdict(list)
    for row in index_rows:
        acc = row.get("acc")
        cik = cik_identity(row.get("cik", ""))
        by_acc[acc].append(row)
        by_pair[(acc, cik)].append(row)

    shared_accs = {
        acc for acc, rows in by_acc.items()
        if len({cik_identity(row.get("cik", "")) for row in rows}) > 1
    }
    primary_by_acc = {}
    for acc in shared_accs:
        xml_names = {norm(row.get("name")) for row in recs if row["acc"] == acc}
        if len(xml_names) != 1:
            continue
        xml_name = next(iter(xml_names))
        index_names = by_acc[acc]
        exact = {
            cik_identity(row.get("cik", "")) for row in index_names
            if norm(row.get("name")) == xml_name
        }
        if len(exact) == 1:
            primary_by_acc[acc] = next(iter(exact))
            continue
        prefix = {
            cik_identity(row.get("cik", "")) for row in index_names
            if len(row.get("name", "")) == 55
            and xml_name.startswith(norm(row.get("name")))
        }
        if len(prefix) == 1:
            primary_by_acc[acc] = next(iter(prefix))

    annotated = []
    for row in recs:
        rec = dict(row)
        acc = rec["acc"]
        cik = cik_identity(rec["cik"])
        metadata = by_pair.get((acc, cik), [])
        metadata_names = {entry.get("name", "") for entry in metadata
                          if entry.get("name", "")}
        rec["_sharedAcc"] = acc in shared_accs
        rec["_sharedCiks"] = sorted({
            cik_identity(entry.get("cik", "")) for entry in by_acc.get(acc, [])
        }) if acc in shared_accs else []
        rec["_xmlPrimaryName"] = row.get("name")
        rec["_primaryCik"] = primary_by_acc.get(acc)
        rec["_nameFromIndex"] = False
        rec["_nameTruncated"] = False
        primary = primary_by_acc.get(acc)
        if acc in shared_accs:
            if primary and cik == primary:
                pass  # retain the full XML primary issuer name
            elif len(metadata_names) == 1:
                rec["name"] = next(iter(metadata_names))
                rec["_nameFromIndex"] = True
                # EDGAR accessions-index issuer names are capped at 55
                # characters; even shorter values may be cut at a word edge.
                rec["_nameTruncated"] = True
            elif len(metadata_names) != 1:
                rec["name"] = f"CIK {cik} · issuer name unresolved"
                rec["_nameFromIndex"] = False
                rec["_nameUnresolvedShared"] = True
        rec.setdefault("_nameUnresolvedShared", False)
        annotated.append(rec)
    return annotated


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
            out.append([f"{k} issuer" + ("" if k == 1 else "s"), d[k]])
    over = sum(c for k, c in d.items() if k > cap)
    if over:
        out.append([f"{cap + 1}+ issuers", over])
    return out


def repeat_industries(idx, issuer_profiles):
    """Count every non-fund issuer profile attached to a repeated person key.

    The repeat-name index keeps only six issuer examples for display, so use
    the complete folded profiles for this distribution.
    """
    c = Counter()
    repeated = {key for key, value in idx.items() if value["d"] > 1}
    for issuer in issuer_profiles:
        industry = issuer["ind"] or "unclassified"
        for (is_entity, name_key) in issuer["p"]:
            if not is_entity and (False, name_key) in repeated:
                c[industry] += 1
    return c


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
    recs.sort(key=lambda r: (r["filed"], r["acc"]))
    return recs


def fold(recs):
    """Build one latest-filing profile per CIK and union its related persons.

    This is an issuer directory, not an offering-lineage fold. Multiple filings
    for one CIK may be amendments or separate offerings.
    """
    issuers = {}
    for r in recs:
        cur = issuers.get(r["cik"])
        if cur is None:
            cur = {
                "acc": r["acc"], "cik": r["cik"], "name": r["name"], "form": r["form"],
                "filed": r["filed"], "ind": r["ind"], "ftype": r["ftype"],
                "etype": r["etype"], "juris": r["juris"], "state": r["state"],
                "offer": r["offer"], "offerInd": r["offerIndef"], "sold": r["sold"],
                "ninv": r["ninv"], "c506": r["506c"], "filingCount": 1, "p": {},
                "proceeds": r["proceeds"], "fees": r["fees"], "comm": r["comm"],
                "secs": r["secs"], "yet": r["yet"], "bcombo": r["bcombo"],
                "prev": r["prev"], "sale0": r["sale0"], "sig": r["sig"],
                "sharedLatest": r.get("_sharedAcc", False),
                "nameFromIndex": r.get("_nameFromIndex", False),
                "nameTruncated": r.get("_nameTruncated", False),
                "nameUnresolvedShared": r.get("_nameUnresolvedShared", False),
                "joint": {},
            }
            issuers[r["cik"]] = cur
        else:
            cur["filingCount"] += 1
            fields = {
                "acc": "acc", "name": "name", "form": "form", "filed": "filed",
                "ind": "ind", "ftype": "ftype", "etype": "etype", "juris": "juris",
                "state": "state", "offer": "offer", "offerInd": "offerIndef",
                "sold": "sold", "ninv": "ninv", "c506": "506c", "proceeds": "proceeds",
                "fees": "fees", "comm": "comm", "secs": "secs", "yet": "yet",
                "bcombo": "bcombo", "prev": "prev", "sale0": "sale0", "sig": "sig",
                "sharedLatest": "_sharedAcc", "nameFromIndex": "_nameFromIndex",
                "nameTruncated": "_nameTruncated",
                "nameUnresolvedShared": "_nameUnresolvedShared",
            }
            for target, source in fields.items():
                cur[target] = r[source]
        if r.get("_sharedAcc"):
            shared = cur["joint"].setdefault(r["acc"], {
                "ciks": r.get("_sharedCiks", []), "primaryCik": r.get("_primaryCik"),
                "xmlName": r.get("_xmlPrimaryName"), "p": {},
            })
        for p in r["p"]:
            entity = is_entity(p["n"])
            name_key = entity_key(p["n"]) if entity else person_key(p["n"])
            if not name_key:
                continue
            k = (entity, name_key)
            if r.get("_sharedAcc"):
                slot = shared["p"].setdefault(k, {
                    "n": p["n"], "r": [], "e": entity, "c": p.get("c"),
                })
                for rel in p["r"]:
                    if rel not in slot["r"]:
                        slot["r"].append(rel)
                continue
            slot = cur["p"].setdefault(k, {
                "n": p["n"], "r": [], "e": entity, "c": p.get("c"),
            })
            for rel in p["r"]:
                if rel not in slot["r"]:
                    slot["r"].append(rel)
    return issuers


def source_fixture_pair():
    """Read the one captured SEC excerpt used to verify the corrected XML path."""
    root = ET.parse(LINEAGE_FIXTURE).getroot()
    amendment = root.find("./offeringData/typeOfFiling/newOrAmendment")
    if amendment is None:
        return None, None, root.get("cik")
    acc = root.get("accession")
    previous = amendment.findtext("previousAccessionNumber")
    return acc, previous.strip() if previous else None, root.get("cik")


def _cik_identity(cik):
    return str(cik).lstrip("0") or "0"


def amendment_lineage(recs):
    amendments = [r for r in recs if r["form"] == "D/A"]
    accessions = {r["acc"] for r in recs}
    fixture_acc, fixture_previous, fixture_cik = source_fixture_pair()
    fixture_cik = _cik_identity(fixture_cik) if fixture_cik else None
    fixture_rows = [r for r in recs if r["acc"] == fixture_acc
                    and _cik_identity(r["cik"]) == fixture_cik and r["form"] == "D/A"]
    fixture_targets = [r for r in recs if r["acc"] == fixture_previous
                       and _cik_identity(r["cik"]) == fixture_cik]
    fixture_in_sample = bool(fixture_rows and fixture_targets)
    fixture_da_to_d = (
        fixture_in_sample
        and any(r["form"] == "D" for r in fixture_targets)
    )
    checked_rows = [r for r in amendments
                    if r.get("prevAccStatus") == "checked" and r.get("prevAcc")]
    checked_count = len(checked_rows)
    missing_field = sum(
        1 for r in amendments
        if r.get("prevAccStatus") == "missing_field"
        or (r.get("prevAccStatus") == "checked" and not r.get("prevAcc"))
    )
    fetch_failed = sum(1 for r in amendments if r.get("prevAccStatus") == "fetch_failed")
    parse_failed = sum(1 for r in amendments if r.get("prevAccStatus") == "parse_failed")
    inspected_statuses = {"checked", "missing_field", "fetch_failed", "parse_failed"}
    unverified = sum(1 for r in amendments
                     if r.get("prevAccStatus") not in inspected_statuses)
    reparsed = checked_count + missing_field
    unresolved = sum(1 for r in amendments
                     if r.get("prevAccStatus") != "checked" or not r.get("prevAcc"))
    sampled_link_rows = sum(1 for r in checked_rows if r["prevAcc"] in accessions)
    fixture_row_checked = any(
        r["acc"] == fixture_acc
        and _cik_identity(r["cik"]) == fixture_cik
        and r.get("prevAccStatus") == "checked"
        and r.get("prevAcc") == fixture_previous
        for r in checked_rows
    )
    matched = sampled_link_rows + int(fixture_in_sample and not fixture_row_checked)
    return {
        "amendments": len(amendments),
        "reparsed": reparsed,
        "checked": checked_count,
        "missingField": missing_field,
        "fetchFailed": fetch_failed,
        "parseFailed": parse_failed,
        "unverified": unverified,
        "unresolved": unresolved,
        "sourceConfirmedLinksInSample": matched,
        "lowerBound": matched,
        "complete": unresolved == 0,
        "exactLinksInSample": matched if unresolved == 0 else None,
        "fixture": {
            "accession": fixture_acc,
            "previousAccession": fixture_previous,
            "source": "https://www.sec.gov/Archives/edgar/data/2152949/000101297526000878/primary_doc.xml",
            "pairInSample": fixture_in_sample,
            "daToDInSample": fixture_da_to_d,
        },
    }


def main():
    recs = load()
    index_rows = json.load(open(ACCESSIONS))["rows"] if os.path.exists(ACCESSIONS) else []
    recs = annotate_accession_rows(recs, index_rows)
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
            "N": cur["filingCount"], "g": cur["ind"], "s": cur["state"],
            "I": cur["offerInd"], "d": cur["sold"], "k": cur["ninv"],
            "6": cur["c506"], "R": sorted({r for p in people for r in p["r"]}),
            "P": [person_display(p["n"]) for p in people],
            "E": [p["n"] for p in ents],
            "J": [{"acc": acc, "ciks": shared["ciks"],
                   "primaryCik": shared["primaryCik"], "xmlName": shared["xmlName"],
                   "p": [{"n": p["n"], "e": p["e"], "r": p["r"]}
                         for p in shared["p"].values()]}
                  for acc, shared in sorted(cur["joint"].items())],
            "sharedLatest": cur["sharedLatest"],
            "nameFromIndex": cur["nameFromIndex"],
            "nameTruncated": cur["nameTruncated"],
            "nameUnresolvedShared": cur["nameUnresolvedShared"],
        })

    funds = [i for i in out_issuers if i["g"] == FUND]
    cos = [i for i in out_issuers if i["g"] != FUND]

    # ---- who is named, and how often
    def index(rows, only=None):
        """rows: list of (name, entity_flag, roles, filed, issuer_name) tuples"""
        out = defaultdict(lambda: {"d": 0, "r": Counter(), "m": Counter(), "ex": []})
        for name, ent, roles, filed, iname in rows:
            if only == "person" and ent:
                continue
            if only == "entity" and not ent:
                continue
            k = (ent, entity_key(name) if ent else person_key(name))
            if not k[1]:
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
    idx_all = index(tuples(issuers.values()))
    idx_people = index(tuples(issuers.values()), "person")
    idx_named_all = index(tuples(issuers.values()), "person")  # people, every filing
    idx_cos = index(tuples(cos_folded), "person")
    idx_entities = index(tuples(issuers.values()), "entity")

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
            ent = slot["e"]
            k = (ent, entity_key(slot["n"]) if ent else person_key(slot["n"]))
            shown = slot["n"] if ent else person_display(slot["n"])
            display.setdefault(k, shown)

    def people_list(m, limit=400):
        rows = []
        for k, v in m.items():
            if v["d"] < 2:
                continue
            rows.append({
                "n": display.get(k, k[1]), "d": v["d"],
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
            # The cache predates the blank-preserving parser. Its zero values
            # may be explicit zeroes or blanks that an older parser collapsed.
            "cachedZeroOrLegacyBlank": sum(1 for i in rows if i["k"] == 0),
            "unreported": sum(1 for i in rows if i["k"] is None),
            "reportingPct": pct(len(with_n), len(rows)),
            "medianBackers": int(sorted(i["k"] for i in with_n)[len(with_n) // 2]) if with_n else 0,
            "maxBackers": max((i["k"] for i in with_n), default=0),
            "checkN": len(checks),
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

    def filing_rows(rows):
        return [{"k": r["ninv"], "d": r["sold"]} for r in rows]

    fund_filings = [r for r in recs if r["ind"] == FUND]
    co_filings = [r for r in recs if r["ind"] != FUND]
    inv_all = investor_stats(filing_rows(recs), "all sampled filings")
    inv_cos = investor_stats(filing_rows(co_filings), "non-fund filing rows")
    inv_co_issuers = investor_stats(cos, "latest sampled filing per non-fund issuer CIK")

    # ---- a few complete filings, rendered as the actual form
    def full(r):
        return {
            "acc": r["acc"], "cik": r["cik"],
            "name": r.get("_xmlPrimaryName", r["name"]), "cikName": r["name"],
            "primaryCik": r.get("_primaryCik"), "form": r["form"],
            "filed": r["filed"], "juris": r["juris"], "etype": r["etype"],
            "yinc": r["yinc"], "city": r["city"], "state": r["state"], "prev": r["prev"],
            "p": [{"n": p["n"], "r": p["r"], "c": p["c"], "st": p["st"],
                   "e": is_entity(p["n"])} for p in r["p"]],
            "sharedAcc": r.get("_sharedAcc", False),
            "sharedCiks": r.get("_sharedCiks", []),
            "nameFromIndex": r.get("_nameFromIndex", False),
            "nameTruncated": r.get("_nameTruncated", False),
            "nameUnresolvedShared": r.get("_nameUnresolvedShared", False),
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
                f["label"] = label(f) if callable(label) else label
                picks.append(f)
                return f
        return None

    def money(v):
        v = v or 0
        return f"${v/1e6:.1f}m" if v < 1e9 else f"${v/1e9:.1f}bn"

    def investors_text(f):
        if f["ninv"] is None:
            return "investor count unavailable"
        if f["ninv"] == 0:
            return "cached investor count 0 (explicit zero or legacy blank unknown)"
        return f"{f['ninv']} reported investors"

    want(lambda f: f"A biotech issuer, {money(f['sold'])} sold, {investors_text(f)}",
         lambda f: f["ind"] == "Biotechnology" and 500_000 < (f["sold"] or 0) < 5_000_000
         and (f["ninv"] or 0) >= 5 and 2 <= len(people_of(f)) <= 4)
    want(lambda f: f"An insurer reporting {money(f['sold'])} sold and {investors_text(f)}",
         lambda f: f["ind"] == "Insurance" and (f["sold"] or 0) > 1_000_000_000)
    want(lambda f: f"A real estate vehicle with {investors_text(f)}",
         lambda f: "Real Estate" in (f["ind"] or "") and (f["ninv"] or 0) >= 40
         and (f["sold"] or 0) > 1_000_000)
    want(lambda f: f"A fund, {len(people_of(f))} names deep",
         lambda f: f["ind"] == FUND and len(people_of(f)) >= 8)
    want(lambda f: f"A manufacturer, {money(f['sold'])} sold, {investors_text(f)}",
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
    if index_rows:
        rows = index_rows
        pop["filings"] = len(rows)
        pop["days"] = len({r["filed"] for r in rows})
        mc = Counter(r["filed"][:6] for r in rows)
        pop["byMonth"] = [[k, v] for k, v in sorted(mc.items())]
        dc = Counter(r["filed"] for r in rows)
        pop["peak"] = dc.most_common(1)[0]

    by_ind = Counter(i["g"] or "Unclassified" for i in out_issuers)
    co_by_ind = Counter(i["g"] or "Unclassified" for i in cos)
    # Which of the non-fund issuers are the kind of company a startup directory
    # means, and which are operating businesses of another sort. The distinction
    # matters because the non-fund CIK slice is not the same thing as startups.
    VENTURESOME = {
        "Other Technology", "Technology", "Computers", "Telecommunications",
        "Biotechnology", "Pharmaceuticals", "Other Health Care", "Health Care",
        "Business Services", "Manufacturing",
    }
    co_tech = sum(v for k, v in co_by_ind.items() if k in VENTURESOME)
    co_other = len(cos) - co_tech
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
    lineage = amendment_lineage(recs)
    repeat_ind = repeat_industries(idx_cos, cos_folded)

    stats = {
        "window": f"{WINDOW[0]}-{WINDOW[1]}",
        "cacheModified": datetime.date.fromtimestamp(
            os.path.getmtime(SRC)).isoformat(),
        "seed": SAMPLE_SEED,
        "sample": len(recs),
        "uniqueAccessions": len({r["acc"] for r in recs}),
        "sharedAccInPopulation": len({r["acc"] for r in recs
                                       if r.get("_sharedAcc")}),
        "sharedRows": sum(1 for r in recs if r.get("_sharedAcc")),
        "sharedAccSampleMultiCik": sum(
            1 for acc in {r["acc"] for r in recs}
            if len({r["cik"] for r in recs if r["acc"] == acc}) > 1),
        "sharedRowsSampleMultiCik": sum(
            1 for r in recs
            if len({x["cik"] for x in recs if x["acc"] == r["acc"]}) > 1),
        "firstSaleDatesParsed": sum(1 for r in recs if r.get("sale0")),
        "yetToOccur": sum(1 for r in recs if r.get("yet") is True),
        "fundFilings": len(fund_filings),
        "coFilings": len(co_filings),
        "fundFilingPct": pct(len(fund_filings), len(recs)),
        "coFilingPct": pct(len(co_filings), len(recs)),
        "entityOnlyFilings": sum(
            1 for r in recs if not any(not is_entity(p["n"]) for p in r["p"])),
        "popFilings": pop["filings"],
        "popDays": pop["days"],
        "popByMonth": pop["byMonth"],
        "popPeak": pop["peak"],
        "sampleRate": pct(len(recs), pop["filings"]) if pop["filings"] else None,
        "issuers": len(out_issuers),
        "amendments": sum(1 for r in recs if r["form"] == "D/A"),
        "amendLinksInSample": lineage["exactLinksInSample"],
        "amendLineage": lineage,
        "multiFilingIssuers": sum(1 for v in issuers.values() if v["filingCount"] > 1),
        "days": len({r["filed"] for r in recs}),
        "funds": len(funds),
        "fundPct": pct(len(funds), len(out_issuers)),
        "cos": len(cos),
        "coPct": pct(len(cos), len(out_issuers)),
        "allNames": profile(idx_all),
        "peopleNames": profile(idx_people),
        "entityNames": {"entities": profile(idx_entities)},
        "coNames": profile(idx_cos),
        "cosWithPeople": sum(1 for i in cos if i["P"]),
        "cosWithPeoplePct": pct(sum(1 for i in cos if i["P"]), len(cos)),
        "entityOnly": sum(1 for i in out_issuers if i["E"] and not i["P"]),
        "byInd": by_ind.most_common(),
        "coByInd": co_by_ind.most_common(),
        "coTech": co_tech,
        "coOther": co_other,
        "coTechPct": pct(co_tech, len(cos)),
        "byState": by_state_co.most_common(12),
        "byStateAll": by_state.most_common(12),
        "byMonth": [[k, v] for k, v in sorted(by_month.items())],
        "degCo": deg_hist(idx_cos),
        "degAll": deg_hist(idx_named_all),
        "repeatInd": sorted(repeat_ind.items(),
                             key=lambda item: (-item[1], item[0])),
        "repeatIndTotal": sum(repeat_ind.values()),
        "nonUs": non_us.most_common(6),
        "nonUsTotal": sum(non_us.values()),
        "mergedIssuers": sum(1 for v in issuers.values() if v["filingCount"] > 1),
        "rule506c": sum(1 for i in out_issuers if i["6"]),
        "rule506cCo": sum(1 for i in cos if i["6"]),
        "fundsNoAmount": sum(1 for i in funds if i["d"] is None),
        "cosNoAmount": sum(1 for i in cos if i["d"] is None),
        "indefiniteOfferings": sum(1 for i in out_issuers if i["I"]),
        "investors": {"all": inv_all, "co": inv_cos, "coIssuers": inv_co_issuers},
        "soldBandsCo": band_counts(
            [i["d"] for i in cos if i["d"]],
            [(0, 100_000, "under $100k"), (100_001, 500_000, "$100k to $500k"),
             (500_001, 1_000_000, "$500k to $1M"), (1_000_001, 5_000_000, "$1M to $5M"),
             (5_000_001, 20_000_000, "$5M to $20M"), (20_000_001, 100_000_000, "$20M to $100M"),
             (100_000_001, 10**15, "over $100M")]),
    }

    payload = {
        "meta": {"window": stats["window"], "seed": SAMPLE_SEED,
                 "cacheModified": stats["cacheModified"],
                 "source": "SEC EDGAR Form D and Form D/A, primary_doc.xml"},
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
    print("  person-name heuristic only:", json.dumps(stats["peopleNames"]))
    print("  non-fund issuer profiles:", json.dumps(stats["coNames"]))
    print("  investors all:", {k: v for k, v in inv_all.items() if k not in ("checks", "ninvBands", "checkBands")})
    print("  investors co: ", {k: v for k, v in inv_cos.items() if k not in ("checks", "ninvBands", "checkBands")})
    print("  top repeats:  ", [(r["n"], r["d"], r["r"][:2]) for r in repeats_all[:10]])
    print("  co repeats:   ", [(r["n"], r["d"], r["r"][:2]) for r in repeats_cos[:6]])


if __name__ == "__main__":
    main()
