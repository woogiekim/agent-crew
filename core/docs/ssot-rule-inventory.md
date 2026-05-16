# Instruction Rule Inventory

This document enumerates the canonical rule IDs derived from the
current `core/global-agents.md` source. It is consumed by
`core/scripts/seed-instruction-rules.sh` to seed the mnemos global
layer on first migration.

Each row maps to a mnemos item with `id = rule:<slug>`, tag
`instruction-rule`, and a body whose YAML front matter declares
`applies_to`. The order in this table is also the default `priority`
order (lower = renders earlier in assembled output).

| # | Rule ID | Title | applies_to | Source section in `core/global-agents.md` |
|---|---|---|---|---|
| 10 | `rule:input-language` | Input Language | all | `## Input Language` |
| 20 | `rule:output-language` | Output Language | claude | `## Output Language` (only present in CLAUDE.md today; promoted to canonical) |
| 30 | `rule:no-direct-implementation` | No Direct Implementation | all | `## No Direct Implementation` |
| 40 | `rule:agent-routing-criteria` | Agent Routing Criteria | all | `## Agent Routing Criteria` |
| 50 | `rule:parallel-first` | Parallel-First Execution Rule | all | `## Parallel-First Execution Rule` |
| 60 | `rule:auto-execution-triggers` | Auto-Execution Triggers | all | `## Auto-Execution Triggers` (includes commit 011e6be's crew:agent routing block) |
| 70 | `rule:codex-routing-fallback` | Codex Routing Fallback | codex | `### Codex Routing Fallback` (host-specific sub-section) |
| 80 | `rule:stop-directive` | STOP Directive Rule | all | `### STOP Directive Rule` |
| 90 | `rule:workflow-intents` | Workflow Intents | all | `## Workflow Intents` |
| 100 | `rule:structured-choice` | Structured Choice Rules | all | `## Structured Choice Rules` |
| 110 | `rule:approval-gate` | Approval Rule (Framework-Level) | all | `## Approval Rule (Framework-Level)` |
| 120 | `rule:subagent-plan-approval` | Subagent Plan Approval Rule | all | `## Subagent Plan Approval Rule` |
| ~~130~~ | ~~`rule:mnemos-capture`~~ | ~~Memory (mnemos)~~ | _excluded_ | The mnemos `Memory` section in `~/.claude/CLAUDE.md` lives between mnemos's OWN marker pair (`<!-- mnemos-start --> ... <!-- mnemos-end -->`) and is managed by the mnemos installer, not by agent-crew. Seeding it here would cause Claude to receive the same guidance twice (once in each marker block). The rule body is intentionally NOT captured to mnemos as an `instruction-rule` — its canonical location is the mnemos installer's templates. |

## Notes

- `rule:codex-routing-fallback` was previously a sub-section of
  Auto-Execution Triggers. It is split out so that the Codex host
  receives it but the others do not — demonstrating the per-host
  filter capability.
- `rule:mnemos-capture` is Claude-specific because it documents the
  hook-injected `/compact` flow; Codex does not have an equivalent
  hook today.
- `rule:output-language` is currently only present in CLAUDE.md but is
  marked Claude-only here. If future Codex / Generic adapters gain the
  same status-keyword parser, add their identifier to `applies_to`.
- All other rules are flagged `applies_to: [all]` and reproduce
  verbatim in every host's marker block. Round-trip identity for
  `rule:auto-execution-triggers` is the key smoke-test target since
  it contains the recent commit 011e6be content.
