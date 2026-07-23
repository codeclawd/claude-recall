# X / Twitter post

## Primary post (the hook — keep the link OUT of tweet 1 for reach; put it in the first reply)

> Everyone building memory for Claude Code reaches for a vector DB + an MCP server.
>
> I built that. Then I actually measured it.
>
> On my vault, semantic search scored 1/5. Tuned keyword search got 15/15 — at ~400× lower latency.
>
> So I deleted the embeddings. 🧵

**First reply (the link):**
> Single Python file, stdlib only, wired as a Claude Code hook. No MCP, no vector DB, no API calls.
> github.com/YOURNAME/claude-recall

## Thread (optional, for depth)

**2/**
> The setup is a `UserPromptSubmit` hook. On every prompt it reads your Markdown vault (~40ms), ranks the pages, and injects the relevant ones — before Claude re-derives what you already decided together.

**3/**
> Why did semantic lose? On a *personal* vault, embeddings kept surfacing "plausibly related" pages instead of the actually-relevant one — and paid a 1.2s–16s latency tax to do it. The embeddings were current. It just wasn't better.

**4/**
> Two boring ideas beat it:
> • IDF + length normalization (raw match-count let the biggest file win 9/19 unrelated queries)
> • a strict gate keyed on *word choice*: a rare proper noun can name a page; "design"/"memory"/"launch" can't.

**5/**
> The design rule that matters: a missed recall costs nothing (Claude just reads the repo). A *false* injection pollutes the context window permanently. So it optimizes precision over recall, hard. It stays silent unless it's sure.

**6/**
> It's one dependency-free file — fork it, point it at any folder of Markdown, adapt the I/O for any agent. Every fire is logged so you can audit precision on your own data.
>
> Full numbers + methodology in the repo. If semantic wins on *your* corpus, keep it — just measure first.

## Shorter variant (single standalone tweet)

> I measured semantic search vs plain keyword search for Claude Code memory.
>
> On my vault: embeddings 1/5, tuned lexical 15/15, ~400× faster.
>
> So I shipped a memory-recall hook with zero embeddings, zero MCP, one Python file.
>
> github.com/YOURNAME/claude-recall

## Notes for posting
- Replace `YOURNAME` with your GitHub handle.
- X down-ranks posts with external links in the main tweet — lead with the claim, drop the
  repo link in the first reply (as above).
- Best hook line is the contrarian number; keep tweet 1 under ~250 chars so it renders clean.
- Suggested hashtags (use 1–2 max, in a reply, not the hook): #ClaudeCode #buildinpublic
- A screenshot of the benchmark table (README §"The result that made me delete the
  embeddings") as media on tweet 1 lifts engagement — attach it if you can.
