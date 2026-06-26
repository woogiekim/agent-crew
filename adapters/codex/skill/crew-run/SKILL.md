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
   A leading `$crew-run 코드리뷰` means "run the `코드리뷰` task"; it does
   not mean "review the `$crew-run` skill". Only treat the wrapper itself as
   the review target when the prompt explicitly says the skill, wrapper, file,
   or `SKILL.md` is the object.
3. Preserve explicitly invoked Codex skill context as task input for
   requirements collection, supervisor handoffs, and generated prompts.
   Do not auto-load non-agent-crew or third-party host/plugin skills from
   trigger-description matches during agent-crew execution.
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

Load only applicable agent-crew skills before acting and record the exact loaded
skill path(s) in `{TASK_DIR}/context/skill-load.md` or
`{TASK_DIR}/context/skill-load.json`. Agent-crew skills are the framework
system/user skills under `~/.agent-crew/system/skills/`,
`~/.agent-crew/user/skills/`, `~/.agent-crew/skills/`,
`~/.agent-crew/system/agents/skills/`, or the active host's agent-crew mirrors
under paths such as `~/.claude/agent-crew/skills/`,
`~/.codex/skills/agent-crew/`, and `~/.codex/agent-crew/skills/`. Every selected
skill name must have matching load evidence (`selected_skill:
frontend-typescript-react` requires `frontend-typescript-react.md`,
`selected_skill: tdd` requires `tdd.md`). Do not load unrelated host/plugin
skills, including plugin cache skills, by description match. If a
non-agent-crew skill is genuinely needed, ask for explicit user approval first
and record it in `{TASK_DIR}/context/external-skill-approval.md` or `.json`.
Repairing a mutating current-session fallback as completed may reject the
handoff when skill-load evidence is missing or when an external skill lacks
approval.

Optional skill-use notes may be recorded in
`{TASK_DIR}/context/skill-use.json` or `{TASK_DIR}/context/skill-use.md`, but
they are diagnostic coverage, not required proof artifacts. TDD remains covered
by red/green/refactor evidence. For other loaded skills, real task outcomes,
tests, diffs, reviews, and tool events are the evidence that the skill was
applied; repair should report missing or incomplete skill-use notes as advisory
gaps instead of rejecting completion.

Optional operational understanding notes may be recorded in
`{TASK_DIR}/context/skill-plan.json` or `{TASK_DIR}/context/skill-plan.md` and
linked from `rule_evidence` in `context/skill-use.json`, but these notes are
diagnostic coverage only. Repair should surface missing skill-plan or
rule-evidence notes as advisory gaps when actual task outcomes, tests, diffs,
reviews, or tool events are sufficient.

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
