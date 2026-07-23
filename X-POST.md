# X / Twitter post — @codeclawd

Voice-matched to the bio ("I write hooks and verification loops for coding agents… I publish
the runs that fail") and to `CodeClawd X Strategy`. No three-item lists, no em-dashes, no
"not X but Y", no stacked anaphora. Terse, declarative, first-person.

---

## Primary post (Premium — link in-post, no penalty)

> Coding-agent memory defaults to a vector DB and an MCP server.
>
> I benchmarked that against keyword search on my own vault.
>
> Embeddings scored 1/5. Tuned keyword search scored 15/15, and ran 400x faster.
>
> I deleted the embeddings.
>
> github.com/codeclawd/claude-recall

## Optional first reply (adds the "how", keeps the hook clean)

> One Python file, standard library only. It never calls an API. Wired as a UserPromptSubmit hook.

## Thread (optional)

**2/**
> The embeddings were current, but they returned pages that were related and wrong, taking 1 to 16 seconds per query. Semantic search lost on accuracy and on speed.

**3/**
> The fix was two boring ideas. IDF scoring with length normalization, because raw match counts rank the biggest file first. A strict gate then reads word choice, so "design" doesn't pull up your redesign doc.

**4/**
> A missed recall costs nothing, since the agent reads the repo anyway. A false injection pollutes the context window for the rest of the session. I tuned the gate around that asymmetry. It fires only on a page-name hit or an explicit recall phrase, and stays quiet otherwise.

**5/**
> It's one file with no dependencies. Point it at any folder of Markdown and fork it. The tool logs every fire, so you can grade precision on your own vault. If semantic wins on your corpus, keep it.

## Shorter standalone variant

> I measured semantic search against keyword search for coding-agent memory.
>
> On my vault: embeddings 1/5, tuned keyword search 15/15, 400x faster.
>
> So I shipped a recall hook with no embeddings and no MCP. One Python file.
>
> github.com/codeclawd/claude-recall

---

## Link placement — you're on Premium, so it's in-post

The 2026 link-reach penalty applies to non-Premium accounts only. You're Premium, so the
repo link sits directly in the primary post above with no reach cost. The "optional first
reply" is now just a place to add the one-line "how" without lengthening the hook tweet.

## Two moves from your strategy doc worth taking here

1. **A screen recording will outrun this text.** Your scrape found mckaywrigley's whole top
   catalogue is 2–6 min captures with a one-line caption, and video beats a weak network. A
   15-second capture of the `🧠 SECOND BRAIN` injection firing live, posted with the primary
   line as caption, is the higher-ceiling version of this. It doubles as a YouTube short.
2. **At minimum, attach the benchmark table as media.** Screenshot the README table (the
   1/5 vs 15/15 row is the whole hook) and attach it to the primary post. Media lifts dwell,
   and dwell is the signal that matters more than the link.

## Reply-target option (not required)

The strategy doc flags high-visibility posts open for replies (the Artificial Analysis
Coding Agent Index, the Kimi K3 arena post). A short reply there — "I got tired of guessing
and benchmarked memory retrieval on my own vault, keyword beat embeddings 15/5" with the link
below it — reaches an established audience without needing your own to exist yet.
