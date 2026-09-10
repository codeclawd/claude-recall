#!/bin/bash
# Auto-updates the second-brain vault at session end.
# Uses obsidian-cli if available, falls back to a direct file write.

VAULT_PATH="${CLAUDE_RECALL_VAULT:-${SECOND_BRAIN_VAULT:-$HOME/Documents/SecondBrain}}"
# Source of the session summary. Default is the `remember` plugin's buffer;
# override with CLAUDE_RECALL_SESSION_LOG to point at any file your setup writes.
NOW_FILE="${CLAUDE_RECALL_SESSION_LOG:-$HOME/.remember/now.md}"
DATE=$(date +%Y-%m-%d)
NOTE_TITLE="Session $DATE"
NOTE_DIR="$VAULT_PATH/daily-notes"   # staged layout: session logs live here

# Skip if vault doesn't exist or now.md is empty
[[ ! -d "$VAULT_PATH" ]] && exit 0
[[ ! -s "$NOW_FILE" ]] && exit 0
mkdir -p "$NOTE_DIR"

# POISONING / SECRET GUARD — never write raw session text into the vault.
# The vault is durable, git-tracked and syncable: a key landing here is exfiltrated
# on the next sync and survives in git history after deletion. Daily notes are also
# re-read on resume and surfaced by brain-recall, so instruction-shaped text
# replays into future context as trusted memory (OWASP ASI06, "poison once,
# exploit forever").
# FAIL CLOSED: if the sanitizer is missing or errors, write NOTHING. Falling back
# to the raw file would defeat the guard exactly when it matters most.
SANITIZER="${CLAUDE_RECALL_SANITIZER:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/vault-sanitize.py}"
SAFE_FILE="$(mktemp -t vaultsafe)"
trap 'rm -f "$SAFE_FILE"' EXIT
if [[ ! -x "$SANITIZER" && ! -f "$SANITIZER" ]]; then
    echo "vault-update: sanitizer missing at $SANITIZER — refusing to write" >&2
    exit 0
fi
if ! python3 "$SANITIZER" < "$NOW_FILE" > "$SAFE_FILE" 2>/dev/null || [[ ! -s "$SAFE_FILE" ]]; then
    echo "vault-update: sanitize failed — refusing to write raw session text" >&2
    exit 0
fi
NOW_FILE="$SAFE_FILE"   # everything below writes the SANITIZED text only

if command -v obsidian-cli &>/dev/null; then
    # Use obsidian-cli — creates or appends to today's session note
    CONTENT="$(cat "$NOW_FILE")"
    EXISTING="$NOTE_DIR/$NOTE_TITLE.md"

    if [[ ! -f "$EXISTING" ]]; then
        obsidian-cli create "$NOTE_TITLE" --content "# $NOTE_TITLE

$CONTENT

---

Related: [[Session Handoffs Index]] | [[Projects Index]]" 2>/dev/null \
            || printf '# %s\n\n%s\n\n---\n\nRelated: [[Session Handoffs Index]] | [[Projects Index]]\n' "$NOTE_TITLE" "$CONTENT" > "$EXISTING"
    else
        printf "\n---\n\n%s\n" "$CONTENT" >> "$EXISTING"
    fi
else
    # Fallback: direct file write
    SESSION_NOTE="$NOTE_DIR/$NOTE_TITLE.md"
    if [[ ! -f "$SESSION_NOTE" ]]; then
        { echo "# $NOTE_TITLE"; echo; cat "$NOW_FILE"; echo; echo "---"; echo; echo "Related: [[Session Handoffs Index]] | [[Projects Index]]"; } > "$SESSION_NOTE"
    else
        { echo; echo "---"; echo; cat "$NOW_FILE"; } >> "$SESSION_NOTE"
    fi
fi

# Best-effort: never fail the session-stop hook on a write hiccup.
exit 0
