# Instruction Rule Inventory

This document enumerates the repository baseline rule IDs consumed by
`core/scripts/seed-instruction-rules.sh`. Mnemos is canonical after initial
migration: `bootstrap-missing` creates absent items but preserves every
existing rule, while `runtime-command-surface` reconciles only its explicitly
maintained command-contract subset.

Each row maps to a mnemos item with `id = rule:<slug>`, tag
`instruction-rule`, and a body whose YAML front matter declares
`applies_to`. The order in this table is also the default `priority`
order (lower = renders earlier in assembled output).

| # | Rule ID | Title | applies_to | Source section in `core/global-agents.md` |
|---|---|---|---|---|
| 10 | `rule:input-language` | Raw Input Preservation | all | `## Raw Input Preservation` |
| 20 | `rule:output-language` | Output Language | claude | `## Output Language` |
| 30 | `rule:no-direct-implementation` | Explicit Execution Entry | all | `## Explicit Execution Entry` |
| 40 | `rule:agent-routing-criteria` | Run And Agent Boundaries | all | `## Run And Agent Boundaries` |
| 50 | `rule:parallel-first` | Candidate And Registry Boundaries | all | `## Candidate And Registry Boundaries` |
| 60 | `rule:auto-execution-triggers` | Hidden Routing Prohibition | all | `## Hidden Routing Prohibition` |
| 65 | `rule:code-style-context-breaks` | Code Style Context Breaks | all | `## Code Style Context Breaks` |
| 70 | `rule:codex-routing-fallback` | Codex Routing Fallback | codex | `### Codex Routing Fallback` (host-specific adapter wrapper) |
| 75 | `rule:current-session-fallback` | Current-Session Fallback | all | `### Current-Session Fallback` (host-neutral fallback evidence requirements) |
| 80 | `rule:stop-directive` | Technical Hook Boundary | all | `## Technical Hook Boundary` |
| 85 | `rule:route-directive` | Explicit Scope Boundary | all | `## Explicit Scope Boundary` |
| 90 | `rule:workflow-intents` | Workflow Intents | all | `## Workflow Intents` |
| 100 | `rule:structured-choice` | Structured Choice Rules | all | `## Structured Choice Rules` |
| 110 | `rule:approval-gate` | Approval Rule (Framework-Level) | all | `## Approval Rule (Framework-Level)` |
| 120 | `rule:subagent-plan-approval` | Risky Action Execution Rule | all | `## Risky Action Execution Rule` |
| ~~130~~ | ~~`rule:mnemos-capture`~~ | ~~Memory (mnemos)~~ | _excluded_ | The mnemos `Memory` section in `~/.claude/CLAUDE.md` lives between mnemos's OWN marker pair (`<!-- mnemos-start --> ... <!-- mnemos-end -->`) and is managed by the mnemos installer, not by agent-crew. Seeding it here would cause Claude to receive the same guidance twice (once in each marker block). The rule body is intentionally NOT captured to mnemos as an `instruction-rule` — its canonical location is the mnemos installer's templates. |

## Notes

- `rule:codex-routing-fallback` contains only the Codex host adapter wrapper.
  Current-session fallback evidence requirements are host-neutral and live in
  `rule:current-session-fallback`, so Claude and Codex receive the same TDD,
  skill-load, skill-use, specialist-dispatch, and repair obligations.
- `rule:mnemos-capture` is Claude-specific because it documents the
  hook-injected `/compact` flow; Codex does not have an equivalent
  hook today.
- `rule:output-language` is currently only present in CLAUDE.md but is
  marked Claude-only here. If future Codex / Generic adapters gain the
  same status-keyword parser, add their identifier to `applies_to`.
- All other baseline rules are flagged `applies_to: [all]`. Additional global
  instruction rules may exist only in mnemos; the bootstrap profile does not
  claim ownership of or remove those additions.
