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


@pytest.mark.parametrize('argv,outcome', [(['missing-test-command-78213'], 'error'),
    ([sys.executable, '-c', 'import nonexistent_dependency_78213'], 'error'),
    ([sys.executable, '-c', 'import time;time.sleep(1)'], 'timeout')])
def test_failure_case_collector_infrastructure_is_not_assertion_red(contract, argv, outcome):
    task, root, runner = contract

    result = runner.execute_test(task, root, 'red', ['tests/change.py'], argv, timeout=0.05)

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
