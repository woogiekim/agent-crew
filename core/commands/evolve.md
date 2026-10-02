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
- `approval_required` 승인 대기와 `investigation_required` 조사 대상을 구분한다.
- 문서 형식 경고는 내용 품질이나 독립적인 작업 실패의 증거가 아니다.
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
- 기존 스킬 수정안은 `target_skill`, `patch_body`, `evidence_refs`,
  `expected_impact`가 모두 준비되어야 승인할 수 있다. 불완전한 제안은
  `investigation_required`로 분류한다. 실행 승인을 리뷰 승인으로 대체하지 않는다.
- 동일한 스킬 파일·내용 해시·문제의 정적 감사는 작업 수만큼 실패로 집계하지 않는다.

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
