# crew:evolve

Provider-neutral command for explicit self-evolution proposal lifecycle control.

`crew:evolve` never discovers new learning candidates by itself. It only reads
or mutates proposals that already exist under the current project state:

```text
{STATE_DIR}/learning-candidates/proposals.json
```

## Subcommands

### status

Read-only and fast path.

- Read `learning-candidates/proposals.json`.
- Report pending `approval_required` proposals.
- Do not run aggregate, analyzer, Mnemos, `crew:agent-maker`, or any agent.
- Do not create `agent-maker-requests/`.

Native CLI:

```bash
crew evolve status
```

Codex:

```text
$crew:evolve status
```

Claude Code:

```text
/crew:evolve status
```

### approve

Approve exactly one proposal by `candidate_id`.

- Allowed transition: `approval_required` -> `approved`.
- Record `approved_by`, `approved_at`, and `decision_reason`.
- Idempotent when the proposal is already `approved`.
- Reject terminal or non-approval states.

```bash
crew evolve approve <candidate_id> --approved-by <operator> --reason "<reason>"
```

### apply

Apply exactly one approved proposal.

- Requires `status=approved`.
- `patch_existing_skill` may append a guarded marker block to an existing skill.
- `create_skill`, `create_agent`, and `create_command` create a
  `learning-candidates/agent-maker-requests/<candidate_id>.md` request artifact.
- Creation proposals must be completed through `crew:agent-maker`; direct asset
  creation is forbidden.

```bash
crew evolve apply <candidate_id>
```

## Latency Boundary

Lifecycle hooks may only read the existing JSON pending count if they surface
any self-evolution signal. They must not run aggregation, analysis, Mnemos
retrieval, agent-maker, or host AI routing.
