# Approval, Recovery, And Audit Demo

Date: 2026-06-01

This demo is the product-facing proof point for agent-crew's control-plane
wedge. It shows why the project is more than an agent or skill catalog: the
operator can prove what happened after a guarded workflow, including approval
state, recovery state, trace state, and update evidence.

## Demo Goal

Run a small workflow that needs an explicit gate, then show the local evidence
that answers these questions:

- What task was requested?
- Which branch or state directory did it use?
- Was a destructive or externally visible action blocked or approved?
- Did the host bridge complete automatically or require manual continuation?
- Where is the result recorded?
- How can another operator inspect or resume the same workflow?

## Demo Script

```bash
# 1. Confirm the installed control plane is healthy enough to demo.
crew doctor --mode host

# 2. Start the guarded workflow from the host prompt runtime.
crew:run "Create a small evidence artifact, verify it, and prepare a guarded publish/update plan."

# 3. Inspect the short operator view.
crew status --summary

# 4. Inspect the durable trace.
crew trace --recent 1 --include-tools

# 5. Inspect aggregate quality and intervention signals.
crew telemetry --recent 5

# 6. If the host required manual continuation, close the loop explicitly.
crew repair TASK_ID \
  --status completed \
  --note "Completed guarded workflow in host session." \
  --quality-bypass-reason "Demo-only guarded workflow; evidence is trace and audit state."
```

## Evidence Checklist

| Evidence | Location |
|---|---|
| task state | `~/.agent-crew/state/<project>/tasks/<task-id>/` |
| register | `register.json` |
| pipeline | `pipeline.json` |
| progress trace | `progress.buffer.jsonl` or `progress.log` |
| tool trace | `tool-events.jsonl` |
| manual recovery record | `context/manual-fallback-repair.json` |
| dangerous command audit | `~/.agent-crew/audit/dangerous-commands.jsonl` |
| update integrity | `~/.agent-crew/state/<project>/integrity/update-integrity.json` |

## Pass Criteria

- The workflow prints a `TASK_ID` and `TASK_DIR`.
- `crew status --summary` shows current task counts and the next action.
- Guarded operations either remain blocked or show a command-bound approval
  record before execution.
- Any manual continuation is recorded with `crew repair`.
- A reviewer or operator can inspect the task directory and reconstruct the
  workflow without relying on chat history.

## Positioning Note

Use this demo to show agent-crew's strongest niche: local governance and
evidence for AI-host workflows. Avoid framing the demo as an attack on other
harnesses; the goal is to prove the control-plane value on its own terms.
