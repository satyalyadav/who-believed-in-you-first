# Post and DM drafts

Nothing here has been sent. Both need your go-ahead, and the DM is a write
action on someone else's account, so I will not touch it until you say so.

## Links

- Live: https://satyalyadav.github.io/who-believed-in-you-first/
- Git: https://github.com/satyalyadav/who-believed-in-you-first
- Transcript in the repo: `TRANSCRIPT.md`
- Also live: https://satyalyadav.github.io/who-believed-in-you-first/TRANSCRIPT.md

## Post, for LinkedIn

> Built a drop on cosign, read against the only public record of who backs whom
> that already exists.
>
> cosign says profiles get "cosigned by the people who believe in them," built
> from "attributable context from people who have worked together." I wanted to
> see how much of that record is actually on disk.
>
> The US government has been publishing its own version every day since 2001.
> Form D: before a company sells shares under an exemption, it files a notice
> naming its officers, directors and promoters, its industry, the size of the
> raise, and how many people had already bought. Free, no key, machine readable,
> every filing since 2001.
>
> I pulled 1,500 of the 15,282 Form D filings made in Q3 2026 and read them.
>
> Two thirds of them are pooled investment funds rather than startups. Of the
> 484 that are operating companies, they name 1,251 distinct people and 97.52%
> of those appear on exactly one company. 31 people appear on two or more. So the
> whole vouching graph is 31 nodes and 38 edges, with no investors in it at all,
> because investors are not who Form D names.
>
> The names that do recur across the quarter are filing agents. One
> administrative services company signs as director on behalf of 75 separate
> vehicles. Another shows up 75 times. Another 35.
>
> The one field that counts backers asks for a number and no names. 404 of those
> 484 filings fill it in. Median seven backers, median cheque $206,250, Gini
> 0.903. You can measure the shape of a cap table from public filings without
> learning a single investor's name. That is a strange thing to be true, and it
> is a very real gap.
>
> So I modelled the mechanism cosign describes: attributed, durable endorsements,
> a visibility threshold, reputation weighting, early endorsers rewarded with
> reach. Seed it with 25% of the network already credible and that cohort ends up
> holding 2.87x its share of all reputation, and 40% of the top 1% after twenty
> rounds are still in the top 1% a thousand rounds later. Turn every endorsement
> into discovery instead of social proof and the same cohort lands at 1.00x, which
> is parity. A head start is worth nothing when nothing compounds.
>
> The drop has a searchable directory of the filings, five of them rendered as
> the actual form, and the model with the sliders. Have at it:
> https://satyalyadav.github.io/who-believed-in-you-first/
>
> Git and the full transcript of the agent conversation that built it are in the
> repo. The transcript is the part I would read first, because it includes the
> two hours I lost to an SEC rate limit, a rate limiter that was silently doing
> nothing, a metric that fell apart at both ends of its range, and one sentence
> I had written asserting the exact opposite of what the model does.
> https://github.com/satyalyadav/who-believed-in-you-first

## Shorter version, for X

> Cosign's pitch is a public record of who believed in whom. There is already a
> US version of that, filed daily, machine readable, free since 2001: Form D.
>
> I pulled 1,500 of the 15,282 made in Q3 2026. Two thirds are funds, not
> startups. Of the 484 that are companies, they name 1,251 people and 97.52% of
> them appear on exactly one company. The whole vouching graph is 31 nodes, 38
> edges, no investors.
>
> The names that recur are filing agents. The one field that counts backers asks
> for a number and no names.
>
> https://satyalyadav.github.io/who-believed-in-you-first/

## DM to Dhruv

> Hey Dhruv, built the drop. Git and the transcript of the agent conversation
> that built it are below.
>
> Live: https://satyalyadav.github.io/who-believed-in-you-first/
> Git: https://github.com/satyalyadav/who-believed-in-you-first
>
> The transcript is the part I would point you at. It is the whole arc including
> the parts that went wrong: two hours lost to an SEC rate limit, a rate limiter
> that was silently a no-op because I forgot a `global` in one function, a
> headline metric that collapsed at both ends of its range, and a sentence I had
> already written asserting the opposite of what the model does. All three of the
> last ones got caught by sweeping the parameters instead of trusting the default
> view.
>
> The substance, briefly. cosign is a public record of who believed in whom.
> There is already a US record of who stood behind a private company, filed
> daily, machine readable, free, since 2001. It is Form D, and it is much thinner
> than the pitch, mostly for two reasons: two thirds of it is asset managers
> rather than startups, and Form D names officers and directors but never names
> investors. Not one field, on any filing.
>
> Which is either the strongest argument I can think of for what you are
> building, or a sign the record is thinner than it looks from the outside, and I
> could not tell you which from where I was sitting. Happy to walk through the
> crawl, or argue about the model, which is the part I would most like to be
> wrong about.
>
> Satya

## Notes on the drafts

- The post leads with the finding, not with the build. "I pulled 1,500 filings
  and the record is thinner than the pitch" is the hook; the tooling is the
  second paragraph.
- The transcript is pitched as the interesting artifact, because he asked for it
  by name and because the failures are the credible part.
- The DM ends by asking for a fight rather than a compliment, and offers a
  specific next step. He said he would at minimum respond.
- Every number in both drafts is read off the receipts table in `build_drop.py`,
  so they cannot drift from the crawl. Re-check them if the crawl is re-run with
  a different seed.
