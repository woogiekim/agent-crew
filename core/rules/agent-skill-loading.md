# Agent Skill Loading Convention

## Purpose

This document specifies **how implementation agents declare every skill they
load before execution and how those skills are audited**. Following this convention makes skill coverage
self-documenting, auditable, and Open/Closed — adding a new skill never
requires editing this rule or any existing agent file.

---

## Convention: "## Skills (Loaded Upfront)" Section

The section is the authoritative **agent-associated upfront loading**
registry: once an agent is selected, it MUST load every skill listed in
that agent's section before execution. The agent must not select a subset
based on perceived task need.

Every implementation agent that consumes skill files MUST include a section
with the exact heading:

```markdown
## Skills (Loaded Upfront)
```

The section lists each skill as a relative file path and a one-line purpose
annotation. The format is:

```markdown
## Skills (Loaded Upfront)

Read every skill file listed below before execution. These are the skills
associated with this agent; do not select a subset:
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

### Mandatory application triggers

Some skills are mandatory (agent MUST read before proceeding with a phase).
These are called out inline in the agent's Execution Flow section with a
`> **MANDATORY: …**` block. The skill path must still appear in the
"## Skills (Loaded Upfront)" section — the `MANDATORY` block is a phase
application note, not a substitute for the upfront registry entry. Skills
marked `yes` in the matrix are also loaded upfront; `MANDATORY` means a phase
cannot proceed until the named rule has been applied.

### External host/plugin skill boundary

Agent-crew skills are the only skills that may be auto-loaded by the framework.
Allowed automatic skill sources are:

- `core/agents/skills/` in the source repository.
- `~/.agent-crew/system/skills/`, `~/.agent-crew/user/skills/`,
  `~/.agent-crew/skills/`, and `~/.agent-crew/system/agents/skills/`.
- Host mirrors populated from the agent-crew skill layers, such as
  `~/.claude/agent-crew/skills/`, `~/.claude/agent-crew/agents/skills/`,
  `~/.codex/skills/agent-crew/`, and `~/.codex/agent-crew/skills/`.
- Agent-crew host wrapper skills, such as Codex `crew-*` wrappers.

Do not auto-load non-agent-crew host/plugin skills merely because a host skill
description appears to match the task. This applies to every host adapter, not only Codex. If a non-agent-crew host/plugin skill is genuinely needed, ask the
user first and record the approval in
`{TASK_DIR}/context/external-skill-approval.md` or
`{TASK_DIR}/context/external-skill-approval.json`.

---

## Open/Closed Extension Protocol

**Adding a new skill requires only two steps:**

1. Create `core/agents/skills/{new-skill}.md` following `SKILL-TEMPLATE.md`.
2. Add a bullet line to the relevant agent's "## Skills (Loaded Upfront)"
   section.

**What does NOT need to change:**

- This rule file (`core/rules/agent-skill-loading.md`)
- Any other agent file not consuming the skill
- The supervisor, planner, or any orchestration layer
- `core/agents/skills/` index or any registry file

This is the Open/Closed guarantee: skill creation is additive only.

---

## Audit / Verification

### Content-Depth Audit

File existence and section shape are necessary but not sufficient. A skill that
loads successfully can still be too shallow to drive the implementation or
review judgment the agent needs to make.

Use the content-depth audit when changing `core/agents/skills/*.md` or when a
review miss suggests a loaded skill did not contain enough concrete guidance:

```bash
python3 core/scripts/skill-content-audit.py --format json
python3 core/scripts/skill-content-audit.py --format markdown
```

Completed mutating workflows run the same audit automatically through the
quality-loop completion gate and persist the JSON result at
`{TASK_DIR}/context/skill-content-audit.json`. Reviewer approval should also
include that artifact when evaluating whether loaded language skills were
actually usable for concrete review decisions.

The audit records:

- inventory for every source skill file;
- consuming agents and mandatory/upfront-load status from the matrix and agent
  declarations;
- declared sources, rule counts, and checklist markers;
- targeted content contracts for known high-value review misses;
- follow-up categories for every `effective-*` skill.

Depth rubric:

| Question | Required evidence |
|---|---|
| Does the skill cover the canonical source's high-impact items? | Named item, rule, or source section. |
| Does it include concrete review triggers? | A reviewer can match a changed hunk to a specific rule. |
| Does it include positive and negative patterns? | Both examples or explicit anti-pattern bullets. |
| Does it map to implementation, test-writer, and reviewer behavior? | The rule states when to apply and how to verify. |
| Does it include examples matching real review decisions? | Example code or artifact shape similar to observed misses. |

Known content contracts should live in `core/scripts/skill-content-audit.py` so
they fail in CI instead of relying on manual review memory. For example,
`effective-java.md` must keep Effective Java Item 17, Item 50, Item 54, and
canonical immutable empty collection guidance because these rules are concrete
review triggers for read-only fallback collection refactors.

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
| `refactoring-catalog.md` | yes | yes | — | yes |
| `legacy-code-seams.md` | yes | yes | yes | — |
| `documentation-impact.md` | yes | yes | — | yes |

> This matrix is informational. The authoritative source of truth is the
> "## Skills (Loaded Upfront)" section in each agent file. Update both when
> adding a new skill.

---

## Relation to `agent-tool-dispatch.md`

This rule covers **declared** skill consumption: an agent file lists its
agent-associated skills by path in a `## Skills (Loaded Upfront)` section.
Dispatcher agents that load adapter skills by **convention** (e.g.
`issuer` loading `~/.agent-crew/user/skills/issuer-<tool>.md` based on
the detected git remote) follow the complementary 5-step protocol in
`core/rules/agent-tool-dispatch.md`.

The two conventions are not competing — they answer different
questions:

| Convention | Question answered |
|---|---|
| Declared skill loading (this file) | Which skills are associated with this agent and therefore loaded upfront, and which phases require explicit application? |
| Convention-based dispatch (`agent-tool-dispatch.md`) | Which adapter skill does this agent need *given runtime conditions* (git remote, framework manifest, etc.)? |

An agent may use both simultaneously. For example, a future `backend`
dispatcher MAY declare `tdd.md` + `effective-kotlin.md` via the
agent-associated section above while also dispatching to
`backend-kotlin-spring` via convention.
