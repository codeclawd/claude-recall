#!/usr/bin/env bash
# Regression test for the relevance floor (FLOOR_ABS / FLOOR_REL).
# Before the floor, brain-recall emitted exactly MAX_PAGES pages on EVERY fire —
# a miss looked identical to a hit. This asserts it no longer does.
set -euo pipefail
cd "$(dirname "$0")/.."
export CLAUDE_RECALL_VAULT="$PWD/tests/fixture-vault"

count() { echo "{\"prompt\":\"$1\"}" | python3 brain-recall.py | python3 -c "
import sys,json
d=sys.stdin.read().strip()
print(0 if not d else json.loads(d)['hookSpecificOutput']['additionalContext'].count('\n• '))"; }

fail=0
check() { local got; got=$(count "$2"); if [ "$got" != "$3" ]; then
  echo "FAIL $1: expected $3 pages, got $got"; fail=1; else echo "ok   $1 ($got pages)"; fi; }

check F1-focused  "what did we decide about the auth system refresh tokens" 1
check F2-unmatched "what did we decide about the kubernetes ingress controller" 0
check F3-entity   "remind me what Cache Layer says" 1
check F4-one-strong "what did we decide about caching stale reads" 1

exit $fail
