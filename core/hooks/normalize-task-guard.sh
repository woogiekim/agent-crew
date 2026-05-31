#!/usr/bin/env bash
# normalize-task-guard.sh
# PreToolUse[Agent|Task] hook — defence-in-depth enforcement of the
# input-normalization contract documented in core/rules/normalization-adapter.md
# and core/rules/korean-input.md.
#
# Blocks any Agent/Task tool call whose prompt carries raw non-English
# (Hangul) content inside a TASK:/REQUIREMENTS: slot WITHOUT a matching
# NORMALIZED_TASK: provenance line. The canonical AI-agnostic enforcement
# remains the instruction/rule files themselves; this hook is one
# capability-gated implementation that runs on Claude.
#
# Exemptions:
#   - subagent_type == input-normalizer or korean-normalizer
#   - any prompt body whose first ~400 chars name those agents
#   - AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=1 environment override
#
# Exit codes (Claude Code PreToolUse contract):
#   0  — allow (no block decision)
#   2  — block (Claude sees the reason and the tool call is cancelled)
#
# See also: core/rules/normalization-adapter.md (canonical contract),
# core/rules/korean-input.md (Hangul rule), tests/shell/test_normalize_task_guard.bash.

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json
import os
import re
import sys

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

def allow():
    sys.exit(0)

def block(reason):
    payload = {"decision": "block", "reason": reason}
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)
    sys.exit(2)

try:
    data = json.loads(raw_input)
except Exception:
    allow()

tool_name = data.get("tool_name", "")
if tool_name not in ("Agent", "Task"):
    allow()

tool_input = data.get("tool_input", {}) or {}
prompt = ""
if isinstance(tool_input, dict):
    prompt = tool_input.get("prompt") or ""
if not isinstance(prompt, str) or not prompt.strip():
    allow()

# Escape hatch: explicit env override.
if os.environ.get("AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK", "").strip() == "1":
    allow()

# Exemption: the normalizer agents themselves legitimately receive raw input.
EXEMPT_AGENTS = {"input-normalizer", "korean-normalizer"}
subagent_type = ""
if isinstance(tool_input, dict):
    subagent_type = (tool_input.get("subagent_type") or "").strip().lower()
if subagent_type in EXEMPT_AGENTS:
    allow()

# Also recognize the exemption when the prompt body explicitly names the agent
# (host adapters sometimes pass the agent definition inline rather than via
# subagent_type, e.g. for custom-agent dispatch).
PROMPT_HEAD = prompt[:800].lower()
for name in EXEMPT_AGENTS:
    # Match "input-normalizer" or "input_normalizer" or "input normalizer"
    pat = re.compile(r"\b" + re.escape(name).replace(r"\-", r"[-_ ]") + r"\b")
    if pat.search(PROMPT_HEAD):
        allow()

# Hangul detection: U+AC00-U+D7A3 (precomposed syllables),
# U+1100-U+11FF (Jamo), U+3130-U+318F (Compatibility Jamo).
HANGUL_RE = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")

# Identify TASK: / REQUIREMENTS: slots. The contract is that the slot starts
# at the beginning of a line (optionally after a leading "- " bullet or
# whitespace) with the literal token followed by a colon.
SLOT_RE = re.compile(
    r"(?im)^[ \t\-*]*(?P<slot>TASK|REQUIREMENTS|CHANGE\s+REQUEST)\s*:\s*(?P<body>.*)$"
)

# Provenance pair: if NORMALIZED_TASK: appears anywhere in the prompt, the
# author has already produced the audit-artifact form. The hook trusts that
# pairing and allows the call. The audit artifact itself (normalized_task.md)
# is enforced by core/commands/run.md Step 1 and core/commands/agent.md Step 5.
HAS_NORMALIZED_TASK = bool(
    re.search(r"(?im)^[ \t\-*]*NORMALIZED_TASK\s*:", prompt)
)

violations = []
for match in SLOT_RE.finditer(prompt):
    slot = match.group("slot").upper().replace(" ", "_")
    body = match.group("body") or ""
    # Allow REQUIREMENTS: | (heredoc marker with no inline body) — the
    # downstream lines are themselves separate keys; the Hangul check still
    # runs across the whole prompt below, so a Korean nested value will be
    # caught by the multi-line scan.
    if HANGUL_RE.search(body):
        violations.append((slot, body.strip()[:120]))

# Multi-line scan: catch nested YAML-style REQUIREMENTS blocks where the
# Korean lives on continuation lines (indented under "REQUIREMENTS: |").
in_req_block = False
for line in prompt.splitlines():
    stripped = line.rstrip()
    head = re.match(r"^[ \t\-*]*(TASK|REQUIREMENTS|CHANGE\s+REQUEST)\s*:", stripped, re.IGNORECASE)
    if head:
        in_req_block = head.group(1).upper().startswith(("REQUIREMENTS", "CHANGE"))
        continue
    if in_req_block:
        # Stop the block when an unindented, non-empty line appears
        if stripped and not (line.startswith(" ") or line.startswith("\t")):
            in_req_block = False
            continue
        if HANGUL_RE.search(line):
            violations.append(("REQUIREMENTS_BODY", line.strip()[:120]))

if not violations:
    allow()

# If the author already supplied a NORMALIZED_TASK: provenance line, treat
# the call as compliant with the audit-artifact contract and allow it.
if HAS_NORMALIZED_TASK:
    allow()

# Compose the block reason. Reference the canonical rule and the audit
# artifact so the agent / operator knows exactly how to remediate.
slots = ", ".join(sorted({slot for slot, _ in violations}))
reason = (
    "[agent-crew] normalize-task-guard blocked — raw non-English (Hangul) "
    f"content detected in {slots} slot(s) of the Agent/Task prompt.\n\n"
    "Input normalization must occur BEFORE any host AI is asked the question. "
    "This is an AI-agnostic contract — see core/rules/normalization-adapter.md "
    "and core/rules/korean-input.md.\n\n"
    "Remediation:\n"
    "  1. Run the input-normalizer agent (or the inline equivalent in "
    "core/commands/run.md Step 1 / core/commands/agent.md Step 5).\n"
    "  2. Write the audit artifact to "
    "{TASK_DIR}/context/normalized_task.md (or "
    "~/.agent-crew/state/{PROJECT_NAME}/normalized-tasks/{ts}.md when no "
    "TASK_DIR exists) with both RAW_INPUT and NORMALIZED_TASK fields.\n"
    "  3. Pass NORMALIZED_TASK (English) downstream — never the raw input.\n\n"
    "Escape hatch (use only when normalization has happened upstream and the "
    "host stream has not yet been updated): set "
    "AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=1 in the environment."
)
block(reason)
PYEOF
