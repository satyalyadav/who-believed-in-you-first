# Transcript

The conversation that produced the drop, condensed. Tool calls are summarised;
findings, decisions and dead ends are kept because they are the useful part.

---

## 1. The brief

**User:** posts a screenshot of a LinkedIn post from Dhruv Gupta, a16z product
and engineering, hiring engineers. The ask, in full: take a look at
drops.mts.now, build a drop themed around cosign and social networks ideally,
post about it, and DM him the git with a transcript of the agent conversation
used to build it.

**Agent:** the transcript is part of the deliverable, so this document is one of
the outputs rather than a byproduct.

---

## 2. Working out what the subject actually is

Read `drops.mts.now` and the existing archive. The house style is clear:
dark, editorial, data-driven, numbered like a filing, every claim tied to a
receipt. Twenty-four prior drops, all about systems rather than opinions.

Read cosign.co. The load-bearing copy:

> Build and browse profiles that showcase what makes someone exceptional,
> cosigned by the people who believe in them.

> Attributable context from people who have worked together.

Searched for launch coverage. Confirmed: 25 September 2026, Erik Torenberg,
David Booth, Dani Grant, Katie Kirsch. MTS's own post called it "Wikipedia meets
LinkedIn meets AngelList." One partner's framing is the most useful line anyone
wrote about it: "The most valuable data in all of Silicon Valley is who has
conviction in whom."

That is a falsifiable product claim, and there is an unusually direct way to test
it. The US government has been publishing a record of who stood behind a private
company, in machine-readable form, every day since 2001. **Form D.**

---

## 3. Proving the data exists before designing anything

Tested whether EDGAR was reachable and what it would take to pull a quarter.

```
$ curl -s -o /dev/null -w "%{http_code}" \
    -A "ResearchProject research@example.com" \
    "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260924.idx"
200
```

First attempt used a `curl` user agent that was too informal. SEC answered 403
with a page titled "Your Request Originates from an Undeclared Automated Tool."
Their current policy wants a declared UA with contact details. Fixed, 200.

Walked the daily dissemination index for Q3 2026: **15,282 Form D and Form D-A
filings across 61 business days**, about 227 a day. All of it free, no key.

Fetched one filing. The URL that matters is not the human-facing one:

```
.../Archives/edgar/data/2141133/000214113326000001/primary_doc.xml
```

That is structured XML, not the HTML rendering, and it is 8KB instead of 36KB.
A probe of 25 accessions found `primary_doc.xml` present in 25 of 25, so the
crawl needs exactly one request per filing and no index lookup.

The fields that matter, straight out of the schema:

```xml
<relatedPersonsList>
  <relatedPersonInfo>
    <relatedPersonName><firstName>William</firstName><lastName>Brilliant</lastName>
    <relatedPersonRelationshipList><relationship>Executive Officer</relationship>
<offeringSalesAmounts>
  <totalOfferingAmount>Indefinite</totalOfferingAmount>
  <totalAmountSold>0</totalAmountSold>
<investors><totalNumberAlreadyInvested>0</totalNumberAlreadyInvested>
```

That last block is the whole story. `totalNumberAlreadyInvested` is the only
place on the form where the number of people who backed a company appears. There
is no field for who they were. Not one, anywhere on the form.

---

## 4. Two hours lost to a rate limit, and what it taught

The crawl worked at 4 requests a second for about a minute. Then this:

```
throttled (429) on primary_doc.xml; pausing 6s
throttled (429) on primary_doc.xml; pausing 16s
throttled (429) on primary_doc.xml; pausing 32s
```

SEC answers a nonexistent key with `403 AccessDenied` and answers too much
traffic with `429`, with no `Retry-After` header. My first version retried both,
so every weekend in the window cost 16 seconds of exponential backoff before
giving up, and the crawler spent most of its life asleep.

Diagnosed it properly rather than guessing:

```
$ curl -w "%{http_code}" -A "Mozilla/5.0 ... Chrome/140.0" <url>   # 429
$ curl -w "%{http_code}" -A "research@example.com" <url>           # 429
$ curl -w "%{http_code}" --http1.1 <url>                           # 429
```

Not the user agent, not the protocol, not the URL. An IP-level block, and it
survived eight minutes of complete silence. Fixed the 403/429 conflation by
reading the body, wrote a prober that waits for a 200 before starting, and
accepted that the sample would have to be smaller.

Two more things went wrong here and both are now load-bearing in the repo:

**A variable that was not global.** `PACE = args.pace` inside `main()` created a
function-local, so the rate limiter silently ran at its 0.14s default for the
whole session. Discovered by arithmetic: 289 records in 45 seconds is 6.4/s, and
the limiter was supposed to cap at 1.1/s. Fixed with an explicit `global`.

**A socket that would not let go.** `urlopen(timeout=30)` sets the timeout per
socket operation, not for the request. The crawler stalled at 497 records, then
again at 996, both times on a response that trickled bytes forever. Thread
cancellation cannot interrupt a blocking read, so the fix was to stop trying to
be clever: `supervise.py` runs the fetcher under a 150-second wall clock and
starts it again. It is resumable, and once the sample moved to being drawn from
the whole population rather than from whatever was left to fetch, a restart
picks up exactly where it stopped.

Lesson worth keeping: the polite, resumable, wall-clock-bounded design was not
gold-plating. It was the only reason the crawl finished.

---

## 5. Deciding the shape of the sample

Two options. Fetch all 15,282 filings, which at a survivable 1/s is four hours.
Or take a seeded sample and say so.

Sampled, 1,500 filings, seed 20260926, and the seed is printed in the receipts
table and in the README so anyone can reproduce the exact corpus. The
population count comes from the daily index, which was read in full, so the
denominator is exact even though the numerator is a sample.

First instinct was to frame the page around the whole quarter. The first pass
through the data killed that:

```
distinct persons: 3,083 appearances, 3,538
  appear exactly once: 2,834  (91.9%)
top repeat names:
  'N/A Fund GP, LLC'                 75  as Director
  'N/A Belltower Fund Group, Ltd.'   75  as Director
  'LLC Sydecar'                      35  as Director
  'Brett Sagan'                      33  as Executive Officer
  'Cameron Vail'                     29  as Executive Officer
```

Two thirds of the corpus is pooled investment funds, and the only names that
recur at any scale are administrative agents signing as director on behalf of
seventy-five separate vehicles. The framing that survived: **two thirds of Form D
is not startups**, and a startup directory built on this feed has to throw that
away first. Every statistic on the page is now reported twice, once for the whole
corpus and once for operating companies only, because the two stories are
different and only one of them is about startups.

---

## 6. The bug that moved the headline number

Telling a legal entity from a person decides every number in Item 4, and the test
that does it had no word boundaries:

```python
ENTITY_TAIL.search(n)     # pattern: llc|inc|corp|co|...|as|ab|ag|...
```

Which meant "Salene Hitchcock-Gear" matched on `co` inside "hitchcock", and
"Reshma Abraham" matched on `ab`. Real officers of Prudential's variable life
company were being filed as shell companies, 194 filings that name nobody human
were really naming people, and the repeater count was 31 when it should have
been 36.

Nobody would have caught this by reading the code, because the regex looks like
what it says. What caught it was writing a second implementation from scratch and
asking the two to agree. They did not, on three names, all of them starting with
"LLC". The rule is now written out as five numbered tests in prose at the top of
`build_drop.py`, stated independently in `verify.py`, and asserted by
`scripts/verify.py` on 27 figures. An all-caps test that the original rule used
never fired once on this corpus and has been deleted rather than left to misfire
on the next one.

The corrected figures, and they are the ones the page now publishes:

```
people on operating-company filings   1,504 distinct, 1,548 appearances
  appear exactly once                   1,468  (97.61%)
  appear on two or more                    36, adding 44 edges
filings naming no human being            196 of 1,500
```

## 7. Two claims that were simply wrong

**The filing deadline.** The page said Form D is filed "before the first sale."
The form itself says no later than 15 days *after* it. That is not a pedantic
correction, it is the whole of Item 5: by the time the form is filed the money
is already committed, and it still records only how many people were in, never
who they were.

**Rule 506.** The page said 506 "lets a company sell shares to accredited
investors." That is 506(c). Under 506(b) there is no accredited-investor
requirement at all, no general solicitation is allowed, and up to 35 purchasers
may be non-accredited provided each is financially sophisticated. Both readings
now appear, with investor.gov linked.

**The backer distribution.** The page described "a lot of rounds with one or two
backers, a long thin tail of funds buying a hundred small cheques." The data
says a quarter of operating companies report one backer, a third report eleven or
more, and the largest single band is three to five. It is not a tail of tiny
cheques. Rewritten to the shape that is actually there.

## 8. Three things I got wrong, all of them visible on the page

**"true" in the form.** The related-persons block rendered the literal string
`true` in the label column of every row, because a placeholder helper was called
with a boolean. Only caught it by looking at a screenshot. Fixed, and the block
now mirrors the real form: a name row and a relationship row per person.

**A metric that saturated.** The simulation's headline number was "the share of
accumulated reputation held by whoever was visible on day one." At the default
settings it read a clean 75% against a 24% control, which looked great. Sweeping
the sliders showed that at a 2% day-one cohort it reads 100.0%, and at a 60%
cohort it also reads 100.0%, and neither is possible unless the metric is
degenerate. It was: when the day-one cohort is the only group that can endorse,
it necessarily collects almost everything, so the ratio pins at 1.

Replaced it with a capture ratio, reputation share divided by the cohort's share
of the network, where 1.0 is parity. It is defined everywhere in the parameter
space and it means the same thing at 2% and at 60%: **2.87x** at the defaults
against **1.00x** for the all-discovery control.

**Copy I had not checked.** I had written that the visibility threshold "barely
matters." The sweep says it moves the capture ratio from 2.22x at one required
endorsement to 3.82x at twelve. So it matters a great deal, and I was about to
publish the opposite. Rather than write a safer sentence, the page now runs the
model at both ends of that slider on every change and prints the two numbers it
measures. Any claim about the model on the page is now a number the page just
computed.

The sensitivity sweep that did it:

| setting | capture | control | visible |
| --- | --- | --- | --- |
| defaults | 2.87x | 1.00x | 1,757 |
| threshold 1 | 2.22x | 1.01x | 1,976 |
| threshold 12 | 3.82x | 2.40x | 537 |
| reputation weight 0 | 3.72x | 1.15x | 769 |
| reputation weight 0.98 | 2.84x | 1.03x | 1,770 |
| day-one cohort 2% | 14.56x | 0.99x | 1,764 |
| day-one cohort 60% | 1.48x | 1.01x | 1,837 |
| all discovery | 0.99x | 1.00x | 2,000 |

---

## 9. A second audit, because the first one only checked itself

The first verification pass recomputed the numbers from the crawl with a second
implementation, which catches implementation bugs but not shared assumptions.
This round checked the assumptions themselves, and three of them were wrong.

**Ground truth.** Twelve filings were re-fetched from EDGAR and compared field by
field against what the page stores: entity name, industry group, amount sold, the
investor count, and the full list of related persons. Twelve of twelve agreed.
The pipeline had never been tested against its source before, only against
itself.

**Two factual claims were flatly contradicted by the data sitting underneath
them.** The page said Form D "misses Rule 504 offerings", and there are eight
Rule 504 filings in the sample. It said Form D "misses every non-US issuer", and
there are 219, led by 131 Cayman companies and 28 from Luxembourg, because a
foreign vehicle selling into the United States files a Form D like anyone else.
Both sentences were in a paragraph whose whole job was to be precise about
coverage.

**The graph was described in the wrong units.** The page said "the entire
recorded social graph is 36 nodes and 44 edges." Those are the repeaters. The
graph is 1,988 nodes and 1,548 edges, of which 1,504 are the single connection
each person has and 44 are the only edges that connect anything. The finding is
unchanged and now stated correctly.

**The amendment arithmetic did not mean what it said.** The receipts read "1,487,
after folding 546 amendments onto the filing they amend." There are 546
amendments, but zero of them amend another filing inside the sample, so nothing
was folded. The 1,500 filings collapse to 1,487 because 13 issuers happened to
file twice inside the window. The number was right and the explanation was wrong,
which is the worse of the two failures.

**One model claim was false.** The page told the reader to "change who starts
with reach, which nobody argues about at all, and watch that it decides
everything." Measured across the full range of that slider, capture moves from
2.93x to 3.01x. It is the least influential knob on the panel, by an order of
magnitude. Measured ranking of everything on the panel:

| dial | capture range | effect |
| --- | --- | --- |
| day-one cohort, 2% to 60% | 14.11x to 1.48x | −90% |
| discovery share, 0.02 to 1.00 | 3.82x to 0.99x | −74% |
| visibility threshold, 1 to 12 | 2.26x to 3.82x | +69% |
| endorsements per round | 3.82x to 1.99x | −48% |
| reputation weight, 0 to 0.98 | 3.72x to 2.84x | −24% |
| noise, 0 to 1 | 3.41x to 2.63x | −23% |
| network size, 500 to 6000 | 3.34x to 3.03x | −9% |
| early endorsers amplified | 2.93x to 3.01x | +3% |

The paragraph now reports the extremes it measures at both ends of three of those
sliders, on every redraw, so it cannot drift from the model again.

## 10. Making the slider live

The complaint was that the graph sat still while the slider moved and only
updated on release. It did not, quite: it was updating about seven times a
second. But each update needed four full simulations, so the curve lagged the
thumb badly enough to read as static.

Three changes. The curve now streams back from the worker in batches as it is
computed, so it draws itself instead of appearing whole, and the head of the line
is marked so a run in flight is visibly in flight. The three comparison runs are
skipped while a drag is in progress and only requested once the pointer is
released, which takes a redraw from about 250ms of work to about 30ms. And small
runs were rejected as a preview tier: at 250 agents the curve is four times
faster and visibly different from the real one, which would be dishonest to draw.

The measurement is honest this time. My first attempt at it reported that the
slider never updated at all, because I was driving the mouse at y=9024 in a
1000-pixel viewport. It was dragging nothing. Worth writing down: a test that
reports zero has to be checked before its result is believed.

Result: 51 canvas redraws across a two-second drag, 27 per second, worst frame
gap 18ms, first repaint 20ms after the knob moves, and the comparison numbers
landing about a fifth of a second after release. That is a live instrument rather
than a screenshot of one.

## 11. Design, in one pass

The subject is a regulatory form, so the page is a regulatory form. Cold paper
rather than cream, one mono family for everything structural and a high-contrast
serif for the voice narrating it. The only ornament is the X you put in a box
when something is true, which is the actual interaction on Form D and became the
page's progress indicator, its checkbox and its accent colour.

The hero is a real filing, not a title card. CorePower Magnetics, Pittsburgh,
fourteen and a third million dollars sold, seven investors named as a count.
Pick a filing you have actually read and the headline stops being a headline and
starts being a caption.

Rejected on the way: a force-directed graph of the whole name graph, which is a
hairball when 97.5% of nodes have degree one. A force layout earns its keep when
there is structure; here the absence of structure is the finding, and a
histogram of degrees says it in one bar.

---

## 12. Verification

Layout was checked in a real browser rather than by eye. The preview tool's
screenshot path was broken in this environment, so a local Chromium was
installed and driven with Playwright: one screenshot per section at 1440px, one
at 390px, plus a scripted overflow audit and a click-through of the search,
filters, sorting, person links, filing detail and every slider.

Three layout bugs came out of that and none would have been obvious without it:
SVG charts scaling their own text to 2.7x because the viewBox was a fixed 420px
in a 1116px column, a grid blowout on mobile because `.chart` was missing
`min-width: 0`, and a horizontal scroll on the whole page traced to a `nav` with
`min-width: auto` inside a grid.

Speed came next, and the measurement was not where I expected. The endorsement
model was not slow because the inner loop was slow; 100 rounds of it cost 1ms.
It was slow because the run happened four times per redraw, and each run took a
snapshot 200 times, and each snapshot spread a `Float64Array` into a JavaScript
array, filtered it and sorted it. That is 800 sorts per keystroke. Sorting the
typed array directly is about five times faster, the three extra runs only need
one number each so they skip snapshotting entirely, the visible set only ever
grows so it is appended to rather than rescanned every round, and the whole thing
moved into a Web Worker so a redraw never blocks the page. A slider drag went
from a 1.1s blocking handler to a 0ms one, with the curve arriving about 300ms
later and the frame gap never exceeding 20ms. `scripts/check-model.mjs` checks
the fast implementation against a deliberately naive one across eight
configurations, because an optimisation that changes the answer is worse than a
slow page.

The directory payload lost 290KB by dropping nine fields the page never reads,
and the 400 table rows now use `content-visibility`. Page load went from 687ms to
308ms to DOMContentLoaded.

Final numbers, all computed in `build_drop.py`, independently recomputed by
`scripts/verify.py` across 37 checks, and printed in the receipts table so the
page cannot disagree with the crawl:

```
sample: 1,500 of 15,282 filings in the quarter, seed 20260926
issuers: 1,487 distinct CIKs, 13 of which filed twice
amendments: 546, none amending another filing in the sample
funds: 1,003 (67.45%)      operating companies: 484 (32.55%)
non-US issuers present: 219 (131 Cayman, 28 Luxembourg)
names on operating companies: 1,504 distinct, 1,548 appearances
  97.61% appear once, 36 repeaters contributing the only 44 connecting edges
graph: 1,988 nodes, 1,548 edges
filings naming no human being: 196 of 1,500
backer counts: 404 of 484 report at least one, none blank
  median 7 backers, median implied cheque $206,250, Gini 0.903
Rule 504 filings present: 8 (so Rule 504 is not an exclusion)
```

---

## 13. What I would do next

The 484 operating-company filings are one quarter of one exemption. The same
code against Reg A and Reg CF, and against the 13D/G and Form ADV records where
fund managers and their LPs are named, would connect the two thirds of the corpus
that this drop throws away. The interesting graph is not people to companies, it
is people to funds to companies, and the fund half of it is sitting in a
different set of filings that nobody has joined up.

The other thing worth saying out loud: this page measures a filing corpus, and a
filing corpus is a record of what somebody was required to write down. Form D
names officers and directors because the SEC needed to know who was responsible
for the disclosure. It does not name investors because nobody required it. The
absence is not evidence that nobody vouched for anybody. It is evidence that
nobody thought to ask them to say so on a form, which is precisely the gap cosign
is selling into, and precisely why the product is worth building.
