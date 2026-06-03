# Hosted Adapter Validation Evidence

Hosted validation proves that Codex, Claude, and generic adapters can complete
normal workflows without manual repair under realistic hosted execution.
Credential-dependent hosted runs are external operations and require approval
before execution.

## Required Evidence

For each adapter, capture:

- adapter name and version or commit
- hosted environment and host version
- task id and task directory
- workflow type and realistic workload description
- started and completed timestamps
- host bridge status
- manual repair count
- human intervention count
- retry count
- task success status
- validation commands or evidence files
- redaction statement

Use `docs/templates/hosted-adapter-validation.json` for the machine-readable
record. Store completed evidence under the task context or release evidence
bundle.

## Pass Criteria

A hosted adapter run is clean when:

- `task_success` is true
- `host_bridge_status` is `auto_completed`
- `manual_repairs` is `0`
- `human_interventions` is `0`
- approval gates were preserved for any externally visible operation
- no credential, token, or private customer content appears in the evidence

## External Gate

Do not run hosted validation from CI or local automation unless the operator has
provided credentials, approved the billable/external run, and confirmed the
target environment. Without those prerequisites, produce an action plan and mark
the hosted gate blocked or deferred.

## Hosted Runbook

Run this only in an approved non-nested hosted environment for the target
adapter. The current local Codex session is not sufficient evidence when nested
host bridge execution is refused.

1. Start from a clean checkout at the candidate commit.
2. Run `crew update` and `crew setup`.
3. Run one realistic `crew:run` task that completes without manual repair.
4. Run one `crew:agent` read-only analysis task that completes without manual
   repair.
5. Generate workload evidence:

   ```bash
   python3 core/scripts/hosted-workload-evidence.py \
     --state-dir "${HOME}/.agent-crew/state/agent-crew" \
     --adapter codex \
     --include-agent-requests \
     --output dist/hosted-codex-validation.json \
     --format text
   ```

6. Repeat for Claude with `--adapter claude` and
   `--output dist/hosted-claude-validation.json`.
7. Confirm both artifacts show `manual_repairs: 0`,
   `human_interventions: 0`, and completed host bridge evidence.
8. Redact host-specific paths or private content before publishing the bundle.

## Current Blocker Artifact

When a clean hosted run cannot be produced from the active session, write a
machine-readable blocker/action-plan artifact instead of treating a repaired
local handoff as hosted evidence. The current action-plan location is:

```text
dist/hosted-validation-action-plan-20260601.json
```

That file must list the blocked adapter, the required external environment, and
the exact pass criteria for the replacement `dist/hosted-*-validation.json`
artifact.
