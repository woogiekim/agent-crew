# Automatic Issue Reporting

## Purpose

When an operator explicitly reports an agent-crew bug/error, or a `crew`
command emits explicit bug/error output through a host hook payload, agent-crew
can automatically publish a GitHub issue to the agent-crew remote repository.

This is an advisory reporting path. It must not block the user's current
prompt, tool call, or pipeline execution.

## Hook Surface

The installed hook wrapper is:

```text
core/hooks/auto-issue-report.sh
```

The provider-neutral implementation is:

```text
core/scripts/auto-issue-reporter.py
```

Adapters wire it into:

- `UserPromptSubmit` — detects explicit user reports such as "agent-crew
  error", "에이전트크루 오류", or "crew run traceback".
- `PostToolUse[Bash]` — detects Bash tool payloads whose command is a `crew` /
  agent-crew command and whose output contains an explicit bug/error signal.
  A non-zero return code alone is not enough because normal host handoff
  blockers also use non-zero exits.

## Publication Target

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

## Safeguards

- **Narrow trigger**: prompt reports require both an agent-crew signal and a
  bug/error signal; Bash reports require a `crew` command plus bug/error output.
  Generic application errors and normal host-bridge handoff blockers are
  ignored.
- **Local deduplication**: reports are fingerprinted and recorded under
  `${AGENT_CREW_AUTO_ISSUE_STATE_DIR}` or
  `${AGENT_CREW_HOME}/state/auto-issue-reports`.
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
| `AGENT_CREW_AUTO_ISSUE_REPO=owner/repo` | Override the GitHub target repository. |
| `AGENT_CREW_AUTO_ISSUE_STATE_DIR=/path` | Override dedup/queue state location. |
| `AGENT_CREW_AUTO_ISSUE_TTL_SECONDS=N` | Local duplicate suppression window. Default: 7 days. |
| `AGENT_CREW_AUTO_ISSUE_TIMEOUT_SECONDS=N` | Timeout for each `gh` call. Default: 8 seconds. |
| `AGENT_CREW_AUTO_ISSUE_DRY_RUN=1` | Record and report classification without calling `gh`. |

## Manual Diagnostic

```bash
printf '{"prompt":"agent-crew error: traceback"}' \
  | python3 core/scripts/auto-issue-reporter.py --format json
```
