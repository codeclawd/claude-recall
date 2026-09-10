#!/usr/bin/env bash
# Branch test for the write-back gate. The point of this hook is to BLOCK, so the
# test must prove it blocks in exactly one case and stays out of the way in the rest.
# A run where every branch allows is a broken harness, not a passing test.
set -uo pipefail
cd "$(dirname "$0")/.."

WB=$(mktemp -d); BIG=$(mktemp); SMALL=$(mktemp)
trap 'rm -rf "$WB" "$BIG" "$SMALL" /tmp/vault-wb-TESTSESS' EXIT
mkdir -p "$WB/wiki"
printf '# Old\n%.0s' {1..40} > "$WB/wiki/Old Page.md"
head -c 900 /dev/zero | tr '\0' 'x' > "$BIG"
head -c 100 /dev/zero | tr '\0' 'x' > "$SMALL"
stale() { touch -t "$(date -v-7H +%Y%m%d%H%M 2>/dev/null || date -d '7 hours ago' +%Y%m%d%H%M)" "$WB/wiki/Old Page.md"; }

verdict() {  # $1=vault $2=sessionfile $3=json  -> prints BLOCK|allow
  CLAUDE_RECALL_VAULT="$1" CLAUDE_RECALL_SESSION_LOG="$2" \
  python3 hooks/writeback-check.py <<< "$3" | python3 -c \
'import sys,json
d=sys.stdin.read().strip()
print("BLOCK" if d and json.loads(d).get("decision")=="block" else "allow")'
}

fail=0
check(){ rm -f /tmp/vault-wb-TESTSESS; local got; got=$(verdict "$2" "$3" "$4")
  if [ "$got" != "$5" ]; then echo "FAIL $1: wanted $5, got $got"; fail=1; else echo "ok   $1 ($got)"; fi; }

LIVE='{"session_id":"TESTSESS","stop_hook_active":false}'
DONE='{"session_id":"TESTSESS","stop_hook_active":true}'

stale; check W1-substantial-stale-wiki "$WB" "$BIG"   "$LIVE" BLOCK
stale; check W2-stop-hook-active       "$WB" "$BIG"   "$DONE" allow
stale; check W3-trivial-session        "$WB" "$SMALL" "$LIVE" allow
touch "$WB/wiki/Old Page.md"
       check W4-wiki-just-written      "$WB" "$BIG"   "$LIVE" allow
stale; check W5-no-vault               "/nonexistent" "$BIG" "$LIVE" allow

# W6: fires at most once per session — second call must allow.
stale; rm -f /tmp/vault-wb-TESTSESS
first=$(verdict "$WB" "$BIG" "$LIVE"); second=$(verdict "$WB" "$BIG" "$LIVE")
if [ "$first" = "BLOCK" ] && [ "$second" = "allow" ]; then echo "ok   W6-once-per-session ($first then $second)"
else echo "FAIL W6-once-per-session: wanted BLOCK then allow, got $first then $second"; fail=1; fi

exit $fail
