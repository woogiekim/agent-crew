# Automatic Issue Reporting

## Purpose

When an operator explicitly reports an agent-crew bug/error, a `crew` command
emits explicit bug/error output through a host hook payload, or the supervisor
halts on an unexpected infrastructure blocker, agent-crew stores a native local
report. GitHub publication is an optional publisher backend, not part of the
hook contract.

This is an advisory reporting path. It must not block the user's current
prompt, tool call, or pipeline execution.

## Hook Surface

The installed hook wrapper is:

```text
core/hooks/auto-issue-report.sh
```

The hook delegates to the native report command:

```text
crew report auto
```

The provider-neutral implementation is:

```text
core/scripts/auto-issue-reporter.py
```

Adapters wire it into:

- `UserPromptSubmit` — detects explicit user reports such as "agent-crew
  error", "에이전트크루 오류", or "crew run traceback".
- `PostToolUse[Bash]` — detects Bash tool payloads whose command actually
  invokes the `crew` executable or `crew:<intent>` notation, and whose tool
  outcome is explicitly failed plus bug/error output. Paths such as
  `.agent-crew/commands/agent.md`, documentation text, and read-only commands
  that merely mention agent-crew are not treated as crew command executions.
  When the host payload has no explicit outcome metadata, the reporter accepts
  only high-confidence failure text from an actual crew invocation, such as
  tracebacks, exceptions, panics, fatal errors, or structured infrastructure
  blockers. Successful payloads are ignored even if their output contains words
  such as `error` in filenames or documentation paths. A non-zero return code
  alone is not enough because normal host handoff blockers also use non-zero
  exits.
- `source=supervisor_blocked` payloads — detects unexpected supervisor
  infrastructure blockers such as schema validation, capability, runtime,
  host-tool, or install drift failures. Normal host bridge handoff blockers
  remain ignored.

## Native Report Outbox

By default, reports are written under:

```text
${AGENT_CREW_REPORT_STATE_DIR}
${AGENT_CREW_AUTO_ISSUE_STATE_DIR}
${AGENT_CREW_HOME}/state/reports
```

Each accepted report has a dedup record under `reported/` and a publishable
JSON document under `outbox/`. This keeps reporting reliable when the operator
is offline, unauthenticated, or using a non-GitHub workflow.

Each outbox document includes stable structured fields:

```text
schema_version
fingerprint
source
classification
title
evidence
body
```

`classification` is one of `user_reported_error`, `crew_command_failure`, or
`infrastructure_blocker`. The report body must label captured text as untrusted
diagnostic evidence so copied prompts, logs, or tool output cannot become
workflow instructions during triage.

## Optional GitHub Publisher

Default GitHub repository:

```text
woogiekim/agent-crew
```

Override with:

```text
AGENT_CREW_AUTO_ISSUE_REPO=owner/repo
```

The reporter uses the `gh` CLI. If `gh` is missing or unavailable, the hook
writes a local queued report and exits successfully.

To publish during automatic reporting:

```text
AGENT_CREW_REPORT_PUBLISH=github
```

To publish queued reports later:

```bash
crew report publish --backend github
```

To quarantine malformed local records and false-positive Bash reports whose
command did not actually invoke crew:

```bash
crew report cleanup --format json
```

## Safeguards

- **Narrow trigger**: prompt reports require both an agent-crew signal and a
  bug/error signal; Bash reports require an actual `crew` invocation, a failed
  or high-confidence failure outcome, and bug/error output. Generic application
  errors, successful diagnostic commands, documentation/path reads, and normal
  host-bridge handoff blockers are ignored.
- **Local deduplication**: reports are fingerprinted and recorded under the
  native report state directory.
- **Remote deduplication**: when `gh` works, the reporter searches existing
  GitHub issues for the fingerprint before creating a new issue.
- **Secret redaction**: common token/password/API-key patterns are redacted
  before publication.
- **Advisory failure mode**: every hook path exits 0. Reporting failure must not
  break the operator workflow.

## Environment Controls

| Variable | Behavior |
|---|---|
| `AGENT_CREW_AUTO_ISSUE_REPORT=0` | Disable automatic issue reporting. |
| `AGENT_CREW_AUTO_ISSUE_REPORT_DISABLED=1` | Disable automatic issue reporting. |
| `AGENT_CREW_REPORT_STATE_DIR=/path` | Override native report state location. |
| `AGENT_CREW_REPORT_PUBLISH=github` | Publish accepted automatic reports through GitHub. Omit for local-only reports. |
| `AGENT_CREW_AUTO_ISSUE_REPO=owner/repo` | Override the GitHub target repository. |
| `AGENT_CREW_AUTO_ISSUE_STATE_DIR=/path` | Legacy alias for native report state location. |
| `AGENT_CREW_AUTO_ISSUE_TTL_SECONDS=N` | Local duplicate suppression window. Default: 7 days. |
| `AGENT_CREW_AUTO_ISSUE_TIMEOUT_SECONDS=N` | Timeout for each `gh` call. Default: 8 seconds. |
| `AGENT_CREW_AUTO_ISSUE_DRY_RUN=1` | Record and report classification without calling `gh`. |

## Manual Diagnostic

```bash
printf '{"prompt":"agent-crew error: traceback"}' \
  | crew report auto --format json
```

## Replay Verification

`core/evaluations/workflow-replay.json` contains a normal-use structured blocker
case that expects `auto-issue-reporter.py` to return `status=recorded`. This
keeps issue-reporting coverage in the deterministic replay suite instead of
only in isolated hook tests.
