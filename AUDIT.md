# Audit: is the corpus actually read back?

Most notes systems die the same way. You write to them, they grow, and nothing ever reads
them again. So the only question worth measuring is not "does retrieval work" but **is any
of this ever surfaced back to me at the moment it mattered.**

This is that measurement, run against my own vault over 25 active days. It includes the
results that went against me.

Project names are replaced with placeholders. Nothing else is edited.

## Coverage — written and forgotten, or actually retrieved?

| Metric | Value |
|---|---|
| pages in the vault | 97 |
| **pages ever surfaced by the hook** | **94** |
| never surfaced | 3 |

The 3 are deliberate. `SKIP_BASENAMES` excludes `index`, `MEMORY`, `CLAUDE`, `log` and
`README`, because pure-navigation catalogs match every term and crowd out real pages.
Effective coverage of the eligible corpus is 100%. Nothing was written and forgotten.

## Cost

- **220,603 tokens** across **564 fires**, 25 active days
- **390 tokens per fire** — about 0.2% of a 200K window
- Zero fires surfaced no pages *and* still paid for the attempt

## Benefit, scored blind

Ten logged fires, judged against the prompt that triggered them:

| Result | n |
|---|---|
| Strong hit | 5 |
| Partial | 2 |
| **Miss** | **3** |

Roughly 60-70% of fires deliver something useful. At 390 tokens I take that trade.

## The bug this audit found

The hook emitted **exactly 5 pages on every fire**, whatever the top score was. On a miss it
padded the context with 5 confidently-formatted irrelevant pages. At ~40% noise that is
roughly **88K of the 220K tokens wasted** — and worse than the tokens, a padded miss *looks*
like a hit, so the injected pages carry authority they never earned.

Three of the silenced prompts turned out to have **no matching page in the vault at all**.
The hook had been answering a direct "what did we decide about X" with five confident
irrelevant pages, which is the worst output it can produce.

The fix is a floor: emit 1-5 pages, or none. Pages the user *named* bypass it, because
naming a page is itself the relevance signal. Everything else is lexical spillover and has
to clear both an absolute and a lead-relative bar.

Backtested over the 492 re-scorable fires: **2495 → 1094 emitted pages (−56.2%)**, mean
5.00 → 2.19, **zero entity pages dropped**, 6 fires silenced.

## Where I was wrong

**My first measurement of my own fix did not reproduce.** I reported "2460 → 1081, mean 2.20,
8 fires silenced" from an inline reimplementation of the scoring logic written *before* the
function was patched. It measured my intent, not the deployed code. An independent re-measure
calling the shipped function got −56.2%, mean 2.19, and **6** silenced. The "8" was never real.

That pass also found the replay corpus is compromised: the logger truncates prompts to 100
characters, so **54% of logged fires are stubs**. The mean and the zero-entity-loss result held
across a clean subset, but exact counts from the replay should not be quoted.

**The floor is not free.** Independent sampling of fires with removals found a genuine false
positive: a prompt asking about "express vpns" lost an on-topic page titled `ExpressVPN…`,
because entity matching fails to fold "express vpns" → `ExpressVPN` and it fell through to the
filtered lexical path. My original "removes only noise" framing was too clean. The repair
belongs in the entity gate, not in loosening the floor to accommodate one sampled case.

**The kill criterion was never written.** The code pointed at a file naming the conditions under
which I would retire this system. That file did not exist. The instrument logged faithfully for
six weeks with no pre-registered definition of failure — which is exactly the shape that lets a
system be graded by whoever is already invested in it. That file now exists, with four
pre-registered retirement conditions: coverage below 70%, hit rate below 40% on a blind 20-fire
sample, sustained cost above 1,500 tokens per fire, or more than 2% of fires losing a named page
to the floor. Any one of them and this gets cut back to on-demand search.

## An earlier audit disagreed

An independent pass over 41 fires across 2 days called the whole apparatus **"partially worth
it"**: no confirmed case of the vault preventing a repeat mistake, and one documented case of
the system costing real hours investigating itself. It also found the hook structurally never
reached subagent dispatches — 0 of 84 subagent transcripts carried the triggering event — so in
a heavily multi-agent workflow, real coverage was a fraction of actual work.

That pass still graded out as a keep: 70.7% usefulness overall, 85% across the most recent 20
fires. Both verdicts can be true at different points — a young instrument judged on 2 days of
thin data, then vindicated on 25 days of real use. I am not going to quote only the flattering
one.

## Reproduce this on your own vault

Every fire is logged as JSON. Point the log at a file, use the tool for a couple of weeks, then
grade a blind sample yourself. If semantic search wins on your corpus, keep it — see
[BENCHMARK.md](BENCHMARK.md) for how the comparison was run here.
