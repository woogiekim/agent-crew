# agent-crew 3-Minute Quick Start

This path gets a project from zero to a visible agent-crew handoff without
requiring the operator to understand the full state model first.

## 0:00-0:45 — Install Or Refresh

```bash
curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash
source ~/.zshrc
```

For an existing install:

```bash
crew update
```

## 0:45-1:15 — Initialize The Project

Run this from the repository root:

```bash
crew setup
crew doctor --mode host
```

Expected outcome:

```text
Summary: N pass, 0 warn, M info
```

`info` is acceptable for capability-gated hosts such as Codex default mode.
Warnings need attention before trusting a long workflow.

## 1:15-2:15 — Start A Real Task

Inside the host AI session, use workflow notation:

```text
crew:run "Add a small validation feature with tests"
```

From a terminal, the native command creates the same state and handoff:

```bash
crew run "Add a small validation feature with tests"
```

If the host bridge cannot complete automatically, continue from the printed
`NEXT` handoff path in the same host session. After the manual continuation is
done, record the outcome:

```bash
crew repair TASK_ID --status completed --note "Completed in host session"
```

For read-only validation tasks, attach the report and state why implementation
quality-loop evidence is not applicable:

```bash
crew repair TASK_ID \
  --status completed \
  --evidence dist/report.json \
  --quality-bypass-reason "Read-only validation; no production files edited." \
  --note "Validation completed."
```

## 2:15-3:00 — Monitor And Debug

```bash
crew status --summary
crew trace --recent 1
crew telemetry --recent 5
crew doctor --mode runtime
```

Use `crew status` when you need the full recent-task table. Use
`crew status --json` or `crew doctor --format json` when another tool needs
machine-readable evidence. Use text mode for operators; `crew doctor` ends with
a compact pass/warn/info summary.

## What To Remember

- `crew:run` is for implementation, mutation, git, release, and validation work.
- `crew:agent` is for read-only questions and analysis.
- State lives under `~/.agent-crew/state/<project>/`.
- If a host bridge stalls, do not guess: read the printed `NEXT` line, continue
  the handoff, then use `crew repair` or `crew cancel`.
