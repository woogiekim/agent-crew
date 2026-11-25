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


@pytest.mark.parametrize('git_backed,new_preserved_test', [(False, False), (True, False), (True, True)])
def test_success_case_observer_collects_real_boundaries(tmp_path, git_backed, new_preserved_test):
    """success-case(audit) - 관찰기가 직접 읽은 begin/end/open으로 검사한다."""
    from test_contract_tdd_evidence import checklist_case
    task, root, sut = checklist_case(tmp_path, new_preserved_test=new_preserved_test)
    events = sut.event_payloads(task)
    execution = events[-1]['execution']
    if git_backed:
        import _trace_gate_fixtures as fixtures
        fixtures.init_git_repo(root)
        (task / 'tool-events.jsonl').unlink()
        baseline = sut.capture_baseline(task, root, checklist_evidence_version=1)
        assert baseline['files'] == {}
    else:
        baseline = events[0]
        (task / 'tool-events.jsonl').write_text(json.dumps(sut._event_row(task, baseline)) + '\n')
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
    assert sut.event_payloads(task)[0] == baseline
    if new_preserved_test:
        (root / 'tests/preserved.py').write_text('assert True\n')
        assert run((task, root, sut), 'characterization')['outcome'] == 'passed'
    with pytest.raises(ValueError):
        sut.observe_checklist_phase(task, root, 'unsupported', execution)
    (root / 'tests/change.py').write_text('assert True\n')
    with pytest.raises(ValueError, match='checklist_preflight_failed'):
        sut.execute_test(task, root, 'characterization', ['tests/change.py'], [sys.executable, 'tests/change.py'])
    with pytest.raises(ValueError, match='checklist_preflight_failed'):
        sut.observe_checklist_phase(task, root, 'review_begin', execution)
    (root / 'tests/test_unapproved.py').write_text('assert True\n')
    assert sut.checklist_preflight_status(task)['valid'] is False


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


def test_git_baseline_hashes_only_existing_changes(tmp_path):
    import subprocess
    import _trace_gate_fixtures as fixtures

    root = tmp_path / 'repo'
    fixtures.init_git_repo(root)
    (root / 'large.bin').write_bytes(b'x' * 2_000_001)
    (root / 'tests').mkdir()
    (root / 'tests/test_existing.py').write_text('assert True\n')
    fixtures._git(root, 'add', '-A')
    fixtures._git(root, 'commit', '-m', 'tracked files')
    sut = helper()

    baseline = sut.capture_baseline(tmp_path / 'clean', root, checklist_evidence_version=1)
    assert baseline['git_head'] == subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    assert baseline['files'] == {}
    assert baseline['complete'] is True

    (root / 'tests/test_existing.py').write_text('assert False\n')
    (root / 'tests/test_new.py').write_text('assert True\n')
    dirty = sut.capture_baseline(tmp_path / 'dirty', root, checklist_evidence_version=1)

    assert dirty['files'] == sut.snapshot(root, ['tests/test_existing.py', 'tests/test_new.py'])
    assert dirty['complete'] is True


def test_git_baseline_paths_are_relative_to_project_subdirectory(tmp_path):
    import _trace_gate_fixtures as fixtures

    repo = tmp_path / 'repo'
    fixtures.init_git_repo(repo)
    root = repo / 'project'
    root.mkdir()
    (root / 'changed.py').write_text('value = 1\n')
    (root / 'clean.py').write_text('value = 1\n')
    (repo / 'outside.py').write_text('value = 1\n')
    fixtures._git(repo, 'add', '-A')
    fixtures._git(repo, 'commit', '-m', 'project files')
    sut = helper()
    clean = sut.snapshot(root, ['clean.py'])

    (root / 'changed.py').write_text('value = 2\n')
    (repo / 'outside.py').write_text('value = 2\n')
    baseline = sut.capture_baseline(tmp_path / 'task', root)

    assert baseline['complete'] is True
    assert baseline['files'] == sut.snapshot(root, ['changed.py'])
    assert sut.baseline_file_states(root, baseline, ['clean.py']) == clean


@pytest.mark.parametrize('change', ['edit', 'delete', 'new', 'restore_head', 'ignored_target'])
def test_git_baseline_rejects_test_delta_before_checklist_review(tmp_path, change):
    import _trace_gate_fixtures as fixtures

    root, task = tmp_path / 'repo', tmp_path / 'task'
    fixtures.init_git_repo(root)
    target = root / 'tests/test_existing.py'
    target.parent.mkdir()
    target.write_text('assert True\n')
    (root / '.gitignore').write_text('tests/test_ignored.py\n')
    fixtures._git(root, 'add', '-A')
    fixtures._git(root, 'commit', '-m', 'tracked test')
    if change == 'restore_head':
        target.write_text('assert False\n')
    sut = helper()
    sut.capture_baseline(task, root, checklist_evidence_version=1)
    stage = {'authorized_test_paths': ['tests/test_ignored.py']} if change == 'ignored_target' else {}
    (task / 'pipeline.json').write_text(json.dumps({'stages': [stage]}))

    if change == 'ignored_target':
        (target.parent / 'test_ignored.py').write_text('assert True\n')
    elif change == 'delete':
        target.unlink()
    elif change == 'new':
        (target.parent / 'test_new.py').write_text('assert True\n')
    else:
        target.write_text('assert True\n' if change == 'restore_head' else 'assert False\n')

    with pytest.raises(ValueError, match='checklist_preflight_failed:baseline_or_tests_changed'):
        sut.observe_checklist_phase(task, root, 'review_begin', {'implementation_stage_index': 1})


def test_git_baseline_proves_tdd_against_the_original_commit(tmp_path):
    import _trace_gate_fixtures as fixtures
    from test_contract_tdd_evidence import cycle

    task, root, sut = contract.__wrapped__(tmp_path)
    fixtures.init_git_repo(root)
    (task / 'tool-events.jsonl').unlink()
    baseline = sut.capture_baseline(task, root)
    assert baseline['files'] == {}

    cycle((task, root, sut))

    assert verdict((task, root, sut))['tdd_verified'] is True


@pytest.mark.parametrize('outcome,summary,end,expected', [
    ('passed', 'Tests run: 3, Failures: 0, Errors: 0, Skipped: 0', 'BUILD SUCCESS', True),
    ('passed', 'Tests run: 3, Failures: 0, Errors: 0, Skipped: 3', 'BUILD SUCCESS', False),
    ('failed', 'Tests run: 3, Failures: 1, Errors: 0, Skipped: 0', 'BUILD FAILURE', True),
    ('failed', 'Tests run: 3, Failures: 0, Errors: 1, Skipped: 0', 'BUILD FAILURE', False),
])
def test_maven_binds_only_selected_surefire_class_results(outcome, summary, end, expected):
    sut = helper()
    argv = ['mvn', '-o', '-B', '-Dtest=ContractTest', 'test']
    target = 'src/test/java/sample/ContractTest.java'
    output = (
        '[INFO] --- surefire:3.2.5:test (default-test) @ project ---\n'
        f'[INFO] {summary}, Time elapsed: 0.1 s -- in sample.ContractTest\n'
        f'[INFO] {end}\n'
    )
    if end == 'BUILD FAILURE':
        output += ('[ERROR] Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:3.2.5:test '
                   '(default-test) on project community: There are test failures.\n')

    assert sut.targets_bound([target], argv) is True
    assert sut.execution_targets(argv, output, outcome, [target]) == ([target] if expected else [])
    assert sut.execution_targets(argv, output, outcome, ['src/test/java/other/ContractTest.java']) == []


@pytest.fixture()
def maven_contract(contract):
    task, root, runner = contract
    preserved = 'src/test/java/sample/PreservedTest.java'
    changed = 'src/test/java/sample/ChangeTest.java'
    (root / preserved).parent.mkdir(parents=True)
    for test in [preserved, changed]:
        (root / test).write_text('// fixture\n')
    pipeline_path = task / 'pipeline.json'
    pipeline = json.loads(pipeline_path.read_text())
    plan = pipeline['stages'][0]['contract_preservation']
    plan.update(preserved_test_targets=[preserved], change_test_targets=[changed])
    pipeline_path.write_text(json.dumps(pipeline))
    mvn = root / 'mvn'
    mvn.write_text(
        f'#!{sys.executable}\n'
        'from pathlib import Path\n'
        'import sys\n'
        'Path("maven-started").touch()\n'
        'selected = next(arg[7:] for arg in sys.argv if arg.startswith("-Dtest=")).split(",")\n'
        'failed = "ChangeTest" in selected and Path("module.py").read_text() == "VALUE = 1\\n"\n'
        'print("[INFO] startup\\n" * 10000)\n'
        'print("[INFO] --- surefire:3.2.5:test (default-test) @ project ---")\n'
        'for name in selected:\n'
        '    count = int(failed and name == "ChangeTest")\n'
        '    print(f"[INFO] Tests run: 1, Failures: {count}, Errors: 0, Skipped: 0, Time elapsed: 0.1 s -- in sample.{name}")\n'
        'print("[INFO] diagnostic output\\n" * 8000)\n'
        'print("[INFO] BUILD " + ("FAILURE" if failed else "SUCCESS"))\n'
        'if failed:\n'
        '    print("[ERROR] Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:3.2.5:test (default-test): There are test failures.")\n'
        'sys.exit(int(failed))\n'
    )
    mvn.chmod(0o700)

    return contract, preserved, changed, str(mvn)


def test_long_maven_logs_keep_surefire_evidence_for_common_gate(maven_contract):
    contract, preserved, changed, mvn = maven_contract
    task, root, runner = contract
    runner.execute_test(task, root, 'characterization', [preserved], [mvn, '-Dtest=PreservedTest', 'test'])
    red = runner.execute_test(task, root, 'red', [changed], [mvn, '-Dtest=ChangeTest', 'test'])
    (root / 'module.py').write_text('VALUE = 2\n')
    args = [mvn, '-Dtest=PreservedTest,ChangeTest', 'test']
    runner.execute_test(task, root, 'green', [preserved, changed], args)
    runner.execute_test(task, root, 'refactor', [preserved, changed], args)

    log = (task / red['output_ref']).read_text()
    assert '[bounded output]' in log
    assert 'Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.1 s -- in sample.ChangeTest' in log
    assert verdict(contract)['tdd_verified'] is True


@pytest.mark.parametrize('missing_from', ['targets', 'selection'])
def test_maven_green_rejects_missing_preserved_test_before_subprocess(maven_contract, missing_from):
    contract, preserved, changed, mvn = maven_contract
    task, root, runner = contract
    targets = [changed] if missing_from == 'targets' else [preserved, changed]
    selected = 'ChangeTest' if missing_from == 'selection' else 'PreservedTest,ChangeTest'

    with pytest.raises(ValueError, match='maven_green_missing_preserved_tests.*PreservedTest'):
        runner.execute_test(task, root, 'green', targets, [mvn, f'-Dtest={selected}', 'test'])

    assert not (root / 'maven-started').exists()
    assert all(event['kind'] != 'test_run' for event in runner.event_payloads(task))


def test_maven_evidence_over_retention_limit_stays_unverified():
    sut = helper()
    target = 'src/test/java/sample/ContractTest.java'
    argv = ['mvn', '-Dtest=ContractTest', 'test']
    output = (
        '[INFO] --- surefire:3.2.5:test (default-test) @ project ---\n'
        + '[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.1 s -- in sample.ContractTest\n' * 1800
        + '[INFO] BUILD SUCCESS\n'
    )

    bounded = sut._bounded_test_output(output, 'maven')

    assert 'Surefire evidence exceeds retention limit' in bounded
    assert sut.execution_targets(argv, bounded, 'passed', [target]) == []
