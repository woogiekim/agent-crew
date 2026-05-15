---
name: agent-crew
description: Use when the user invokes agent-crew workflow commands in Codex, including crew:setup, crew:run, crew:status, crew:cost, or crew:agent-maker. Also use for natural-language coding, implementation, refactoring, migration, testing, deployment, or agent-crew workflow requests in a workspace initialized with agent-crew. This skill bootstraps agent-crew before project-local AGENTS.md or .codex hooks exist, and prevents Codex from interpreting crew commands as generic repository inspection, verification, CI, Gradle, npm, lint, or direct implementation requests.
---

# Agent Crew Command Bootstrap

This skill handles provider-neutral agent-crew workflow commands inside Codex.

Codex may run without trusted lifecycle hooks, or hooks may inject only advisory
context. This skill is therefore the Codex fallback routing layer. Treat these
rules as authoritative even when `~/.agent-crew/hooks/auto-route.sh` did not
inject `[agent-crew]` context.

## Command Recognition

When the user message begins with one of these command forms, treat it as an
explicit command invocation, not ordinary natural language:

- `crew:setup`
- `crew:run`
- `crew:run "..."`
- `crew:status`
- `crew:cost`
- `crew:agent-maker`

Do not reinterpret these commands as requests to inspect the repository, run
Gradle, run npm, run CI, lint, test, or perform a host-default validation pass.

## Natural-Language Routing

When the user asks Codex to build, implement, create, add, update, fix, remove,
move, change, migrate, refactor, replace, extend, integrate, test, deploy,
merge, roll back, or otherwise perform development work, route the request
through `crew:run`.

This includes Korean equivalents such as:

- `구현`, `개발`, `추가`, `수정`, `개선`, `보완`
- `변경`, `삭제`, `이동`, `마이그레이션`, `리팩터링`
- `테스트`, `배포`, `머지`, `롤백`, `반영`

Do not start by reading repository files, running shell commands, editing files,
or asking implementation questions unless the loaded command definition requires
that step.

Respond directly only when the user is asking a pure explanation or diagnostic
question, such as "how", "why", "what", "explain", "describe", `어떻게`, `왜`,
`무엇`, or `설명`, and the message does not also request implementation.

## Dependency Inversion Boundary

Keep workflow decisions dependent on the provider-neutral command definitions
under `~/.agent-crew/commands/` and global rules under `~/.agent-crew/AGENTS.md`.
Codex-specific behavior in this skill may only select and invoke those workflow
intents. Do not duplicate task-runner, planner, backend, frontend, resolver, or
approval logic inside this skill.

## Execution Map

Load and follow the matching command definition:

| User command | Command definition |
|---|---|
| `crew:setup` | `~/.agent-crew/commands/setup.md` |
| `crew:run` | `~/.agent-crew/commands/run.md` |
| `crew:status` | `~/.agent-crew/commands/status.md` |
| `crew:cost` | `~/.agent-crew/commands/cost.md` |
| `crew:agent-maker` | `~/.agent-crew/commands/agent-maker.md` |

If the command definition file is missing, tell the user to install agent-crew
globally first.

## `crew:setup` Rules

For `crew:setup`, execute the setup workflow directly:

1. Read `~/.agent-crew/commands/setup.md`.
2. Follow its steps exactly.
3. Run the host adapter setup dispatcher as specified there.
4. Initialize the agent-crew state directory.

Before setup, do not inspect repository build files, package manifests, Gradle
configuration, CI files, or existing source code unless the setup command file
explicitly asks for that.

## `crew:run` Rules

For `crew:run`, execute the full orchestration workflow from
`~/.agent-crew/commands/run.md`:

1. Treat arguments after `crew:run` as task descriptions.
2. If no task description is provided, follow Step 1 of the command definition
   and ask for the task through the host structured input UI.
3. Perform mandatory requirements collection.
4. Delegate to task-runner as defined by the command.
5. Show the required run and implementation summaries.

Never replace `crew:run` with `./gradlew check`, `npm test`, linting, generic
CI, repository validation, or direct implementation.

## Codex Auto-Route Fallback

For a natural-language implementation request, behave as if the user had typed:

```text
crew:run "{original request}"
```

Then execute the full `crew:run` workflow from `~/.agent-crew/commands/run.md`.
Preserve the original user wording as the task input, subject to the command
definition's required normalization and requirements-collection steps.

## Capability fallbacks

Codex does not currently expose a native structured-question tool. The Codex
adapter therefore advertises `interactive_question = false` in its
`capabilities.json` (see `core/rules/host-capabilities.md` and
`core/rules/capabilities/interactive-question.md`).

When core emits an `ask_question(prompt, options[])` intent — for example, at
the `crew:run` Step 1.5 injection prompt, the task-runner Phase 1d plan
approval gate, or the Phase 2.5 stage action gate — Codex MUST fall back to a
**structured markdown question** in the chat. The format is:

```markdown
{prompt}

Pick one (reply with the option number):

1. **{label_1}** — {description_1}
2. **{label_2}** — {description_2}
3. **{label_3}** — {description_3}
0. **cancel**
```

Rules for the markdown fallback:

- Always include numbered options (1..N) plus an explicit `0. **cancel**`.
- Use one option per line; do not collapse into prose.
- After printing, **stop and wait** for the user's reply. Do not infer the
  user's choice from prior context.
- When the user replies with a number, treat the corresponding option as the
  selected `chosen_label` and proceed exactly as `ask_question` would have on
  a host where `interactive_question=true`. When the user replies with `0`,
  `cancel`, `취소`, or any free-text refusal, treat the result as the
  `__cancelled__` sentinel and route to the cancel branch in the calling
  command definition.
- Never ask plain-text yes/no questions ("Should I deploy?", "Shall I merge?")
  — that violates both `core/rules/disambiguation.md` and the centralized
  approval-gate rule in `core/global-agents.md`.
- Cache the user's resolved choice in the task's state directory so a retry
  of the same stage does not re-prompt (see
  `core/rules/disambiguation.md` Implementation Requirements §4).

This fallback is the operational path for every `ask_question` intent emitted
by core when running under the Codex adapter. If a future Codex release
exposes a native elicitation surface, `adapters/codex/setup.sh` may flip
`interactive_question` to `true` and bind the intent to that surface in this
file's "Capability mappings" section (currently absent — Codex has no other
host-bound tool calls today, so no mapping table is yet warranted).
