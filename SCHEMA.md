# Vault schema

`brain-recall.py` will read any folder of Markdown. This is the layout it was tuned against,
and the two conventions that do real work: **aliases** and **bi-temporal keys**.

You do not have to adopt any of it. Skip to [Aliases](#aliases) and
[Bi-temporal keys](#bi-temporal-keys-the-part-that-actually-matters) if you only want the parts
that change retrieval quality.

## Layout

```
vault/
  wiki/         evergreen knowledge — one page per concept, project or entity.
                This is what recall reads and what accumulates.
  projects/     active work. Frontmatter `status:` required.
  daily-notes/  one note per day. The session-log hook writes here.
  index/        immutable source material. NEVER auto-injected (see below).
```

Only `wiki/`, `projects/`, `daily-notes/` and the vault root are scanned. **`index/` is
deliberately out of scope.** Raw sources are often third-party text, and third-party text in a
prompt is data, never instructions. Auto-injecting it would replay whatever it contains into
future context as trusted memory.

`index`, `MEMORY`, `CLAUDE`, `log` and `README` are skipped by basename anywhere they appear.
Navigation catalogs match every term and crowd out real pages.

## Page conventions

Filenames are Title Case, one concept per page. Wikilinks resolve by basename, so pages move
between folders without breaking links.

Frontmatter:

```yaml
---
type: project | concept | entity | source | comparison | synthesis | reference
tags: [retrieval, ranking]
aliases: [BM25, keyword search]
created: 2026-01-14
updated: 2026-03-02
---
```

## Aliases

`aliases` is the synonym layer recall uses to find a page by the vocabulary you actually type,
rather than by its title. A page called `Search Ranking` that you always refer to as "BM25"
will not match until `BM25` is an alias.

This is the cheapest quality win in the whole system. Add an alias every time you catch
yourself searching for a page and not finding it.

## Contradictions

Never silently overwrite a claim that conflicts with what a page already says. Flag it inline:

```markdown
> [!warning] Contradiction — the 2024 benchmark says the opposite; current best view is X because Y.
```

Overwriting destroys the one signal that tells you which of your notes drifted.

## Bi-temporal keys (the part that actually matters)

`updated` tells you when the *page* was touched. It cannot tell you whether the *claim* is still
true. For anything that can go stale, use:

```yaml
valid_from: 2026-01-14        # when the fact became true in the world
verified: 2026-03-02          # when it was last checked
verified_against: "src/rank.py:341 — FLOOR_ABS read live"
```

`verified_against` should cite a running system, not another document. A doc citing a doc is how
a wrong claim survives.

When a claim is replaced, keep the old one under a `### Superseded` heading with a warning
callout, stating the window it was true and what replaced it. **Never delete a superseded
claim.** Its provenance is how you find out which layers drifted.

**Why this exists.** A configuration fact here was true in June, changed in July, and nothing
marked the original claim stale. It survived in three separate places for two weeks while the
live config said something else the entire time. Three layers wrong, and the only correct record
was a file queued for deletion. A `valid_from` + `verified_against` pair makes that drift
visible instead of invisible.
