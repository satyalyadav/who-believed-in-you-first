#!/usr/bin/env python3
"""
Crawl SEC EDGAR Form D / Form D/A filings for a date window and emit one compact
JSON record per filing.

Form D is an SEC notice of an exempt securities offering. It reports related
persons and a separate total investor count. It does not identify investors or
record endorsements.

Stage 1  collect Form D / Form D/A rows from EDGAR daily dissemination indexes
Stage 2  fetch the primary_doc.xml for each row's accession and CIK
Stage 3  parse the fields we care about, append one record per index row

Resumable: re-running skips accession/CIK filing rows already present in the output file.
Use --refresh-lineage to replace cached D/A rows after the parser is corrected.
"""
import argparse
import gzip
import http.client
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

UA = None
HEADERS = {}
CONTACT_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net", "example.edu"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "formd.jsonl")
INDEX_OUT = os.path.join(DATA, "accessions.json")

_print_lock = threading.Lock()
_gate = threading.Lock()
_next_slot = [0.0]
PACE = 0.25  # seconds between request starts, shared by every worker


def configure_contact(contact=None):
    """Require a real operator contact before making any SEC request."""
    global UA, HEADERS
    contact = (contact or os.environ.get("DROP_SEC_CONTACT", "")).strip()
    domain = contact.rsplit("@", 1)[-1].lower() if "@" in contact else ""
    if (not CONTACT_RE.fullmatch(contact) or domain in PLACEHOLDER_DOMAINS
            or domain.startswith("example.")):
        raise ValueError(
            "Set DROP_SEC_CONTACT to a real, monitored email address before "
            "accessing EDGAR. Do not use an example address."
        )
    UA = f"WhoBelievedInYouFirst {contact}"
    HEADERS = {
        "User-Agent": UA,
        "Accept-Encoding": "gzip",
        "Accept": "*/*",
    }
    return UA


def log(*a):
    with _print_lock:
        print(*a, file=sys.stderr, flush=True)


def pause(seconds):
    """Push every worker back by `seconds` after a rate-limit response."""
    with _gate:
        _next_slot[0] = max(_next_slot[0], time.time() + seconds)


def slot():
    with _gate:
        now = time.time()
        start = max(now, _next_slot[0])
        _next_slot[0] = start + PACE
    wait = start - now
    if wait > 0:
        time.sleep(wait)


MISSING = object()  # the key does not exist on EDGAR; not a rate-limit problem


def fetch_bytes(url, deadline_s=25):
    """Read the complete response body within one deadline, including gzip bodies.

    urlopen's timeout applies per socket operation. Use read1 so each iteration
    returns after one socket read, then reset the socket timeout to the remaining
    monotonic budget; a trickle cannot restart the total body deadline.
    """
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        deadline = time.monotonic() + max(0, deadline_s)
        sock = getattr(getattr(getattr(r, "fp", None), "raw", None), "_sock", None)
        if sock is None:
            raise RuntimeError("cannot enforce response body deadline on this HTTP response")
        chunks = []
        remaining_body = r.length
        while remaining_body != 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("response body exceeded deadline")
            sock.settimeout(remaining)
            try:
                chunk = r.read1(65536)
            except TimeoutError as exc:
                raise TimeoutError("response body exceeded deadline") from exc
            if time.monotonic() > deadline:
                raise TimeoutError("response body exceeded deadline")
            if not chunk:
                if remaining_body is not None and remaining_body > 0:
                    raise http.client.IncompleteRead(b"".join(chunks), remaining_body)
                break
            chunks.append(chunk)
            if remaining_body is not None:
                remaining_body = max(0, remaining_body - len(chunk))
        body = b"".join(chunks)
        if r.headers.get("Content-Encoding", "").strip().lower() == "gzip":
            return gzip.decompress(body)
        return body


def get(url, tries=8, missing=MISSING):
    """Fetch a URL. Returns None on a real failure and `missing` on a 404.

    EDGAR answers a nonexistent key with a 403 AccessDenied page, so the status
    code alone is ambiguous. The body tells the two apart: "AccessDenied" means
    the key is absent, "Undeclared Automated Tool" means we are going too fast
    and must back off hard.
    """
    for i in range(tries):
        try:
            slot()
            return fetch_bytes(url)
        except urllib.error.HTTPError as e:
            try:
                body = e.read(8000)
                if e.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                body = body.decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                body = ""
            if "AccessDenied" in body or e.code == 404:
                return missing
            if e.code in (403, 429, 500, 502, 503, 504):
                wait = min(90, 4.0 * (2 ** i)) + random.random() * 2
                pause(wait)
                log(f"  throttled ({e.code}) on {url.rsplit('/', 1)[-1]}; pausing {wait:.0f}s")
                time.sleep(wait * 0.25)
                continue
            return None
        except Exception:  # noqa: BLE001
            time.sleep(1.0 * (i + 1) + random.random())
    return None


def accession_url(cik, acc, doc="primary_doc.xml"):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"


def index_url(cik, acc):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/index.json"


def filing_key(row):
    """An accession may appear for multiple CIKs in the dissemination index."""
    cik = str(row["cik"]).lstrip("0") or "0"
    return str(row["acc"]), cik


def uncached_rows(candidates, cached):
    """Return candidate filing rows whose accession/CIK pair is not cached."""
    done = {filing_key(row) for row in cached}
    return [row for row in candidates if filing_key(row) not in done]


def apply_lineage_results(cached, targets, refreshed):
    """Replace only the matching accession/CIK rows after a lineage refresh."""
    replacements = {}
    failures = {}
    for row, (record, failure_status) in zip(targets, refreshed):
        key = filing_key(row)
        if record:
            replacements[key] = record
        else:
            failures[key] = failure_status
    updated = []
    for row in cached:
        key = filing_key(row)
        if key in replacements:
            updated.append(replacements[key])
        elif key in failures:
            updated.append({**row, "prevAccStatus": failures[key]})
        else:
            updated.append(row)
    return updated, replacements, failures


# ---------------------------------------------------------------- stage 1
def collect_accessions(start, end, tries=8):
    """Walk the EDGAR daily dissemination indexes and pull every Form D row.

    If a wider crawl is already cached we slice it locally instead of asking
    EDGAR for the same index files twice.
    """
    if os.path.exists(INDEX_OUT):
        cached = json.load(open(INDEX_OUT))
        window = cached.get("window") or ["", ""]
        rows = cached.get("rows") or []
        if window[0] <= start and window[1] >= end and rows:
            sliced = [r for r in rows if start <= r["filed"] <= end]
            log(f"accessions: sliced {len(sliced)} rows out of the cached "
                f"{window[0]}-{window[1]} crawl")
            return sliced

    rows = []
    y = int(start[:4])
    day = start
    while day <= end:
        m = int(day[4:6])
        q = (m - 1) // 3 + 1
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{day}.idx"
        raw = get(url, tries=tries, missing=None)
        if raw is None:
            day = _next_day(day)
            continue
        text = raw.decode("utf-8", "replace")
        n = 0
        for line in text.split("\n"):
            form = line[0:10].strip()
            if form not in ("D", "D/A"):
                continue
            mm = re.search(r"edgar/data/(\d+)/(\d{10}-\d{2}-\d{6})\.txt", line)
            if not mm:
                continue
            rows.append(
                {
                    "acc": mm.group(2),
                    "cik": mm.group(1),
                    "form": form,
                    "name": line[10:72].strip(),
                    "filed": day,
                }
            )
            n += 1
        day = _next_day(day)
        if day[8:] == "01":
            time.sleep(0.2)
    os.makedirs(DATA, exist_ok=True)
    json.dump({"window": [start, end], "rows": rows}, open(INDEX_OUT, "w"))
    log(f"accessions: {len(rows)} Form D/D/A EDGAR index rows between {start} and {end}")
    return rows


def _next_day(day):
    d = int(day[6:8]) + 1
    m, y = int(day[4:6]), int(day[:4])
    while d > _days_in(m, y):
        d = 1
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return f"{y:04d}{m:02d}{d:02d}"


def _days_in(m, y):
    return [31, 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28, 31, 30, 31, 30,
            31, 31, 30, 31, 30, 31][m - 1]


# ---------------------------------------------------------------- stage 3
def txt(node, *path):
    cur = node
    for p in path:
        if cur is None:
            return None
        cur = cur.find(p)
    return cur.text if cur is not None else None


def money(v):
    if v is None:
        return None
    v = v.strip().replace(",", "").replace("$", "")
    if not v or v.lower() in ("indefinite", "n/a", "not applicable"):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def count(v):
    """Parse a filed integer without turning a blank field into zero."""
    if v is None:
        return None
    v = v.strip().replace(",", "")
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def parse_previous_accession(offering):
    """Read the prior accession from the EDGAR Form D amendment section."""
    node = offering.find("./typeOfFiling/newOrAmendment/previousAccessionNumber")
    return node.text.strip() if node is not None and node.text else None


def parse_formd(raw, meta):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    iss = root.find("primaryIssuer")
    if iss is None:
        return None

    persons = []
    for rp in root.findall("./relatedPersonsList/relatedPersonInfo"):
        first = (txt(rp, "relatedPersonName", "firstName") or "").strip()
        middle = (txt(rp, "relatedPersonName", "middleName") or "").strip()
        last = (txt(rp, "relatedPersonName", "lastName") or "").strip()
        if not first and not middle and not last:
            continue
        rels = [r.text for r in rp.findall("./relatedPersonRelationshipList/relationship") if r.text]
        if rels == ["None"]:
            rels = []
        clar = txt(rp, "relationshipClarification")
        persons.append(
            {
                "n": " ".join(x for x in (first, middle, last) if x).strip(),
                "f": first,
                "m": middle,
                "l": last,
                "r": rels,
                "c": (clar or "").strip() or None,
                "st": txt(rp, "relatedPersonAddress", "stateOrCountry"),
            }
        )

    off = root.find("offeringData")
    if off is None:
        return None

    ind = off.find("industryGroup")
    industry = None
    fund_type = None
    is_40act = None
    if ind is not None:
        gt = txt(ind, "industryGroupType")
        industry = gt.strip() if gt else None
        fund_type = txt(ind, "investmentFundInfo", "investmentFundType")
        is_40act = txt(ind, "investmentFundInfo", "is40Act")

    exc = [i.text for i in off.findall("./federalExemptionsExclusions/item") if i.text]

    sig = off.find("./signatureBlock/signature")
    signer = None
    if sig is not None:
        signer = {
            "n": txt(sig, "nameOfSigner"),
            "t": txt(sig, "signatureTitle"),
            "d": txt(sig, "signatureDate"),
        }

    am = off.find("./typeOfFiling/newOrAmendment/isAmendment")
    prev = parse_previous_accession(off)
    dfs = off.find("./typeOfFiling/dateOfFirstSale")
    first_sale = None
    yet_to_occur = None
    if dfs is not None:
        first_sale = txt(dfs, "value")
        yet_to_occur = txt(dfs, "yetToOccur") == "true"

    sold = money(txt(off, "offeringSalesAmounts", "totalAmountSold"))
    offering_raw = txt(off, "offeringSalesAmounts", "totalOfferingAmount")
    remaining_raw = txt(off, "offeringSalesAmounts", "totalRemaining")

    yr = off.find("./issuerSize/revenueRange")
    nav = off.find("./issuerSize/aggregateNetAssetValueRange")

    sec_types = []
    st = off.find("typesOfSecuritiesOffered")
    if st is not None:
        for child in st:
            tag = child.tag
            if child.text and child.text.strip().lower() in ("true", "false"):
                if child.text.strip().lower() == "true":
                    sec_types.append(tag)

    return {
        "acc": meta["acc"],
        "cik": meta["cik"],
        "form": meta["form"],
        "filed": meta["filed"],
        "name": (txt(iss, "entityName") or meta["name"]).strip(),
        "juris": txt(iss, "jurisdictionOfInc"),
        "etype": txt(iss, "entityType"),
        "yinc": txt(iss, "yearOfInc", "value"),
        "city": txt(iss, "issuerAddress", "city"),
        "state": txt(iss, "issuerAddress", "stateOrCountry"),
        "prev": [p.text for p in iss.findall("./issuerPreviousNameList/value") if p.text and p.text != "None"],
        "p": persons,
        "ind": industry,
        "ftype": fund_type,
        "f40": is_40act == "true" if is_40act is not None else None,
        "rev": yr.text.strip() if yr is not None else None,
        "nav": nav.text.strip() if nav is not None else None,
        "exc": exc,
        "506c": "06c" in exc,
        "amend": am is not None and am.text == "true",
        "prevAcc": prev,
        "prevAccStatus": (
            ("checked" if prev else "missing_field")
            if meta["form"] == "D/A" else "not_applicable"
        ),
        "sale0": first_sale,
        "yet": yet_to_occur,
        "offer": money(offering_raw),
        "offerIndef": bool(offering_raw and "ndefined" in offering_raw),
        "sold": sold,
        "rem": money(remaining_raw),
        "remIndef": bool(remaining_raw and "ndefined" in remaining_raw),
        "ninv": count(txt(off, "investors", "totalNumberAlreadyInvested")),
        "comm": money(txt(off, "salesCommissionsFindersFees", "salesCommissions", "dollarAmount")),
        "fees": money(txt(off, "salesCommissionsFindersFees", "findersFees", "dollarAmount")),
        "proceeds": money(txt(off, "useOfProceeds", "grossProceedsUsed", "dollarAmount")),
        "secs": sec_types,
        "bcombo": txt(off, "businessCombinationTransaction", "isBusinessCombinationTransaction") == "true",
        "sig": signer,
    }


# ---------------------------------------------------------------- stage 2
def fetch_one(row, stats, with_failure_status=False, tries=8):
    raw = get(accession_url(row["cik"], row["acc"]), tries=tries, missing=None)
    if raw is None:
        # agent-generated filing: find the real xml name via the index
        raw = None
        idx = get(index_url(row["cik"], row["acc"]), tries=tries, missing=None)
        if idx:
            try:
                items = json.loads(idx)["directory"]["item"]
                for it in items:
                    n = it["name"]
                    if n.endswith(".xml") and "primary_doc" not in n and not n.startswith("xsl"):
                        raw = get(accession_url(row["cik"], row["acc"], n),
                                  tries=tries, missing=None)
                        if raw:
                            break
            except Exception:  # noqa: BLE001
                pass
    if raw is None:
        with _print_lock:
            stats["miss"] += 1
        return (None, "fetch_failed") if with_failure_status else None
    rec = parse_formd(raw, row)
    if rec is None:
        with _print_lock:
            stats["unparsed"] += 1
        return (None, "parse_failed") if with_failure_status else None
    with _print_lock:
        stats["ok"] += 1
        stats["done"] += 1
        if stats["done"] % 500 == 0:
            log(f"  {stats['done']}/{stats['total']} parsed")
    return (rec, None) if with_failure_status else rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260701")
    ap.add_argument("--end", default="20260926")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pace", type=float, default=0.14)
    ap.add_argument("--tries", type=int, default=4)
    ap.add_argument("--sample", type=int, default=0,
                    help="take a reproducible random sample of N EDGAR index rows")
    ap.add_argument("--seed", type=int, default=20260831)
    ap.add_argument("--contact", help="operator contact email for the SEC User-Agent (or set DROP_SEC_CONTACT)")
    ap.add_argument("--refresh-lineage", action="store_true",
                    help="refetch cached D/A rows whose previous-accession field has not been checked")
    args = ap.parse_args()
    try:
        configure_contact(args.contact)
    except ValueError as exc:
        ap.error(str(exc))
    global PACE
    PACE = args.pace

    if args.refresh_lineage:
        if not os.path.exists(OUT):
            ap.error("--refresh-lineage needs an existing data/formd.jsonl cache")
        cached = []
        for line in open(OUT, encoding="utf-8"):
            if line.strip():
                cached.append(json.loads(line))
        targets = [r for r in cached if r.get("form") == "D/A"
                   and (r.get("prevAccStatus") != "checked" or not r.get("prevAcc"))]
        log(f"cached D/A rows: {sum(r.get('form') == 'D/A' for r in cached)}; "
            f"lineage refresh needed: {len(targets)}")
        stats = {"ok": 0, "miss": 0, "unparsed": 0, "done": 0, "total": len(targets)}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            refreshed = list(ex.map(
                lambda r: fetch_one(r, stats, with_failure_status=True, tries=args.tries),
                targets))
        updated, replacements, failures = apply_lineage_results(cached, targets, refreshed)
        reparsed_rows = sum(1 for record, _ in refreshed if record)
        checked = sum(1 for record, _ in refreshed
                      if record and record.get("prevAccStatus") == "checked" and record.get("prevAcc"))
        missing_field = sum(1 for record, _ in refreshed
                            if record and record.get("prevAccStatus") == "missing_field")
        # Use refreshed response counts above for the log; the retained cache can
        # contain separate CIK rows sharing one accession.
        unresolved = sum(1 for r in updated if r.get("form") == "D/A"
                         and (r.get("prevAccStatus") != "checked" or not r.get("prevAcc")))
        tmp = OUT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for row in updated:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        os.replace(tmp, OUT)
        log(f"lineage refresh: {reparsed_rows}/{len(targets)} rows parsed; "
            f"{checked} have a prior accession; {missing_field} parsed without the required field; "
            f"{stats['miss']} fetches returned no document; {stats['unparsed']} fetched XML documents could not be parsed; "
            f"{unresolved} D/A rows remain unresolved. "
            "Cache updated by accession/CIK identity, preserving separate CIK rows.")
        return

    os.makedirs(DATA, exist_ok=True)
    rows = collect_accessions(args.start, args.end, tries=args.tries)

    # the sample is drawn from the whole population, not from whatever is left
    # to fetch, so re-running with the same seed always yields the same corpus
    if args.sample:
        rnd = random.Random(args.seed)
        todo = sorted(rnd.sample(rows, min(args.sample, len(rows))), key=filing_key)
    else:
        todo = list(rows)

    cached = []
    if os.path.exists(OUT):
        for line in open(OUT):
            try:
                cached.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    done = {filing_key(row) for row in cached}
    todo = uncached_rows(todo, cached)
    if args.limit:
        todo = todo[: args.limit]
    log(f"filings: {len(rows)} total, {len(done)} accession/CIK pairs already on disk, {len(todo)} to fetch")

    stats = {"ok": 0, "miss": 0, "unparsed": 0, "done": 0, "total": len(todo)}
    t0 = time.time()
    with open(OUT, "a") as fh, ThreadPoolExecutor(max_workers=args.workers) as ex:
        for rec in ex.map(lambda r: fetch_one(r, stats, tries=args.tries), todo):
            if rec:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
                fh.flush()
    dt = time.time() - t0
    log(f"filings: {stats['ok']} parsed, {stats['miss']} missing, {stats['unparsed']} unparsed in {dt:.0f}s "
        f"({stats['ok']/max(dt,1):.1f}/s) -> {OUT}")


if __name__ == "__main__":
    main()
