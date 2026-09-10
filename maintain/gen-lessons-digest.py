#!/usr/bin/env python3
"""Generate the always-loaded lessons digest from the vault's Lessons.md.

WHY
---
`$VAULT/wiki/Lessons.md` holds 37 hard-won rules (~9k
tokens) and was NEVER loaded — CLAUDE.md only referenced it as a place to WRITE.
So every rule was knowledge Claude was supposed to have and structurally could
not. That is the "model doesn't know what it should already know" failure, and no
retrieval hook fixes it: retrieval needs a question, and the whole problem is that
no question gets asked.

The fix is not retrieval, it's LOADING. Each lesson's `### ` title in that file is
already a complete, self-sufficient imperative rule (the vault's own convention),
so titles alone compress ~9k tokens -> ~1.1k with no loss of actionability. Full
rationale for any rule stays one Read away in Lessons.md.

MECHANISM, NOT INSTRUCTION
--------------------------
This runs from the Stop hook, so the digest regenerates itself after every session
that touches the vault. A digest that depended on someone remembering to run it
would rot — which is the exact disease this whole system kept dying of.
"""
import os, re, sys, datetime, tempfile

VAULT = os.path.expanduser(
    os.environ.get("CLAUDE_RECALL_VAULT")
    or os.environ.get("SECOND_BRAIN_VAULT")
    or "~/Documents/SecondBrain"
)
SRC = os.path.join(VAULT, "wiki", "Lessons.md")
DST = os.path.expanduser("~/.claude/rules/lessons-digest.md")
MAX_TITLE = 240        # one heading; longer is a fat-finger, not a rule
MAX_LESSONS = 300      # sanity ceiling; real count is ~38

HEADER = """# lessons-digest.md — what you already learned (AUTO-GENERATED, do not hand-edit)

> Generated from `$VAULT/wiki/Lessons.md` by
> `~/.claude/scripts/gen-lessons-digest.py` (Stop hook). Edit the vault, not this file.
> Last generated: {date} · {n} lessons · ~{tok} tokens.

These are rules YOU established from real mistakes — mostly your own. They are loaded
every session precisely because the failure they address is not "couldn't recall it"
but "didn't know to ask." Treat each line as already-known: if one bears on what you
are about to do, it governs — you do not need to look it up first.

Full context for any rule (what happened, why, date, origin project) is in
`Lessons.md` — read the matching `### ` section before acting on a surprising one.

"""


def main():
    try:
        text = open(SRC, encoding="utf-8").read()
    except Exception as e:
        print(f"lessons-digest: cannot read {SRC}: {e}", file=sys.stderr)
        return 1
    # Blank out fenced code blocks BEFORE splitting: a `### heading` quoted inside
    # a ``` fence is not a lesson, but the naive split baked it into the
    # always-loaded rules with a log line that looked completely normal.
    scrubbed = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    titles = [b.split("\n", 1)[0].strip()
              for b in re.split(r"^### ", scrubbed, flags=re.M)[1:]]
    # Cap a single title: a fat-fingered 5k-char heading otherwise lands whole in
    # every future session (~1.4k tokens for one bogus entry).
    titles = [(t[:MAX_TITLE] + "…") if len(t) > MAX_TITLE else t for t in titles if t]
    if not titles:
        print("lessons-digest: no lessons parsed; refusing to write empty digest",
              file=sys.stderr)
        return 1
    # Sanity gate: this file is injected into EVERY session and ~/.claude is not a
    # git repo, so there is no recovery from a bad write. Refuse implausible output
    # rather than poison the always-loaded rules.
    if len(titles) > MAX_LESSONS:
        print(f"lessons-digest: {len(titles)} lessons exceeds sanity cap {MAX_LESSONS}; "
              "refusing to write (is Lessons.md malformed?)", file=sys.stderr)
        return 1
    body = "\n".join(f"- {t}" for t in titles)
    approx = (len(HEADER) + len(body)) // 4
    out = HEADER.format(date=datetime.date.today().isoformat(),
                        n=len(titles), tok=approx) + body + "\n"
    try:
        os.makedirs(os.path.dirname(DST), exist_ok=True)
        # only rewrite on change, so mtime stays meaningful
        if os.path.exists(DST):
            old = open(DST, encoding="utf-8").read()
            if old.split("\n", 6)[-1] == out.split("\n", 6)[-1]:
                return 0
        # ATOMIC write: temp file in the SAME dir + os.replace (atomic on POSIX).
        # A plain open(w).write() is not atomic — two concurrent Stop hooks
        # interleaved and corrupted this file in 2 of 15 reproduction runs. This
        # user runs parallel sessions/worktrees, so concurrent Stop hooks are the
        # normal case, and a corrupted always-loaded rules file has no recovery
        # path (~/.claude is not version-controlled).
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(DST), prefix=".digest-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(out)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, DST)          # atomic: readers see old or new, never a mix
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as e:
        print(f"lessons-digest: cannot write {DST}: {e}", file=sys.stderr)
        return 1
    print(f"lessons-digest: {len(titles)} lessons -> {DST} (~{approx} tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
