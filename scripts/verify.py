#!/usr/bin/env python3
"""
Independently recompute the page's data-derived figures from data/formd.jsonl.
The focused parser, cache, and identity regression checks also exercise
production helpers, so this verifier is separate in its aggregate calculations,
not wholly code-disjoint. Run it after any crawl or build change:

    python3 scripts/verify.py

Exits non-zero on the first disagreement. The page reads its numbers out of
site/drop.json, so if this passes, the page cannot be quoting a stale figure.
"""
import json
import gzip
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import re
import sys
import threading
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "formd.jsonl")
POP = os.path.join(ROOT, "data", "accessions.json")
OUT = os.path.join(ROOT, "site", "drop.json")
LINEAGE_FIXTURE = os.path.join(ROOT, "data", "fixtures", "formd-amendment-000878.xml")
FIRST_SALE_FIXTURE = os.path.join(ROOT, "data", "fixtures", "formd-first-sale-000001.xml")

W0, W1 = "20260701", "20260926"
FUND = "Pooled Investment Fund"

fails = []


def check(label, got, want, tol=0):
    ok = (abs(got - want) <= tol) if isinstance(want, (int, float)) else (got == want)
    print(f"  {'ok  ' if ok else 'FAIL'}  {label:<52} page {want!r:>12}   raw {got!r}")
    if not ok:
        fails.append(label)


def verify_fetch_bytes_local():
    """Exercise fetch_bytes against clean and truncated localhost responses."""
    scripts = os.path.join(ROOT, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from fetch_formd import fetch_bytes

    body = b"complete local Form D response"
    gzip_body = gzip.compress(body, mtime=0)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):  # noqa: N802
            if self.path == "/plain":
                payload = body
                encoding = None
            elif self.path == "/gzip":
                payload = gzip_body
                encoding = "gzip"
            elif self.path in ("/truncated", "/truncated-gzip"):
                payload = b"partial-body"
                encoding = "gzip" if self.path.endswith("gzip") else None
            else:
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Content-Length",
                             "100" if self.path.startswith("/truncated") else str(len(payload)))
            if encoding:
                self.send_header("Content-Encoding", encoding)
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            self.wfile.write(payload)
            self.wfile.flush()

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def rejects_truncation(path):
        try:
            received = fetch_bytes(base + path, deadline_s=1)
        except (http.client.IncompleteRead, TimeoutError):
            return "incomplete response rejected"
        except Exception as exc:  # noqa: BLE001
            return f"unexpected {type(exc).__name__}"
        return f"returned {len(received)} bytes"

    try:
        check("localhost plain response remains intact",
              fetch_bytes(base + "/plain", deadline_s=1), body)
        check("localhost gzip response remains intact",
              fetch_bytes(base + "/gzip", deadline_s=1), body)
        check("localhost truncated Content-Length is rejected",
              rejects_truncation("/truncated"), "incomplete response rejected")
        check("localhost truncated gzip Content-Length is rejected",
              rejects_truncation("/truncated-gzip"), "incomplete response rejected")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def verify_first_sale_fixture():
    """Check cached XML parsing fields, including investor-count blank handling."""
    scripts = os.path.join(ROOT, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from fetch_formd import parse_formd

    raw = open(FIRST_SALE_FIXTURE, "rb").read()
    meta = {"acc": "0002111089-26-000001", "cik": "2111089", "form": "D",
            "filed": "20260731", "name": "Mangrove Therapeutics Inc."}
    record = parse_formd(raw, meta)
    check("SEC fixture first-sale date path", record.get("sale0") if record else None,
          "2026-07-21")
    check("SEC fixture middle name is preserved", record["p"][0]["n"] if record else None,
          "Benjamin Zhiyi Chen")

    yet_raw = b"""<edgarSubmission><primaryIssuer><entityName>Example</entityName></primaryIssuer>
      <offeringData><typeOfFiling><dateOfFirstSale><yetToOccur>true</yetToOccur>
      </dateOfFirstSale></typeOfFiling></offeringData></edgarSubmission>"""
    yet_record = parse_formd(yet_raw, {**meta, "acc": "synthetic-yet", "name": "Example"})
    check("explicit yet-to-occur flag remains true",
          (yet_record.get("sale0"), yet_record.get("yet")) if yet_record else None,
          (None, True))

    count_prefix = b"""<edgarSubmission><primaryIssuer><entityName>Example</entityName></primaryIssuer>
      <offeringData><investors>"""
    count_suffix = b"""</investors></offeringData></edgarSubmission>"""
    zero_record = parse_formd(
        count_prefix + b"<totalNumberAlreadyInvested>0</totalNumberAlreadyInvested>" + count_suffix,
        {**meta, "acc": "synthetic-investors-zero", "name": "Example"})
    check("explicit investor count zero stays zero",
          zero_record.get("ninv") if zero_record else None, 0)
    empty_record = parse_formd(
        count_prefix + b"<totalNumberAlreadyInvested></totalNumberAlreadyInvested>" + count_suffix,
        {**meta, "acc": "synthetic-investors-empty", "name": "Example"})
    check("empty investor count stays unknown",
          empty_record.get("ninv") if empty_record else None, None)
    missing_record = parse_formd(
        count_prefix + count_suffix,
        {**meta, "acc": "synthetic-investors-missing", "name": "Example"})
    check("missing investor count stays unknown",
          missing_record.get("ninv") if missing_record else None, None)


def verify_filing_identity_helpers():
    """Keep same-accession, different-CIK rows separate during resume/refresh."""
    scripts = os.path.join(ROOT, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from fetch_formd import apply_lineage_results, fetch_one, filing_key, uncached_rows
    from build_drop import amendment_lineage, annotate_accession_rows
    from unittest.mock import patch

    accession = "0000000001-26-000001"
    previous = "0000000001-26-000000"
    row_a = {"acc": accession, "cik": "101", "form": "D/A", "name": "cached A",
             "prevAccStatus": "unverified"}
    row_b = {"acc": accession, "cik": "202", "form": "D/A", "name": "cached B",
             "prevAccStatus": "unverified"}
    pending = uncached_rows([row_a, row_b], [row_a])
    check("resume treats one accession under two CIKs as separate filings",
          [filing_key(row) for row in pending], [filing_key(row_b)])

    refreshed_a = {**row_a, "name": "refreshed A", "prevAcc": previous,
                   "prevAccStatus": "checked"}
    updated, _, _ = apply_lineage_results(
        [row_a, row_b], [row_a], [(refreshed_a, None)])
    check("lineage refresh replaces only its accession/CIK row",
          [(row["cik"], row["name"]) for row in updated],
          [("101", "refreshed A"), ("202", "cached B")])

    retry_calls = []
    retry_xml = b"""<edgarSubmission><primaryIssuer><entityName>Example</entityName></primaryIssuer>
      <offeringData><investors><totalNumberAlreadyInvested>0</totalNumberAlreadyInvested>
      </investors></offeringData></edgarSubmission>"""

    def fake_get(url, tries=8, missing=None):
        retry_calls.append(tries)
        return retry_xml

    retry_stats = {"ok": 0, "miss": 0, "unparsed": 0, "done": 0, "total": 1}
    with patch("fetch_formd.get", side_effect=fake_get):
        fetched = fetch_one({"acc": accession, "cik": "101", "form": "D",
                             "filed": "20260701", "name": "Example"},
                            retry_stats, tries=3)
    check("filing fetch passes configured retry count", retry_calls, [3])
    check("filing fetch still parses the record", fetched.get("ninv") if fetched else None, 0)

    shared_das = [
        {"acc": accession, "cik": cik, "form": "D/A", "prevAcc": previous,
         "prevAccStatus": "checked"}
        for cik in ("101", "202")
    ]
    shared_originals = [
        {"acc": previous, "cik": cik, "form": "D"}
        for cik in ("101", "202")
    ]
    lineage = amendment_lineage(shared_das + shared_originals)
    check("lineage metrics count same-accession D/A rows separately",
          (lineage["amendments"], lineage["reparsed"], lineage["checked"],
           lineage["unresolved"], lineage["exactLinksInSample"]),
          (2, 2, 2, 0, 2))

    shared_recs = [
        {"acc": "shared-primary", "cik": "10", "name": "Full Primary Name LLC"},
        {"acc": "shared-primary", "cik": "11", "name": "Full Primary Name LLC"},
        {"acc": "no-primary", "cik": "20", "name": "XML Name Not In Index"},
        {"acc": "no-primary", "cik": "21", "name": "XML Name Not In Index"},
        {"acc": "ambiguous-pair", "cik": "30", "name": "Ambiguous Primary LLC"},
        {"acc": "ambiguous-pair", "cik": "31", "name": "Ambiguous Primary LLC"},
    ]
    shared_index = [
        {"acc": "shared-primary", "cik": "10", "name": "Full Primary Name LLC"},
        {"acc": "shared-primary", "cik": "10", "name": "Primary alias"},
        {"acc": "shared-primary", "cik": "11", "name": "Secondary Name LLC"},
        {"acc": "no-primary", "cik": "20", "name": "Index Name A LLC"},
        {"acc": "no-primary", "cik": "21", "name": "Index Name B LLC"},
        {"acc": "ambiguous-pair", "cik": "30", "name": "Ambiguous Primary LLC"},
        {"acc": "ambiguous-pair", "cik": "30", "name": "Primary alias"},
        {"acc": "ambiguous-pair", "cik": "31", "name": "Candidate One LLC"},
        {"acc": "ambiguous-pair", "cik": "31", "name": "Candidate Two LLC"},
    ]
    labeled = annotate_accession_rows(shared_recs, shared_index)
    by_key = {(row["acc"], row["cik"]): row for row in labeled}
    check("unique primary keeps full XML name despite multiple same-pair index labels",
          (by_key[("shared-primary", "10")]["name"],
           by_key[("shared-primary", "10")]["_primaryCik"],
           by_key[("shared-primary", "10")]["_nameFromIndex"]),
          ("Full Primary Name LLC", "10", False))
    check("secondary with one pair label uses and flags index name",
          (by_key[("shared-primary", "11")]["name"],
           by_key[("shared-primary", "11")]["_nameFromIndex"],
           by_key[("shared-primary", "11")]["_nameTruncated"]),
          ("Secondary Name LLC", True, True))
    check("no unique primary uses each unambiguous pair label",
          (by_key[("no-primary", "20")]["_primaryCik"],
           by_key[("no-primary", "20")]["name"],
           by_key[("no-primary", "21")]["name"]),
          (None, "Index Name A LLC", "Index Name B LLC"))
    check("ambiguous secondary pair gets unresolved CIK label",
          (by_key[("ambiguous-pair", "31")]["name"],
           by_key[("ambiguous-pair", "31")]["_nameUnresolvedShared"]),
          ("CIK 31 · issuer name unresolved", True))


def verify_duplicate_accession_directory(D):
    """Keep same-accession issuer profiles distinct in directory detail UI."""
    profiles = defaultdict(list)
    for row in D["issuers"]:
        profiles[row["i"]].append(row)
    shared = profiles["0002140772-26-000001"]
    check("shared accession retains both sampled issuer CIK profiles",
          sorted(row["c"] for row in shared), ["2140770", "2140771"])
    check("shared-accession directory keys distinguish issuer profiles",
          len({f"{row['c']}:{row['i']}" for row in shared}), len(shared))

    app = open(os.path.join(ROOT, "site", "app.js"), encoding="utf-8").read()
    builder = open(os.path.join(ROOT, "scripts", "build_drop.py"), encoding="utf-8").read()
    check("directory detail button carries CIK and accession",
          'data-detail-cik="${esc(i.c)}" data-detail-acc="${esc(i.i)}"' in app,
          True)
    check("detail lookup matches profile CIK and accession",
          "D.issuers.find(x => x.c === cik && x.i === acc)" in app,
          True)
    check("filing links retain the profile CIK",
          'edgar(i.c, i.i)' in app, True)
    check("form payload keeps XML issuer name separate from selected CIK label",
          '"cikName": r["name"]' in builder
          and '"name": r.get("_xmlPrimaryName", r["name"])' in builder
          and all("cikName" in form for form in D.get("forms", [])), True)
    check("shared form template distinguishes XML name and index row label",
          "Name of issuer in XML Item 1" in app
          and "Selected row's issuer label" in app, True)
    check("joint Item 3 details use a block value container",
          '<span class="k">Joint Item 3 names, not CIK-assigned</span><div class="v">' in app,
          True)
    joint_group = next(g for row in shared for g in row["J"]
                       if g["acc"] == "0002140772-26-000001")
    check("shared Item 3 group carries the full XML Item 1 primary issuer name",
          joint_group.get("xmlName"), "Digital Fort Gillem REIT, LLC")
    check("shared Item 3 detail renders XML name separately from selected CIK label",
          '<strong>XML Item 1 primary issuer name:</strong> ${group.xmlName ? esc(group.xmlName) : "unavailable in cached XML"}' in app
          and "Full-window EDGAR index CIKs on this accession" in app
          and "The selected profile label and its source are shown separately" in app, True)


def primary_cik_for_shared_accession(acc, xml_name, index_by_acc):
    """Independently identify a primary CIK only from one unique index name."""
    rows = index_by_acc.get(acc, [])
    xml_key = plain_key(xml_name)
    exact = {str(row["cik"]).lstrip("0") or "0" for row in rows
             if plain_key(row.get("name")) == xml_key}
    if len(exact) == 1:
        return next(iter(exact))
    prefix = {str(row["cik"]).lstrip("0") or "0" for row in rows
              if len(row.get("name", "")) == 55
              and xml_key.startswith(plain_key(row.get("name")))}
    return next(iter(prefix)) if len(prefix) == 1 else None


# Person suffixes are removed only at the end of a name. Entity keys keep every
# token, including Roman numerals, because they can distinguish legal entities.
PERSON_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "mba", "cpa", "jd", "esq"}


def plain_key(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def key(s):
    words = plain_key(s).split()
    while words and words[-1] in PERSON_SUFFIXES:
        words.pop()
    return " ".join(words)


def entity_key(s):
    return plain_key(s)


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
    n = plain_key(raw)
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
    print("\nfetch_bytes localhost response integrity")
    verify_fetch_bytes_local()
    print("\nSEC first-sale and related-person parser fixture")
    verify_first_sale_fixture()
    print("\nfiling identity and lineage row handling")
    verify_filing_identity_helpers()

    rows = []
    for line in open(RAW, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rows = [r for r in rows if W0 <= r["filed"] <= W1]
    D = json.load(open(OUT))
    S = D["stats"]
    pop_rows = json.load(open(POP))["rows"]
    index_by_acc = defaultdict(list)
    index_by_pair = defaultdict(list)
    population_ciks = defaultdict(set)
    for row in pop_rows:
        acc = row["acc"]
        cik = str(row["cik"]).lstrip("0") or "0"
        index_by_acc[acc].append(row)
        index_by_pair[(acc, cik)].append(row)
        population_ciks[acc].add(cik)
    shared_accs = {acc for acc, ciks in population_ciks.items() if len(ciks) > 1}
    sample_ciks_by_acc = defaultdict(set)
    for row in rows:
        sample_ciks_by_acc[row["acc"]].add(str(row["cik"]).lstrip("0") or "0")
    sample_shared_multi = {acc for acc, ciks in sample_ciks_by_acc.items() if len(ciks) > 1}

    primary_ciks = {}
    for acc in shared_accs:
        xml_names = {plain_key(row["name"]) for row in rows if row["acc"] == acc}
        if len(xml_names) == 1:
            primary = primary_cik_for_shared_accession(acc, next(iter(xml_names)), index_by_acc)
            if primary:
                primary_ciks[acc] = primary

    expected_name_by_cik = {}
    expected_joint_by_cik = defaultdict(lambda: defaultdict(dict))
    for row in sorted(rows, key=lambda item: (item["filed"], item["acc"])):
        acc = row["acc"]
        cik = str(row["cik"]).lstrip("0") or "0"
        name = row["name"]
        from_index = False
        truncated = False
        unresolved = False
        if acc in shared_accs:
            meta_names = {entry.get("name", "") for entry in index_by_pair.get((acc, cik), [])
                          if entry.get("name", "")}
            if acc in primary_ciks and cik == primary_ciks[acc]:
                pass  # keep the full XML primary issuer name
            elif len(meta_names) == 1:
                name = next(iter(meta_names))
                from_index = True
                truncated = True  # the EDGAR index caps names at 55 chars
            elif len(meta_names) != 1:
                name = f"CIK {cik} · issuer name unresolved"
                unresolved = True
        expected_name_by_cik[cik] = (
            name, from_index, truncated, unresolved
        )
        if acc in shared_accs:
            group = expected_joint_by_cik[cik][acc]
            for person in row["p"]:
                person_type = "person" if is_person(person["n"]) else "entity"
                name_key = key(person["n"]) if person_type == "person" else entity_key(person["n"])
                group[(person_type, name_key)] = (person["n"], tuple(sorted(person.get("r", []))))

    print("\nshared-accession issuer directory profiles")
    verify_duplicate_accession_directory(D)
    shared_sample_rows = [r for r in rows if r["acc"] in shared_accs]
    check("sample rows whose population accession has multiple CIKs",
          len(shared_sample_rows), S["sharedRows"])
    check("sample accessions with multiple population CIKs",
          len({r["acc"] for r in shared_sample_rows}), S["sharedAccInPopulation"])
    check("shared accessions repeated under multiple CIKs within sample",
          len(sample_shared_multi), S["sharedAccSampleMultiCik"])
    check("rows in within-sample repeated-accession groups",
          sum(1 for r in rows if r["acc"] in sample_shared_multi),
          S["sharedRowsSampleMultiCik"])
    check("known secondary CIK profile names use their index row",
          (next(i["n"] for i in D["issuers"] if i["c"] == "2140770"),
           next(i["n"] for i in D["issuers"] if i["c"] == "2140771")),
          ("Digital Moores Chapel Co-Invest REIT, LLC",
           "Digital Moores Chapel REIT, LLC"))
    check("known shared-accession issuer names carry index source tags",
          sorted((i["c"], i["nameFromIndex"]) for i in D["issuers"]
                 if i["i"] == "0002140772-26-000001"),
          [("2140770", True), ("2140771", True)])
    check("all secondary index names are marked as possibly truncated",
          sum(1 for i in D["issuers"] if i["nameFromIndex"] and not i["nameTruncated"]), 0)
    app_source = open(os.path.join(ROOT, "site", "app.js"), encoding="utf-8").read()
    check("directory renders an ellipsis and truncation note for index names",
          "i.nameTruncated ? \"…\" : \"\"" in app_source
          and "may be truncated" in app_source, True)

    check("interior initials stay in the person key", key("Jd Tueller"),
          "jd tueller")
    check("terminal suffixes still fold", key("Jane Doe Jr."), "jane doe")
    check("entity keys preserve Roman numerals",
          entity_key("N/A AQR Capital Management II, LLC"),
          "n a aqr capital management ii llc")
    aqr = next(i for i in D["issuers"] if i["c"] == "2136966")
    check("AQR II and non-II names stay separate in the directory",
          sorted(aqr["E"]), sorted([
              "N/A AQR Capital Management II, LLC",
              "N/A AQR Capital Management, LLC",
          ]))

    print("\npopulation and sample")
    pop = json.load(open(POP))["rows"]
    check("population, 1 Jul to 26 Sep", len(pop), S["popFilings"])
    check("business days in the population", len({r["filed"] for r in pop}), S["popDays"])
    check("filings sampled", len(rows), S["sample"])
    check("unique accession numbers in the sample", len({r["acc"] for r in rows}),
          S["uniqueAccessions"])
    check("cached first-sale dates parsed", sum(1 for r in rows if r.get("sale0")),
          S["firstSaleDatesParsed"])
    check("sampled rows explicitly marked yet-to-occur",
          sum(1 for r in rows if r.get("yet") is True), S["yetToOccur"])
    check("pooled-fund filing rows", sum(r["ind"] == FUND for r in rows), S["fundFilings"])
    check("non-fund filing rows", sum(r["ind"] != FUND for r in rows), S["coFilings"])
    check("distinct CIKs sampled", len({r["cik"] for r in rows}), S["issuers"])
    check("amendments in the sample",
          sum(1 for r in rows if r["form"] == "D/A"), S["amendments"])

    # Fold in filing order so the profile uses the latest sampled filing's
    # values, including a blank rather than an older nonblank value.
    fold = {}
    for r in sorted(rows, key=lambda row: (row["filed"], row["acc"])):
        cik = str(r["cik"]).lstrip("0") or "0"
        e = fold.setdefault(cik, {"inds": set(), "latest_ind": None,
                                       "ninv": None, "sold": None,
                                       "people": defaultdict(int),
                                       "entities": defaultdict(int)})
        e["latest_ind"] = r["ind"]
        e["name"], e["nameFromIndex"], e["nameTruncated"], e["nameUnresolvedShared"] = expected_name_by_cik[cik]
        e["sharedLatest"] = r["acc"] in shared_accs
        if r["ind"]:
            e["inds"].add(r["ind"])
        for f in ("ninv", "sold"):
            e[f] = r[f]
        # one entry per issuer, not per filing: an amendment that repeats a
        # director has not put them on a second company. Shared-accession
        # Item 3 names are not allocated to a specific co-issuer CIK, so those
        # links belong only in the joint filing detail and not the CIK graph.
        seen = e.setdefault("seen", set())
        if r["acc"] in shared_accs:
            continue
        for p in r["p"]:
            person = is_person(p["n"])
            namespace = "person" if person else "entity"
            k = key(p["n"]) if person else entity_key(p["n"])
            namespaced = (namespace, k)
            if k and namespaced not in seen:
                seen.add(namespaced)
                target = e["people"] if person else e["entities"]
                target[k] += 1

    # The directory must expose every normalized name retained by each CIK
    # fold. Compare name-key sets independently of the builder's display text.
    directory_by_cik = {profile["c"]: profile for profile in D["issuers"]}
    directory_name_mismatches = 0
    issuer_label_mismatches = 0
    issuer_name_source_mismatches = 0
    for cik, e in fold.items():
        profile = directory_by_cik.get(cik, {})
        issuer_label_mismatches += profile.get("n") != e["name"]
        issuer_name_source_mismatches += (
            (profile.get("nameFromIndex"), profile.get("nameTruncated"),
             profile.get("nameUnresolvedShared")) !=
            (e["nameFromIndex"], e["nameTruncated"], e["nameUnresolvedShared"]))
        expected_people = set(e["people"])
        expected_entities = set(e["entities"])
        people_list = [key(name) for name in profile.get("P", [])]
        entities_list = [entity_key(name) for name in profile.get("E", [])]
        actual_people = set(people_list)
        actual_entities = set(entities_list)
        directory_name_mismatches += len(expected_people ^ actual_people)
        directory_name_mismatches += len(expected_entities ^ actual_entities)
        directory_name_mismatches += len(people_list) - len(actual_people)
        directory_name_mismatches += len(entities_list) - len(actual_entities)
    check("directory issuer labels match XML or identified index metadata",
          issuer_label_mismatches, 0)
    check("directory issuer-name source flags match local metadata",
          issuer_name_source_mismatches, 0)
    check("directory retains every folded related-name key",
          directory_name_mismatches, 0)
    check("directory profiles with more than 8 person names",
          sum(len(profile["P"]) > 8 for profile in D["issuers"]), 51)
    check("directory profiles with more than 4 entity names",
          sum(len(profile["E"]) > 4 for profile in D["issuers"]), 5)
    check("maximum person-name keys in a directory profile",
          max(len(profile["P"]) for profile in D["issuers"]), 23)
    check("maximum entity-name keys in a directory profile",
          max(len(profile["E"]) for profile in D["issuers"]), 9)

    expected_joint_signature = {}
    for cik, accessions in expected_joint_by_cik.items():
        expected_joint_signature[cik] = {
            acc: {
                "ciks": sorted(population_ciks[acc]),
                "primaryCik": primary_ciks.get(acc),
                "xmlName": next(r["name"] for r in rows if r["acc"] == acc),
                "p": sorted((kind, name_key, value[1])
                            for (kind, name_key), value in entries.items()),
            }
            for acc, entries in accessions.items()
        }
    actual_joint_signature = {}
    for profile in D["issuers"]:
        actual_joint_signature[profile["c"]] = {
            group["acc"]: {
                "ciks": group["ciks"], "primaryCik": group["primaryCik"],
                "xmlName": group["xmlName"],
                "p": sorted(("person" if not p["e"] else "entity",
                             key(p["n"]) if not p["e"] else entity_key(p["n"]),
                             tuple(sorted(p["r"])))
                            for p in group["p"]),
            }
            for group in profile.get("J", [])
        }
    joint_mismatches = sum(
        actual_joint_signature.get(cik, {}) != groups
        for cik, groups in expected_joint_signature.items()
    ) + sum(cik not in expected_joint_signature
            for cik in actual_joint_signature if actual_joint_signature[cik])
    check("joint Item 3 names remain visible but outside CIK arrays",
          joint_mismatches, 0)

    # Recompute the industry table from every repeated person-key / non-fund
    # issuer-profile association. The repeat-name index intentionally caps its
    # issuer examples at six, so its example list cannot supply this total.
    person_profiles = defaultdict(list)
    for e in fold.values():
        if e["latest_ind"] == FUND:
            continue
        industry = e["latest_ind"] or "unclassified"
        for person_key in e["people"]:
            person_profiles[person_key].append(industry)
    repeat_industry_raw = Counter(
        industry
        for industries in person_profiles.values() if len(industries) > 1
        for industry in industries
    )
    repeat_industry_expected = [
        [industry, count] for industry, count in sorted(
            repeat_industry_raw.items(), key=lambda item: (-item[1], item[0]))
    ]
    print("\nindustries across repeated person / issuer-profile associations")
    check("raw repeated-name issuer-profile associations",
          sum(repeat_industry_raw.values()), 74)
    check("generated repeated-name industry association total",
          S.get("repeatIndTotal"), sum(repeat_industry_raw.values()))
    check("visible repeated-name industry links sum",
          sum(count for _, count in S["repeatInd"]),
          sum(repeat_industry_raw.values()))
    check("generated full repeated-name industry category map",
          S["repeatInd"], repeat_industry_expected)

    funds = [e for e in fold.values() if FUND in e["inds"]]
    cos = [e for e in fold.values() if FUND not in e["inds"] and e["inds"]]

    print("\ncorpus shape")
    check("pooled investment funds", len(funds), S["funds"])
    check("non-fund issuer CIK profiles", len(cos), S["cos"])
    check("fund share, percent", round(100 * len(funds) / len(fold), 2), S["fundPct"])
    entity_only = 0
    for r in rows:
        if not any(is_person(p["n"]) for p in r["p"]):
            entity_only += 1
    check("filings with no name matching the person-name heuristic", entity_only,
          S["entityOnlyFilings"])

    print("\nname keys classified by the person-name heuristic on non-fund issuer CIK profiles")
    deg = Counter()
    for e in cos:
        for k, v in e["people"].items():
            deg[k] += v
    once = sum(1 for v in deg.values() if v == 1)
    check("distinct normalized name keys", len(deg), S["coNames"]["distinct"])
    check("appearances", sum(deg.values()), S["coNames"]["appearances"])
    check("appear exactly once", once, S["coNames"]["once"])
    check("percent of name keys that appear once",
          round(100 * once / len(deg), 2), S["coNames"]["oncePct"])
    check("name keys on two or more issuer profiles",
          sum(1 for v in deg.values() if v > 1), S["coNames"]["repeat"])
    check("edges those repeaters add",
          sum(v - 1 for v in deg.values() if v > 1), S["coNames"]["bridged"])

    print("\nall related-person keys and entity-only keys")
    all_deg = Counter()
    entity_deg = Counter()
    for e in fold.values():
        for k in e["people"]:
            all_deg[("person", k)] += 1
        for k in e["entities"]:
            all_deg[("entity", k)] += 1
            entity_deg[k] += 1

    def check_profile(label, counts, expected):
        once = sum(1 for v in counts.values() if v == 1)
        check(f"{label}: distinct keys", len(counts), expected["distinct"])
        check(f"{label}: profile appearances", sum(counts.values()), expected["appearances"])
        check(f"{label}: keys appearing once", once, expected["once"])
        check(f"{label}: once percentage",
              round(100 * once / len(counts), 2) if counts else 0,
              expected["oncePct"])
        check(f"{label}: repeated keys",
              sum(1 for v in counts.values() if v > 1), expected["repeat"])
        check(f"{label}: repeat edges",
              sum(v - 1 for v in counts.values() if v > 1), expected["bridged"])

    check_profile("all related-person keys", all_deg, S["allNames"])
    check_profile("entity-only name keys", entity_deg, S["entityNames"]["entities"])

    print("\nname keys matching the person-name heuristic across the whole sample")
    pdeg = Counter()
    pseen = defaultdict(set)
    for r in rows:
        if r["acc"] in shared_accs:
            continue
        for p in r["p"]:
            if is_person(p["n"]):
                pseen[key(p["n"])].add(r["cik"])
    for k, v in pseen.items():
        pdeg[k] = len(v)
    check("distinct normalized name keys", len(pdeg), S["peopleNames"]["distinct"])
    check("appear exactly once",
          sum(1 for v in pdeg.values() if v == 1), S["peopleNames"]["once"])

    print("\nmost frequent names")
    top = Counter()
    tseen = defaultdict(set)
    for r in rows:
        if r["acc"] in shared_accs:
            continue
        for p in r["p"]:
            person = is_person(p["n"])
            k = key(p["n"]) if person else entity_key(p["n"])
            tseen[("person" if person else "entity", k)].add(r["cik"])
    for k, v in tseen.items():
        top[k] = len(v)
    named = {k: v for k, v in top.items() if v > 1}
    for i, (k, v) in enumerate(sorted(named.items(), key=lambda x: -x[1])[:3]):
        check(f"repeat name #{i + 1} filings", v, D["repeats"][i]["d"])
    # The top repeated normalized keys often carry administrative Form D roles.
    admin = 0
    for k, v in sorted(named.items(), key=lambda x: -x[1])[:9]:
        for r in rows:
            if r["acc"] in shared_accs:
                continue
            for p in r["p"]:
                person = is_person(p["n"])
                pkey = ("person", key(p["n"])) if person else (
                    "entity", entity_key(p["n"]))
                if pkey == k and p.get("c"):
                    c = p["c"].lower()
                    if any(w in c for w in ("agent", "general partner", "administrator",
                                            "manager of", "authorized")):
                        admin += 1
                    break
            else:
                continue
            break
    check("of the top 9 repeats, named as agents or GPs", admin, 9)

    aqr_profile = next(i for i in D["issuers"] if i["c"] == "2136966")
    expected_aqr_names = {
        "N/A AQR Capital Management II, LLC",
        "N/A AQR Capital Management, LLC",
    }
    aqr_repeats = {entity_key(r["n"]): r["d"] for r in D["repeats"]
                   if "aqr capital management" in entity_key(r["n"])}
    check("AQR II and non-II names stay separate in all-name repeats",
          set(aqr_repeats), {
              "n a aqr capital management ii llc",
              "n a aqr capital management llc",
          })
    check("AQR II entity profile appearances",
          aqr_repeats.get("n a aqr capital management ii llc"), 14)
    check("AQR non-II entity profile appearances",
          aqr_repeats.get("n a aqr capital management llc"), 15)

    print("\nwhat the non-fund issuers actually are")
    VENT = {
        "Other Technology", "Technology", "Computers", "Telecommunications",
        "Biotechnology", "Pharmaceuticals", "Other Health Care", "Health Care",
        "Business Services", "Manufacturing",
    }
    ind_of = {}
    for r in rows:
        if r["ind"]:
            ind_of[r["cik"]] = r["ind"]
    other_group = sum(1 for cik, e in fold.items()
                      if FUND not in e["inds"] and e["inds"]
                      and ind_of.get(cik) == "Other")
    check("broad Other category excluded from named-industry count",
          other_group, 80)
    tech = sum(1 for e in cos if FUND not in e["inds"] and ind_of.get(
        next((c for c in fold if fold[c] is e), ""), "") in VENT)
    check("non-fund issuer profiles that are tech, health, services or manufacturing",
          tech, S["coTech"])
    check("the rest of the non-fund issuers", len(cos) - tech, S["coOther"])

    print("\ninvestor counts, non-fund filing rows")
    co_rows = [r for r in rows if r["ind"] != FUND]
    all_inv = S["investors"]["all"]
    all_positive = sum(1 for r in rows if r["ninv"] is not None and r["ninv"] > 0)
    all_cached_zero = sum(1 for r in rows if r["ninv"] == 0)
    all_unreported = sum(1 for r in rows if r["ninv"] is None)
    check("all-sample positive investor counts", all_positive, all_inv["reporting"])
    check("all-sample cached zero or legacy-blank values", all_cached_zero,
          all_inv["cachedZeroOrLegacyBlank"])
    check("all-sample unreported cached counts", all_unreported, all_inv["unreported"])
    check("all-sample stats do not claim a zero/blank split",
          "zero" not in all_inv and "blank" not in all_inv, True)
    withn = [e for e in co_rows if e["ninv"] and e["ninv"] > 0]
    cached_zero_or_legacy_blank = [e for e in co_rows if e["ninv"] == 0]
    unreported = [e for e in co_rows if e["ninv"] is None]
    inv = S["investors"]["co"]
    check("non-fund filing rows", len(co_rows), inv["n"])
    check("reporting at least one investor", len(withn), inv["reporting"])
    check("cached non-fund zero values, explicit or legacy blank",
          len(cached_zero_or_legacy_blank), inv["cachedZeroOrLegacyBlank"])
    check("non-fund rows with an unreported cached count", len(unreported), inv["unreported"])
    check("non-fund stats do not claim a zero/blank split",
          "zero" not in inv and "blank" not in inv, True)
    med = sorted(e["ninv"] for e in withn)[len(withn) // 2]
    check("median reported investors", med, inv["medianBackers"])
    checks = sorted(e["sold"] / e["ninv"] for e in withn if e["sold"] and e["sold"] > 0)
    check("ratio sample with positive count and amount sold", len(checks), inv["checkN"])
    check("median implied cheque", int(checks[len(checks) // 2]), inv["checkMedian"])
    check("max reported investor count", max(e["ninv"] for e in withn), inv["maxBackers"])

    all_ratio_rows = [r for r in rows if r["ninv"] is not None and r["ninv"] > 0
                      and r["sold"] is not None and r["sold"] > 0]
    check("all-sample ratio rows with positive count and amount sold",
          len(all_ratio_rows), S["investors"]["all"]["checkN"])

    print("\nfiler attestations")
    band = lambda k: ("1" if k == 1 else "2" if k == 2 else "3-5" if k <= 5 else
                      "6-10" if k <= 10 else "11-25" if k <= 25 else
                      "26-100" if k <= 100 else "100+")
    got = Counter(band(e["ninv"]) for e in withn)
    want = {b: c for b, c in inv["ninvBands"]}
    check("investor count bands", dict(sorted(got.items())), dict(sorted(want.items())))

    print("\nlatest sampled filing per non-fund issuer CIK")
    grouped_inv = S["investors"]["coIssuers"]
    grouped_withn = [e for e in cos if e["ninv"] and e["ninv"] > 0]
    check("distinct non-fund issuer CIKs", len(cos), grouped_inv["n"])
    check("CIKs with a positive latest investor count", len(grouped_withn), grouped_inv["reporting"])
    grouped_cached_zero = [e for e in cos if e["ninv"] == 0]
    grouped_unreported = [e for e in cos if e["ninv"] is None]
    check("latest CIK profiles with cached zero, explicit or legacy blank",
          len(grouped_cached_zero), grouped_inv["cachedZeroOrLegacyBlank"])
    check("latest CIK profiles with unreported cached count", len(grouped_unreported),
          grouped_inv["unreported"])
    check("latest-profile stats do not claim a zero/blank split",
          "zero" not in grouped_inv and "blank" not in grouped_inv, True)

    print("\namendment parser fixture and cached lineage coverage")
    fixture_root = ET.parse(LINEAGE_FIXTURE).getroot()
    fixture_offering = fixture_root.find("./offeringData")
    filing_type = fixture_offering.find("typeOfFiling") if fixture_offering is not None else None
    new_or_amendment = None
    if filing_type is not None:
        new_or_amendment = next((node for node in filing_type
                                 if node.tag == "newOrAmendment"), None)
    fixture_previous = None
    if new_or_amendment is not None:
        fixture_previous = next((node.text.strip() for node in new_or_amendment
                                 if node.tag == "previousAccessionNumber" and node.text), None)
    fixture_acc = fixture_root.get("accession")
    check("SEC fixture accession", fixture_acc, "0001012975-26-000878")
    check("SEC fixture previous accession", fixture_previous, "0001012975-26-000877")
    try:
        from fetch_formd import parse_previous_accession
        production_previous = parse_previous_accession(fixture_offering)
    except Exception as exc:  # noqa: BLE001
        production_previous = f"parser error: {exc}"
    check("fetcher parser reads SEC fixture path", production_previous, fixture_previous)

    amendments = [r for r in rows if r["form"] == "D/A"]
    accs = {r["acc"] for r in rows}
    fixture_cik = str(fixture_root.get("cik", "")).lstrip("0") or "0"
    fixture_da_rows = [r for r in rows if r["acc"] == fixture_acc
                       and (str(r["cik"]).lstrip("0") or "0") == fixture_cik
                       and r["form"] == "D/A"]
    fixture_target_rows = [r for r in rows if r["acc"] == fixture_previous
                           and (str(r["cik"]).lstrip("0") or "0") == fixture_cik]
    fixture_in_sample = bool(fixture_da_rows and fixture_target_rows)
    fixture_da_to_d = fixture_in_sample and any(r["form"] == "D" for r in fixture_target_rows)
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
    sampled_link_rows = sum(1 for r in checked_rows if r["prevAcc"] in accs)
    fixture_row_checked = any(
        r["acc"] == fixture_acc
        and (str(r["cik"]).lstrip("0") or "0") == fixture_cik
        and r.get("prevAccStatus") == "checked"
        and r.get("prevAcc") == fixture_previous
        for r in checked_rows
    )
    known_matches = sampled_link_rows + int(fixture_in_sample and not fixture_row_checked)
    lineage = S["amendLineage"]
    check("cached D/A rows", len(amendments), lineage["amendments"])
    check("cached D/A rows re-parsed", reparsed, lineage["reparsed"])
    check("cached D/A rows with a checked prior accession", checked_count, lineage["checked"])
    check("cached D/A rows parsed without the required prior accession", missing_field,
          lineage["missingField"])
    check("cached D/A fetches that returned no document", fetch_failed,
          lineage["fetchFailed"])
    check("cached D/A XML parse failures", parse_failed, lineage["parseFailed"])
    check("legacy D/A rows without a recorded lineage inspection", unverified,
          lineage["unverified"])
    check("D/A rows still unresolved", unresolved, lineage["unresolved"])
    check("fixture D/A-to-D pair for its CIK is in the sample", fixture_da_to_d,
          lineage["fixture"]["daToDInSample"])
    check("fixture D/A and prior accession rows for its CIK are in the sample", fixture_in_sample,
          lineage["fixture"]["pairInSample"])
    check("source-confirmed D/A-to-declared-previous links in sample",
          known_matches, lineage["sourceConfirmedLinksInSample"])
    check("reported D/A-to-declared-previous link lower bound",
          known_matches, lineage["lowerBound"])
    exact = known_matches if unresolved == 0 else None
    check("exact D/A-to-declared-previous link count only when cache is complete",
          S["amendLinksInSample"], exact)

    print("\nissuer/name graph totals")
    raw_edges = sum(deg.values())
    raw_nodes = len(deg) + len(cos)
    repeat_edges = sum(v - 1 for v in deg.values() if v > 1)
    check("raw issuer/name edges against generated count",
          raw_edges, S["coNames"]["appearances"])
    check("raw issuer/name nodes against generated count",
          raw_nodes, S["coNames"]["distinct"] + S["cos"])
    check("edges = distinct name keys + repeat edges",
          len(deg) + repeat_edges, raw_edges)

    print("\nsampled filing profiles")
    twice = 0
    per = defaultdict(int)
    for r in rows:
        per[r["cik"]] += 1
    twice = sum(1 for v in per.values() if v > 1)
    check("issuers that filed more than once", twice, S["multiFilingIssuers"])

    print("\nselected filing card labels")
    raw_by_acc = {r["acc"]: r for r in rows}

    def label_money(value):
        value = value or 0
        return f"${value / 1e6:.1f}m" if value < 1e9 else f"${value / 1e9:.1f}bn"

    def label_investors(row):
        if row["ninv"] is None:
            return "investor count unavailable"
        if row["ninv"] == 0:
            return "cached investor count 0 (explicit zero or legacy blank unknown)"
        return f"{row['ninv']} reported investors"

    def selected_label_expected(row, label):
        if label.startswith("A biotech issuer,"):
            return (f"A biotech issuer, {label_money(row['sold'])} sold, "
                    f"{label_investors(row)}")
        if label.startswith("An insurer reporting"):
            return (f"An insurer reporting {label_money(row['sold'])} sold and "
                    f"{label_investors(row)}")
        if label.startswith("A real estate vehicle with"):
            return f"A real estate vehicle with {label_investors(row)}"
        if label.startswith("A fund,"):
            people = sum(1 for p in row["p"] if is_person(p["n"]))
            return f"A fund, {people} names deep"
        if label.startswith("A manufacturer,"):
            return (f"A manufacturer, {label_money(row['sold'])} sold, "
                    f"{label_investors(row)}")
        return None

    forms = D.get("forms", [])
    check("selected filing card count", len(forms), 5)
    for form in forms:
        row = raw_by_acc.get(form["acc"])
        expected = selected_label_expected(row, form["label"]) if row else None
        check(f"card label agrees with selected row {form['acc']}",
              form["label"], expected)

    print("\nnon-US issuers are present, not missing")
    foreign = [r for r in rows if r["juris"] and r["juris"].upper() not in {
        "DELAWARE", "CALIFORNIA", "TEXAS", "NEW YORK", "NEVADA", "COLORADO", "OHIO",
        "FLORIDA", "MASSACHUSETTS", "ILLINOIS", "WASHINGTON", "GEORGIA", "VIRGINIA",
        "MARYLAND", "UTAH", "ARIZONA", "OREGON", "PENNSYLVANIA", "NEW JERSEY",
        "NORTH CAROLINA", "MINNESOTA", "MISSOURI", "TENNESSEE", "WISCONSIN",
        "INDIANA", "MICHIGAN", "CONNECTICUT", "ALABAMA", "LOUISIANA", "KENTUCKY",
        "OKLAHOMA", "SOUTH CAROLINA", "KANSAS", "IOWA", "ARKANSAS", "IDAHO",
        "MONTANA", "NEBRASKA", "NEW MEXICO", "HAWAII", "ALASKA", "RHODE ISLAND",
        "VERMONT", "WYOMING", "MAINE", "NEW HAMPSHIRE", "MISSISSIPPI",
        "WEST VIRGINIA", "NORTH DAKOTA", "SOUTH DAKOTA", "DISTRICT OF COLUMBIA",
        "PUERTO RICO", "GUAM", "VIRGIN ISLANDS",
    }]
    foreign_ciks = {r["cik"] for r in foreign}
    check("non-US issuers in the sample", len(foreign_ciks), S["nonUsTotal"])

    print("\nRule 504 is covered by Form D, so it is not an exclusion")
    codes = Counter(e for r in rows for e in (r["exc"] or []))
    check("filings using Rule 504", sum(v for k, v in codes.items()
                                        if k.startswith("04")), 8)

    print("\nno field identifies investors by name in the checked sample")
    keys = set()
    for r in rows:
        keys |= set(r.keys())
    bad = [k for k in keys if re.search(r"investor|buyer|purchaser|holder", k, re.I)]
    check("fields identifying investors or buyers by name", bad, [])

    print("\n" + ("all checks passed" if not fails else f"{len(fails)} FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
