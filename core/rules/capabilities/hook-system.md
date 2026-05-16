# hook_system Capability

## Purpose

The host exposes a lifecycle-hook surface (`PreToolUse`, `PostToolUse`,
`SessionStart`, etc.) into which core wires validators that enforce
invariants at execution time, rather than relying on model-side
guidance alone. This is the difference between "the model is told not
to do X" and "the host blocks X."

Consumers:

- **Forbid plain-text approval** (Phase G6 — implemented). A
  `PostToolUse[Agent]` validator inspects the agent's response for
  forbidden patterns like "Shall I merge and push?" /
  "...진행할까요?" and surfaces a blocking message (exit 2) when
  found. Script: `core/scripts/check-plaintext-approval.py`. Hook
  wrapper: `core/hooks/forbid-plaintext-approval.sh`. Registered by
  `adapters/claude/setup.sh` when `hook_system=true`.
- **Autonomous task injection guards** (planned — refactor item 14). A
  pre-routing hook detects inject-intent phrases ("추가로 해줘",
  "이것도 부탁해", etc.) and steers them into the injection flow when
  a session is live.

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
  `auto-route`, `context-guard`, `verify-rules`.

## Consumer Contract (core)

Consumers fall in two layers:

- **Existing hook scripts** under `core/hooks/*.sh` are ready to be
  wired by any adapter that advertises `hook_system=true`. As of
  Phase G6 this set includes `forbid-plaintext-approval.sh`.
- **Provider-neutral validators** under `core/scripts/check-*.py` are
  the canonical implementations that the adapter wires in. Phase G6
  ships `check-plaintext-approval.py`; `check-task-injection.py`
  remains planned (refactor item 14). These scripts run on
  stdin/stdout with exit codes so they can be invoked from any host's
  hook mechanism.

Core's input shape assumes a `${HOOK_INPUT}` JSON environment variable
available to hook scripts (matching the current Claude convention). If
a different host uses a different injection mechanism, the adapter
wraps the script so the contract still holds.

Hook scripts MUST be idempotent and side-effect-minimal: they read repo
state, read `approval.md`, inspect tool input, etc. They MUST NOT
mutate pipeline state (`pipeline.json`, `progress.log`, etc.).

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
- `core/hooks/context-guard.sh`
- `core/hooks/verify-rules.sh`
- `core/hooks/forbid-plaintext-approval.sh` (Phase G6)

Consumer — validator scripts:

- `core/scripts/check-plaintext-approval.py` (Phase G6 — implemented)
- `core/scripts/check-task-injection.py` (refactor item 14 — not
  present yet)

Cross-flag:

- `cost_tracking`: Claude implements `cost_tracking` through its hook
  system (`core/hooks/cost-tracker.sh` is a `PostToolUse` hook). The
  two flags are independent on purpose — a future host could advertise
  `cost_tracking=true` without `hook_system=true` if it ships token
  usage some other way.
