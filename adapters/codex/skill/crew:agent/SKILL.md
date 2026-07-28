---
name: crew:agent
description: Use when the user explicitly mentions $crew:agent or invokes crew:agent direct-agent execution in Codex. This is a thin Codex skill wrapper for crew:agent and delegates all behavior to ~/.agent-crew/commands/agent.md.
---

# crew:agent

This Codex skill is an alias for:

```text
crew:agent
```

## Execution

1. Load `~/.agent-crew/commands/agent.md`.
2. Treat any user text after `$crew:agent` as the agent invocation arguments.
3. Preserve explicitly invoked Codex skill context as direct-agent input. Do
   not treat domain-selected third-party host/plugin skills as implicitly
   approved.
4. Follow the command definition exactly.

Use this skill for direct single-agent invocation. The selected agent may mutate
files or state when its own definition allows mutation. Agents that are
read-only declare that rule in their own instructions. Use `crew:run` when the
task needs supervisor planning, parallelism, centralized approval, or the
automatic reviewer stage.

## Codex current-session fallback

When `crew:agent` returns:

```text
STATUS: handoff_ready
HOST_BRIDGE: current_session_required
```

the Codex host bridge intentionally refused to spawn a nested `codex exec`
from an already-active Codex session. This is not an agent failure.

Continue the direct-agent request in the current Codex session:

1. Read the printed `handoff.md` path.
2. Apply the requested agent role and any inline normalization contract.
3. Answer the user directly.

Do not report the request as blocked solely because nested Codex execution was
refused.
