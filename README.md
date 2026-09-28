# Who believed in you first?

A standalone interactive drop about Cosign's public professional endorsements and the different record kept by SEC Form D. Cosign describes attributed professional endorsements, an early-discovery angle, and a separate private intent network. Form D reports certain issuer-related persons and an aggregate investor count. It does not identify investors or endorsements, so this project does not treat one record as a proxy for the other.

The sample contains 1,500 EDGAR daily-index rows, covering 1,497 unique accession numbers, selected with seed 20260926 from a local index window covering 1 July through 26 September 2026. That is a partial-quarter window, not all of Q3. Some accessions appear under multiple CIKs; row-based figures count each index row. Index rows and distinct CIK issuer profiles are reported separately: the cache has 491 non-fund rows and 484 non-fund issuer profiles. The sample also includes pooled-fund index rows and issuer profiles. "Non-fund" is a filing category; it does not mean every issuer is an operating company or startup.

The site includes a searchable issuer directory, sample filings rendered from parsed records, an issuer-related-person co-occurrence graph, filing-level investor-count summaries, and a hypothetical network simulation. The directory unions CIK-attributed related-person names across sampled filings by CIK; values come from the latest sampled row. The full-window index contains 28 sample rows under 25 accessions that appear with multiple CIKs; six rows across three accessions are repeated under multiple CIKs within the sample. For identified secondary CIK rows, the directory uses the matching local index name and visibly marks every such name as potentially truncated; EDGAR index names are capped at 55 characters. The shared accession rows inherit one XML offering record. Their amounts and investor counts are joint-offering values that can repeat across CIK rows. Form D Item 3 names may relate to any issuer on the notice, so the site shows those names separately without CIK assignment and excludes them from CIK-level name metrics. Row-based investor summaries still count each EDGAR index row. Table rows abbreviate long name lists, while search and details use all retained CIK-attributed names. For entries matching the person-name heuristic, the script removes listed suffixes only at the end of a name. For entries classified as entities, it normalizes case, diacritics, and punctuation while preserving every token, including Roman numerals. The current cache omits filed middle names for related people; no names were reconstructed. The corrected parser preserves middle names in future records, but this cache was not refreshed. These rules do not verify identity and can merge distinct parties or split one person across keys, so net counting error is unknown.

The corrected parser reads the Form D Item 7 date from `dateOfFirstSale/value` and preserves related-person middle names. The existing cache was not refreshed, so its historical first-sale dates and middle names remain unverified or absent. It does retain 282 sampled EDGAR index rows explicitly marked “first sale yet to occur.”

Investor-count blanks are preserved as `None` by the corrected parser, but the current cache still contains legacy values from the earlier parser that turned blanks into zero. The cache has 1,205 positive counts and 295 zeros across all 1,500 rows. In the non-fund slice, 408 of 491 rows have positive counts and the other 83 cached values are zero; among the latest sampled row for each of 484 non-fund CIK profiles, 404 are positive and 80 are zero. Those cached zeros may be explicit zeroes or collapsed blanks. The exact split is unknown until a refresh replaces the old records.

## Run it

Before making EDGAR requests, configure a real, monitored operator email address with the DROP_SEC_CONTACT environment variable or the --contact option. Both SEC-fetching scripts validate this contact and include it in the User-Agent. Do not substitute an example or guessed address. The SEC's [EDGAR fair-access policy](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) describes its request and identification requirements.

To use the existing accession cache and fetch only uncached records, run:

    python3 scripts/fetch_formd.py --start 20260701 --end 20260926 --sample 1500 --seed 20260926
    python3 scripts/build_drop.py
    python3 scripts/verify.py
    python3 -m http.server 8000 --directory site

To refresh cached Form D/A lineage fields after the parser changes, run fetch_formd.py with --refresh-lineage. That mode replaces successfully parsed accession/CIK rows in place, reports missing previous-accession fields, requests that returned no document, and fetched XML documents that could not be parsed. It does not append duplicate accession/CIK pairs; separate CIK rows sharing an accession are retained. The refresh makes network requests and requires an operator contact. No lineage refresh was run for the current generated data; the exact count of sampled D/A filings whose declared previous accession is also sampled remains unknown. The SEC source fixture identifies one sampled D/A-to-D link.

The page uses four source assets and one generated data file: index.html, app.js, style.css, model-worker.js, and drop.json. There is no package build step; Google Fonts are fetched for typography.

## Repository map

- scripts/fetch_formd.py reads the EDGAR daily index and fetches and parses each filing's primary XML document.
- scripts/supervise.py runs the fetcher in bounded slices.
- scripts/run_when_allowed.py waits for EDGAR to respond before starting a crawl.
- scripts/build_drop.py builds site/drop.json from the parsed filing cache and captured lineage fixture.
- scripts/verify.py independently recomputes data counts and checks the corrected previous-accession parser against the SEC source fixture.
- scripts/check-model.mjs compares the hypothetical model with a reference implementation and checks its completed-round labels.
- site/index.html, site/app.js, site/style.css, and site/model-worker.js implement the interactive page.
- data/formd.jsonl contains parsed filing records; data/accessions.json contains the cached daily-index rows.
- data/fixtures/formd-amendment-000878.xml captures the relevant amendment field from an SEC filing for offline parser verification.
- TRANSCRIPT.md is a complete visible-conversation transcript reconstructed from the mapped local session. It includes every visible user and assistant text part and every tool invocation and result ordered by source timestamp, with message and part IDs as the tie-breaker. Source timestamps resolve only to milliseconds, so the original sub-millisecond UI order cannot be recovered. It redacts email addresses, credentials and tokens, local paths and endpoints, phone numbers, and internal identifiers. It omits the 305 private reasoning parts and binary image contents from four user image parts and 31 tool PNG attachments.
- POST-AND-DM.md contains review drafts. They have not been sent or posted.

## Scope and limitations

Form D applies to exempt offerings under Regulation D Rules 504 and 506 and Securities Act Section 4(a)(5). It is a public issuer notice, not an endorsement registry. The SEC says a new notice is due within 15 calendar days after the first sale; if the deadline falls on a Saturday, Sunday, or holiday, it moves to the next business day. Amendments may be required for specified changes or annually while an offering continues. SEC staff guidance says filing is not a condition to Rule 504 or Rule 506 exemption availability, although Rule 507 describes possible consequences. See the SEC's [Form D filing guide](https://www.sec.gov/resources-small-businesses/exempt-offerings/filing-form-d-notice), [Form D FAQ](https://www.sec.gov/about/divisions-offices/division-corporation-finance/frequently-asked-questions-answers-form-d), and [Securities Act interpretations](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/securities-act-rules).

The selected dates stop on 26 September 2026. This dataset cannot show offerings outside its filing window, records that were late or never filed, or who invested. The name rules do not expand initials or aliases and cannot establish identity. Shared Item 3 lists are joint offering-level data and are not attributed to any one co-issuer; their name-to-CIK edges are excluded from the graph and CIK-level repeat counts. The graph is a co-occurrence graph from CIK-attributed names and issuer CIKs in sampled records, not an endorsement graph. The site's section 6 is a hypothetical simulation; its visibility threshold, reputation weight, and cohort assumptions are not documented Cosign product mechanics.

The SEC cache contains parsed JSON rather than the original XML for every sampled filing. Because an earlier parser read the wrong XML path for amendment lineage, the current cache cannot establish the exact number of sampled D/A filings whose declared previous accession is also present in the sample. A previous-accession link does not by itself establish the target filing's form. The corrected parser and safe refresh path are documented above. See the appended audit note in TRANSCRIPT.md for the correction record.
