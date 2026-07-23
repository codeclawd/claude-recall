# Benchmark & methodology

Every number here was measured on **one real vault** — 83 Markdown files, ~1.3 MB, a
personal knowledge base built from months of Claude Code sessions — and graded by an
independent pass over held-out queries. This is an honest **n=1**. The value isn't "these
numbers are universal"; it's the *method*, and the fact that the boring option kept winning.
Reproduce it on your own vault before trusting any of it.

## 1. Semantic search lost to lexical

Graded on 5 held-out recall queries (does the right page come back?):

| Method | Score | Notes |
|---|---|---|
| qmd BM25 (keyword engine) | 0 / 5 | |
| qmd vector (embeddings) | 1 / 5 | +1.2s per query |
| ripgrep + vector RRF (hybrid fusion) | 2 / 5 | |
| qmd reranked `query` | good | but **~15.9s** per query — unusable in a per-prompt hook |
| tuned in-process lexical | **5 / 5** | ~40ms |

Embeddings were confirmed **current** (re-indexed, not stale), so this isn't an indexing
bug. On a personal vault the semantic engine repeatedly surfaced *plausibly related* pages
over the *actually relevant* one. Lexical, tuned, did not.

## 2. Length normalization was load-bearing

Scoring pages by raw match count made the **single largest file** (80,716 bytes vs 1,224 for
the smallest) rank #1 for **9 of 19 unrelated queries** — big files simply contain more
words, so they match more incidental terms.

Fix: weight each term by IDF (`log(1 + N/df)`) and divide the page score by
`sqrt(page_length / 1024)`. That one change fixed **11 held-out misses at once: 4/15 → 15/15**.

```python
score[page] = sum(log(1 + N/df[t]) for t in matched_terms) / sqrt(len(page)/1024)
```

## 3. The precision/recall wall — solved by word choice, not a threshold

A loose gate (any wh-word + a pronoun) fired on **44.8% of real prompts, ~80–97% of them
false**. Tightening to "require 2 matching tags" killed the false fires but **collapsed
recall 8/8 → 3/8** — now distinctive single-word page names stopped matching.

Neither threshold worked because the real signal is **which word**:

- A distinctive proper noun (`tor`, `nostr`, `orbstack`) *can* name a page on its own.
- A common English word (`memory`, `design`, `launch`, `build`) *cannot* — unless the prompt
  is actually asking about your work (a question form + a first-person pronoun).

Encoding that (`NAME_TOO_COMMON` + an "asking about us" check) held **both** sides: 14/15
accuracy and 7/8 recall, with every known bad fire silent.

Real false fires this caught (correct lexical match, wrong *intent*):
- "improve the design of this button" → a "…Redesign" page (design ≈ redesign)
- "fix the app crash on launch" → a "…Launcher" page (launch ≈ launcher)
- "what memory does this process use" (a RAM question) → a "Memory System" page

## 4. Humans type short; machines paste long

Prompt-length distribution on real traffic:

| Source | Median | p90 |
|---|---|---|
| Human prompts | 92 chars | 787 chars |
| Subagent / tool briefings | 12,378 chars | — |

A **134× separation.** A 1200-char cap skips **96.1%** of machine briefings (which shouldn't
trigger recall — no human reads them) while losing only **6.9%** of human prompts (all long
pastes, where a miss costs nothing). One length rule replaced an endless game of
whack-a-mole enumerating machine-turn patterns, *and* killed the latency tail (fuzzy matching
is O(prompt × titles); a 1 MB pasted prompt was the worst case).

## 5. No subprocesses — the corpus fits in memory

Reading and searching the entire vault in Python: **~39ms** (p95). Shelling out to ripgrep —
once to rank, then once per page for snippets — cost **p95 2.7s, max 5.6s**. At 1.3 MB the
whole vault fits in memory; there's no reason to fork a process per query.

## Reproduce it on your vault

There's no packaged benchmark runner here (the graded query sets were hand-labeled against a
private vault). To measure on yours:

1. Turn on the fire log (it's on by default) and use Claude Code normally for a week.
2. Read `~/.claude/logs/brain-recall.jsonl` — each line records the prompt, which gate
   fired, the pages injected, and the context size.
3. Label each fire: was the injected page actually relevant? That gives you precision.
4. For recall, take prompts where you *expected* a page and it stayed silent.
5. If you want to compare against semantic: index the same vault in your embedding tool of
   choice, run the same labeled prompts, and grade identically. Then decide with data.

If semantic wins on your corpus, use it. The claim of this repo is narrow and testable:
**on a personal Markdown vault, tuned lexical was good enough to make embeddings not worth
their latency — and you should measure before assuming otherwise.**
