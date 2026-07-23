#!/usr/bin/env python3
"""UserPromptSubmit hook: deterministic second-brain retrieval.

WHY THIS EXISTS
---------------
Write-back to the vault was automated (a Stop hook writes it every session), but
read-first was left to Claude's discretion AND pointed at `qmd` — an MCP server a
hook cannot call. So "query the brain first" was never mechanically reachable: the
vault could only grow, never be read. This hook does the retrieval ITSELF and
injects matching pages inline, making read-first deterministic.

Scope note: this only helps RECALL (a question was asked). The larger failure —
"the model doesn't know what it should already know" — is not a retrieval problem
and is handled instead by `~/.claude/rules/lessons-digest.md`, which is simply
LOADED every session (no gate, no query, immune to typos/phrasing).

MEASURED, NOT ASSUMED (every number below came from an independent grader)
-------------------------------------------------------------------------
* Semantic engines lost to plain lexical on this vault: qmd BM25 0/5, qmd vector
  1/5 (+1.2s), rg+vector RRF 2/5 — no gain. `qmd query` (rerank) is good but 15.9s.
  Embeddings were confirmed CURRENT, so it isn't staleness. No qmd in the hot path.
* Ranking MUST length-normalise. Scoring by raw match count made the vault's
  LARGEST page (80,716 bytes vs 1,224 for the smallest) rank top for 9 of 19
  UNRELATED queries — the "ghost" pages were simply the biggest files. IDF +
  /sqrt(len) fixed 11 held-out misses at once (4/15 -> 15/15).
* The gate must be strict. A loose gate (any wh-word + a pronoun) fired on 44.8%
  of real prompts at ~80-97% false — on the bare word "continue", on bug reports.
  Precision over recall: a miss costs nothing (Claude just reads the repo); a
  false fire permanently pollutes the context window.
* The precision/recall wall is real, and the two graders wanted OPPOSITE things:
  the accuracy grader needed loose matching (single tags like "tor"/"llm" name a
  page) while the cost grader needed strict matching (one tag let a pasted API key
  fire, and dragged the biggest project page into an unrelated bug report). Requiring two tags fixed
  the false fires and collapsed recall 8/8 -> 3/8.
  The resolution was NOT a threshold but WORD CHOICE: a distinctive proper noun
  ("tor", "nostr", "orbstack") may name a page alone; a common English word
  ("memory", "design", "launch") may not, unless the prompt is actually asking
  about us (NAME_TOO_COMMON + ours_q). That held BOTH sides: 14/15 and 7/8 with
  every known bad fire silent.
* No subprocesses. The vault is 83 files / 1.3 MB — Python reads and searches all
  of it in ~39ms, while shelling out to ripgrep (once for ranking, then once per
  page for snippets) cost p95 2.7s / max 5.6s. The corpus fits in memory; use it.
"""
import sys, json, os, re, glob, difflib, math, unicodedata

# --- Config: point this at your notes. Zero dependencies, stdlib only. ---------
# Your vault is any folder of Markdown files (Obsidian, plain notes, a docs/ dir).
# Override with the CLAUDE_RECALL_VAULT env var (SECOND_BRAIN_VAULT also honored).
VAULT = os.path.expanduser(
    os.environ.get("CLAUDE_RECALL_VAULT")
    or os.environ.get("SECOND_BRAIN_VAULT")
    or "~/Documents/SecondBrain"
)
MAX_PAGES = 5
MAX_CHARS = 1900
MAX_TERMS = 10

# HUMANS TYPE SHORT; MACHINES PASTE LONG. Measured over this user's real corpus:
# human prompts median 92 chars (p90 787); Task-tool/subagent briefings median
# 12,378 chars — a 134x separation. A 1200-char cap skips 96.1% of machine
# briefings while losing only 6.9% of human prompts (all long pastes, where a miss
# costs nothing anyway).
#
# This one rule fixes BOTH findings of the final audit, which shared a root cause:
#   * false fires (~58%) were dominated by subagent briefings ("You are one finder
#     angle...", "You are summarizing a Claude Code session...") that sailed past
#     MACHINE_TURN and tripped INTENT on template boilerplate ("we decided").
#     Enumerating those patterns was whack-a-mole; length is the invariant.
#   * the latency tail (max 5.22s) came from 680KB-1.2MB summarizer prompts, since
#     difflib fuzzy matching is O(prompt_tokens x titles) with no input cap.
MAX_PROMPT_CHARS = 1200
MIN_TAG_HITS = 1          # see NAME_TOO_COMMON — the real filter is word choice

# A single COMMON English word cannot "name" a page, however distinctive it is
# inside the vault. Audits caught: "improve the design of this button" -> Portfolio
# Redesign (fuzzy design~redesign), "fix the app crash on launch" -> Docker
# Projects Launcher (launch~launcher), "what memory does this process use" (a RAM
# question) -> Memory System. These are CORRECT lexical matches to the WRONG
# intent — separating them needs semantics, which the local vector engine does
# worse (1/5). A distinctive proper noun ("tor", "nostr", "orbstack") still names
# a page on its own; an everyday word must be corroborated by a second token.
NAME_TOO_COMMON = {
    "memory", "design", "redesign", "launch", "launcher", "crash", "button",
    "process", "system", "tool", "tools", "code", "data", "test", "tests",
    "build", "web", "page", "file", "files", "server", "client", "user",
    "users", "search", "review", "plan", "state", "stack", "mode", "kit",
}

# STRONG recall intent ONLY — an explicit reference to PAST work. Generic topic
# words (plan/design/review/decide/setup/continue) are deliberately absent: they
# are the vocabulary of DOING work, not of ASKING about past work.
INTENT = re.compile(
    r"("
    r"\bremind me\b|\bremember\b|\brecall\b|"
    r"\bwhat (did|have) (we|i|you)\b|\bwhy did (we|i|you)\b|\bhow did (we|i|you)\b|"
    r"\bwhat was (our|my|the)\b|\bwhich .{0,20}\bdid (we|i)\b|"
    r"\blast (time|session|week)\b|\bpreviously\b|\bearlier (we|i|you)\b|"
    r"\bwe (decided|chose|agreed|said)\b|\b(i|you) (decided|chose|said)\b|"
    r"\balready (did|built|shipped|decided|discussed)\b|"
    r"\bwhat.{0,15}\b(preference|convention|standard)s?\b|"
    r"\bpast work\b|\bcatch (me )?up\b|\bwhere (did|were) we\b|\bcontext on\b"
    r")",
    re.I,
)

STOP = set((
    "the a an and or of to in for on with is are be was were this that these those it its as at by "
    "from into over under about above below out up down off then than so if but not no yes do does "
    "did done can could should would will shall may might must have has had how what why when where "
    "who whom which whose your you i we our us my me mine ours he she they them their his her make "
    "made making fix fixed adding add added use used using look looking find found get got set new "
    "also just only more most some any all each every please lets let need want like give show "
    "tell said say says here there now today thing stuff again really actually"
).split())

# Pure-navigation catalogs: they list every project, so they match many terms and
# (being small) score high once length-normalised. An audit caught them padding
# fires with irrelevant content. Content pages that happen to be named "* Index"
# (e.g. Model Routing Index) are deliberately NOT excluded.
SKIP_BASENAMES = {"index", "MEMORY", "CLAUDE", "log", "README",
                  "Projects Index", "Claude Code Brain Index"}

# Harness / inter-agent / skill-preamble turns reach UserPromptSubmit but are NOT
# a human asking anything. An audit found this list badly incomplete: coordinator
# relays, Stop-hook feedback, skill preambles and subagent briefings all fired the
# hook, injecting brain content into messages no human will ever read. This user
# runs heavy multi-agent orchestration, so that traffic dominates the corpus.
MACHINE_TURN = re.compile(
    r"(\[SYSTEM NOTIFICATION|<task-notification>|<local-command-|<command-name>|"
    r"<system-reminder>|<teammate-message|This is an automated background-task event|"
    r"Stop hook feedback|hook additional context|Base directory for this skill|"
    r"(The coordinator|Another Claude session|A teammate) sent|"
    r"You are (Voter|Agent|Evaluator|an? [A-Z])|"
    r"^\s*(READ-ONLY|Review this change|Changed files:|Summarize (this|the) session)|"
    r"tool_use_id|<function_results>)",
    re.I | re.M,
)

# A pasted secret is not a question. (An audit caught a raw API key firing the
# hook through a provider tag.)
SECRETISH = re.compile(r"\b(gsk_|sk-|ghp_|xox[baprs]-|AKIA|eyJ[A-Za-z0-9_-]{10,})")

# LOCAL file paths carry no recall intent, but their path segments tokenise and
# satisfy the entity gate. Measured: 4 of 41 real fires (~10%) were bare
# `file:///Users/you/Library/Messages/Attachments/...` or a dropped PDF path,
# each injecting unrelated pages. Stripped BEFORE matching.
# http(s) URLs are deliberately NOT stripped — "youtube.com/@yourchannel" is a
# genuine, graded-good entity signal.
LOCAL_PATH = re.compile(r"(file://\S+|(?<![\w/])(?:~|/Users|/private|/var|/tmp|/opt)/\S+)", re.I)

# Used ONLY to license a common word to name a page (see NAME_TOO_COMMON). As a
# general gate this was far too loose (44.8% fire / ~80% false); scoped to just
# this decision it is the right discriminator: "what stack do WE use" is asking
# about us, "improve the design of this button" is an instruction.
QUESTIONY = re.compile(r"(\?|^\s*(what|which|how|why|where|when|whats))", re.I)
OURS = re.compile(r"\b(we|our|us|my|mine|i)\b", re.I)

TITLE_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with",
              "my", "our", "index", "app", "site", "project"}


def read_stdin():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}      # a top-level array used to crash


def all_pages():
    out = []
    for sub in ("wiki", "projects", "daily-notes", ""):
        for p in glob.glob(os.path.join(VAULT, sub, "*.md")):
            if os.path.splitext(os.path.basename(p))[0] in SKIP_BASENAMES:
                continue
            out.append(p)
    return sorted(set(out))


def load_docs(pages):
    """Read the whole vault once (1.3 MB) and reuse it for meta, ranking AND
    snippets. Replaces 1 + N ripgrep subprocesses."""
    docs = {}
    for p in pages:
        try:
            docs[p] = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            pass
    return docs


def page_meta(text):
    tags, aliases = [], []
    if not text.startswith("---"):
        return tags, aliases
    end = text.find("\n---", 3)
    for ln in text[3:end if end > 0 else 800].splitlines():
        m = re.match(r"\s*(tags|aliases):\s*\[(.*)\]", ln, re.I)
        if m:
            vals = [v.strip().strip('"\'').lower() for v in m.group(2).split(",") if v.strip()]
            (tags if m.group(1).lower() == "tags" else aliases).extend(vals)
    return tags, aliases


def fold(s):
    """Strip diacritics for matching: nobody types 'é' on a US keyboard reliably.
    Unicode-awareness alone was NOT enough — "café notes" matched but "cafe notes",
    the phrasing a human actually types, stayed silent (fuzzy can't rescue a short
    token either). NFKD + drop combining marks folds both sides to "cafe" so they meet."""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def title_tokens(name):
    # `[^\W_]+` is unicode-aware; `[a-z0-9]+` was not, and it silently broke real
    # pages: "Café App" tokenised to [] (the é split "café" into caf/, "caf" <3 chars
    # after some inputs, and "app" is a stopword), making that page UNREACHABLE by its
    # own name. Accented / Arabic / CJK titles were equally invisible — bad for any
    # vault with non-ASCII page names.
    return [t for t in re.findall(r"[^\W_]+", fold(name.lower()))
            if len(t) >= 3 and t not in TITLE_STOP]


def _fuzzy_in(tok, prompt_toks):
    """Exact, else near-match: the user types fast and misspells ('obsidean',
    'capasitor'), and exact-only matching lost those outright."""
    if tok in prompt_toks:
        return True
    # Fuzzy needs >=6 chars. At 5, ordinary informal typing collides with proper
    # nouns: a 5-char everyday word can score ~0.9 against an unrelated 5-6 char page
    # name and pull it in from a dropped-file prompt. Real typo saves are longer anyway
    # ("obsidean"->obsidian 8, "capasitor"->capacitor 9), so this costs nothing.
    if len(tok) < 6:
        return False
    for p in prompt_toks:
        if len(p) >= 6 and abs(len(p) - len(tok)) <= 2 and \
                difflib.SequenceMatcher(None, tok, p).ratio() >= 0.85:
            return True
    return False


def matched_entities(prompt_lc, names, alias_map, ours_q=False):
    """Does the prompt NAME a page? High precision, so it fires regardless of
    intent — naming a page IS the signal.

    Title match: significant tokens, fuzzy, so fragments and typos land
    ("pwa to ios" -> "PWA to iOS Conversion Kit", "red flags" -> "Red Flags
    Scanner"). Requiring the full title as a literal substring missed both.

    Tag match: needs >=2 DISTINCTIVE tags. One generic tag is shared vocabulary,
    not a name — it made four pages claim "ios", let a pasted API key fire on a
    provider tag, and dragged the biggest page into an unrelated bug report.
    """
    prompt_toks = set(re.findall(r"[^\W_]+", fold(prompt_lc)))  # unicode-aware + diacritic-folded
    # Glue "word 101" -> "word101": product names are typed with a space far more
    # often than they are written. Measured gap: "acme 101" matched NOTHING while
    # "acme101" hit correctly — the natural spelling silently failed.
    seq = re.findall(r"[^\W_]+", fold(prompt_lc))
    # b may carry a trailing possessive/plural ("acme 101s" -> acme101), so glue
    # onto the DIGIT PREFIX of b rather than requiring b be all digits.
    for a, b in zip(seq, seq[1:]):
        if a.isalpha() and len(a) >= 3 and b and b[0].isdigit():
            digits = re.match(r"\d+", b).group(0)
            prompt_toks.add(a + digits)
    freq, afreq = {}, {}
    for n in names:
        for t in set(title_tokens(n)):
            freq[t] = freq.get(t, 0) + 1
        for a in set(alias_map.get(n, [])):
            afreq[a] = afreq.get(a, 0) + 1
    hits = []
    for n in names:
        toks = title_tokens(n)
        if not toks:
            continue
        got = [t for t in toks if _fuzzy_in(t, prompt_toks)]
        common = got and all(g in NAME_TOO_COMMON for g in got)
        if got and (not common or ours_q) and (
                len(got) == len(toks) or len(got) >= 2
                or (len(got) == 1 and len(got[0]) >= 5 and freq.get(got[0], 9) == 1)):
            hits.append(n)
            continue
        distinctive = 0
        for a in alias_map.get(n, []):
            if afreq.get(a, 9) > 2:
                continue
            words = [w for w in re.findall(r"[^\W_]+", a) if len(w) >= 3]
            if not words or (all(w in NAME_TOO_COMMON for w in words) and not ours_q):
                continue
            if all(_fuzzy_in(w, prompt_toks) for w in words):
                distinctive += 1
        if distinctive >= MIN_TAG_HITS:
            hits.append(n)
    return hits


def salient_terms(prompt, entity_hits):
    terms = [e.lower() for e in entity_hits]
    for raw in re.findall(r"[^\W_][\w\-]{3,}", prompt):   # unicode-aware
        w = raw.lower()
        if w in STOP or w in terms:
            continue
        terms.append(w)
    seen, out = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t); out.append(t)
        if len(out) >= MAX_TERMS:
            break
    return out


def lexical_rank(terms, docs_lc):
    """IDF-weighted distinct-term hits, length-normalised. Pure python.

    Length normalisation is the load-bearing part: without it the biggest file in
    the vault wins nearly every query on incidental matches.
    """
    if not terms:
        return {}
    N = max(len(docs_lc), 1)
    postings = {p: {t for t in terms if t in txt} for p, txt in docs_lc.items()}
    postings = {p: ts for p, ts in postings.items() if ts}
    df = {}
    for ts in postings.values():
        for t in ts:
            df[t] = df.get(t, 0) + 1
    scores = {}
    for p, ts in postings.items():
        s = sum(math.log(1 + N / df[t]) for t in ts)
        scores[p] = s / (math.sqrt(max(len(docs_lc[p]), 1) / 1024.0) or 1.0)
    return scores


def rank(lex, entity_hits, terms, meta):
    scores = dict(lex)
    for p, (tags, aliases) in meta.items():
        n = sum(1 for t in terms if t in tags or t in aliases)
        if n:
            scores[p] = scores.get(p, 0.0) + 0.30 * n
    for p in list(scores):
        base = os.path.splitext(os.path.basename(p))[0]
        if base in entity_hits:
            scores[p] += 3.0
        scores[p] += 0.25 * sum(1 for t in terms if t in base.lower())
        if os.sep + "wiki" + os.sep in p:
            scores[p] += 0.05
        if os.sep + "daily-notes" + os.sep in p:
            scores[p] -= 0.06
    return sorted(scores, key=scores.get, reverse=True)[:MAX_PAGES]


def page_desc(text):
    # Strip YAML frontmatter FIRST. A `# comment` inside frontmatter otherwise wins
    # the "first heading" match — bi-temporal comments in Model Routing Index made
    # the hook advertise the page as "Bi-temporal: valid_from = when the FACT...".
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    fm, body = (m.group(1), text[m.end():]) if m else ("", text)
    d = re.search(r"^\s*description:\s*(.+)$", fm, re.M | re.I)
    if d:
        return d.group(1).strip().strip('"')[:140]
    h = re.search(r"^#\s+(.+)$", body[:1500], re.M)
    return h.group(1).strip()[:140] if h else ""


def snippets(text, terms):
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        ll = line.lower()
        if any(t in ll for t in terms):
            out.append(f"    L{i}: {re.sub(r'[ \t]+', ' ', line).strip()[:150]}")
            if len(out) == 2:
                break
    return out


LOG = os.path.expanduser(os.environ.get("CLAUDE_RECALL_LOG")
                         or "~/.claude/logs/brain-recall.jsonl")


def _log_fire(prompt, ent_hits, ranked, ctx_chars):
    """Append-only record of every FIRE, so the keep/kill call is made on data.

    This hook was kept over an auditor's delete recommendation on a specific
    argument: its "no measured payoff" verdict judged a mechanism that was 0 hours
    old, while the alternative (discretionary read-first) has a MEASURED 15-day,
    100%-failure record. That argument is only honest if the payoff actually gets
    measured from here. KILL CRITERION in ~/.claude/logs/brain-recall.README.
    Best-effort and silent: logging must never break a prompt.
    """
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        rec = {
            "ts": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "prompt": prompt[:100],          # truncated; secret-shaped prompts never reach here
            "gate": "entity" if ent_hits else "intent",
            # INTENT has fired 0/51 times because the entity gate always wins
            # first. Log it independently so the 2026-07-30 review can decide on
            # data whether the regex is dead weight or a rare-but-real backstop.
            "intent_only": bool(not ent_hits),
            "intent_would_match": bool(INTENT.search(prompt)),
            "entities": ent_hits[:3],
            "pages": [os.path.basename(p) for p in ranked],
            "ctx_chars": ctx_chars,
        }
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    if not os.path.isdir(VAULT):
        return
    prompt = (read_stdin().get("prompt") or "").strip()
    if not (8 <= len(prompt) <= MAX_PROMPT_CHARS) or \
            MACHINE_TURN.search(prompt[:400]) or SECRETISH.search(prompt):
        return

    pages = all_pages()
    docs = load_docs(pages)
    if not docs:
        return
    docs_lc = {p: t.lower() for p, t in docs.items()}
    meta = {p: page_meta(t) for p, t in docs.items()}
    alias_map = {os.path.splitext(os.path.basename(p))[0]: (tg + al)
                 for p, (tg, al) in meta.items()}
    names = [os.path.splitext(os.path.basename(p))[0] for p in pages
             if os.sep + "daily-notes" + os.sep not in p]

    ours_q = bool(QUESTIONY.search(prompt) and OURS.search(prompt))
    # Match against the prompt with LOCAL file paths removed. Their segments
    # tokenise ("Library", "Attachments", "Downloads", a filename) and satisfy the
    # entity gate even though a dropped file carries no recall intent — measured at
    # 4 of 41 real fires. http(s) URLs are intentionally preserved.
    match_text = LOCAL_PATH.sub(" ", prompt).lower()
    ent_hits = matched_entities(match_text, names, alias_map, ours_q)
    if not (ent_hits or INTENT.search(prompt)):
        return

    terms = salient_terms(prompt, ent_hits)
    if not terms:
        return
    ranked = rank(lexical_rank(terms, docs_lc), ent_hits, terms, meta)
    if not ranked:
        return

    out = ["🧠 SECOND BRAIN — pages matching THIS prompt (retrieved for you; the "
           "read-first step is done). These hold prior decisions/context you already "
           "filed — consult them before re-deriving:"]
    budget = MAX_CHARS
    for p in ranked:
        chunk = "\n".join(
            [f"• {os.path.relpath(p, VAULT)}" +
             (f" — {page_desc(docs[p])}" if page_desc(docs[p]) else "")]
            + snippets(docs[p], terms))
        if len(chunk) > budget:
            break
        out.append(chunk); budget -= len(chunk)
    out.append("Open the page for the full context. If this turn produces something "
               "durable, write it back to the vault.")
    ctx = "\n".join(out)
    _log_fire(prompt, ent_hits, ranked, len(ctx))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": ctx,
    }}))


if __name__ == "__main__":
    main()
