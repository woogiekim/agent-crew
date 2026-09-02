# Direct-Edit Guard — Enforcement Contract

## Purpose

The `direct-edit-guard.sh` PreToolUse hook enforces the "No Direct
Implementation" rule from `core/global-agents.md`: all coding, file
edits, and implementation work must be routed through
`crew:run` → supervisor → stage agents. The main AI session must not
perform direct `Edit` or `Write` calls to project source files.

## Why enforcement is mechanical, not prose

A prose convention without a mechanical gate is not a rule — it is a
wish. The AI can always satisfy the literal instruction ("I'll route
next time") without satisfying the intent ("actually route the work
now"). Issue #17 documents a concrete incident (2026-05-17) where the
main session directly edited `core/scripts/seed-instruction-rules.sh`,
ran apply scripts, committed, and pushed to main — all without routing
through `crew:run`. The hook did not fire. This document records the
root-cause analysis and the fixed contract.

## Enforcement mode: block (exit 2)

Unlike issue #16 (mnemos capture guard, advisory-only), this hook uses
**exit 2** to block the tool call when no active crew task is present.

Rationale for the different choice:

| Factor | mnemos capture guard (#16) | direct-edit guard (#17) |
|---|---|---|
| False-positive cost | High — ✻ 🧠 notifications appear in many turns | Low — most Edit calls to source files ARE implementation work |
| False-negative cost | Low — missing a capture notification is recoverable | High — implementation work slipping past unrouted is the exact failure mode |
| Escape hatch available? | Yes (command skips gracefully) | Yes (env var + marker, documented below) |

Blocking is the correct default. The escape hatch prevents legitimate
direct edits (user-authorized config changes, trivial typo corrections)
from being blocked.

## How the hook works

1. Called by Claude Code as a PreToolUse hook for `Edit`, `Write`,
   `MultiEdit`, and `apply_patch` tool calls.
2. Resolves the `git` project root of the file being edited.
3. Checks for an active crew task marker in
   `~/.agent-crew/state/{project}/tasks/`:
   - `tasks/active` — legacy singleton, written by supervisor Phase 1c
   - `tasks/active.<TASK_ID>` — per-task marker, for background fan-out
4. If either marker exists: allows the edit (crew pipeline is active).
5. If no marker exists: blocks with exit 2 and surfaces the reason.

## Active task marker lifecycle

The supervisor writes the marker at Phase 1c (bootstrap):

```bash
touch "${TASKS_DIR}/active"
touch "${TASKS_DIR}/active.${TASK_ID}"
```

The supervisor removes the marker at Phase 3 (close-out):

```bash
rm -f "${TASKS_DIR}/active.${TASK_ID}"
# Legacy singleton: only clear when no per-task markers remain
REMAINING=$(ls "${TASKS_DIR}"/active.* 2>/dev/null | wc -l | tr -d ' ')
if [ "${REMAINING}" = "0" ]; then
  rm -f "${TASKS_DIR}/active"
fi
```

**Stale markers**: If a task is interrupted before Phase 3, the marker
may persist. This creates a false-allow window for subsequent main
session edits. The fix (issue #17) does not address stale-marker
cleanup directly — that is a separate Phase 3 hardening task. However,
the improved exit-code fix (exit 2) means that when NO marker is
present, the block is now enforced correctly.

## Escape hatch: authorized direct edits

Two mechanisms allow legitimate direct edits:

### 1. Environment variable (one-time or session-wide)

Set `AGENT_CREW_ALLOW_DIRECT_EDIT=1` before running Claude Code, or
export it in the session:

```bash
export AGENT_CREW_ALLOW_DIRECT_EDIT=1
# ... make your direct edit ...
unset AGENT_CREW_ALLOW_DIRECT_EDIT
```

This escape hatch does not widen an active task whose register declares
`mutation_scope=read_only`. Such a task may write only inside its own
task-state directory; start a new explicitly writable execution if project
mutation is required.

Use cases:
- Quick typo fix in documentation that does not warrant a full pipeline
- Editing `~/.claude/settings.json` or agent-crew config files directly
- Emergency hot-fix with explicit user authorization

### 2. Allowed path prefixes (automatic)

When no active read-only task overrides them, the hook automatically allows edits to:
- `~/.agent-crew/` — crew state, agent definitions, harness config
- `~/.claude/` — Claude host config

These paths remain available to legacy and `workspace_write` tasks. A
`read_only` task is limited to its own task-state directory.

## Files touched by this feature

| File | Role |
|---|---|
| `core/hooks/direct-edit-guard.sh` | Hook implementation |
| `core/rules/direct-edit-guard.md` | This document (enforcement contract) |
| `tests/shell/test_direct_edit_guard.bash` | Regression tests |
| `adapters/claude/setup.sh` | Registers the hook in `~/.claude/settings.json` |
| `install.sh` | Copies hook to installed location |

## Root cause: 2026-05-17 incident (issue #17)

**Bug 1 — wrong exit code (primary):**
The original hook printed a `{"decision": "block", ...}` JSON to
stdout but then called `sys.exit(0)`. Claude Code's PreToolUse hook
contract uses the exit code to determine whether to block:
- exit 0 → allow (no block decision)
- exit 2 → block (reason surfaced to model, tool call cancelled)

Printing the block JSON and then exiting 0 is contradictory — the host
ignores the JSON because the exit code says "allow." Fixed: block path
now exits with `sys.exit(2)`.

**Bug 2 — stale active marker (contributing):**
The `tasks/active` legacy singleton was created by previous task runs
and never cleaned up (tasks were interrupted before Phase 3). The guard
checked for the marker's presence and found it, so the hook allowed the
edit without reaching the block path at all.

The primary fix (exit code) is sufficient to enforce blocking when no
marker exists. Stale-marker cleanup is a separate hardening concern.

## Related

- GitHub issue #17 — this fix
- GitHub issue #16 — mnemos capture guard (same architectural pattern,
  advisory mode)
- GitHub issue #15 — memory wrapper (same pattern)
- `core/hooks/forbid-plaintext-approval.sh` — another blocking hook (exit 2)
- `supervisor-bootstrap.md` Phase 1c — where markers are created
- `supervisor-retry.md` Phase 3.3 — where markers are cleaned up
