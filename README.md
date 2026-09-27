# Who believed in you first?

An interactive drop built from SEC Form D filings, published in answer to
[cosign](https://cosign.co)'s launch on 25 September 2026.

The claim under test is on cosign's own homepage: profiles are "cosigned by the
people who believe in them," built from "attributable context from people who
have worked together." The United States has been publishing its own version of
that record in machine-readable form since 2001, in Form D, and it turns out to
be mostly empty. Across 484 operating-company filings, 1,251 distinct people are
named and 97.52% of them appear on exactly one company. The whole recorded graph
of who stood behind American startups in a quarter is 31 nodes and 38 edges, and
not one investor is in it.

## Run it

```
python3 scripts/fetch_formd.py --start 20260701 --end 20260926 --sample 1500 --seed 20260926
python3 scripts/build_drop.py
python3 -m http.server 8000 --directory site
```

No dependencies, no build step. The site is three files and one JSON.

`scripts/supervise.py` wraps the crawler in slices, and `run_when_allowed.py`
waits for EDGAR to stop rate-limiting before starting. Both exist because of a
specific failure described in [TRANSCRIPT.md](TRANSCRIPT.md).

## What is in here

| Path | |
| --- | --- |
| `scripts/fetch_formd.py` | reads the EDGAR daily dissemination index, draws a seeded sample, fetches and parses `primary_doc.xml` for each filing |
| `scripts/supervise.py` | runs the crawler under a wall clock so a stalled socket cannot wedge it |
| `scripts/run_when_allowed.py` | probes for a 200 before starting, and backs off exponentially on 429 |
| `scripts/build_drop.py` | folds amendments onto their originals, separates funds from operating companies, resolves names, and writes `site/drop.json` |
| `site/index.html` | the page |
| `site/app.js` | directory, charts, and the endorsement model |
| `site/style.css` | the design system |
| `data/formd.jsonl` | one JSON record per filing, as parsed |
| `data/accessions.json` | the complete Q3 population from the daily index |
| `TRANSCRIPT.md` | the conversation that built it, including the parts that went wrong |

## The data

Form D is the notice a US issuer files before selling securities under an
exemption. It names the issuer's officers, directors and promoters, its
industry, the size of the offering, the amount sold, and how many investors had
already bought. It does not ask who those investors were.

The population is every Form D and Form D-A filed between 1 July and 26
September 2026: 15,282 filings across 61 business days, read in full from the
EDGAR daily index. The sample is 1,500 of them, drawn with seed 20260926, which
is the number quoted throughout the page.

| | |
| --- | --- |
| Filings in the sample | 1,500 |
| Distinct issuers after folding amendments | 1,487 |
| Pooled investment funds | 1,003 (67.45%) |
| Operating companies | 484 (32.55%) |
| Distinct people named on operating-company filings | 1,251 |
| Of those, appearing on exactly one company | 97.52% |
| People appearing on two or more | 31, adding 38 edges |
| Filings that name no human being | 335 |
| Operating-company filings reporting an investor count | 404 of 484 |
| Median implied cheque, sold divided by backers | $206,250 |
| Gini of that implied cheque | 0.903 |

## Caveats

Form D covers US private placements under Regulation D only. It misses Reg A,
Reg CF, non-US issuers, anything raised entirely on SAFEs or internal rounds, and
any deal where the notice was late or never filed. Related persons are matched on
normalised name, so a person filing as "J. Smith" in one place and "James Smith"
in another counts as two. All of that makes the corpus noisier than reality
rather than cleaner, which means the sparse graph is a ceiling and not a floor.
