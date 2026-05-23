# Framework Review Round 15

Date: 2026-05-23

Task ID: `not persisted (framework runtime behavior hardening)`

Scope
: Runtime handoff reliability and operator observability under host bridge handoff block.

## Execution Result Summary

Current round focused on the recurring issue raised in prior cycles:

- `crew run` often ends at
  `host AI bridge has not completed this handoff` and prints only generic repair guidance.
- This created noise without actionable resolution hints in environments where the
  host bridge is not auto-invoked (e.g. native runtime invocation).

## Improvement Applied

1. Clarified blocked next-step diagnostics in `core/scripts/crew-runtime.py`
   by extending `host_bridge_next_line(...)`:
   - Keeps existing `crew repair` fallback guidance.
   - Adds explicit runtime reason when host bridge is not automatically invoked.
   - Adds a concrete fix action when bridge command is not configured:
     set `AGENT_CREW_HOST_BRIDGE_COMMAND` or pass `--host-bridge-command`.
   - Preserves the existing manual-run confirmation note.

2. Kept behavior stable for existing blocking flow:
   - Normal handoff block text (`BLOCKER: host AI bridge has not completed this handoff`) remains intact.
   - Existing fake-host quality-gate behavior remains unaffected.
   - No additional command invocation semantics were changed in this round.

## Verification

- `python3 core/scripts/framework-review-check.py --format text`  
  -> `PASS: framework review check`, `controls=40 passed=40 failed=0`
- `python3 -m py_compile core/scripts/crew-runtime.py`  
  -> `OK`
- `bash tests/shell/test_crew_cli.bash`  
  -> 98 tests, 168 assertions passed, 0 failed
- `bash tests/shell/test_auto_issue_reporter.bash`  
  -> 29 tests, 41 assertions passed, 0 failed
- `python3 -m pytest -q tests/python/test_auto_route_fast_path_approval.py tests/python/test_auto_route_question_pat.py tests/python/test_framework_review_check.py tests/python/test_pipeline_quality_plan_check.py tests/python/test_quality_loop_gate.py`  
  -> 81 passed

## Residual Risk (Round 15)

- In native/non-hosted runs, operator must still provide a bridge command path (or
  proceed via manual handoff + `crew repair`). The message now makes that explicit.
- Long-term: add a dedicated troubleshooting command section in docs for bridge setup
  and quick self-diagnosis of blocked handoffs.
