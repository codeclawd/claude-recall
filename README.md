# claude-recall

**A memory-recall hook for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that injects your past decisions into the prompt — using tuned lexical search that beat embeddings on my vault. No MCP. No vector DB. No API calls. One file, standard library only.**

Claude Code forgets everything between sessions. The usual fix is a vector database and an
MCP server doing semantic search over your notes. I built that, measured it, and it lost to
plain keyword search. So this is the opposite: a single Python file, wired as a
`UserPromptSubmit` hook, that reads your Markdown vault in ~40ms and injects the pages
relevant to *this* prompt — before Claude re-derives what you already worked out together.

```
you:    "what did we decide about the payments provider?"
        ▲
        │  brain-recall.py fires on the prompt, ranks your vault, injects:
        ▼
🧠 SECOND BRAIN — pages matching THIS prompt:
• wiki/Payments Service.md — Payments Service
    L4: We chose Stripe over Braintree for the lower international fees.
```

---

## The result that made me delete the embeddings

Measured on my own vault (83 Markdown files, 1.3 MB), graded by held-out queries:

| Retrieval method | Score | Latency |
|---|---|---|
| qmd BM25 (keyword) | 0 / 5 | fast |
| qmd vector (semantic) | 1 / 5 | +1.2s |
| ripgrep + vector RRF (hybrid) | 2 / 5 | slow |
| qmd reranked query | good | **~16s** |
| **tuned in-process lexical (this repo)** | **15 / 15** | **~40ms** |

Embeddings were confirmed current — it wasn't a staleness bug. On a personal knowledge
vault, semantic similarity kept surfacing *plausibly related* pages instead of the *actually
relevant* one, and paid a latency tax to do it. Two cheap, boring ideas beat it:

1. **Length-normalized IDF scoring.** Raw match-count ranking let the single biggest file
   win 9 of 19 *unrelated* queries — big files just contain more words. Adding IDF and
   dividing by `sqrt(length)` fixed 11 held-out misses at once (4/15 → 15/15).
2. **A strict, word-choice-aware gate.** A loose gate fired on ~45% of prompts, ~80–97%
   of them wrong. The fix wasn't a threshold — it was *word choice*: a distinctive proper
   noun (`tor`, `nostr`, `orbstack`) can name a page alone; a common word (`memory`,
   `design`, `launch`) can't unless the prompt is actually asking about your work.

> **Why strict?** A missed recall costs nothing — Claude just reads the repo like normal.
> A *false* injection permanently pollutes the context window. So this optimizes precision
> over recall, hard. It stays quiet unless it's confident.

Full methodology and numbers: **[BENCHMARK.md](BENCHMARK.md)**.

## Install

```bash
git clone https://github.com/codeclawd/claude-recall && cd claude-recall
./install.sh                      # asks for your vault path, wires the hook
# restart Claude Code
```

Or manually (it's one file):

```bash
cp brain-recall.py ~/.claude/hooks/
# then add to ~/.claude/settings.json:
#   "hooks": { "UserPromptSubmit": [ { "hooks": [
#     { "type": "command",
#       "command": "CLAUDE_RECALL_VAULT=\"$HOME/Documents/SecondBrain\" python3 ~/.claude/hooks/brain-recall.py" }
#   ] } ] }
```

Requirements: **Python 3, standard library only.** No pip install, no MCP server, no
embeddings, no network. Your "vault" is any folder of Markdown files — an
[Obsidian](https://obsidian.md) vault, a `docs/` directory, plain notes.

## How it works

On every prompt, the hook:

1. **Gates hard.** Skips machine/subagent turns, pasted secrets, local file paths, and
   prompts over 1200 chars (human prompts run ~92 chars median; a 12k-char subagent
   briefing is not someone asking a question). Fires only on a page-name match or an
   explicit recall intent (`what did we decide…`, `remind me…`, `last time…`).
2. **Ranks in-process.** Reads the whole vault once (a 1.3 MB vault is ~40ms in Python),
   scores pages by length-normalized IDF over the salient terms plus tag/title/alias hits.
3. **Injects the top few.** Emits the matching pages (with line-anchored snippets) as
   `additionalContext`, capped to a tight character budget so it never floods the window.
   Each page carries a **freshness stamp** — see below.

Every fire is logged to `~/.claude/logs/brain-recall.jsonl` so you can audit precision on
your own data and tune the gate.

## Freshness stamps — why recall needs provenance

Retrieval is only as good as the reader's willingness to distrust it. An undated snippet
reads as fact.

This bit us. A recalled line said a daemon was *"already running via brew services"* — true
when written, false for months by the time it surfaced, because the service had moved into
Docker. Nothing in the injected text marked it as old, so it was believed.

So every injected page now gets a compact stamp:

```
• wiki/Fresh Page.md  [verified 2026-08-16] — Fresh Page
• wiki/Stale Page.md  [updated 2026-01-05 · 224d old — STALE? · paused · ⚠has-warning] — Stale Page
• wiki/Undated Page.md  [undated] — Undated Page
```

It reads these optional YAML frontmatter fields. **All of them are optional** — a vault of
plain Markdown still works, you just get `undated`, which is itself the useful signal:

| Field | Role |
|---|---|
| `verified:` | when the claim was last checked **against reality** — preferred over the rest |
| `updated:` | when the page was last touched — fallback |
| `created:` | when the page was written — last resort |
| `status:` | surfaced whenever it is anything other than `active` |

Anything older than 30 days also gets an explicit `Nd old — STALE?`, and a page containing
an Obsidian `> [!warning]` callout is flagged `⚠has-warning` — a page that already
contradicts itself should be read, not skimmed.

The distinction between `updated` and `verified` is the whole point: `updated` only says
when someone touched the file. It cannot tell you whether the claim inside is still true.

## Configure

Everything is env-driven — no config file:

| Variable | Default | Meaning |
|---|---|---|
| `CLAUDE_RECALL_VAULT` | `~/Documents/SecondBrain` | Folder of Markdown notes to search |
| `CLAUDE_RECALL_LOG` | `~/.claude/logs/brain-recall.jsonl` | Fire log (audit precision here) |

The retrieval knobs live as constants at the top of `brain-recall.py` (`MAX_PAGES`,
`MAX_CHARS`, `MAX_PROMPT_CHARS`, `MIN_TAG_HITS`, the `INTENT` regex, `NAME_TOO_COMMON`).
They're heavily tuned — change conservatively and watch the fire log.

## Fork it

This is deliberately **one dependency-free file** so it's trivial to adapt:

- **Different note format?** It only assumes Markdown with optional YAML frontmatter
  (`tags:`, `aliases:`). Point `CLAUDE_RECALL_VAULT` at any Markdown tree.
- **Different agent?** The hook reads `{"prompt": "..."}` on stdin and prints a Claude Code
  `hookSpecificOutput` JSON. Swap the I/O shape and the core ranker works anywhere.
- **Want semantic anyway?** Add it as a fallback tier — but measure on *your* corpus first
  (see BENCHMARK.md for the harness idea). The point of this repo isn't "never use
  embeddings," it's "measure before you reach for them."

PRs welcome — especially additional graded query sets from other people's vaults.

## FAQ

**Does this need an MCP server?** No. It's a hook, not an MCP. It runs a Python file on each
prompt and returns text.

**Does it use embeddings / a vector database?** No. That's the whole point — tuned lexical
search outscored semantic on this corpus at ~400× lower latency.

**Is this RAG?** It's retrieval-augmented, yes — but the retrieval is keyword/IDF, not
vector similarity, and it's injected deterministically by a hook rather than decided by the
model.

**How is it different from Claude Code's built-in memory / `CLAUDE.md`?** `CLAUDE.md` is
always-on and small; it can't hold months of project knowledge without bloating every
prompt. This injects only the pages relevant to the current prompt, so the vault can be huge
while the context cost stays tiny.

**Will it work with plain notes, not Obsidian?** Yes. Obsidian is just Markdown files;
so is a `docs/` folder.

**n=1?** The 15/15 is my vault. Your mileage will vary — that's why every fire is logged, so
you can check precision on your own data. If semantic wins on your corpus, keep it.

## License

MIT — see [LICENSE](LICENSE).

---

<sub>Topics: `claude-code` · `claude` · `anthropic` · `ai-memory` · `second-brain` · `rag` · `retrieval` · `obsidian` · `llm` · `developer-tools` · `hooks` · `context-engineering`</sub>
