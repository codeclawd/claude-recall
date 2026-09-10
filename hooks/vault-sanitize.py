#!/usr/bin/env python3
"""vault-sanitize — filter session text before it is written into the vault.

WHY
---
`vault-update.sh` (Stop hook) appends `~/.remember/now.md` VERBATIM into
`daily-notes/Session <date>.md` every session — no filter, no cap. Two problems:

1. SECRETS. The vault is a durable, git-tracked, iCloud-syncable store. A key that
   lands there is exfiltrated the moment the vault is synced/backed up/shared, and
   it persists in git history after deletion. House rule: record credential
   LOCATIONS, never values. (Scanned 2026-07-16: no secrets in the vault yet — this
   guard is preventive, so keep it that way.)

2. MEMORY POISONING (OWASP Agentic AI ASI06 — "poison once, exploit forever").
   Daily notes are re-read on resume and surfaced by the brain-recall hook. Any
   instruction-shaped text that lands here gets replayed into future context as if
   it were trusted memory. A session that merely QUOTES an injection attempt (or a
   harness control tag) would otherwise persist it verbatim, forever.

Defanging, not deleting: content is preserved and marked, so provenance survives
and a human can still see what was there. This filter never silently drops a note.

Usage:  cat now.md | python3 vault-sanitize.py   ->  sanitized text on stdout
"""
import sys, re

MAX_BYTES = 40_000        # a session note larger than this is a paste accident

SECRETS = [
    ("GROQ_KEY",     re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    # ANTHROPIC first: the OPENAI pattern also matches sk-ant-* and would
    # otherwise claim the hit, mislabelling which provider's key leaked.
    ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OPENAI_KEY",   re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("SLACK_TOKEN",  re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("AWS_KEY",      re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("JWT",          re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*")),
    ("PRIVATE_KEY",  re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("BEARER",       re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{25,}")),
    ("DB_URL_PW",    re.compile(r"(?i)\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:/@]+:[^\s@]{6,}@")),
    ("GENERIC_ASSIGN", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|passwd|password)\s*[:=]\s*['\"]?([A-Za-z0-9/\+_-]{16,})['\"]?")),
]

# Harness/control tags: if replayed out of a note they read as live instructions.
CONTROL = re.compile(
    r"</?(system-reminder|task-notification|teammate-message|function_results|"
    r"local-command-[a-z]+|command-name|persisted-output)\s*>", re.I)

# Instruction-shaped text aimed at a future model reading this note.
INJECTION = re.compile(
    r"(?i)(ignore (all )?(previous|prior|above) instructions|"
    r"disregard (the )?(above|previous)|"
    r"you are now [a-z]|new instructions:|"
    r"system prompt:|override (your|the) (rules|instructions))")


def sanitize(text):
    notes = []

    if len(text.encode()) > MAX_BYTES:
        text = text.encode()[:MAX_BYTES].decode("utf-8", "ignore")
        notes.append(f"truncated to {MAX_BYTES} bytes")

    for label, pat in SECRETS:
        if label == "GENERIC_ASSIGN":
            def _g(m):
                return f"{m.group(1)}=[REDACTED:{label}]"
            text, n = pat.subn(_g, text)
        else:
            text, n = pat.subn(f"[REDACTED:{label}]", text)
        if n:
            notes.append(f"{n}x {label} redacted")

    text, n = CONTROL.subn(lambda m: "`" + m.group(0) + "`", text)
    if n:
        notes.append(f"{n}x control tag defanged")

    text, n = INJECTION.subn(lambda m: f"[DEFANGED-INJECTION: {m.group(0)}]", text)
    if n:
        notes.append(f"{n}x injection-shaped phrase defanged")

    if notes:
        text += ("\n\n> [!warning] vault-sanitize: " + "; ".join(notes) +
                 ". Content was defanged, not deleted — see vault-sanitize.py\n")
    return text


def main():
    data = sys.stdin.read()
    sys.stdout.write(sanitize(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
