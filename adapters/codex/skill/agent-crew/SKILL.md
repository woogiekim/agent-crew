---
name: agent-crew
description: Use when the user invokes agent-crew workflow commands in Codex, including crew:setup, crew:run, crew:status, crew:cost, crew:agent-maker, ac:setup, ac:crew, ac:task, ac:cost, or ac:agent-maker. This skill bootstraps agent-crew before project-local AGENTS.md or .codex hooks exist, and prevents Codex from interpreting crew commands as generic repository inspection, verification, CI, Gradle, npm, or lint requests.
---

# Agent Crew Command Bootstrap

This skill handles provider-neutral agent-crew workflow commands inside Codex.

## Command Recognition

When the user message begins with one of these command forms, treat it as an
explicit command invocation, not ordinary natural language:

- `crew:setup`
- `crew:run`
- `crew:run "..."`
- `crew:status`
- `crew:cost`
- `crew:agent-maker`
- `ac:setup`
- `ac:crew`
- `ac:task`
- `ac:cost`
- `ac:agent-maker`

Do not reinterpret these commands as requests to inspect the repository, run
Gradle, run npm, run CI, lint, test, or perform a host-default validation pass.

## Execution Map

Load and follow the matching command definition:

| User command | Command definition |
|---|---|
| `crew:setup`, `ac:setup` | `~/.agent-crew/commands/setup.md` |
| `crew:run`, `ac:crew`, `ac:task` | `~/.agent-crew/commands/run.md` |
| `crew:status` | `~/.agent-crew/commands/status.md` |
| `crew:cost`, `ac:cost` | `~/.agent-crew/commands/cost.md` |
| `crew:agent-maker`, `ac:agent-maker` | `~/.agent-crew/commands/agent-maker.md` |

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
