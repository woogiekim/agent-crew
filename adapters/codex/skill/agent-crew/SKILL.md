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
