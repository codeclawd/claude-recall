#!/usr/bin/env bash
#
# claude-recall installer — wires brain-recall.py into Claude Code as a
# UserPromptSubmit hook. Idempotent, backs up settings.json, never clobbers
# hooks you already have.
#
#   ./install.sh                       # interactive (asks for your vault)
#   ./install.sh --vault ~/notes       # non-interactive
#   ./install.sh --dry-run             # show what it would do
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"

VAULT=""; DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault) VAULT="$2"; shift;;
    --dry-run) DRY=1;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac; shift
done

if [[ -z "$VAULT" ]]; then
  read -r -p "Path to your notes/vault [$HOME/Documents/SecondBrain]: " ans || true
  VAULT="${ans:-$HOME/Documents/SecondBrain}"
fi
VAULT="${VAULT/#\~/$HOME}"

CMD="CLAUDE_RECALL_VAULT=\"$VAULT\" python3 $HOOKS/brain-recall.py"
echo "vault : $VAULT"
echo "hook  : $CMD"

if [[ $DRY -eq 1 ]]; then
  echo "[dry-run] would copy brain-recall.py -> $HOOKS/ and add the UserPromptSubmit hook above."
  exit 0
fi

mkdir -p "$HOOKS"
cp "$HERE/brain-recall.py" "$HOOKS/brain-recall.py"

python3 - "$SETTINGS" "$CMD" <<'PY'
import json, os, sys, datetime
path, cmd = sys.argv[1], sys.argv[2]
try:
    s = json.load(open(path))
except FileNotFoundError:
    s = {}
hooks = s.setdefault("hooks", {})
ups = hooks.setdefault("UserPromptSubmit", [])
# already wired (any brain-recall.py entry)? replace it so the vault stays current.
for e in ups:
    e["hooks"] = [h for h in e.get("hooks", []) if "brain-recall.py" not in h.get("command", "")]
ups[:] = [e for e in ups if e.get("hooks")]
ups.append({"hooks": [{"type": "command", "command": cmd}]})
if os.path.exists(path):
    bak = f"{path}.bak.{datetime.datetime.now():%Y%m%d-%H%M%S}"
    json.dump(json.load(open(path)), open(bak, "w"), indent=2)
    print(f"backed up -> {bak}")
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(s, open(path, "w"), indent=2); open(path, "a").write("\n")
print("wired UserPromptSubmit -> brain-recall.py")
PY

echo
echo "Done. Restart Claude Code so the hook loads."
echo "Test it:  echo '{\"prompt\":\"what did we decide about X\"}' | CLAUDE_RECALL_VAULT=\"$VAULT\" python3 $HOOKS/brain-recall.py"
