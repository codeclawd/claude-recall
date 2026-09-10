#!/usr/bin/env python3
"""Stop hook: refuse to end a substantial session that filed NOTHING to wiki/.

WHY THIS EXISTS
---------------
`wiki/` — the durable synthesis layer — is the ONE major memory operation with no
mechanism behind it:
    daily-notes/  <- vault-update.sh writes it automatically (Stop hook)
    Lessons.md    -> gen-lessons-digest.py only READS it
    wiki/         <- NOTHING writes it. 100% discretionary.

Measured cost of that gap: the same "file durable learnings as you go" rule was
written into Lessons.md FOUR separate times — 2026-05-06, 07-03, 07-06, 07-11 —
and failed every time, because a written rule competes for attention and loses. In
three of those the USER had to ask "did you update the brain?". Same shape as
read-first, which failed for 15 straight days until a hook did the work.

WHY IT BLOCKS RATHER THAN NOTIFIES
----------------------------------
v1 of this script printed `{"outputToClient": ...}`. That field is NOT documented
for Stop hooks and is silently ignored — so v1 did nothing at all. Worse, even had
it worked it addressed the USER, leaving the loop as "hook tells user -> user tells
Claude", which is precisely the asking-loop this is meant to remove.

`{"decision": "block", "reason": ...}` feeds the reason back to CLAUDE, so the
write-back becomes something that must be cleared before the turn can end. The
script still does not write anything — choosing what is durable, which page it
belongs on, and whether it contradicts an existing claim all need judgement.
Detection is mechanical; the writing stays Claude's job.

SAFETY (docs: code.claude.com/docs/en/hooks)
--------------------------------------------
* `stop_hook_active` is true when Claude is already continuing due to a previous
  block -> exit immediately, or this loops.
* Claude Code force-overrides a Stop hook after 8 consecutive blocks. We block at
  most ONCE per session anyway (session-id marker).
* Stop hooks fire on EVERY response, not just at task end — so an unguarded block
  would interrupt every single turn. The substantial-session + once-per-session
  guards exist for exactly that.
* Firing mid-session is correct, not a bug: all four source lessons say file
  DURING the work, not at the end.
"""
import json, os, sys, time, glob, re

VAULT = os.path.expanduser(
    os.environ.get("CLAUDE_RECALL_VAULT")
    or os.environ.get("SECOND_BRAIN_VAULT")
    or "~/Documents/SecondBrain"
)
WIKI = os.path.join(VAULT, "wiki")
STATE_DIR = os.path.expanduser("~/.claude/logs")
STATE = os.path.join(STATE_DIR, "vault-writeback.json")
NOW_FILE = os.path.expanduser("~/.remember/now.md")

MIN_SESSION_CHARS = 600     # below this nothing durable was plausibly produced
QUIET_HOURS = 6             # wiki/ untouched this long => nothing was filed


def newest_wiki_mtime():
    best = 0.0
    for p in glob.glob(os.path.join(WIKI, "*.md")):
        try:
            best = max(best, os.path.getmtime(p))
        except OSError:
            pass
    return best


def allow():
    print(json.dumps({"continue": True}))
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    # 1. Already continuing because WE blocked -> never block again.
    if payload.get("stop_hook_active"):
        return allow()

    if not os.path.isdir(WIKI):
        return allow()

    # 2. Only once per session.
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", str(payload.get("session_id") or "nosess"))
    marker = os.path.join("/tmp", f"vault-wb-{sid}")
    if os.path.exists(marker):
        return allow()

    # 3. Was this session substantial enough to have produced anything durable?
    try:
        session_size = os.path.getsize(NOW_FILE) if os.path.exists(NOW_FILE) else 0
    except OSError:
        session_size = 0
    if session_size < MIN_SESSION_CHARS:
        return allow()

    # 4. Was something already filed recently? Then stay out of the way.
    age_h = (time.time() - newest_wiki_mtime()) / 3600.0
    if age_h < QUIET_HOURS:
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            json.dump({"streak": 0, "last_ok": time.time()}, open(STATE, "w"))
        except Exception:
            pass
        return allow()

    # 5. Substantial work + untouched wiki/ = a durable-writeback miss. Block once.
    try:
        st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    except Exception:
        st = {}
    streak = int(st.get("streak", 0)) + 1
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        json.dump({"streak": streak, "last_miss": time.time(),
                   "wiki_age_hours": round(age_h, 1)}, open(STATE, "w"))
        open(marker, "w").close()
    except Exception:
        pass

    reason = (
        f"VAULT WRITE-BACK CHECK (miss #{streak}): this session produced real work "
        f"but `{WIKI}` has not been touched in {age_h:.0f}h. daily-notes/ is the "
        f"ephemeral log; `wiki/` is the durable layer that retrieval and the "
        f"lessons-digest are BUILT FROM — knowledge that never lands there is "
        f"effectively lost.\n\n"
        f"Before finishing, do ONE of these:\n"
        f"  (a) File what's durable — a decision + its rationale, a root cause, a "
        f"user correction, a gotcha — into the relevant `wiki/` page (edit, never "
        f"clobber; flag contradictions with `> [!warning]`), append a "
        f"`## [YYYY-MM-DD] <op> | <title>` line to log.md, and say what you filed.\n"
        f"  (b) If this session genuinely produced nothing durable, say so "
        f"explicitly in one line and stop.\n\n"
        f"Do not ask the user whether to file — that is the loop this check exists "
        f"to remove. Decide, act, and report. (Fires at most once per session.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        try:
            print(json.dumps({"continue": True}))
        except Exception:
            pass
        sys.exit(0)          # never fail a session over a memory nudge
