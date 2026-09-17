---
name: smoke-test
description: Use when the user explicitly invokes $smoke-test to run a local smoke verification using IntelliJ .http requests, with the project server running locally and only external systems such as DB or Redis running in Docker.
---

# smoke-test

This Codex skill delegates to the provider-neutral workflow in
`~/.agent-crew/commands/smoke-test.md`.

## Execution

1. Load `~/.agent-crew/commands/smoke-test.md` in full before acting.
2. Treat text after `$smoke-test` as the smoke scope. With no text after the
   command, resolve the current task TC from the active agent-crew task context.
3. Name smoke artifacts by feature name, not by issue, ticket, MR, PR, branch,
   or commit identifiers.
4. Use a local project server, not a full-service local environment
   orchestrator. Reuse an existing matching local project server when it fits
   the target.
5. Use Docker only for external systems such as DB, Redis, message brokers,
   localstack, and mock upstreams.
6. Use IntelliJ `.http` requests as the primary request surface. Fall back to
   shell HTTP only when IntelliJ HTTP is unavailable or the command definition
   allows the fallback.
7. Remain local-only and read-only by default. Stop for approval before any
   mutating request, process kill/restart that affects unrelated services,
   remote write, push, merge, deploy, or issue transition.
8. Report server readiness separately from the actual smoke scenario result.
