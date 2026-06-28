# hook_system Capability

## Purpose

The host exposes a lifecycle-hook surface (`UserPromptSubmit`, `PreToolUse`,
`PostToolUse`, `SessionStart`, etc.) into which core wires prompt compilers,
observers, and only-when-needed validators. The primary prompt-facing hook
responsibility is to improve user prompts before downstream agents see them:
normalize, enrich, infer, structure, and optimize. Blocking behavior is a
backstop for unsafe, impossible, out-of-scope, or invariant-breaking actions,
not the default user experience.

Consumers:

- **Prompt Compiler routing context** (implemented). The `UserPromptSubmit`
  `auto-route` hook classifies arbitrary user input, emits the STOP/ROUTE
  workflow lock, and appends a `PROMPT_COMPILER` block with intent,
  `NORMALIZED_TASK`, context enrichment, project rules, missing-information
  recovery, risk assessment, success criteria, deliverables, soft-validation
  policy, and role-specific prompts for planner/developer/tester/reviewer or
  analyst/historian. Hook wrapper: `core/hooks/auto-route.sh`. Contract:
  `core/rules/agent-routing.md`.
- **Forbid plain-text approval** (Phase G6 — implemented). A
  `PostToolUse[Agent]` validator inspects the agent's response for
  forbidden patterns like "Shall I merge and push?" /
  "...진행할까요?" and surfaces a blocking message (exit 2) when
  found. Script: `core/scripts/check-plaintext-approval.py`. Hook
  wrapper: `core/hooks/forbid-plaintext-approval.sh`. Registered by
  `adapters/claude/setup.sh` when `hook_system=true`.
- **Route directive compliance** (Issue #125 — implemented). A
  `PostToolUse[Agent]` validator detects Agent responses that received
  an auto-route `[agent-crew] STOP` or `[agent-crew] ROUTE` directive
  but answered inline instead of entering `crew:run` / `crew:agent`.
  Script: `core/scripts/check-route-directive-compliance.py`. Hook
  wrapper: `core/hooks/route-directive-guard.sh`.
- **Autonomous task injection** (Phase J14 — implemented in `crew:run`
  Step 1.5, no hook required). `core/scripts/detect-inject-intent.sh`
  classifies the user's input for inject-intent phrases ("추가로 해줘",
  "이것도 부탁해", "Also do...", etc.) and `crew:run` auto-routes to
  the injection path when the phrase matches AND a session is live.
  Skips the structured user-choice prompt for unambiguous phrasing.
  This consumer runs inline in `crew:run` rather than through a
  PostToolUse hook, so it works on every adapter regardless of
  `hook_system`.
- **Automatic issue reporting** (implemented). A `UserPromptSubmit`
  observer and a `PostToolUse[Bash]` observer detect explicit
  agent-crew bug/error reports or failed `crew` command payloads with
  explicit/high-confidence bug evidence, then call `crew report auto` to store
  a deduplicated native report/outbox entry. Successful diagnostic commands are
  ignored even when filenames contain words such as `error`. GitHub publication
  is an optional backend through `crew report publish`. Script:
  `core/scripts/auto-issue-reporter.py`. Hook wrapper:
  `core/hooks/auto-issue-report.sh`. Contract:
  `core/rules/auto-issue-reporting.md`.

## Required Adapter Surface (flag=true)

Adapter MUST provide:

- **A registration mechanism** — a way to register a shell command to
  fire at one or more lifecycle moments. The moments core depends on:
  - `PreToolUse` — validator runs before a tool call; a non-zero exit
    blocks the call (with a stderr message surfaced to the model).
  - `PostToolUse` — observer runs after a tool call; the exit code is
    advisory.
  - `SessionStart` (optional) — startup-time validator.
- **Registration happens in `adapters/{host}/setup.sh`**, which
  references the scripts under `core/hooks/` and/or `core/scripts/`.
- The adapter MAY pre-register the canonical set of hooks that ship
  with agent-crew: `direct-edit-guard`, `cost-tracker`,
  `guard-dangerous-commands`, `agent-diff-pre` / `agent-diff-post`,
  `auto-route`, `auto-issue-report`, `context-guard`, `verify-rules`.

## Consumer Contract (core)

Consumers fall in two layers:

- **Existing hook scripts** under `core/hooks/*.sh` are ready to be
  wired by any adapter that advertises `hook_system=true`. This set
  includes `forbid-plaintext-approval.sh` and
  `route-directive-guard.sh`.
- **Provider-neutral validators** under `core/scripts/check-*.py` are
  the canonical implementations that the adapter wires in.
  `check-plaintext-approval.py`, `check-route-directive-compliance.py`,
  and `detect-inject-intent.sh` ship today (the latter is invoked
  inline by `crew:run` Step 1.5 rather than through a hook).
  `check-task-injection.py` for the mid-injection duplicate-disambiguation
  prompt remains planned (refactor item 14b).
  These scripts run on stdin/stdout with exit codes so they can be
  invoked from any host's hook mechanism.

Core's input shape assumes a `${HOOK_INPUT}` JSON environment variable
available to hook scripts (matching the current Claude convention). If
a different host uses a different injection mechanism, the adapter
wraps the script so the contract still holds.

Hook scripts MUST be idempotent and side-effect-minimal: they read repo
state, read `approval.md`, inspect tool input, etc. They MUST NOT
mutate pipeline state (`pipeline.json`, `progress.log`, etc.).

Prompt-facing hooks prefer soft validation. They should transform executable
but vague input into compiled context and proceed. They should reject only when
the request cannot be made executable safely or within project scope.

## Absence Behavior (flag=false)

Enforcement degrades to model-side guidance. The same invariants are
restated as instructions in:

- `core/agents/devops.md` and `core/agents/skills/deployment-ops.md` —
  approval-phrasing rules.
- `adapters/{host}/invocation.md` and `SKILL.md` — host-specific
  framing of the same rules.

The validator scripts under `core/scripts/check-*.py` (when introduced)
still exist as standalone diagnostic tools the user can run manually.
Enforcement is best-effort, not strict, in this mode.

## Adapter Examples

| Adapter | hook_system | How it is implemented |
|---|---|---|
| claude  | true  | Native `settings.json` hooks block; `adapters/claude/setup.sh` wires every script under `core/hooks/` via Python merge snippets into `~/.claude/settings.json`. |
| codex   | false | No equivalent lifecycle-hook surface today. Uses `SKILL.md` model-side rules to convey the same invariants. |
| generic | false | No lifecycle-hook surface; model-side guidance only. |

## Related Files

Producer:

- `adapters/claude/setup.sh` (registers hooks via Python merge into
  `~/.claude/settings.json`)

Consumer — current hook scripts:

- `core/hooks/agent-diff-pre.sh`, `core/hooks/agent-diff-post.sh`
- `core/hooks/direct-edit-guard.sh`
- `core/hooks/cost-tracker.sh`
- `core/hooks/guard-dangerous-commands.sh`
- `core/hooks/auto-route.sh`
- `core/hooks/auto-issue-report.sh`
- `core/hooks/context-guard.sh`
- `core/hooks/verify-rules.sh`
- `core/hooks/forbid-plaintext-approval.sh` (Phase G6)
- `core/hooks/route-directive-guard.sh` (Issue #125)

Consumer — validator scripts:

- `core/scripts/check-plaintext-approval.py` (Phase G6 — implemented)
- `core/scripts/check-route-directive-compliance.py` (Issue #125 — implemented)
- `core/scripts/auto-issue-reporter.py` (implemented; advisory
  UserPromptSubmit/PostToolUse native report engine)
- `core/scripts/detect-inject-intent.sh` (Phase J14 — implemented;
  invoked by `crew:run` Step 1.5 to auto-route on unambiguous
  inject-intent phrasing)
- `core/scripts/check-task-injection.py` (refactor item 14b — not
  present yet; mid-injection duplicate-disambiguation prompt)

Cross-flag:

- `cost_tracking`: Claude implements `cost_tracking` through its hook
  system (`core/hooks/cost-tracker.sh` is a `PostToolUse` hook). The
  two flags are independent on purpose — a future host could advertise
  `cost_tracking=true` without `hook_system=true` if it ships token
  usage some other way.
