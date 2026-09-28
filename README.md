# Who believed in you first?

An interactive drop built from SEC Form D filings, published in answer to
[cosign](https://cosign.co)'s launch on 25 September 2026.

The claim under test is on cosign's own homepage: profiles are "cosigned by the
people who believe in them," built from "attributable context from people who
have worked together." The United States has been publishing its own version of
that record, in Form D, and it turns out to be mostly empty. Across 484
operating-company filings, 1,504 distinct people are named and 97.61% of them
appear on exactly one company. The graph has 1,988 nodes and 1,548 edges, and
1,504 of those edges are the single connection each person has. The other 44,
contributed by 36 people, are the only places in the whole graph where anything
connects, and not one investor is among them.

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
| `scripts/verify.py` | recomputes every figure on the page from the raw crawl with a second implementation that shares no code, and fails loudly on disagreement |
| `scripts/check-model.mjs` | checks the endorsement model against a naive reference implementation across the parameter space |
| `site/index.html` | the page |
| `site/app.js` | directory, charts, and the endorsement model. The model runs in two workers: one streams the curve, one recomputes the comparison so the dashed line moves with the slider |
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
| Distinct people named on operating-company filings | 1,504 |
| Of those, appearing on exactly one company | 97.61% |
| People appearing on two or more | 36, contributing the only 44 edges that connect anything |
| Graph, operating companies only | 1,988 nodes, 1,548 edges |
| Amendments | 546, none of which amends another filing in the sample |
| Issuers that filed twice | 13 |
| Non-US issuers present | 219 |
| Filings that name no human being | 196 of 1,500 |
| Operating-company filings reporting at least one backer | 404 of 484, none blank |
| Median implied cheque, sold divided by backers | $206,250 |
| Gini of that implied cheque | 0.903 |

## Caveats

Form D covers US private placements under Rule 504 and Rule 506 of Regulation D.
It misses Regulation A, Regulation CF, non-US issuers, anything raised entirely
on SAFEs or internal rounds, and any offering where the notice was late or never
filed, which the SEC does enforce. Related persons are matched on normalised
name with generational suffixes stripped, so "J. Smith" in one place and
"James Smith" in another are one person, and so are a father and a son who share
a name, which makes the repeater count larger rather than smaller. Telling a
person from a legal entity is a judgement call, so the rule is written out in
both scripts rather than left to a regex, and the two are required to agree. All
of that makes the corpus noisier than reality rather than cleaner, which means
the sparse graph is a ceiling and not a floor.
