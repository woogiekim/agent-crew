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
