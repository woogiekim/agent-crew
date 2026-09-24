---
name: crew:run
description: Use when the user explicitly mentions $crew:run or asks to run an agent-crew task workflow in Codex. This is a thin Codex skill wrapper for crew:run and delegates all behavior to ~/.agent-crew/commands/run.md.
---

# crew:run

This Codex skill is an alias for:

```text
crew:run
```

## Execution

1. Load `~/.agent-crew/commands/run.md`.
2. Treat any user text after `$crew:run` as the task description.
   A leading `$crew:run 코드리뷰` means "run the `코드리뷰` task"; it does
   not mean "review the `$crew:run` skill". Only treat the wrapper itself as
   the review target when the prompt explicitly says the skill, wrapper, file,
   or `SKILL.md` is the object.
3. Preserve explicitly invoked Codex skill context as task input for
   requirements collection, supervisor handoffs, and generated prompts.
   Do not auto-load non-agent-crew or third-party host/plugin skills from
   trigger-description matches during agent-crew execution.
4. Follow the command definition exactly, including mandatory requirements collection.
5. Delegate execution to supervisor as defined by the command. In the
   current-session fallback, the current Codex session itself is that
   supervisor; do not spawn a second top-level supervisor.

## Workflow Origin vs Target Scope

`$crew:run`, `crew:run`, and this wrapper are workflow origins by default. They
become review targets only when the prompt explicitly says the skill, wrapper,
file, command definition, or `SKILL.md` is the object being reviewed.
Only treat the wrapper itself as the review target when that explicit target
wording is present.

## Current-Session Fallback

When `crew:run` returns `HOST_BRIDGE: current_session_required`, continue from
the printed `handoff.md` in the current Codex session. The current session is
the supervisor for the pinned plan. Never spawn or select another top-level
`supervisor` child in this mode. Execute bounded work inline by default; the
default selected subagent set is empty. Before doing any task work, re-apply
specialist and skill selection for the normalized task. Select a child agent
only when it owns an independently bounded unit that materially benefits from
delegation.

Read `{TASK_DIR}/context/current-session-execution.json` and obey its wait and
lifecycle bounds. Its `execution_profile` is authoritative:

- `inline_tdd`: keep the whole simple implementation in the current session;
  do not spawn requirements, brainstorm, analyst, planner, test-writer, or
  reviewer children. Perform the listed quality gates inline.
- `inline_readonly`: perform the read-only investigation and inline review in
  the current session without manufacturing a TDD cycle.
- `full_crew`: delegate only the independently bounded specialist units needed
  by the pinned plan. The current session still remains the top-level
  supervisor.

For an inline profile, record every `required_quality_gates` entry as `passed`
in `{TASK_DIR}/context/inline-execution.json`. Do not mark a gate passed without
its real test, diff, or task evidence. If scope ambiguity, cross-repository
dependencies, useful parallel units, external writes, or hard-to-reverse risk
are discovered, escalate to `full_crew` and record the reason instead of
continuing with an invalid inline profile.

Every selected child must have a lifecycle record under
`{TASK_DIR}/context/stage-lifecycle/` that reaches `terminal_completed` and
`parent_resumed`. A bounded wait may not exceed `max_wait_seconds_per_call`.
After `max_unchanged_waits` unchanged waits, inspect or interrupt the exact
child instead of polling indefinitely. Completion repair rejects a nested
supervisor and any selected child without terminal and parent-resume evidence.

Record the selection in `{TASK_DIR}/context/specialist-dispatch.md` when
available before manual execution. Include `selected_agent`, `selection_reason`,
and `execution_mode`; include any applicable `selected_user_agent`,
`selected_subagents`, and `selected_skill` / `selected_skills` entries. Missing
or incomplete dispatch coverage is reported as an advisory gap during repair.
For an inline profile, the absence of child specialists is intentional rather
than a dispatch gap. Execute the pinned plan as the current-session supervisor.

Load only applicable agent-crew skills before acting and record the exact loaded
skill path(s) in `{TASK_DIR}/context/skill-load.md` or
`{TASK_DIR}/context/skill-load.json` when available. Agent-crew skills are the framework
system/user skills under `~/.agent-crew/system/skills/`,
`~/.agent-crew/user/skills/`, `~/.agent-crew/skills/`,
`~/.agent-crew/system/agents/skills/`, or the active host's agent-crew mirrors
under paths such as `~/.claude/agent-crew/skills/`,
`~/.claude/agent-crew/agents/skills/`, `~/.codex/agent-crew/skills/`, or
agent-crew host wrapper skills such as `~/.codex/skills/crew:<intent>/`. Every
selected skill name should have matching load coverage (`selected_skill:
frontend-typescript-react` maps to `frontend-typescript-react.md`,
`selected_skill: tdd` maps to `tdd.md`). Do not load unrelated host/plugin
skills, including plugin cache skills, by description match. If a
non-agent-crew skill is genuinely needed, ask for explicit user approval first
and record it in `{TASK_DIR}/context/external-skill-approval.md` or `.json`.
Repair reports missing or incomplete skill-load coverage as advisory gaps. It
still rejects an external host/plugin skill load when explicit user approval is
missing.

Optional skill-use notes may be recorded in
`{TASK_DIR}/context/skill-use.json` or `{TASK_DIR}/context/skill-use.md`, but
they are diagnostic coverage, not required proof artifacts. TDD and other
loaded skills are covered first by real task outcomes, tests, diffs, reviews,
pipeline/progress state, reviewer quality metrics, and tool events; repair
should report missing or incomplete notes as advisory gaps instead of rejecting
standard-risk completion.

Optional operational understanding notes may be recorded in
`{TASK_DIR}/context/skill-plan.json` or `{TASK_DIR}/context/skill-plan.md` and
linked from `rule_evidence` in `context/skill-use.json`, but these notes are
diagnostic coverage only. Repair should surface missing skill-plan or
rule-evidence notes as advisory gaps when actual task outcomes, tests, diffs,
reviews, or tool events are sufficient.

For implementation or other production-code mutations with a testable surface,
do not patch production code until the focused test target is identified, added
or updated, and run. If a runnable harness or red failure cannot reasonably be
produced, make the explicit exception available before implementation. After
green, perform the refactor review or document a no-op refactor decision and
rerun focused verification. Repairing production-code implementation as
completed may reject missing runtime quality-loop outcomes or high-risk hard
blockers, but standard-risk missing phase-note artifacts are advisory coverage
gaps.

Outside the current-session fallback, do not implement directly or duplicate
supervisor logic in this skill. Inside the fallback, execute only the already
pinned plan as the inline supervisor; do not re-plan or widen scope.
