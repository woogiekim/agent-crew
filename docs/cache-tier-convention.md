# Prompt-cache tier convention for agent definitions

This convention applies to every Markdown file under `core/agents/` and the
`core/agents/skills/` skill files. Following it lets prompt-cache-aware
hosts (Claude API and equivalents) reach the highest possible cache hit
rate when an agent is invoked many times across a session and across
sessions.

## Rationale

When a host caches a prompt, the cache key is a prefix of the prompt
content. The longer the cache prefix the host can match against the
incoming prompt, the lower the per-invocation cost. If your agent file
mixes stable identity content with per-turn output formatting, the
cache prefix terminates at the first volatile block — even if all the
content below it would also have been a cache hit.

By **ordering content within each agent file from most-stable to
most-volatile**, the cache prefix can extend deep into the file before
it hits the first per-turn variable. For an agent invoked 50 times in
a single session this is a meaningful cost reduction.

## The four tiers

Every agent file SHOULD lay out its content in this order:

### Segment 1 — Static (top of file, just below frontmatter)

Content that is identical across every invocation of every agent.
Changes only when the agent itself is redesigned.

Examples:

- Agent identity, role, summary
- Hard rules ("MUST NOT do X", "always Y")
- References to skills (`Read core/agents/skills/...`)
- References to framework conventions (`per core/rules/...`)
- Cross-cutting policies that apply to every Phase or Step

### Segment 2 — Session-stable

Content that is constant for the lifetime of one crew session but may
differ between projects, hosts, or capability flag configurations.

Examples:

- Capability flag references (`if HAS_TASK_TOOLS == 1...`)
- Adapter notes ("on a host with `agent_background = true`...")
- Log format conventions tied to the host's progress mechanism
- Stable lists of MCP tool names this agent depends on

### Segment 3 — Task-variable

Phase-specific procedures that reference TASK / TASK_ID / PRD /
REQUIREMENTS / PROJECT_ROOT. These vary per task but stay constant
within one task's execution.

Examples:

- Phase 1 dispatch procedures
- Phase 2 stage protocols
- Plan-approval contracts
- Step-by-step workflow content keyed off task inputs

### Segment 4 — Turn-variable (bottom of file)

Per-stage / per-iteration concerns that are most likely to be affected
by what just happened in the previous turn.

Examples:

- STATUS handling (per-iteration close-out)
- Retry rules (per-attempt counter state)
- Individual stage emit patterns
- Per-turn output format templates
- Current-iteration completion checklists

## The execution-flow exception

Some content carries semantic ordering — "Phase 0 must come before
Phase 1", "Acceptance Criteria must follow the protocol it qualifies",
"Resume Check must precede normal startup". These execution-flow
dependencies dominate the cache-tier ordering.

**Where execution-flow order conflicts with stability-tier order,
execution-flow order wins.** Do not break the agent's instructions to
optimize cache. The four tiers apply to **independent content blocks**
whose order does not carry semantic meaning.

In practice this means: a Phase 0 block that contains capability flag
loading (segment 2 by content) belongs at the top of the execution
section because it must run first, not because it's session-stable.
Do not extract it to a separate segment-2 block above the execution
flow.

## Skills are exempt

Files under `core/agents/skills/` are pure segment-1 content (stable
methodology references loaded on demand). They follow a different
canonical shape (Purpose → When to Apply → Techniques → Checklist) and
do not need tier reordering.

## Reference files

- `core/agents/supervisor.md` — the post-C2 supervisor index. Identity →
  cross-cutting principles → progress reporting → input parameters →
  phase routing → absolute rules. Already aligned.
- `core/agents/analyst.md` — frontmatter → identity → skills → inputs
  → workflow steps → rules. Canonical small-agent shape.
- `core/agents/mentor.md` (post-C1) — illustrates moving
  cross-cutting policies (glossary rules, language adaptation,
  behavioral principles) above the per-Phase execution body.
- `core/agents/devops.md` (post-C1) — illustrates promoting hard rules
  (`# YOU MUST NOT`) from the bottom of the file to immediately after
  identity / skills.

## Checklist for adding a new agent

When you create a new `core/agents/{name}.md` file:

- [ ] YAML frontmatter on lines 1 to ~12 (provider-neutral identity).
- [ ] Identity / role heading immediately after frontmatter.
- [ ] Skills section (`## Skills (Loaded Upfront)`) above any
      execution content, listing agent-associated skill files that load upfront.
- [ ] Hard rules and absolute prohibitions ("YOU MUST NOT", "Absolute
      Rules") near the top — segment 1 — not at the bottom of the file.
- [ ] Inputs / parameter shape declared before the execution flow.
- [ ] Capability flag handling, when present, sits inside the execution
      step that needs it (execution-flow exception) rather than as a
      separate top-level block.
- [ ] Workflow / Execution Flow steps numbered or named in execution
      order — these are segment 3 and 4, near the bottom.
- [ ] Per-iteration close-out content (STATUS handling, return value
      contract) at the very bottom.
- [ ] Cross-references go by name (`see Phase 1d`, `see
      core/rules/quality-loop.md`), never by line number.

When in doubt: ask "if I changed only this block, would I want every
other agent invocation today to invalidate its cache?" If no → move it
up. If yes → it belongs lower.

## Related files

- `core/agents/` — the directory this convention governs
- `docs/adapter-authoring.md` — the companion guide for writing host
  adapters; the two are independent but contributors writing both new
  adapters and new agents should read both
- `core/rules/host-capabilities.md` — the capability flags that
  segment-2 content typically references
