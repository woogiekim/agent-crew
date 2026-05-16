# crew:agent-maker - AI-Agnostic Agent Asset Designer

Design and create reusable agent-crew assets without binding them to one AI vendor.

## Goal

Create one or more of the following assets:

| Asset | Default path | Purpose |
|---|---|---|
| Project guidance | `AGENTS.md` | Always-on repository rules and conventions |
| Agent definition | `~/.agent-crew/user/agents/<name>.md` | Specialist worker instructions |
| Skill guide | `~/.agent-crew/user/skills/<name>.md` | Reference guide agents consult during specific tasks |
| Workflow command | `~/.agent-crew/commands/<name>.md` | Reusable workflow invoked by name (e.g. crew:run) |
| Hook | `~/.agent-crew/hooks/<name>.sh` | Deterministic automation outside the model |
| Rule document | `~/.agent-crew/rules/<name>.md` | Conditional guidance for a domain or file type |

Compatibility copies may be placed in a host-specific directory only when required by that host tool.
The canonical content must remain usable from `~/.agent-crew`.

## Required Input

If information is missing, use the host AI tool's structured choice UI.
Do not ask open-ended plain text questions when bounded options are possible.

Collect (for all assets):

- Name and purpose
- Trigger conditions
- Skip conditions
- Inputs and outputs
- Required tools or permissions
- State files to read or write
- Verification steps
- Whether a compatibility copy is needed for a specific host AI tool

Collect additionally when creating a **skill guide**:

- Which agents will use this skill (e.g. backend, frontend, planner)
- What domain or topic it covers (e.g. API design, security hardening, TDD)
- Official references to cite (Author, Title, Year / URL)

## Decision Rules

Use the smallest asset that satisfies the requirement:

- Repeated workflow → workflow command
- Agents need domain reference material → skill guide
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

## Skill Guide Template

```markdown
# Skill: <skill-name>

## Purpose
<What capability this skill gives to agents that load it>

## When to Apply
- <trigger condition 1>
- <trigger condition 2>

---

## <Topic Section 1>

(Reference: <Author, Title, Year>)

<Explanation with code examples>

---

## <Topic Section 2>

...

---

## Checklist
- [ ] <verification item 1>
- [ ] <verification item 2>
```

## Workflow Command Template

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

## Finalization — Deploy Agent to All Hosts

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

## Finalization — Deploy Skill to Discovery

After writing a skill guide to `~/.agent-crew/user/skills/<name>.md`, run the deploy
helper so the skill is visible to agents that load skills from the merged discovery path:

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
bash "${AGENT_CREW_HOME}/setup/deploy-user-skill.sh" "<name>.md"
```

The helper copies the skill file into each installed host adapter's skills path and
into the agent-crew mirror path where agents can discover it at task time.

| Adapter | Sentinel path | Deploy action |
|---|---|---|
| Claude Code | `~/.claude/agents/` exists | Copies skill to `~/.claude/agent-crew/skills/` |
| Codex | `~/.codex/agents/` exists | Copies skill to `~/.codex/skills/` |
| Generic (project) | N/A — project root unknown at creation time | Run `crew:update` to pick up the new skill |

The script is idempotent. `crew:update` also runs this merge automatically on every
update cycle, so new skills are discovered without a manual step after the first deploy.

## Completion Checklist

- [ ] Uses `~/.agent-crew/user/agents/` as the canonical write path for agent definitions
- [ ] Uses `~/.agent-crew/user/skills/` as the canonical write path for skill guides
- [ ] Uses `AGENTS.md` for general project guidance
- [ ] Avoids vendor-specific model names
- [ ] Uses `model: inherit` when a model field is required
- [ ] Describes host-specific copies as compatibility only
- [ ] Includes verification steps
- [ ] Runs `deploy-user-agent.sh` to propagate agents to all installed host adapters
- [ ] Runs `deploy-user-skill.sh` to propagate skill guides to all installed host adapters
- [ ] Skill file follows `## Purpose` / `## When to Apply` / code examples / `## Checklist` format
- [ ] Official references cited for every major principle (Author, Title, Year)
- [ ] Skill is discoverable by agents after deploy

## Completion Report

```text
STATUS: completed
FILES: <created or modified paths>
VERIFY: <checks run>
```
