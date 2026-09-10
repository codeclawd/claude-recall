#!/usr/bin/env python3
"""brain-sweep — read-only consolidation / contradiction / staleness report.

WHY
---
Two memory systems grew in parallel and nothing ever reconciled them:
  * native auto-memory  ~/.claude/projects/<proj>/memory/*.md  (Anthropic-managed)
  * the Obsidian vault  $VAULT/wiki/*.md (canonical)
CLAUDE.md says auto-memory is "the short-lived companion layer that gets promoted,
not the durable record" — and promotion DID happen (15/18 feedback files are in the
vault). But nothing ever pruned the originals, because pruning was an instruction,
not a mechanism. So the same lesson now lives in three places.

This is the mechanism. It is deliberately READ-ONLY: it reports, you decide.

WHAT IT DOES *NOT* DO
---------------------
It does not judge meaning. Overlap is measured with word-shingle Jaccard — cheap,
deterministic, explainable. Semantic calls ("are these two pages really the same
claim?", "do these contradict?") are left to a human/Claude reading the shortlist.
A script that guesses at meaning would just relocate the error.

Usage:  python3 ~/.claude/scripts/brain-sweep.py [--full]
"""
import os
import time, re, sys, glob, itertools, datetime

VAULT = os.path.expanduser(
    os.environ.get("CLAUDE_RECALL_VAULT")
    or os.environ.get("SECOND_BRAIN_VAULT")
    or "~/Documents/SecondBrain"
)
WIKI = os.path.join(VAULT, "wiki")
MEM_ROOT = os.path.expanduser("~/.claude/projects")
SHINGLE = 5
DUP_HI, DUP_LO = 0.18, 0.06     # tuned to be indicative, not authoritative


def words(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)          # drop code blocks
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return [w for w in text.split() if len(w) > 2]


def shingles(text, n=SHINGLE):
    w = words(text)
    return {" ".join(w[i:i + n]) for i in range(max(len(w) - n + 1, 0))}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


COMMON = set((
    "the and for with that this from you your not are was were will can could should would have has "
    "had but they them their then than when what which who whom how why where all any our out use "
    "used using make made get got set new only just also into over under more most some each every "
    "memory node type name description metadata claude code file files project projects user rule "
    "rules always never before after work working done need needs want wants like time first last"
).split())


def distinctive(text, maxn=40):
    """Rare, identifying tokens ('aria2c', 'orbstack', 'x16') — the fingerprint of
    a fact.

    NOT word-shingles. Shingles measure copy-paste, and the vault PARAPHRASES:
    calibrated against a known-duplicate (feedback_use_aria2 vs the vault, where
    `aria2c` and `-x16` demonstrably appear in both), 5-word shingles reported
    0.0% covered and even bigrams only 14%. A metric that scores a confirmed
    duplicate at zero would have recommended promoting 73 already-present files.
    Distinctive-term presence answers the question actually being asked: "is this
    FACT recorded in the vault?", regardless of wording.
    """
    # Strip YAML frontmatter and machine identifiers first. Auto-memory files carry
    # UUIDs, slug echoes of their own filename, and field names
    # (originSessionId...). Those are metadata, not knowledge: counting them as
    # "distinctive terms missing from the vault" made well-covered files look
    # like gaps and inflated the MIXED bucket.
    body = re.sub(r"\A---.*?\n---\n", "", text, flags=re.S)
    body = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", " ", body)
    body = re.sub(r"\b[0-9a-f]{16,}\b", " ", body)
    toks = [t for t in re.findall(r"[a-z0-9][a-z0-9\-\.]{3,}", body.lower())
            if t not in COMMON and not t.isdigit()
            and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+){2,}", t)          # slug echoes
            and not re.fullmatch(r"(origin)?session ?id|node_?type|metadata", t)]
    freq = {}
    for t in toks:
        freq[t] = freq.get(t, 0) + 1
    # rare-in-this-doc tokens are the identifying ones
    ranked = sorted(freq, key=lambda t: (freq[t], -len(t)))
    return ranked[:maxn]


def term_coverage(text, blob):
    """Fraction of a doc's distinctive terms that appear anywhere in the vault.
    INDICATIVE ONLY — presence of a term is not proof the claim is covered."""
    terms = distinctive(text)
    if not terms:
        return 0.0, [], []
    present = [t for t in terms if t in blob]
    return len(present) / len(terms), present, [t for t in terms if t not in blob]


def read(p):
    try:
        return open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""


def main():
    full = "--full" in sys.argv
    wiki = {os.path.basename(p): read(p) for p in glob.glob(os.path.join(WIKI, "*.md"))}
    if not wiki:
        print("no vault pages found"); return 1
    wiki_sh = {k: shingles(v) for k, v in wiki.items()}
    all_wiki = set().union(*wiki_sh.values()) if wiki_sh else set()

    mem = {}
    for d in glob.glob(os.path.join(MEM_ROOT, "*", "memory")):
        for p in glob.glob(os.path.join(d, "*.md")):
            mem[os.path.relpath(p, MEM_ROOT)] = read(p)

    print("=" * 72)
    print("BRAIN SWEEP — read-only. Nothing is deleted; this is a shortlist to judge.")
    print("=" * 72)

    # 1. Evidence for a human to judge promotion — NOT a verdict.
    blob = "\n".join(wiki.values()).lower()
    print(f"\n## 1. AUTO-MEMORY vs VAULT  ({len(mem)} files)")
    print("   Signal = share of a file's DISTINCTIVE terms that appear in the vault.")
    print("   Indicative only: term presence != claim covered. YOU judge; read before pruning.\n")
    rows = []
    for name, text in sorted(mem.items()):
        cov, present, missing = term_coverage(text, blob)
        best, bestv = "", 0.0
        sh = shingles(text)
        for w, wsh in wiki_sh.items():
            c = jaccard(sh, wsh)
            if c > bestv:
                best, bestv = w, c
        rows.append((cov, name, best, missing))
    hi = [r for r in rows if r[0] >= 0.75]
    mid = [r for r in rows if 0.4 <= r[0] < 0.75]
    lo = [r for r in rows if r[0] < 0.4]
    for label, group, note in (
            ("LIKELY COVERED  ", hi, "← most terms already in vault; READ then consider pruning"),
            ("MIXED           ", mid, "← reconcile: some facts may be vault-only"),
            ("LIKELY VAULT-GAP", lo, "← terms largely absent: PROMOTE these before any prune")):
        print(f"  {label} ({len(group)}) {note}")
        for cov, name, best, missing in sorted(group, key=lambda r: -r[0])[: (99 if full else 6)]:
            miss = (" · missing: " + ", ".join(missing[:3])) if missing and cov < 0.75 else ""
            print(f"    {cov*100:5.1f}%  {os.path.basename(name):<38} nearest≈ {best or '-'}{miss}")
        if not full and len(group) > 6:
            print(f"    … {len(group)-6} more (--full)")
        print()

    # 2. near-duplicate vault pages
    print("## 2. NEAR-DUPLICATE vault pages (candidates to merge)\n")
    dups = []
    for a, b in itertools.combinations(sorted(wiki_sh), 2):
        j = jaccard(wiki_sh[a], wiki_sh[b])
        if j >= DUP_LO:
            dups.append((j, a, b))
    for j, a, b in sorted(dups, reverse=True)[: (99 if full else 8)]:
        flag = "⚠️ " if j >= DUP_HI else "  "
        print(f"  {flag}{j*100:4.1f}%  {a}  ~  {b}")
    print(f"  ({len(dups)} pairs above {DUP_LO*100:.0f}%)" if dups else "  none")

    # 3. staleness / rot
    print("\n## 3. STALENESS\n")
    # Link targets can live ANYWHERE in the vault (index/, projects/, daily-notes/),
    # not just wiki/. Comparing only against wiki/ titles reported 35 "broken"
    # links that were all [[mined-conversations]] — which exists at
    # index/mined-conversations.md. False positives in the checker, not vault rot.
    titles = {os.path.splitext(os.path.basename(p))[0]
              for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True)}
    broken = {}
    for k, v in wiki.items():
        miss = {l for l in re.findall(r"\[\[([^\]|#]+)", v) if l.strip() not in titles}
        if miss:
            broken[k] = miss
    print(f"  pages with broken [[wikilinks]]: {len(broken)}")
    for k, v in sorted(broken.items())[: (99 if full else 5)]:
        print(f"    {k}: {', '.join(sorted(v)[:4])}")
    old = []
    for k, v in wiki.items():
        m = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})", v, re.M)
        if m and m.group(1) < "2026-06-01":
            old.append((m.group(1), k))
    print(f"\n  pages not updated since 2026-06-01: {len(old)}")
    for d, k in sorted(old)[: (99 if full else 5)]:
        print(f"    {d}  {k}")

    # 4. contradiction SHORTLIST — mechanical only; a human/Claude judges
    print("\n## 4. CONTRADICTION shortlist (for a human/Claude to judge — NOT decided here)\n")
    warns = [k for k, v in wiki.items() if "[!warning]" in v]
    print(f"  pages already carrying a > [!warning] contradiction flag: {len(warns)}")
    for k in sorted(warns)[:8]:
        print(f"    {k}")
    print("\n  High-overlap pairs from §2 marked ⚠️ are the ones worth reading for")
    print("  conflicting claims. This script deliberately does not guess at meaning.")

    # 5. bi-temporal: which live-state claims are unverifiable / gone stale?
    #
    # `updated:` says when the PAGE was touched, never whether the CLAIM is still
    # true. The Fable-5 drift (a fact stale for 2 weeks across 3 layers while
    # settings.json disagreed the whole time) was invisible precisely because every
    # page looked freshly "updated". A claim about live config needs
    # verified_against: <file:line> or it cannot be checked at all.
    print("\n## 5. BI-TEMPORAL / verification status\n")
    CONFIG_CLAIM = re.compile(
        r"(settings\.json|availableModels|pinned default|`?claude-[a-z0-9\-]+(\[1m\])?`?|"
        r"enforceAvailableModels|fallbackModel|MCP server|installed at|runs on port)", re.I)
    unver, stale, ok = [], [], []
    today = datetime.date.today()
    for k, v in wiki.items():
        fm = re.match(r"\A---\n(.*?)\n---\n", v, re.S)
        fmt = fm.group(1) if fm else ""
        has_claim = bool(CONFIG_CLAIM.search(v))
        vd = re.search(r"^verified:\s*(\d{4}-\d{2}-\d{2})", fmt, re.M)
        va = re.search(r"^verified_against:\s*(.+)$", fmt, re.M)
        if not has_claim:
            continue
        if not vd or not va:
            unver.append(k)
        else:
            try:
                age = (today - datetime.date.fromisoformat(vd.group(1))).days
            except ValueError:
                age = 999
            (stale if age > 30 else ok).append((k, vd.group(1), age, va.group(1).strip()))
    print(f"  ✅ verified against live state ({len(ok)})")
    for k, d, a, src in ok[: (99 if full else 4)]:
        print(f"    {k}  verified {d} ({a}d) vs {src}")
    print(f"\n  ⏳ verified >30d ago ({len(stale)}) — re-check against the source")
    for k, d, a, src in sorted(stale, key=lambda r: -r[2])[: (99 if full else 4)]:
        print(f"    {k}  verified {d} ({a}d ago) vs {src}")
    print(f"\n  ⚠️  makes live-state claims with NO verified_against ({len(unver)})")
    print("     → cannot be checked; this is how the Fable-5 drift hid for 2 weeks")
    for k in sorted(unver)[: (99 if full else 6)]:
        print(f"    {k}")
    if not full and len(unver) > 6:
        print(f"    … {len(unver)-6} more (--full)")

    # ---- 6. RAW STAGE census -------------------------------------------------
    # Stage 1 sat empty from the vault restructure until 2026-08-30 while wiki/ grew to 97
    # pages -- synthesis with every source discarded. Nothing reported it, so nothing fixed
    # it. This section exists so an empty raw stage is loud instead of invisible.
    print("\n## 6. RAW STAGE (index/ -- immutable ground truth)\n")
    raw_root = os.path.join(VAULT, "index")
    artifacts, total_bytes = [], 0
    for dirpath, _dirs, files in os.walk(raw_root):
        for fn in files:
            if fn.startswith(".") or fn.endswith(".md"):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                total_bytes += os.path.getsize(fp)
            except OSError:
                continue
            artifacts.append(os.path.relpath(fp, raw_root))
    if not artifacts:
        print("  🔴 EMPTY -- every wiki claim is currently unre-derivable.")
        print("     Ingest must deposit the source into index/assets/ BEFORE distilling it;")
        print("     see the ingest recipe in ~/.claude/CLAUDE.md and the vault CLAUDE.md.")
    else:
        by_dir = {}
        for a in artifacts:
            by_dir.setdefault(os.path.dirname(a) or ".", []).append(a)
        print(f"  ✅ {len(artifacts)} artifact(s), {total_bytes/1024:.0f}K across {len(by_dir)} folder(s)")
        for d in sorted(by_dir):
            print(f"     {d}/  {len(by_dir[d])}")
        newest = max(
            (os.path.getmtime(os.path.join(raw_root, a)) for a in artifacts), default=0
        )
        age = (time.time() - newest) / 86400
        flag = "  ⚠️  no new source in >60d -- is anything still being preserved?" if age > 60 else ""
        print(f"     newest artifact: {age:.0f}d old{flag}")

    print("\n" + "=" * 72)
    print("NEXT: (1) promote LIKELY VAULT-GAP files before pruning anything.")
    print("      (2) add verified_against: <file:line> to §5's unverified pages —")
    print("          a claim you cannot check is a claim that will silently rot.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
