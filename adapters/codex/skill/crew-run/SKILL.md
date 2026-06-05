---
name: crew-run
description: Use when the user explicitly mentions $crew-run or asks to run an agent-crew task workflow in Codex. This is a thin Codex skill wrapper for crew:run and delegates all behavior to ~/.agent-crew/commands/run.md.
---

# crew-run

This Codex skill is an alias for:

```text
crew:run
```

## Execution

1. Load `~/.agent-crew/commands/run.md`.
2. Treat any user text after `$crew-run` as the task description.
3. Preserve any explicitly invoked or domain-specific Codex skill context as
   task input for requirements collection, supervisor handoffs, and generated
   prompts.
4. Follow the command definition exactly, including mandatory requirements collection.
5. Delegate execution to supervisor as defined by the command.

## Current-Session Fallback

When `crew:run` returns `HOST_BRIDGE: current_session_required`, continue from
the printed `handoff.md` in the current Codex session. Before doing any task
work, re-apply specialist selection: choose the appropriate agent/user-agent,
subagent(s), and agent skill(s) for the normalized task. This is a general
dispatch requirement for all task axes. It is not limited to commits, deploys,
or any single operation.

Record the selection in `{TASK_DIR}/context/specialist-dispatch.md` before
manual execution. Include `selected_agent`, `selection_reason`, and
`execution_mode`; include any applicable `selected_user_agent`,
`selected_subagents`, and `selected_skill` / `selected_skills` entries. If no
specialist exists, state why and proceed through the regular supervisor/planner
path rather than inventing an ad hoc shortcut.

Load the applicable skill files before acting and record the exact loaded skill
path(s) in `{TASK_DIR}/context/skill-load.md` or
`{TASK_DIR}/context/skill-load.json`. Every selected skill name must have
matching load evidence (`selected_skill: frontend-typescript-react` requires
`frontend-typescript-react.md`, `selected_skill: tdd` requires `tdd.md`).
Repairing a mutating current-session fallback as completed may reject the
handoff when skill-load evidence is missing.

Record how every loaded non-TDD skill was applied in
`{TASK_DIR}/context/skill-use.json` or `{TASK_DIR}/context/skill-use.md`. Each
entry must include `skill_path`, `applied_rules`, `evidence_refs`,
`output_files`, and `verification`. TDD remains covered by red/green/refactor
evidence; other loaded skills require concrete use evidence, not only load
evidence.

Before applying each loaded non-TDD skill, record operational understanding in
`{TASK_DIR}/context/skill-plan.json` or `{TASK_DIR}/context/skill-plan.md`:
`skill_path` plus rule-level `rule_id` or `invariant`,
`task_interpretation`, and `planned_application`. After applying the rule, add
matching `rule_evidence` to `{TASK_DIR}/context/skill-use.json` with
`artifact_refs`, `diff_refs`, `verification`, `adversarial_checks`, and
`reviewer_status: approved`. Repairing a mutating current-session fallback as
completed may reject the handoff when a loaded non-TDD skill is used without
this understanding evidence.

For implementation or other production-code mutations with a testable surface,
do not patch production code until the focused test target is identified,
added or updated, run, and recorded as expected failing red-phase evidence in
`{TASK_DIR}/context/tdd-red.md`. If a runnable harness or red failure cannot
reasonably be produced, record the explicit exception first in
`{TASK_DIR}/context/tdd-exception.md`. After green, perform the refactor review
or document a no-op refactor decision, rerun focused verification, and record it
in `{TASK_DIR}/context/tdd-refactor.md`. Repairing a mutating current-session
fallback as completed may reject the handoff when red-phase/exception evidence
or refactor-phase evidence is missing.

Do not implement directly, run generic verification, inspect the repository as a substitute, or duplicate supervisor logic in this skill.
