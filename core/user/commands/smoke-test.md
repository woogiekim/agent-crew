# /smoke-test — Local server plus Docker dependency smoke verification

## Purpose

Run a small, evidence-backed smoke test for the current task or an explicitly
named scope by running this project server locally and using Docker only for
external systems such as DB, Redis, message brokers, and mock upstreams.
IntelliJ `.http` requests are the primary request surface.

The command is for fast local confidence, not for deployment, remote CI, merge
approval, or exhaustive E2E coverage.

## Trigger

- Codex: `$smoke-test`
- Codex: `$smoke-test <scope>`
- Claude Code: `/smoke-test`
- Claude Code: `/smoke-test <scope>`
- Provider-neutral notation: `smoke-test <scope>`

## Inputs

- `SCOPE` optional.
  - Empty: use the current task TC from the active agent-crew task context.
  - Present: resolve the argument as a commit, issue, MR/PR, branch, endpoint,
    file path, ticket id, or free-text smoke target.
- `FEATURE_NAME` optional human feature name used for artifact naming. If not
  provided, derive it from the resolved TC, endpoint, controller/usecase, or
  user-facing feature wording.
- `PROJECT_ROOT` optional local repository root. Defaults to the current
  working root.
- `LOCAL_SERVER_COMMAND` optional command or IDE run configuration for the
  project server.
- `DOCKER_DEPENDENCIES` optional list of external systems to run in Docker,
  such as DB, Redis, Kafka, localstack, or mock HTTP services.
- `HTTP_FILE` optional IntelliJ `.http` file or request name to prefer.

## Defaults

- Local-only.
- Read-only requests only.
- Exclude full-service local environment orchestrators for the project
  application server.
- Run the project application server as a local process, IDE run configuration,
  or local build-tool task.
- Use Docker only for external systems that the project server depends on.
- Reuse already-running matching local server and Docker dependency containers
  when available.
- Use IntelliJ `.http` requests before shell HTTP clients.
- Do not push, merge, deploy, close issues, post remote comments, or mutate
  external systems.

## Scope Resolution

1. Preserve the raw command text.
2. If `SCOPE` is empty, resolve the current task TC from the active task
   directory:
   - `${TASK_DIR}/context/test-case-mapping.*`
   - `${TASK_DIR}/context/quality-plan.*`
   - `${TASK_DIR}/handoff.md`
   - `${TASK_DIR}/progress.log`
   - `${TASK_DIR}/context/`
3. If no current task TC can be found, stop with `STATUS: blocked` and ask for
   a scope. Do not invent a smoke target from repository names or memory.
4. If `SCOPE` is present, classify it without remote mutation:
   - commit SHA or ref: inspect local diff/history only;
   - issue, ticket, MR, or PR id: use locally available state first, and use
     remote reads only when the invoking environment already has an approved
     read-only command or the user explicitly supplied the remote context;
   - path or endpoint: verify it exists or is reachable in local code/config;
   - free text: convert it into one or more read-only local HTTP scenarios.
5. Resolve `FEATURE_NAME` for artifact naming from the feature under test, not
   from tracking metadata. Prefer names like `client-company-list`,
   `review-meta-audit`, or `article-search-filter`. Do not use issue, ticket,
   MR, PR, branch, or commit identifiers as the artifact name.

## Local Server And Docker Dependency Resolution

1. Do not start the project application server through a full-service local
   environment orchestrator.
2. Detect an existing local project server before starting anything. Reuse it
   when its project root, branch, profile, and port match the target.
3. If no usable local project server exists, start only the target project
   server through the repository's normal local command, build-tool task, or IDE
   run configuration.
4. Start or reuse Docker containers only for external systems required by that
   server, such as DB, Redis, Kafka, localstack, mock HTTP services, or other
   infrastructure dependencies.
5. Do not containerize the project application server for this smoke workflow.
6. Do not kill unrelated processes or containers. If a port conflict, stale
   process, or stale container blocks the smoke test, report the process or
   container, port, proposed action, and risk, then stop for user approval.
7. Treat HTTP server startup as separate from downstream completion. A live
   port is not proof that the smoke scenario passed.

## IntelliJ HTTP First

1. Search the target repository for existing `.http` files before composing
   shell commands.
2. Prefer a request that already matches the endpoint, ticket, controller, or
   TC. If multiple requests match, present numbered choices.
3. If no request exists, create or present the smallest `.http` request needed
   to exercise the smoke target. Keep it local and read-only unless the user
   explicitly approves a mutating smoke.
4. Execute through IntelliJ HTTP when available in the host environment. If it
   is not available, present the `.http` request as the primary artifact and
   use a shell HTTP fallback only after explaining the fallback.
5. Capture request method, URL, headers that matter, response status, response
   shape, and any downstream evidence required by the TC.

## Artifact Naming

1. Name generated smoke artifacts with the feature name:
   `smoke-<feature-name>-<timestamp>.md`.
2. Do not include issue, ticket, MR, PR, branch, or commit identifiers in the
   filename, even when `SCOPE` was supplied as one of those identifiers.
3. If the feature name cannot be derived safely, stop with `STATUS: blocked`
   and ask for the feature name instead of falling back to an identifier.
4. The report body may mention the supplied issue, MR, branch, commit, or ticket
   as scope evidence, but the artifact filename remains feature-based.

## Smoke Execution Flow

1. Resolve scope and TC.
2. Resolve `FEATURE_NAME` for artifact naming.
3. Resolve local project root, local server command, and Docker dependency set.
4. Confirm or start the local project server.
5. Confirm or start only the required external systems in Docker.
6. Select or prepare the IntelliJ `.http` request.
7. Run the read-only smoke request.
8. Verify the expected observable result:
   - HTTP status and response shape;
   - contract-critical fields;
   - logs or downstream read-only evidence when the TC requires it;
   - absence of unexpected error logs for the exercised request path.
9. If the smoke requires a mutating HTTP method, destructive action, remote
   write, data repair, deploy, push, or issue transition, stop and return the
   proposed action, risk, and required approval. Do not execute it inside this
   command.

## Output

```text
STATUS: completed | blocked | cancelled
SCOPE: <resolved scope>
TC: <current task TC or explicit smoke target>
FEATURE_NAME: <feature-name-slug>
PROJECT_ROOT: <local root>
LOCAL_SERVER: reused | started | unavailable | not_required
DOCKER_DEPENDENCIES: reused | started | unavailable | not_required
SERVER: <base URL and service name, or "none">
HTTP_SOURCE: <.http path/request name, generated request path, or fallback reason>
REQUEST: <method URL>
RESULT: pass | fail | blocked
EVIDENCE: <status, key response fields, logs/downstream checks>
ARTIFACTS: <.http path/report path if created, otherwise "none">
NEXT_ACTION: <none or required user decision>
```

## Rules

- No argument means current task TC, not repository-wide smoke.
- An argument narrows or replaces the current task scope; it does not authorize
  broad exploratory E2E.
- Artifact filenames use the feature name, not issue, ticket, MR, PR, branch,
  or commit identifiers.
- Do not use a full-service local environment orchestrator for the project
  application server.
- Run the project application server locally, and use Docker only for external
  systems such as DB, Redis, message brokers, localstack, and mock upstreams.
- Reuse matching local server and Docker dependency containers when they fit the
  target.
- IntelliJ `.http` is the primary request surface. Shell HTTP is a fallback, not
  the default.
- Keep smoke requests read-only by default.
- Do not infer remote mutation from issue, MR, PR, or commit arguments.
- Do not kill or restart unrelated local processes without explicit approval.
- Report server readiness and scenario success separately.
- Every `pass` must include observable request/response evidence.
