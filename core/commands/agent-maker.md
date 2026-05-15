# crew:agent-maker - AI-Agnostic Agent Asset Designer

Design and create reusable agent-crew assets without binding them to one AI vendor.

## Goal

Create one or more of the following assets:

| Asset | Default path | Purpose |
|---|---|---|
| Project guidance | `AGENTS.md` | Always-on repository rules and conventions |
| Agent definition | `~/.agent-crew/user/agents/<name>.md` | Specialist worker instructions |
| Skill / command | `~/.agent-crew/commands/<name>.md` | Reusable workflow invoked by name |
| Hook | `~/.agent-crew/hooks/<name>.sh` | Deterministic automation outside the model |
| Rule document | `~/.agent-crew/rules/<name>.md` | Conditional guidance for a domain or file type |

Compatibility copies may be placed in a host-specific directory only when required by that host tool.
The canonical content must remain usable from `~/.agent-crew`.

## Required Input

If information is missing, use the host AI tool's structured choice UI.
Do not ask open-ended plain text questions when bounded options are possible.

Collect:

- Name and purpose
- Trigger conditions
- Skip conditions
- Inputs and outputs
- Required tools or permissions
- State files to read or write
- Verification steps
- Whether a compatibility copy is needed for a specific host AI tool

## Decision Rules

Use the smallest asset that satisfies the requirement:

- Repeated workflow → command / skill
- Specialist implementation role → agent definition
- Always-on repository convention → `AGENTS.md`
- Deterministic validation or routing → hook
- File-type or directory-specific convention → rule document

## Agent Definition Template

```markdown
---
name: <agent-name>
description: >
  TRIGGER when: <specific trigger conditions>.
  SKIP when: <specific skip conditions>.
  Output: <expected artifacts>.
model: inherit
---

# <Agent Title>

## Role
<Short responsibility statement>

## Inputs
- `TASK_DIR`
- `PROJECT_ROOT`
- `HANDOFF_PATH`

## Workflow
1. Read required files by path.
2. Produce the required artifact.
3. Run verification.
4. Report only concise status and artifact paths.

## Rules
- Do not inline large file contents.
- Preserve user changes.
- Use host AI structured choices for confirmation.
```

## Command / Skill Template

````markdown
# /<name> — <purpose>

## Inputs
- <input>

## Flow
1. <step>
2. <step>
3. <verification>

## Output
```text
STATUS: <completed|blocked|cancelled>
ARTIFACTS: <paths>
```
````

## Hook Template

```bash
#!/usr/bin/env bash
set -euo pipefail

INPUT="$(cat)"
# Parse host-provided JSON when available.
# Emit host-compatible JSON output when the host supports hook context injection.
printf '%s' "$INPUT"
```

## Finalization — Deploy to All Hosts

After writing an agent definition to `~/.agent-crew/user/agents/<name>.md`, run the
deploy helper so the new agent appears in every installed host adapter's discovery path:

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
bash "${AGENT_CREW_HOME}/setup/deploy-user-agent.sh" "<name>.md"
```

The helper detects installed adapters by checking sentinel paths:

| Adapter | Sentinel path | Deploy action |
|---|---|---|
| Claude Code | `~/.claude/agents/` exists | Merges `user/agents/` + `system/agents/` into `~/.claude/agents/` |
| Codex | `~/.codex/agents/` exists | Copies the `.md` file to `~/.codex/agents/` |
| Generic (project) | N/A — project root unknown at creation time | Run `crew:setup` for the project to pick up the new agent |

The script is idempotent and silent when an adapter is not installed. It must
be called once per agent after the file is written — not once per host.

## Completion Checklist

- [ ] Uses `~/.agent-crew/user/agents/` as the canonical write path for agent definitions
- [ ] Uses `AGENTS.md` for general project guidance
- [ ] Avoids vendor-specific model names
- [ ] Uses `model: inherit` when a model field is required
- [ ] Describes host-specific copies as compatibility only
- [ ] Includes verification steps
- [ ] Runs `deploy-user-agent.sh` to propagate the agent to all installed host adapters

## Completion Report

```text
STATUS: completed
FILES: <created or modified paths>
VERIFY: <checks run>
```
