#!/usr/bin/env bash
# seed-instruction-rules.sh — Idempotent seeder for the agent-crew instruction
# SSOT. Captures each rule into the mnemos global layer with id
# `rule:<slug>` and tag `instruction-rule`. Subsequent runs detect
# unchanged content and skip writes (no churn).
#
# Usage:
#   bash core/scripts/seed-instruction-rules.sh            # default: --apply
#   bash core/scripts/seed-instruction-rules.sh --dry-run  # report only
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
MODE="${1:---apply}"
case "${MODE}" in
  --apply|--dry-run) ;;
  *) echo "usage: $0 [--apply|--dry-run]" >&2; exit 2 ;;
esac

if [ ! -x "${MNEMOS_BIN}" ]; then
  echo "ERROR: mnemos CLI not found or not executable at: ${MNEMOS_BIN}" >&2
  echo "       Set MNEMOS_BIN to override." >&2
  exit 1
fi

TAG="instruction-rule"
LAYER="global"

CREATED=0
UPDATED=0
SKIPPED=0
FAILED=0

# capture_rule <id> <priority> <body-variable-name>
#   Compares against current mnemos content; captures or edits only on drift.
#   The body is passed by name (indirect expansion) so heredoc-defined
#   variables holding multi-line content with backticks / $() / quotes
#   round-trip cleanly under bash 3.2 (avoids the "$(cat <<'EOF' ...)"
#   double-quoted command-substitution heredoc pitfall).
capture_rule() {
  local id="$1" prio="$2" varname="$3"
  local body="${!varname}"

  local current
  current="$("${MNEMOS_BIN}" read "${id}" 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("content", ""), end="")
except Exception:
    print("__MISSING__", end="")
' 2>/dev/null)"

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

echo "[seed-instruction-rules] mode=${MODE} mnemos=${MNEMOS_BIN}"
echo ""

# --- rule:input-language --------------------------------------------------
read -r -d '' BODY_INPUT_LANGUAGE <<'RULE_EOF' || true
---
title: Input Language
applies_to: [all]
priority: 10
---

Task descriptions may arrive in Korean. Always apply the Korean Input
Normalization rule (`core/rules/korean-input.md`) before passing TASK to
any agent or writing it to pipeline state. Never pass raw Korean text
as a TASK description to downstream agents.
RULE_EOF
capture_rule "rule:input-language" 10 BODY_INPUT_LANGUAGE

# --- rule:output-language -------------------------------------------------
read -r -d '' BODY_OUTPUT_LANGUAGE <<'RULE_EOF' || true
---
title: Output Language
applies_to: [claude]
priority: 20
---

User-facing output should appear in the user's input language (Claude
follows the conversation's language naturally; other adapters mirror
this where possible). See `core/rules/output-language.md` for the full
rule, including the **English-only status invariant**: structured
tokens like `STATUS: completed`, `REVIEW: APPROVED`, `PLAN:`,
`BLOCKER:` are parsed by regex and MUST be returned in English
regardless of input language. Narrative around those tokens (the
explanation, description, report body) follows the user's language.

The two rules are paired: input is normalized to English for
**internal artifacts** (pipeline.json, register.json, handoff.md,
agent prompts), while output narrative is **NOT forced into English**
for the user-facing surface.
RULE_EOF
capture_rule "rule:output-language" 20 BODY_OUTPUT_LANGUAGE

# --- rule:no-direct-implementation ----------------------------------------
read -r -d '' BODY_NO_DIRECT_IMPL <<'RULE_EOF' || true
---
title: No Direct Implementation
applies_to: [all]
priority: 30
---

When a user requests coding, implementation, or development work, do not start
editing files or generating production code directly.

Always follow this sequence:

1. Classify the request.
2. Invoke the appropriate agent, skill, or workflow intent.
3. Perform implementation only after the required planning or delegated agent step.

This is a system behavior principle. It is not tied to a specific AI vendor.
Host adapters may expose different invocation methods, but the workflow intent
remains provider-neutral.
RULE_EOF
capture_rule "rule:no-direct-implementation" 30 BODY_NO_DIRECT_IMPL

# --- rule:agent-routing-criteria ------------------------------------------
read -r -d '' BODY_AGENT_ROUTING <<'RULE_EOF' || true
---
title: Agent Routing Criteria
applies_to: [all]
priority: 40
---

| Request Type | Execution Method |
|---|---|
| Backend API, domain logic, database work | `crew:run` → supervisor → backend |
| UI, full-stack, or implementation workflows | `crew:run` → supervisor → pipeline agents |
| Multiple independent features | `crew:run` with one supervisor per task |
| Requirements analysis only | `crew:run` → supervisor → planner (no implementation stages) |
RULE_EOF
capture_rule "rule:agent-routing-criteria" 40 BODY_AGENT_ROUTING

# --- rule:parallel-first --------------------------------------------------
read -r -d '' BODY_PARALLEL_FIRST <<'RULE_EOF' || true
---
title: Parallel-First Execution Rule
applies_to: [all]
priority: 50
---

**Default to parallel execution. Never serialize tasks to avoid merge conflicts.**

When a request contains multiple independent sub-tasks — even if they touch the
same files — run them as parallel supervisors:

```
crew:run "Sub-task A" | "Sub-task B" | "Sub-task C"
```

Merge conflicts that arise after parallel completion are resolved by the
**resolver agent**. That is its explicit purpose. Choosing sequential execution
to avoid conflicts is an incorrect optimization that sacrifices throughput for a
problem the resolver already solves.

**Sequential execution is only correct when:**
- Task B cannot start until Task A's output exists (true dependency)
- The tasks are logically a single atomic unit

File overlap alone is never a reason to serialize.
RULE_EOF
capture_rule "rule:parallel-first" 50 BODY_PARALLEL_FIRST

# --- rule:auto-execution-triggers (commit 011e6be content) ----------------
read -r -d '' BODY_AUTO_EXEC <<'RULE_EOF' || true
---
title: Auto-Execution Triggers
applies_to: [all]
priority: 60
---

> Requirements collection (Step 5 of `crew:run`) is always mandatory and must
> never be skipped, even when the request seems self-evident.

Spawn an agent or workflow when the user asks to build, implement, create, add,
update, fix, remove, move, change, migrate, refactor, replace, extend, or
integrate development work.

If the user gives a short confirmation such as "go", "yes", "ok", "continue",
or "proceed" and the prior context is about implementation work, continue
through the appropriate `crew:<intent>` workflow instead of answering directly.

For questions and explanations, route through `crew:agent` (auto-routing
selects analyst for codebase Q, historian for session/git/project state Q).
Direct inline response is permitted ONLY for trivial single-fact replies
(yes/no, file path lookup, single-number metric) AND when no agent in the
registry has the right scope.
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
context. Therefore, the Codex adapter also installs an `agent-crew` skill as a
host-specific routing adapter.

When running in Codex, if a natural-language implementation request matches the
Auto-Execution Triggers above, treat it exactly like:

```text
crew:run "{original request}"
```

This fallback must depend on the provider-neutral command definitions under
`~/.agent-crew/commands/`. Do not embed supervisor, planner, backend, frontend,
resolver, or approval behavior in Codex-specific hooks or skills.
RULE_EOF
capture_rule "rule:codex-routing-fallback" 70 BODY_CODEX_ROUTING

# --- rule:stop-directive --------------------------------------------------
read -r -d '' BODY_STOP <<'RULE_EOF' || true
---
title: STOP Directive Rule
applies_to: [all]
priority: 80
---

When `[agent-crew] STOP` appears anywhere in the system context (injected by
auto-route.sh), the **only permitted first action** is to invoke `crew:run`.

- Do NOT produce any diagnostic output or explanation before calling `crew:run`.
- Do NOT run any Bash command (including exploratory or read-only commands) before calling `crew:run`.
- Do NOT describe what you are about to do — call `crew:run` immediately.
- The STOP directive is authoritative. Treat it as a hard override of any other default behavior.

Violation examples (forbidden when STOP is present):
- Explaining why you need to call `crew:run`
- Reading files to "understand the request first"
- Running `git status` or any other preparatory command
- Asking the user clarifying questions before invoking `crew:run`
RULE_EOF
capture_rule "rule:stop-directive" 80 BODY_STOP

# --- rule:route-directive -------------------------------------------------
read -r -d '' BODY_ROUTE <<'RULE_EOF' || true
---
title: ROUTE Directive Rule
applies_to: [all]
priority: 85
---

When `[agent-crew] ROUTE` appears anywhere in the system context
(injected by auto-route.sh), the **only permitted action** is to
invoke `crew:agent` with the specified agent and question.

- Do NOT answer the question inline.
- Do NOT run any Bash command before calling `crew:agent`.
- Do NOT read files or gather data before calling `crew:agent`.
- The ROUTE directive is authoritative. Treat it as a hard override
  of any other default behavior.
- This rule applies even if the ROUTE directive arrives mid-execution
  (in a tool result system-reminder). Stop immediately and re-route.

Violation examples (forbidden when ROUTE is present):
- Answering the question directly without calling `crew:agent`
- Running `mnemos` commands or reading files to gather context first
- Continuing an in-progress response after ROUTE appears in a tool result
- Treating the ROUTE directive as advisory rather than mandatory
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

When the user's message begins with a workflow command such as `crew:run`,
`crew:setup`, `crew:status`, `crew:cost`, or `crew:agent-maker`,
treat it as an explicit command invocation, not as ordinary natural language.

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

Use `crew:<intent>` as the default invocation style.

Project state is stored under:

```text
~/.agent-crew/state/{PROJECT_NAME}/tasks/{TASK_ID}
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

### Centralized Approval Gate

All approval decisions for the following actions are owned exclusively by the
orchestrator (crew:run for N > 1, supervisor for N == 1):

- Merge (git merge)
- Push to remote (git push)
- Deployment (any deploy script or command)
- Destructive operations (delete, reset, overwrite)
- Branch cleanup (git branch -d / -D)

**Stage agents (devops, and any agent that performs destructive operations) MUST NOT
issue the host's interactive question mechanism for any of the above actions
(see `core/rules/capabilities/interactive-question.md`).** Instead, those agents must:

1. Write their planned actions to `{TASK_DIR}/context/action-plan.md`
2. Return a `PLAN:` block to the supervisor with the following fields:
   ```text
   PLAN:
     actions: {list of planned commands}
     risk: {none | low | medium | high}
     reversible: {yes | no}
   STATUS: plan_ready
   ```
3. Poll `{TASK_DIR}/context/approval.md` for `APPROVED` or `CANCELLED`
   (up to 60s timeout before reporting BLOCKED)
4. Execute only after receiving `APPROVED`; halt with STATUS: BLOCKED on
   `CANCELLED` or timeout

### Orchestrator Approval Gate

The orchestrator (crew:run or supervisor) issues the consolidated structured
user-choice intent (see `core/rules/capabilities/interactive-question.md`)
after collecting all PLAN blocks. This ensures:
- A single approval prompt regardless of how many stage agents need approval
- A consolidated view of all planned actions across all tasks (for N > 1)
- No duplicate or out-of-order approval dialogs

All structured user-choice calls (per `core/rules/capabilities/interactive-question.md`)
for these actions must include at minimum:
- header: action type (e.g., "Deploy", "Approve All Actions", "Merge", "Push", "Rollback")
- question: describing the specific action(s) with relevant details
- options: at minimum "Approve — proceed" and "Cancel — hold"

Plain-text approval requests ("Shall I?", "Should I?", "Do you want me to?")
are FORBIDDEN at every level of the system. Violating this rule is a workflow
consistency error.
RULE_EOF
capture_rule "rule:approval-gate" 110 BODY_APPROVAL_GATE

# --- rule:subagent-plan-approval ------------------------------------------
read -r -d '' BODY_SUBAGENT_PLAN <<'RULE_EOF' || true
---
title: Subagent Plan Approval Rule
applies_to: [all]
priority: 120
---

Stage agents that perform **destructive operations** (deploy, push, merge, overwrite,
or branch cleanup) must present a PLAN block for approval before executing. The planner,
backend, frontend, and designer agents are exempt — they commit code and return STATUS
directly without a PLAN gate.

**How plans flow depends on the agent type:**

### Destructive-action stage agents (devops, and any agent that deploys or pushes)

These agents write their plan to `{TASK_DIR}/context/action-plan.md` and return
a `PLAN:` block to the supervisor. They do NOT issue the host's interactive
question mechanism directly (see `core/rules/capabilities/interactive-question.md`).
The supervisor (or crew orchestrator for parallel runs) owns the approval gate.

PLAN block format:
```text
PLAN:
  actions:
    - {action 1}
    - {action 2}
  risk: {none | low | medium | high}
  reversible: {yes | no}
STATUS: plan_ready
```

### Orchestrator-level approval (supervisor for N == 1, crew:run for N > 1)

After collecting all PLAN blocks, the orchestrator issues a single structured
user-choice intent (per `core/rules/capabilities/interactive-question.md`)
with a consolidated summary of all planned actions.

Standard approval options:

```text
[A] Approve - proceed as planned
[B] Request changes - revise the plan and ask again
[C] Cancel - stop implementation
[D] Custom input
```

Standard plan summary (presented by orchestrator, not stage agents):

```text
[agent-name] Work Plan

Target: {feature name}
Approach: {pattern or methodology summary}
Files:
  - {file path 1} (new or modified)
  - {file path 2} (new or modified)
Planned Actions:
  - {action 1}
  - {action 2}
Risk: {none | low | medium | high}

Proceed with this plan?
```
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
