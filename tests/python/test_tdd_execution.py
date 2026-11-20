"""실제 subprocess 수집과 baseline 불변성의 workflow 계약."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_contract_tdd_evidence import contract, helper, run, verdict


def test_success_case_collector_observes_actual_exit_and_content(contract):
    event = run(contract, 'red')

    assert event['exit_code'] == 1
    assert event['outcome'] == 'failed'
    assert 'AssertionError' in (contract[0] / event['output_ref']).read_text()
    assert event['source_before'] == event['source_after']
    assert event['tests_before']['tests/change.py']['state'] == 'file'


def test_boundary_case_collector_baseline_is_idempotent_with_dirty_source(contract):
    task, root, runner = contract
    first = runner.capture_baseline(task, root, ['module.py'])
    (root / 'module.py').write_text('VALUE = 3\n')
    second = runner.capture_baseline(task, root, ['module.py'])

    assert first == second
    assert sum(json.loads(v)['tdd_execution']['kind'] == 'source_baseline' for v in (task / 'tool-events.jsonl').read_text().splitlines()) == 1


@pytest.mark.parametrize('argv,outcome,timeout', [(['missing-test-command-78213'], 'error', 1),
    ([sys.executable, '-c', 'import nonexistent_dependency_78213'], 'error', 1),
    ([sys.executable, '-c', 'import time;time.sleep(1)'], 'timeout', 0.05)])
def test_failure_case_collector_infrastructure_is_not_assertion_red(contract, argv, outcome, timeout):
    task, root, runner = contract

    result = runner.execute_test(task, root, 'red', ['tests/change.py'], argv, timeout=timeout)

    assert result['outcome'] == outcome
    assert verdict(contract)['red_phase_passed'] is False


def test_failure_case_collector_detects_source_change_during_execution(contract):
    task, root, runner = contract
    runner.execute_test(task, root, 'characterization', ['tests/preserved.py'],
                        [sys.executable, '-c', "open('module.py','w').write('VALUE = 2\\n')"])

    assert 'source_changed_during_test' in verdict(contract)['failures']


def test_boundary_case_collector_new_deleted_and_unrelated_files(contract):
    task, root, runner = contract
    (root / 'unrelated.txt').write_text('dirty')
    event = run(contract, 'characterization')
    assert set(event['source_before']) == {'module.py'}

    (root / 'module.py').unlink()
    assert runner.snapshot(root, ['module.py'])['module.py']['state'] == 'missing'
    assert runner.snapshot(root, ['future.py'])['future.py']['state'] == 'missing'


@pytest.mark.parametrize('target', ['../outside.py', '/tmp/outside.py'])
def test_failure_case_collector_rejects_outside_scope(contract, target):
    with pytest.raises(ValueError):
        contract[2].snapshot(contract[1], [target])


def test_failure_case_collector_symlink_is_not_followed(contract):
    task, root, runner = contract
    (root / 'link.py').symlink_to(root / 'module.py')

    assert runner.snapshot(root, ['link.py'])['link.py']['state'] == 'unsupported'


def test_success_case_collector_native_captures_dirty_source_before_bridge(monkeypatch, tmp_path, capsys):
    import argparse
    import test_current_session_execution_gate as existing
    import _trace_gate_fixtures as fixtures
    runtime = existing.runtime
    root = tmp_path/'repo'
    fixtures.init_git_repo(root)
    (root/'module.py').write_text('dirty baseline\n')
    monkeypatch.setenv('AGENT_CREW_HOME', str(tmp_path/'home'))
    seen = []
    def bridge(*args, **kwargs):
        rows = helper().event_payloads(kwargs['task_dir'])
        seen.append(rows[0])
        assert rows[0]['files']['module.py'] == helper().snapshot(root,['module.py'])['module.py']
        return {'returncode':1,'stdout':'AGENT_CREW_BRIDGE_STATUS: current_session_required\n','stderr':'','timed_out':False,'failure_class':'current_session_required','status':'current_session_required'}
    monkeypatch.setattr(runtime, 'invoke_host_bridge', bridge)

    result = runtime.command_run(argparse.Namespace(task='Implement behavior',project_root=str(root),fake_host_result=None,host_bridge_command='bridge'))

    assert result == 0
    assert seen[0]['kind'] == 'source_baseline'
    assert seen[0]['complete'] is True


def test_failure_case_collector_command_not_targeting_tests_is_not_passed(contract):
    task, root, runner = contract

    event = runner.execute_test(task, root, 'characterization', ['tests/preserved.py'], [sys.executable, '-c', 'pass'])

    assert event['outcome'] != 'passed'


def test_success_case_collector_preserves_tool_event_envelope(contract):
    event = run(contract, 'red')
    row = json.loads((contract[0]/'tool-events.jsonl').read_text().splitlines()[-1])

    assert row['exit_code'] == event['exit_code']
    assert row['started_at'] == event['started_at']
    assert row['trace_id']
    assert row['action_summary']


def test_success_case_collector_documented_cli_executes_actual_target(contract):
    import subprocess
    import _trace_gate_fixtures as fixtures
    task,root,runner=contract
    command=[sys.executable,str(fixtures.SCRIPTS_DIR/'tdd_execution.py'),'--task-dir',str(task),
             '--project-root',str(root),'--phase','characterization','--test-target','tests/preserved.py',
             '--',sys.executable,'-c',"exec(open('tests/preserved.py').read())"]

    result=subprocess.run(command,cwd=root,capture_output=True,text=True)

    assert result.returncode == 0, result.stderr
    event=json.loads(result.stdout)
    assert event['outcome'] == 'passed'
    assert event['test_targets'] == ['tests/preserved.py']
    assert (task/event['output_ref']).is_file()


@pytest.mark.parametrize('code', ["print('tests/preserved.py')", "pass # tests/preserved.py"])
def test_failure_case_collector_argv_mentions_are_not_test_execution(contract, code):
    task, root, runner = contract

    result = runner.execute_test(task, root, 'characterization', ['tests/preserved.py'], [sys.executable, '-c', code])

    assert result['outcome'] == 'unverified'


@pytest.mark.parametrize('code', [
    "exec(open('tests/preserved.py').read());print('done')",
    "exec(open('tests/preserved.py', 'r').read())",
    "exec(open('tests/preserved.py').read(100))",
    "exec(open(path).read())", "exec('tests/preserved.py')", "x = 'tests/preserved.py'", "invalid (",
])
def test_failure_case_collector_does_not_infer_arbitrary_python_execution(contract, code):
    assert contract[2].targets_bound(['tests/preserved.py'], [sys.executable, '-c', code]) is False


@pytest.mark.parametrize('argv', [['sh', '-c', 'pytest tests/preserved.py'], [sys.executable], []])
def test_boundary_case_collector_unknown_runner_selection_is_unverified(contract, argv):
    assert contract[2].targets_bound(['tests/preserved.py'], argv) is False


SYNTHETIC_REDACTION_VALUES = [
    'passwd=review-dummy-value', 'password=review-dummy-value', 'TOKEN=review-dummy-value',
    'secret=review-dummy-value', 'api-key=review-dummy-value', 'api_key=review-dummy-value',
    'apikey=review-dummy-value', 'bearer review_dummy.value+/=', 'sk-review_dummy_value',
    *['gh' + kind + '_review_dummy_value' for kind in 'pousr'],
    'prefixgho_review_dummy_value', 'prefixsk-review_dummy_value',
]


def test_failure_case_collector_preserves_existing_redaction_in_actual_storage(contract):
    import hashlib
    import test_current_session_execution_gate as existing
    task, root, runner = contract
    values = SYNTHETIC_REDACTION_VALUES
    assert all(existing.runtime.redact(value) != value for value in values)
    (root / 'tests/test_redaction.py').write_text(
        'def test_synthetic_output():\n    print(' + repr(values) + ')\n    assert False\n')
    argv = [sys.executable, '-m', 'pytest', '-q', 'tests/test_redaction.py']
    for index, value in enumerate(values):
        argv += ['-o', 'review_unused_' + str(index) + '=' + value]

    event = runner.execute_test(task, root, 'red', ['tests/test_redaction.py'], argv)
    output = task / event['output_ref']
    stored = json.dumps(event) + (task / 'tool-events.jsonl').read_text() + output.read_text()

    assert event['exit_code'] == 1
    assert event['outcome'] == 'failed'
    assert not any(value in stored for value in values)
    assert '[REDACTED]' in output.read_text()
    assert event['output_sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_success_case_collector_redaction_covers_existing_runtime_policy(contract):
    import test_current_session_execution_gate as existing
    expected = {value: existing.runtime.redact(value) for value in SYNTHETIC_REDACTION_VALUES}

    actual = {value: contract[2]._redact(value) for value in SYNTHETIC_REDACTION_VALUES}

    assert actual == expected


def test_boundary_case_collector_preserves_its_existing_broader_masks_and_plain_text(contract):
    assert contract[2]._redact('sk-x') == '[REDACTED]'
    assert contract[2]._redact('GHP_review_dummy_value') == '[REDACTED]'
    assert contract[2]._redact('plain review text') == 'plain review text'


@pytest.mark.parametrize('phase', ['red', 'green', 'refactor'])
def test_failure_case_test_execution_requires_approved_checklist_preflight(contract, phase):
    """failure-case(authorization) - 선행 관찰이 없으면 runner 부수효과 전에 거부한다."""
    task, root, runner = contract
    pipeline = json.loads((task / 'pipeline.json').read_text())
    pipeline['checklist_evidence_version'] = 1
    (task / 'pipeline.json').write_text(json.dumps(pipeline))
    target = root / 'runner-started'
    rejected = False
    try:
        runner.execute_test(task, root, phase, ['tests/change.py'],
                            [sys.executable, '-c', "open('runner-started','w').write('started')"])
    except ValueError as error:
        rejected = 'checklist_preflight_failed' in str(error)

    assert rejected is True
    assert not target.exists()


def test_success_case_observer_collects_real_boundaries(tmp_path):
    """success-case(audit) - 관찰기가 직접 읽은 begin/end/open으로 검사한다."""
    from test_contract_tdd_evidence import checklist_case
    task, root, sut = checklist_case(tmp_path)
    events = sut.event_payloads(task)
    execution = events[-1]['execution']
    (task / 'tool-events.jsonl').write_text(json.dumps(sut._event_row(task, events[0])) + '\n')
    begin = sut.observe_checklist_phase(task, root, 'review_begin', execution)
    lifecycle = json.loads((task / execution['lifecycle_ref']).read_text())
    lifecycle['timing'] = {'dispatched_at': sut.now(), 'terminal_at': sut.now()}
    (task / execution['lifecycle_ref']).write_text(json.dumps(lifecycle))
    end = sut.observe_checklist_phase(task, root, 'review_end', execution)
    impl = json.loads((task / execution['implementer_lifecycle_ref']).read_text())
    impl['timing']['dispatched_at'] = sut.now()
    (task / execution['implementer_lifecycle_ref']).write_text(json.dumps(impl))
    opened = sut.observe_checklist_phase(task, root, 'test_write_open', execution)

    assert sut.checklist_preflight_status(task)['valid'] is True
    assert opened['previous_event_id'] == end['event_id']
    assert end['previous_event_id'] == begin['event_id']
    assert sut.event_payloads(task)[0] == events[0]
    with pytest.raises(ValueError):
        sut.observe_checklist_phase(task, root, 'unsupported', execution)
    (root / 'tests/change.py').write_text('assert True\n')
    with pytest.raises(ValueError, match='checklist_preflight_failed'):
        sut.execute_test(task, root, 'characterization', ['tests/change.py'], [sys.executable, 'tests/change.py'])
    with pytest.raises(ValueError, match='checklist_preflight_failed'):
        sut.observe_checklist_phase(task, root, 'review_begin', execution)


def test_success_case_version_marker_is_optional_and_first_baseline_is_immutable(tmp_path):
    """success-case(idempotency) - 새 version은 최초 관찰에만 결속한다."""
    task, root = tmp_path / 'task', tmp_path / 'root'
    root.mkdir()
    sut = helper()
    first = sut.capture_baseline(task, root, [], checklist_evidence_version=1)

    assert first['checklist_evidence_version'] == 1
    assert sut.capture_baseline(task, root, []) == first


def test_failure_case_checklist_only_is_not_final_approval(tmp_path):
    """failure-case(authorization) - checklist 전용 승인은 final approval이 아니다."""
    import _trace_gate_fixtures as fixtures
    sut = fixtures.load_quality_lib()
    assert sut.event_is_reviewer_approved({'agent': 'reviewer', 'detail': 'REVIEW: APPROVED\nCHECKLIST_REVIEW_RESULT: approved'}, tmp_path) is False


@pytest.mark.parametrize('fault', ['none', 'mode', 'stage', 'attempt', 'self', 'lifecycle', 'span'])
def test_boundary_case_final_review_requires_target_and_independent_identity(tmp_path, monkeypatch, fault):
    """boundary-case(authorization) - 최종 승인은 해당 구현의 독립 실제 실행에 결속된다."""
    import _trace_gate_fixtures as fixtures
    from test_contract_tdd_evidence import checklist_case
    task, root, runner = checklist_case(tmp_path)
    sut = fixtures.load_quality_lib()
    monkeypatch.setattr(sut, 'event_has_quality_metrics', lambda *args: True)
    lifecycle = {'agent': 'reviewer', 'invocation_id': 'final-child', 'stage_index': 3, 'attempt': 1,
                 'outcome': {'terminal_state': 'terminal_completed'}}
    (task / 'context/final-lifecycle.json').write_text(json.dumps(lifecycle))
    row = {'agent': 'reviewer', 'detail': 'REVIEW: APPROVED', 'review_mode': 'final',
           'host_invocation_id': 'final-child', 'span_id': 'final-child',
           'implementation_stage_index': 1, 'attempt': 1, 'lifecycle_ref': 'context/final-lifecycle.json'}
    delegation = {'agent_role': 'reviewer', 'host_invocation_id': 'final-child', 'span_id': 'final-child',
                  'review_mode': 'final', 'implementation_stage_index': 1, 'attempt': 1, 'status': 'completed'}
    with (task / 'delegation.jsonl').open('a') as stream:
        stream.write(json.dumps(delegation) + '\n')
    if fault == 'mode':
        row['review_mode'] = 'test-checklist'
    if fault == 'stage':
        row['implementation_stage_index'] = 2
    if fault == 'attempt':
        row['attempt'] = 2
    if fault == 'self':
        row['host_invocation_id'] = 'backend-child'
    if fault == 'lifecycle':
        row['lifecycle_ref'] = 'context/reviewer-lifecycle.json'
    if fault == 'span':
        row['span_id'] = 'unrelated'

    assert sut.event_is_reviewer_approved(row, task) is (fault == 'none')


def test_failure_case_observer_refuses_missing_preflight_and_self_actor(tmp_path):
    """failure-case(authorization) - 관찰 API도 open 전에 누락·자가 실행을 차단한다."""
    from test_contract_tdd_evidence import checklist_case
    task, root, sut = checklist_case(tmp_path)
    rows = (task / 'tool-events.jsonl').read_text().splitlines()
    execution = sut.event_payloads(task)[-1]['execution']
    (task / 'tool-events.jsonl').write_text('\n'.join(rows[:2]) + '\n')

    with pytest.raises(ValueError, match='checklist_preflight_failed'):
        sut.observe_checklist_phase(task, root, 'test_write_open', execution)

    (task / 'tool-events.jsonl').write_text('\n'.join(rows[:3]) + '\n')
    execution['implementer_identity'] = execution['reviewer_identity']

    with pytest.raises(ValueError, match='checklist_preflight_failed'):
        sut.observe_checklist_phase(task, root, 'test_write_open', execution)


@pytest.mark.parametrize('review_attempt', [1, 2])
@pytest.mark.parametrize('fault', ['none', 'implementation', 'lifecycle_target', 'delegation_target', 'role_lifecycle', 'role_delegation'])
def test_boundary_case_final_review_retry_keeps_implementation_target(tmp_path, monkeypatch, review_attempt, fault):
    """boundary-case(regression) - reviewer 재시도와 대상 구현 attempt를 별도로 검증한다."""
    import _trace_gate_fixtures as fixtures
    from test_contract_tdd_evidence import checklist_case
    task, root, runner = checklist_case(tmp_path)
    sut = fixtures.load_quality_lib()
    monkeypatch.setattr(sut, 'event_has_quality_metrics', lambda *args: True)
    invocation = 'final-retry-' + str(review_attempt)
    lifecycle = {'agent': 'reviewer', 'invocation_id': invocation, 'stage_index': 3,
                 'attempt': review_attempt, 'implementation_attempt': 1,
                 'outcome': {'terminal_state': 'terminal_completed'}}
    row = {'agent': 'reviewer', 'detail': 'REVIEW: APPROVED', 'review_mode': 'final',
           'host_invocation_id': invocation, 'span_id': invocation, 'implementation_stage_index': 1,
           'implementation_attempt': 1, 'attempt': review_attempt, 'lifecycle_ref': 'context/final-retry.json'}
    delegation = {'agent_role': 'reviewer', 'host_invocation_id': invocation, 'span_id': invocation,
                  'review_mode': 'final', 'implementation_stage_index': 1, 'implementation_attempt': 1,
                  'attempt': review_attempt, 'status': 'completed'}
    if fault == 'implementation':
        row['implementation_attempt'] = 2
    if fault == 'lifecycle_target':
        lifecycle['implementation_attempt'] = 2
    if fault == 'delegation_target':
        delegation['implementation_attempt'] = 2
    if fault == 'role_lifecycle':
        lifecycle['attempt'] = 3
    if fault == 'role_delegation':
        delegation['attempt'] = 3
    (task / 'context/final-retry.json').write_text(json.dumps(lifecycle))
    with (task / 'delegation.jsonl').open('a') as stream:
        stream.write(json.dumps(delegation) + '\n')

    assert sut.event_is_reviewer_approved(row, task) is (fault == 'none')
