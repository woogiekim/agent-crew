# Agent Skill Loading Convention

## Purpose

This document specifies **how implementation agents declare which skills they
load and when they load them**. Following this convention makes skill coverage
self-documenting, auditable, and Open/Closed — adding a new skill never
requires editing this rule or any existing agent file.

---

## Convention: "## Skills (Loaded On Demand)" Section

Every implementation agent that consumes skill files MUST include a section
with the exact heading:

```markdown
## Skills (Loaded On Demand)
```

The section lists each skill as a relative file path and a one-line purpose
annotation. The format is:

```markdown
## Skills (Loaded On Demand)

Read the following skill files using the Read tool **only when the specific
technique is needed** during execution — do not load all skills upfront:
- {Purpose annotation}: `{relative path to skill file}`
- {Purpose annotation}: `{relative path to skill file}`
```

### Path resolution

Skill paths are relative to one of two roots:

| Root | Path prefix | When used |
|---|---|---|
| System agents directory | `~/.agent-crew/system/agents/skills/` | Skills installed with agent-crew; path uses `~/.agent-crew/...` |
| Project skill directory | `core/agents/skills/` | Project-specific skills checked into the repo |

All existing skills (as of this writing) live in the project directory and
are referenced as `core/agents/skills/{name}.md`.

### Mandatory load triggers

Some skills are mandatory (agent MUST read before proceeding with a phase).
These are called out inline in the agent's Execution Flow section with a
`> **MANDATORY: …**` block. The skill path must still appear in the
"## Skills (Loaded On Demand)" section — the `MANDATORY` block is a runtime
enforcement note, not a substitute for the registry entry.

---

## Open/Closed Extension Protocol

**Adding a new skill requires only two steps:**

1. Create `core/agents/skills/{new-skill}.md` following `SKILL-TEMPLATE.md`.
2. Add a bullet line to the relevant agent's "## Skills (Loaded On Demand)"
   section.

**What does NOT need to change:**

- This rule file (`core/rules/agent-skill-loading.md`)
- Any other agent file not consuming the skill
- The supervisor, planner, or any orchestration layer
- `core/agents/skills/` index or any registry file

This is the Open/Closed guarantee: skill creation is additive only.

---

## Audit / Verification

To list every skill declared across all implementation agents, run:

```bash
grep -h "core/agents/skills/" \
     core/agents/backend.md \
     core/agents/frontend.md \
     core/agents/test-writer.md \
     core/agents/reviewer.md \
  | grep -o '`[^`]*skills/[^`]*`' \
  | tr -d '`' \
  | sort -u
```

To verify a specific skill file exists for every declared path:

```bash
while IFS= read -r path; do
  [ -f "${path}" ] && echo "OK  ${path}" || echo "MISSING  ${path}"
done < <(
  grep -h "core/agents/skills/" \
       core/agents/backend.md \
       core/agents/frontend.md \
       core/agents/test-writer.md \
       core/agents/reviewer.md \
    | grep -o '`[^`]*skills/[^`]*`' \
    | tr -d '`'
)
```

---

## Skill File Structure

Every skill file MUST follow the structure defined in
`core/agents/skills/SKILL-TEMPLATE.md`:

| Section | Required | Description |
|---|---|---|
| `# Skill: {name}` | yes | H1 title matching the filename |
| `## Source` | yes | Canonical book / article this skill distills |
| `## When to Apply` | yes | Concrete trigger conditions |
| `## Core Rules` | yes | LLM-actionable imperative rules with code examples |
| `## Anti-Patterns` | yes | Explicit list of things NOT to do |
| `## Interaction with Other Skills` | no | Cross-skill dependencies |
| `## References` | yes | Full bibliographic citation |

---

## Agent-to-Skill Matrix (current)

| Skill file | backend | frontend | test-writer | reviewer |
|---|---|---|---|---|
| `tdd.md` | MANDATORY | MANDATORY | MANDATORY | — |
| `oop-principles.md` | MANDATORY | — | — | yes |
| `api-design.md` | MANDATORY | — | — | — |
| `domain-modeling.md` | yes | — | — | — |
| `database-design.md` | yes | — | — | — |
| `error-handling.md` | yes | yes | — | — |
| `security-hardening.md` | yes | — | — | yes |
| `ui-component-design.md` | — | MANDATORY | — | — |
| `code-review.md` | — | — | — | MANDATORY |
| `effective-kotlin.md` | yes | — | yes | yes |
| `effective-java.md` | yes | — | yes | yes |
| `effective-typescript.md` | — | yes | yes | yes |
| `effective-python.md` | yes | — | yes | yes |
| `effective-go.md` | yes | — | yes | yes |
| `effective-rust.md` | yes | — | yes | yes |
| `effective-scala.md` | yes | — | yes | yes |
| `effective-swift.md` | — | yes | yes | yes |
| `clean-architecture.md` | yes | yes | — | MANDATORY |
| `agile-xp.md` | yes | yes | yes | yes |
| `domain-driven-design.md` | yes | — | — | yes |

> This matrix is informational. The authoritative source of truth is the
> "## Skills (Loaded On Demand)" section in each agent file. Update both when
> adding a new skill.
