#!/usr/bin/env bash
# seed-instruction-rules.sh — Reconciles the repository-owned runtime command
# rules and bootstraps missing instruction rules into the canonical mnemos
# global layer. Existing non-runtime rules remain owned by mnemos and are never
# overwritten by bootstrap mode.
#
# Usage:
#   bash core/scripts/seed-instruction-rules.sh            # runtime rules
#   bash core/scripts/seed-instruction-rules.sh --dry-run  # report only
#   bash core/scripts/seed-instruction-rules.sh --apply \
#     --profile runtime-command-surface                    # selected rules
#   bash core/scripts/seed-instruction-rules.sh --apply \
#     --profile bootstrap-missing                          # create only
#
# Environment:
#   MNEMOS_BIN   path to mnemos CLI (default: ~/.local/bin/mnemos)
#
# Exit codes:
#   0  success (all rules captured/updated/skipped cleanly)
#   1  mnemos CLI not found
#   2  one or more rule operations failed

set -u

MNEMOS_BIN="${MNEMOS_BIN:-${HOME}/.local/bin/mnemos}"
MODE="--apply"
PROFILE="runtime-command-surface"

usage() {
  echo "usage: $0 [--apply|--dry-run] [--profile runtime-command-surface|bootstrap-missing]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply|--dry-run)
      MODE="$1"
      shift
      ;;
    --profile)
      if [ "$#" -lt 2 ]; then
        usage
        exit 2
      fi
      PROFILE="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

case "${PROFILE}" in
  runtime-command-surface|bootstrap-missing) ;;
  all)
    echo "seed-instruction-rules: profile 'all' is deprecated; using bootstrap-missing" >&2
    PROFILE="bootstrap-missing"
    ;;
  *)
    echo "seed-instruction-rules: unknown profile: ${PROFILE}" >&2
    exit 2
    ;;
esac

if [ ! -x "${MNEMOS_BIN}" ]; then
  echo "ERROR: mnemos CLI not found or not executable at: ${MNEMOS_BIN}" >&2
  echo "       Set MNEMOS_BIN to override." >&2
  exit 1
fi

MNEMOS_READ_JSON=0
if "${MNEMOS_BIN}" capabilities --json 2>/dev/null | python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(1)
caps = payload.get("capabilities") or {}
sys.exit(0 if caps.get("read_json") is True else 1)
' >/dev/null 2>&1; then
  MNEMOS_READ_JSON=1
fi

TAG="instruction-rule"
LAYER="global"

CREATED=0
UPDATED=0
SKIPPED=0
FAILED=0

rule_selected() {
  local id="$1"

  if [ "${PROFILE}" = "bootstrap-missing" ]; then
    return 0
  fi

  case "${id}" in
    rule:no-direct-implementation|\
    rule:agent-routing-criteria|\
    rule:codex-routing-fallback|\
    rule:current-session-fallback|\
    rule:workflow-intents)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# capture_rule <id> <priority> <body-variable-name>
#   Runtime command mode captures missing rules and edits drift. Bootstrap mode
#   captures missing rules but preserves every existing canonical mnemos item.
#   The body is passed by name (indirect expansion) so heredoc-defined
#   variables holding multi-line content with backticks / $() / quotes
#   round-trip cleanly under bash 3.2 (avoids the "$(cat <<'EOF' ...)"
#   double-quoted command-substitution heredoc pitfall).
capture_rule() {
  local id="$1" prio="$2" varname="$3"
  local body="${!varname}"

  rule_selected "${id}" || return 0

  local current
  if [ "${MNEMOS_READ_JSON}" = "1" ]; then
    current="$("${MNEMOS_BIN}" read --json "${id}" 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("content", ""), end="")
except Exception:
    print("__MISSING__", end="")
' 2>/dev/null)"
    if [ "${current}" = "__MISSING__" ]; then
      current="$("${MNEMOS_BIN}" read "${id}" 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("content", ""), end="")
except Exception:
    print("__MISSING__", end="")
' 2>/dev/null)"
    fi
  else
    current="$("${MNEMOS_BIN}" read "${id}" 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("content", ""), end="")
except Exception:
    print("__MISSING__", end="")
' 2>/dev/null)"
  fi

  if [ "${current}" = "__MISSING__" ] || [ -z "${current}" ]; then
    echo "  + CREATE ${id} (priority=${prio}, ${#body} bytes)"
    if [ "${MODE}" = "--apply" ]; then
      if "${MNEMOS_BIN}" capture --layer "${LAYER}" --id "${id}" \
                       --tag "${TAG}" --content "${body}" --quiet >/dev/null 2>&1; then
        CREATED=$((CREATED + 1))
      else
        echo "    FAIL: capture returned non-zero for ${id}" >&2
        FAILED=$((FAILED + 1))
      fi
    else
      CREATED=$((CREATED + 1))
    fi
  elif [ "${current}" = "${body}" ]; then
    echo "  = SKIP   ${id} (unchanged)"
    SKIPPED=$((SKIPPED + 1))
  elif [ "${PROFILE}" = "bootstrap-missing" ]; then
    echo "  = PRESERVE ${id} (existing canonical rule)"
    SKIPPED=$((SKIPPED + 1))
  else
    echo "  ~ UPDATE ${id} (content drift detected)"
    if [ "${MODE}" = "--apply" ]; then
      if "${MNEMOS_BIN}" edit "${id}" --content "${body}" >/dev/null 2>&1; then
        UPDATED=$((UPDATED + 1))
      else
        echo "    FAIL: edit returned non-zero for ${id}" >&2
        FAILED=$((FAILED + 1))
      fi
    else
      UPDATED=$((UPDATED + 1))
    fi
  fi
}

echo "[seed-instruction-rules] mode=${MODE} profile=${PROFILE} mnemos=${MNEMOS_BIN}"
echo ""

# --- rule:raw-input-preservation ------------------------------------------
read -r -d '' BODY_INPUT_LANGUAGE <<'RULE_EOF' || true
---
title: Raw Input Preservation
applies_to: [all]
priority: 10
---

Preserve the user's task text as an immutable Root Input Snapshot. The system
must not translate, summarize, normalize, correct, or rewrite it before
candidate resolution, planning, handoff, or execution. Deterministic parsing may
split the explicit command and options, resolve declared aliases, and add
derived fields such as `language`, but it never replaces `rawInput`.

Agents and Tasks consume the original language directly. Translation is allowed
only when translation is the explicit Task. New executions do not create or
consume legacy normalization artifacts.
RULE_EOF
capture_rule "rule:input-language" 10 BODY_INPUT_LANGUAGE

# --- rule:output-language -------------------------------------------------
read -r -d '' BODY_OUTPUT_LANGUAGE <<'RULE_EOF' || true
---
title: Output Language
applies_to: [claude]
priority: 20
---

User-facing narrative follows the user's language and defaults to Korean on
this machine. Parser-required tokens such as `STATUS:`, `PLAN:`, `BLOCKER:`,
`REVIEW:`, enum values, commands, paths, and code identifiers remain in their
defined form. Never change the stored Root Input Snapshot to satisfy an output
language preference.
RULE_EOF
capture_rule "rule:output-language" 20 BODY_OUTPUT_LANGUAGE

# --- rule:explicit-execution-entry ----------------------------------------
read -r -d '' BODY_NO_DIRECT_IMPL <<'RULE_EOF' || true
---
title: Explicit Execution Entry
applies_to: [all]
priority: 30
---

Agent Crew never infers execution intent from plain conversation. Ordinary
natural-language input must not start an Agent, LLM router, hidden Tool, or
implementation pipeline.

The user chooses the execution boundary with an explicit command:

- `crew run` / `crew:run` / `$crew:run` for supervised task execution
- `crew agent` / `crew:agent` / `$crew:agent` for direct Agent execution

The current native runtime does not expose `crew task`, `crew workflow`, or
`standalone`. Do not advertise, infer, or select those unavailable commands.
Management commands do not start execution.
RULE_EOF
capture_rule "rule:no-direct-implementation" 30 BODY_NO_DIRECT_IMPL

# --- rule:run-and-agent-boundaries ----------------------------------------
read -r -d '' BODY_AGENT_ROUTING <<'RULE_EOF' || true
---
title: Run And Agent Boundaries
applies_to: [all]
priority: 40
---

`crew run` is the supervised execution entry. One task creates one supervisor
handoff; multiple explicit task arguments may create parallel supervisor
handoffs with the declared barrier and result handling from `run.md`.

`crew agent` is the direct-Agent entry. It uses the selected Agent and its
declared sequential child graph. It must not be silently converted into
`crew run`, and neither entry may invent an unavailable `crew task` or
`crew workflow` command.
RULE_EOF
capture_rule "rule:agent-routing-criteria" 40 BODY_AGENT_ROUTING

# --- rule:candidate-and-registry-boundaries -------------------------------
read -r -d '' BODY_PARALLEL_FIRST <<'RULE_EOF' || true
---
title: Candidate And Registry Boundaries
applies_to: [all]
priority: 50
---

Candidate search is restricted to the explicitly named Registry. Zero
candidates never creates a definition. Multiple candidates, fuzzy or
LLM-recommended candidates, low metadata coverage, and resolver conflicts
require Candidate Selection. Candidate Selection is separate from Execution
Approval and must not start work.
RULE_EOF
capture_rule "rule:parallel-first" 50 BODY_PARALLEL_FIRST

# --- rule:hidden-routing-prohibition --------------------------------------
read -r -d '' BODY_AUTO_EXEC <<'RULE_EOF' || true
---
title: Hidden Routing Prohibition
applies_to: [all]
priority: 60
---

No lifecycle hook, prompt preprocessor, injected directive, or host wrapper may
start a Workflow, Task, Agent, LLM router, or hidden Tool. It must not alter
input meaning, expand scope, create definitions, or persist Agent, Skill, or
Memory changes. Technical hooks are limited to deterministic dangerous-command
protection, bounded cost/tool telemetry, and cleanup.
RULE_EOF
capture_rule "rule:auto-execution-triggers" 60 BODY_AUTO_EXEC

# --- rule:code-style-context-breaks ---------------------------------------
read -r -d '' BODY_CODE_STYLE_CONTEXT_BREAKS <<'RULE_EOF' || true
---
title: Code Style Context Breaks
applies_to: [all]
priority: 65
---

Frontend and backend agents must preserve code readability by inserting a line
break when the implementation context changes.

Treat transitions between setup, validation, transformation, side effects,
rendering or return values, error handling, and reporting as context changes.
Do not reformat unrelated code solely to add spacing; apply this rule to code
the agent writes or directly touches.
RULE_EOF
capture_rule "rule:code-style-context-breaks" 65 BODY_CODE_STYLE_CONTEXT_BREAKS

# --- rule:codex-routing-fallback (codex-only) -----------------------------
read -r -d '' BODY_CODEX_ROUTING <<'RULE_EOF' || true
---
title: Codex Routing Fallback
applies_to: [codex]
priority: 70
section: Auto-Execution Triggers
---

Codex lifecycle hooks can require trust review and may inject only advisory
context. Therefore, the Codex adapter installs explicit `crew:<intent>` skills
as host-specific command adapters.

When running in Codex, do not infer a `crew:run` or `crew:agent` wrapper from
natural language. Use the wrapper only when the user explicitly invokes it.

If the user explicitly invoked another Codex skill, preserve that explicit
context as task input for requirements collection, supervisor handoffs, and
generated prompts. Do not auto-load non-agent-crew host/plugin skills merely
because their descriptions appear to match the task.
Domain-match alone is not approval to load external host/plugin skills.
Non-agent-crew host/plugin skills require explicit user approval under the provider-neutral external skill boundary below.

When a Codex `crew:run` handoff returns `HOST_BRIDGE: current_session_required`,
apply the provider-neutral Current-Session Fallback rule. The Codex session is
only replacing the nested host bridge; it is not an exemption from agent,
subagent, skill, TDD, reviewer, or repair evidence requirements.
RULE_EOF
capture_rule "rule:codex-routing-fallback" 70 BODY_CODEX_ROUTING

# --- rule:current-session-fallback ----------------------------------------
read -r -d '' BODY_CURRENT_SESSION_FALLBACK <<'RULE_EOF' || true
---
title: Current-Session Fallback
applies_to: [all]
priority: 75
section: Auto-Execution Triggers
---

When an explicit `crew run` or `crew agent` handoff returns
`HOST_BRIDGE: current_session_required`, or the operator continues that handoff
manually in the current host session, the session replaces only the nested
bridge. It must execute the already pinned plan, original Root Input Snapshot,
declared Agent/Tool graph, permissions, and versions. It cannot re-resolve candidates,
add execution nodes, widen scope, or bypass approval.

Before acting, load the applicable skill files and record the exact loaded skill
path(s) in `{TASK_DIR}/context/skill-load.md` or
`{TASK_DIR}/context/skill-load.json` when available. Every `selected_skill` /
`selected_skills` entry should have matching load coverage (for example,
`selected_skill: frontend-typescript-react` maps to
`frontend-typescript-react.md`, and `selected_skill: tdd` maps to `tdd.md`).
Automatically loaded skills must come from agent-crew system/user skill
locations or the active host's agent-crew mirrors. Do not auto-load unrelated
host/plugin skills by description match. If a non-agent-crew host/plugin skill
is genuinely needed, ask the user first and record approval in
`{TASK_DIR}/context/external-skill-approval.md` or `.json`. Completion/repair
for a current-session fallback reports missing or incomplete skill-load coverage
as advisory gaps and still rejects unapproved external skill loads.

Optional skill-use notes may be recorded in
`{TASK_DIR}/context/skill-use.json` or `{TASK_DIR}/context/skill-use.md`, but
they are diagnostic coverage, not required proof artifacts. TDD and other
loaded skills are covered first by real task outcomes, tests, diffs, reviews,
pipeline/progress state, reviewer quality metrics, and tool events. Phase notes
such as red/green/refactor files may improve auditability, but missing or
incomplete notes must be reported as advisory gaps for standard-risk work, not
completion blockers.

Optional operational understanding notes may be recorded in
`{TASK_DIR}/context/skill-plan.json` or `{TASK_DIR}/context/skill-plan.md` and
linked from `rule_evidence` in `context/skill-use.json`, but these notes are
diagnostic coverage only. Completion/repair for a mutating current-session
fallback must not require separate skill-plan or rule-evidence artifacts when
the actual task outcomes, tests, diffs, reviews, or tool events are sufficient;
missing notes should be surfaced as advisory gaps.

For implementation or production-code mutation work, the same fallback must not
bypass the full TDD Red → Green → Refactor cycle. Before production-code
mutation, identify the focused test target, add or update the test, and run it;
if no runnable harness or red failure can reasonably be produced, make the
exception explicit before implementation. After green, perform the refactor
review or document a no-op refactor decision and rerun focused verification.
Completion/repair for production-code implementation may reject missing runtime
quality-loop outcomes or high-risk hard blockers, but standard-risk missing
phase-note artifacts are coverage gaps rather than proof-file requirements.

This fallback must depend on the provider-neutral command definitions under
`~/.agent-crew/commands/`. Do not embed supervisor, planner, backend, frontend,
resolver, or approval behavior in Codex-specific hooks or skills.
RULE_EOF
capture_rule "rule:current-session-fallback" 75 BODY_CURRENT_SESSION_FALLBACK

# --- rule:technical-hook-boundary -----------------------------------------
read -r -d '' BODY_STOP <<'RULE_EOF' || true
---
title: Technical Hook Boundary
applies_to: [all]
priority: 80
---

Technical lifecycle hooks may protect dangerous commands, record bounded cost
or tool metadata, and perform cleanup. They must be deterministic, bounded,
traceable, and fail in a documented way. They cannot invoke an LLM or Agent,
select a definition, modify user meaning, duplicate the full context, or create
formal verification artifacts.
RULE_EOF
capture_rule "rule:stop-directive" 80 BODY_STOP

# --- rule:explicit-scope-boundary -----------------------------------------
read -r -d '' BODY_ROUTE <<'RULE_EOF' || true
---
title: Explicit Scope Boundary
applies_to: [all]
priority: 85
---

An explicit command selects exactly one logical Registry. Imported command or
skill origin does not determine the repository, module, endpoint, or contract
to change. Resolve work scope from explicit request and contract evidence, pin
it in the Execution Plan, and request a new plan before any scope expansion.
RULE_EOF
capture_rule "rule:route-directive" 85 BODY_ROUTE

# --- rule:workflow-intents ------------------------------------------------
read -r -d '' BODY_WORKFLOW_INTENTS <<'RULE_EOF' || true
---
title: Workflow Intents
applies_to: [all]
priority: 90
---

### Explicit Command Invocation Rule

`crew:<intent>` is workflow notation used in prompts and host adapter guidance.
The native shell CLI uses space-separated commands.
`crew run` is the native CLI execution entry for supervised work, and
`crew agent` is the native direct-Agent entry. Codex uses `$crew:run` and
`$crew:agent`; Claude Code uses `/crew:run` and `/crew:agent`.

The current runtime does not expose `crew task` or `crew workflow`. Do not
translate `crew:run` into either unavailable command, and do not describe
`crew:run` as deprecated or as compatibility-only candidate resolution.

When the user's message begins with a workflow command such as `crew:run`,
`crew:setup`, `crew:status`, `crew:cost`, or `crew:agent-maker`,
treat it as an explicit command invocation, not as ordinary natural language.
Codex wrapper forms at the beginning of the message, such as `$crew:run`,
`$crew:agent`, `$crew:status`, `$crew:update`, `$crew:smm`, `$crew:setup`,
`$crew:cost`, and `$crew:agent-maker`, are the same kind of explicit command
invocation. The text after a leading `$crew:run` is the task description; only
treat `$crew:run` as the review target when the prompt explicitly names the
skill, wrapper, file, or `SKILL.md` as the object.

For `crew:run` specifically:

- Execute the workflow defined in `~/.agent-crew/commands/run.md`.
- Do not reinterpret bare `crew:run` as "run standard verification", "run CI",
  "summarize the project", or any other host-default task.
- If no task argument is provided, follow Step 1 of the command definition and
  ask for the task description through the host structured input UI.
- If task arguments are provided, use them as the task descriptions and continue
  through requirements collection and supervisor delegation.

For `crew:setup` specifically:

- Execute the workflow defined in `~/.agent-crew/commands/setup.md`.
- Do not reinterpret it as a request to inspect the repository, inspect Gradle or
  package files, run verification, or infer project setup manually.
- Run the host adapter setup flow and initialize agent-crew state exactly as the
  command definition says.

| Intent | Meaning |
|---|---|
| `crew:setup` | Install the current host adapter and initialize the project workspace |
| `crew:run` | Canonical workflow entry point for one or more tasks |
| `crew:cost` | Show the session cost summary |
| `crew:agent-maker` | Design and register a custom agent |
| `crew:sync-instructions` | Re-assemble host AI md files from mnemos rules |
| `$crew:run` | Codex wrapper for `crew:run` |
| `$crew:agent` | Codex wrapper for `crew:agent` |
| `$crew:status` | Codex wrapper for `crew:status` |
| `$crew:update` | Codex wrapper for `crew:update` |
| `$crew:smm` | Codex wrapper for `crew:smm` |
| `$crew:setup` | Codex wrapper for `crew:setup` |
| `$crew:cost` | Codex wrapper for `crew:cost` |
| `$crew:agent-maker` | Codex wrapper for `crew:agent-maker` |

Use `crew:<intent>` as the default invocation style.

Project state is stored under:

```text
~/.agent-crew/state/{PROJECT_STATE_KEY}/tasks/{TASK_ID}
```
RULE_EOF
capture_rule "rule:workflow-intents" 90 BODY_WORKFLOW_INTENTS

# --- rule:structured-choice -----------------------------------------------
read -r -d '' BODY_STRUCTURED_CHOICE <<'RULE_EOF' || true
---
title: Structured Choice Rules
applies_to: [all]
priority: 100
---

Use the host AI tool's structured choice UI when confirmation is required.
Do not add duplicate free-form options if the host UI already provides one.
RULE_EOF
capture_rule "rule:structured-choice" 100 BODY_STRUCTURED_CHOICE

# --- rule:approval-gate ---------------------------------------------------
read -r -d '' BODY_APPROVAL_GATE <<'RULE_EOF' || true
---
title: Approval Rule (Framework-Level)
applies_to: [all]
priority: 110
---

Candidate Selection and Execution Approval are distinct decisions owned by the
Approval Service. Exact deterministic single safe Workflow/Task candidates may
skip approval only after final plan risk assessment. Multiple, fuzzy,
LLM-recommended, low-coverage, or conflicting candidates require selection.
Every direct Agent execution requires approval.

High-cost, destructive, external-write, deployment, push, merge, release,
credential, permission, broad-scope, and hard-to-reverse plans always require
approval. Approval binds definition and Agent versions, Host and installed
asset fingerprints, Root Input Snapshot, execution graph, permissions, Tools,
repository revisions, side effects, cost/risk, and canonical Plan Hash. Any
bound-field change invalidates the decision.

Use a structured host decision surface, structured markdown fallback, or a
strict PREAPPROVED manifest. Headless ambiguity fails immediately instead of
hanging or defaulting to approval.
RULE_EOF
capture_rule "rule:approval-gate" 110 BODY_APPROVAL_GATE

# --- rule:subagent-plan-approval ------------------------------------------
read -r -d '' BODY_SUBAGENT_PLAN <<'RULE_EOF' || true
---
title: Risky Action Execution Rule
applies_to: [all]
priority: 120
---

An Agent that encounters an unapproved destructive or external-write action
must stop and return the proposed action, scope, risk, reversibility, and
compensation needs to the Approval Service. It must not ask a duplicate
free-form question, poll an unrelated file, self-approve, or execute before the
recorded decision. A scope or graph change creates a new Execution Plan.
RULE_EOF
capture_rule "rule:subagent-plan-approval" 120 BODY_SUBAGENT_PLAN

# NOTE: rule:mnemos-capture is INTENTIONALLY NOT seeded here. The mnemos
# "Memory" section in ~/.claude/CLAUDE.md is managed by the mnemos installer
# itself (via the <!-- mnemos-start --> / <!-- mnemos-end --> marker pair —
# a separate, mnemos-owned marker that is independent of
# <!-- agent-crew-start --> / <!-- agent-crew-end -->). If we also seeded
# the mnemos capture rule, the agent-crew sync would write a duplicate
# copy inside the agent-crew block, and Claude would receive the same
# guidance twice. See core/docs/ssot-rule-inventory.md for the policy.

echo ""
echo "[seed-instruction-rules] done. created=${CREATED} updated=${UPDATED} skipped=${SKIPPED} failed=${FAILED}"

if [ "${FAILED}" -gt 0 ]; then
  exit 2
fi
exit 0
