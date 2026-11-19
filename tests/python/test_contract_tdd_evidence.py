"""승인 PRD의 기존 계약 사전 검증 및 사후 TDD 소급 금지 회귀."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_current_session_execution_gate as inline
import _trace_gate_fixtures as fx


def test_failure_case_contract_inline_passed_does_not_invent_red(tmp_path):
    state, task, task_id = inline._write_task(tmp_path, selected_subagents=[])

    result = inline._repair_without_quality_bypass(state, task_id)

    assert result.returncode == 0, result.stderr
    quality = json.loads((task / 'context/manual-fallback-repair.json').read_text())['quality_gate']
    assert quality['red_phase_passed'] is False
    assert quality['green_phase_passed'] is False
    assert quality['refactor_phase_passed'] is False


def helper():
    return fx.load_module(fx.SCRIPTS_DIR / 'tdd_execution.py', 'contract_runner')


@pytest.fixture()
def contract(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'tests').mkdir()
    (root / 'module.py').write_text('VALUE = 1\n')
    (root / 'tests/preserved.py').write_text("import runpy\nassert isinstance(runpy.run_path('module.py')['VALUE'], int)\n")
    (root / 'tests/change.py').write_text("import runpy\nassert runpy.run_path('module.py')['VALUE'] == 2\n")
    task = tmp_path / 'task'
    (task / 'context').mkdir(parents=True)
    plan = {'applicable': True, 'production_paths': ['module.py'], 'contract_sources': ['request'],
            'preserved_test_targets': ['tests/preserved.py'], 'change_test_targets': ['tests/change.py']}
    (task / 'pipeline.json').write_text(json.dumps({'task':'Implement behavior','stages':[{'agents':['backend'],'tdd_mode':'inline','contract_preservation':plan},['reviewer']]}))
    (task / 'register.json').write_text(json.dumps({'project_root': str(root), 'task':'Implement behavior'}))
    runner = helper()
    runner.capture_baseline(task, root, ['module.py'])
    return task, root, runner


def run(contract, phase, targets=None, **kwargs):
    task, root, runner = contract
    targets = targets or (['tests/preserved.py'] if phase == 'characterization' else ['tests/change.py'] if phase == 'red' else ['tests/preserved.py', 'tests/change.py'])
    argv = [sys.executable, '-c', ';'.join("exec(open(%r).read())" % p for p in targets)]
    return runner.execute_test(task, root, phase, targets, argv, **kwargs)


def cycle(contract):
    run(contract, 'characterization')
    run(contract, 'red')
    (contract[1] / 'module.py').write_text('VALUE = 2\n')
    run(contract, 'green')
    run(contract, 'refactor')


def verdict(contract):
    return fx.load_quality_lib().contract_tdd_evidence(contract[0])


def test_success_case_contract_reused_tests_and_real_order_are_verified(contract):
    cycle(contract)

    result = verdict(contract)

    assert result['status'] == 'verified', result
    assert result['tdd_verified'] is True
    assert result['preserved_test_targets'] == ['tests/preserved.py']


def test_failure_case_contract_post_mutation_tests_are_contradicted(contract):
    (contract[1] / 'module.py').write_text('VALUE = 2\n')
    run(contract, 'characterization')
    run(contract, 'red')
    run(contract, 'green')
    run(contract, 'refactor')

    result = verdict(contract)

    assert result['status'] == 'contradicted'
    assert 'test_after_production_mutation' in result['failures']


@pytest.mark.parametrize('phase', ['characterization', 'red', 'green', 'refactor'])
def test_failure_case_contract_missing_phase_never_verifies(contract, phase):
    cycle(contract)
    events = contract[0] / 'tool-events.jsonl'
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    events.write_text(''.join(json.dumps(row)+'\n' for row in rows if row['tdd_execution'].get('phase') != phase))

    assert verdict(contract)['tdd_verified'] is False


def test_failure_case_contract_new_requirement_test_cannot_change_after_red(contract):
    run(contract, 'characterization')
    run(contract, 'red')
    (contract[1] / 'tests/change.py').write_text('assert True\n')
    (contract[1] / 'module.py').write_text('VALUE = 2\n')
    run(contract, 'green')
    run(contract, 'refactor')

    assert 'red_test_changed' in verdict(contract)['failures']


def test_failure_case_contract_preserved_expectation_change_needs_review(contract):
    run(contract, 'characterization')
    run(contract, 'red')
    (contract[1] / 'module.py').write_text('VALUE = 2\n')
    (contract[1] / 'tests/preserved.py').write_text('assert True\n')
    run(contract, 'green')
    run(contract, 'refactor')

    assert 'contract_test_review_required' in verdict(contract)['failures']


def test_failure_case_contract_wrong_red_target_is_not_new_behavior(contract):
    run(contract, 'characterization')
    (contract[1] / 'tests/unrelated.py').write_text('assert False\n')
    run(contract, 'red', ['tests/unrelated.py'])
    (contract[1] / 'module.py').write_text('VALUE = 2\n')
    run(contract, 'green')
    run(contract, 'refactor')

    assert verdict(contract)['red_phase_passed'] is False


def test_failure_case_contract_stale_green_cannot_verify_current_source(contract):
    cycle(contract)
    (contract[1] / 'module.py').write_text('VALUE = 3\n')

    assert 'stale_final_source' in verdict(contract)['failures']


def test_success_case_contract_preimplementation_exception_is_honest(contract):
    task, root, runner = contract
    runner.record_exception(task, root, reason='offline 의존성 미캐시',
                            alternative_evidence=['변경 전 코드·호출자 검토'], residual_risk='실행 경로 미검증')
    (root / 'module.py').write_text('VALUE = 2\n')

    result = verdict(contract)

    assert result['status'] == 'exception'
    assert result['tdd_verified'] is False
    assert result['red_phase_passed'] is False


def test_failure_case_contract_late_exception_is_not_preimplementation(contract):
    task, root, runner = contract
    (root / 'module.py').write_text('VALUE = 2\n')
    runner.record_exception(task, root, reason='환경 없음', alternative_evidence=['코드 확인'], residual_risk='미실행')

    assert verdict(contract)['status'] == 'contradicted'


def test_boundary_case_contract_legacy_evidence_remains_unverified(tmp_path):
    _, _, task = fx.make_state_task(tmp_path)

    result = fx.load_quality_lib().check_quality_loop(task, target_status='completed')

    assert result['contract_tdd']['status'] == 'unverified'
    assert result['contract_tdd']['tdd_verified'] is False


def test_boundary_case_contract_readonly_is_not_required(contract):
    task = contract[0]
    for name in ['register.json', 'pipeline.json']:
        data = json.loads((task / name).read_text())
        data['mutation_scope'] = 'read_only'
        (task / name).write_text(json.dumps(data))

    assert verdict(contract)['required'] is False


def test_failure_case_contract_missing_test_snapshots_never_verifies(contract):
    cycle(contract)
    events = contract[0] / 'tool-events.jsonl'
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    for row in rows:
        row['tdd_execution'].pop('tests_before', None)
        row['tdd_execution'].pop('tests_after', None)
    events.write_text(''.join(json.dumps(row)+'\n' for row in rows))

    assert verdict(contract)['tdd_verified'] is False


def test_failure_case_contract_edited_test_after_refactor_is_stale(contract):
    cycle(contract)
    (contract[1] / 'tests/preserved.py').write_text('assert True\n')

    assert 'stale_final_tests' in verdict(contract)['failures']


def test_failure_case_contract_exception_cannot_hide_prior_observed_mutation(contract):
    task, root, runner = contract
    (root / 'module.py').write_text('VALUE = 2\n')
    run(contract, 'characterization')
    (root / 'module.py').write_text('VALUE = 1\n')
    runner.record_exception(task, root, reason='환경 없음', alternative_evidence=['코드 확인'], residual_risk='미실행')

    assert verdict(contract)['status'] == 'contradicted'


def test_success_case_contract_native_and_inline_use_same_real_evidence(contract):
    from types import SimpleNamespace
    cycle(contract)
    task = contract[0]
    inline.runtime.write_current_session_execution_contract(task, 'task', '2026-11-19T00:00:00Z', 'Implement behavior', 'workspace_write')
    contract_spec = json.loads((task / 'context/current-session-execution.json').read_text())
    (task / 'context/inline-execution.json').write_text(json.dumps({'execution_profile':'inline_tdd', 'gates':{v:'passed' for v in contract_spec['required_quality_gates']}}))
    repair = fx.load_module(fx.REPAIR, 'contract_repair')

    native = fx.load_quality_lib().check_quality_loop(task, target_status='completed')
    fallback = repair.enforce_quality_gate(SimpleNamespace(status='completed'), task, json.loads((task/'register.json').read_text()))

    assert native['contract_tdd'] == fallback['contract_tdd']
    assert native['trace_evidence']['red']['passed'] is True
    assert fallback['tdd_verified'] is True


@pytest.mark.parametrize('disposition', ['expectations_preserved', 'approved_change', 'approved_request', 'wrong_quote', 'unapproved', 'stale'])
def test_boundary_case_contract_changed_preserved_test_review_and_approval(contract, disposition):
    task, root, runner = contract
    run(contract, 'characterization')
    before = runner.snapshot(root, ['tests/preserved.py'])['tests/preserved.py']
    run(contract, 'red')
    (root / 'module.py').write_text('VALUE = 2\n')
    (root / 'tests/preserved.py').write_text("from pathlib import Path\nassert Path('module.py').is_file()\n")
    after = runner.snapshot(root, ['tests/preserved.py'])['tests/preserved.py']
    run(contract, 'green')
    run(contract, 'refactor')
    fx.write_delegation(task, [fx.delegation_row(agent_role='reviewer')])
    patch = task / 'context/test-diff.patch'
    patch.write_text('-assert VALUE in source\n+assert source.is_file()\n')
    review = {'path':'tests/preserved.py', 'before':before, 'after':after,
              'verdict':disposition, 'diff_evidence':'context/test-diff.patch'}
    if disposition == 'approved_change':
        review['approval_ref'] = 'context/brainstorm-approval.json'
        (task / review['approval_ref']).write_text(json.dumps({'decisions':[{'status':'approved', 'decision_at':'2026-11-19T00:00:00Z', 'idempotency_key':'user-decision', 'bound_fields':{'contract_changes':[{'path':review['path'], 'before':before, 'after':after}]}}]}))
    if disposition in {'approved_request', 'wrong_quote'}:
        review.update(verdict='approved_change', approval_ref='context/brainstorm-approval.json',
                      approval_quote='Implement behavior' if disposition == 'approved_request' else '승인하지 않은 변경',
                      approval_decision_id='execution-1')
        (task/review['approval_ref']).write_text(json.dumps({'decisions':[{'decision_id':'execution-1',
            'status':'approved','decision_at':'2026-11-19T00:00:00Z','idempotency_key':'user-decision',
            'bound_fields':{'goals':['Implement behavior']}}]}))
    if disposition == 'stale':
        review.update(verdict='expectations_preserved', after=before)
    (task/'context/review.md').write_text('REVIEW: APPROVED\n```json\n'+json.dumps({'contract_test_review':[review]})+'\n```\n')

    assert verdict(contract)['tdd_verified'] is (disposition in {'expectations_preserved', 'approved_change', 'approved_request'})


def test_failure_case_contract_high_risk_missing_evidence_stays_strict(contract):
    task = contract[0]
    for name in ['register.json','pipeline.json']:
        data = json.loads((task / name).read_text());data['task'] = 'Deploy production change'
        (task / name).write_text(json.dumps(data))

    result = fx.load_quality_lib().check_quality_loop(task, target_status='completed')

    assert 'missing_contract_tdd_evidence' in result['hard_failures']


@pytest.mark.parametrize('contract_plan,expected', [({'applicable':True}, 'incomplete_contract_preservation_plan'),
    ({'applicable':False}, 'contract_preservation_nonapplicable_without_reason'),
    ({'applicable':False,'reason':'new implementation'}, None)])
def test_boundary_case_contract_plan_validates_declared_scope(contract_plan, expected):
    import test_pipeline_quality_plan_check as existing
    checker = fx.load_module(existing.CHECKER, 'contract_plan_checker')
    plan = existing._passing_pipeline()
    plan['stages'][0]['contract_preservation'] = contract_plan

    result = checker.validate_pipeline_quality_plan(plan)

    assert (expected in result['failures']) if expected else result['passed']


def test_boundary_case_contract_unrelated_incomplete_snapshot_does_not_invalidate_scope(contract):
    task = contract[0]
    path = task/'tool-events.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['tdd_execution'].update(complete=False, limitations=['source_snapshot_incomplete'])
    rows[0]['tdd_execution']['files']['unrelated.bin'] = {'state':'unsupported'}
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    cycle(contract)

    assert verdict(contract)['tdd_verified'] is True


def test_failure_case_contract_full_repair_does_not_report_text_as_tdd_pass(tmp_path):
    import test_repair_task_state_tdd_red_gate as existing
    task = existing._write_task(tmp_path/'state')
    (task/'context/tdd-red.md').write_text('TDD-RED: pytest failed before implementation\n')
    (task/'context/tdd-refactor.md').write_text('TDD-REFACTOR: review complete; pytest passed\n')

    result = existing._repair(tmp_path/'state', task.name)

    assert result.returncode == 0, result.stderr
    report = (task/'result.md').read_text()
    assert 'TDD_RED_PHASE: passed' not in report
    assert 'TDD_GREEN_PHASE: passed' not in report
    assert 'TDD_REFACTOR_PHASE: passed' not in report
    quality = json.loads((task/'context/manual-fallback-repair.json').read_text())['quality_gate']
    assert quality['red_phase_passed'] is False
    assert quality['tdd_outcome_source'] == 'unverified'


def test_failure_case_contract_raw_legacy_trace_is_not_a_verified_red(tmp_path):
    _, _, task = fx.make_state_task(tmp_path)
    fx.write_tool_events(task, [fx.tool_event_row(action_summary='python3 -m pytest tests/test_thing.py', started_at='2026-11-19T00:00:00Z', ended_at='2026-11-19T00:00:01Z', exit_code=1)])

    result = fx.load_quality_lib().trace_quality_evidence(task, {})

    assert result['red']['passed'] is False


def test_success_case_contract_full_fallback_consumes_verified_phase_results(contract, tmp_path):
    import test_repair_task_state_tdd_red_gate as existing
    cycle(contract)
    task = existing._write_task(tmp_path/'full-state')
    register = json.loads((task/'register.json').read_text())
    register['project_root'] = str(contract[1])
    (task/'register.json').write_text(json.dumps(register))
    (task/'pipeline.json').write_bytes((contract[0]/'pipeline.json').read_bytes())
    (task/'tool-events.jsonl').write_bytes((contract[0]/'tool-events.jsonl').read_bytes())
    for row in helper().event_payloads(contract[0]):
        if row.get('output_ref'):
            (task/row['output_ref']).write_bytes((contract[0]/row['output_ref']).read_bytes())
    fx.write_delegation(task,[fx.delegation_row(agent_role='reviewer')])

    result = existing._repair(tmp_path/'full-state', task.name)

    assert result.returncode == 0, result.stderr
    quality = json.loads((task/'context/manual-fallback-repair.json').read_text())['quality_gate']
    assert quality['tdd_verified'] is True
    assert quality['red_phase_passed'] is True
    assert 'TDD_VERIFIED: true' in (task/'result.md').read_text()


def test_success_case_contract_git_accepts_real_reuse_without_changed_test_file(contract):
    task, root, runner = contract
    fx._git(root, 'init', '-q')
    fx._git(root, 'add', '-A')
    fx._git(root, 'commit', '-q', '-m', 'baseline')
    fx.write_start_head(task, fx.head_sha(root))
    cycle(contract)

    result = fx.load_quality_lib().check_quality_loop(task, target_status='completed')

    assert result['contract_tdd']['tdd_verified'] is True
    assert result['trace_evidence']['git']['test_paths'] == []
    assert 'test_file_claim_contradicts_git' not in result['failures']
    assert 'missing_tdd_test_file' not in result['failures']


def test_success_case_contract_repeated_requirement_cycles_keep_original_baseline(contract):
    task, root, runner = contract
    pipeline = json.loads((task/'pipeline.json').read_text())
    pipeline['stages'][0]['contract_preservation']['change_test_targets'].append('tests/second.py')
    (task/'pipeline.json').write_text(json.dumps(pipeline))
    (root/'tests/second.py').write_text("import runpy\nassert runpy.run_path('module.py').get('OTHER') == 1\n")
    run(contract, 'characterization')
    run(contract, 'red', ['tests/change.py'])
    (root/'module.py').write_text('VALUE = 2\n')
    run(contract, 'green', ['tests/preserved.py','tests/change.py'])
    run(contract, 'refactor', ['tests/preserved.py','tests/change.py'])
    run(contract, 'red', ['tests/second.py'])
    (root/'module.py').write_text('VALUE = 2\nOTHER = 1\n')
    run(contract, 'green', ['tests/preserved.py','tests/change.py','tests/second.py'])
    run(contract, 'refactor', ['tests/preserved.py','tests/change.py','tests/second.py'])

    result = verdict(contract)

    assert result['status'] == 'verified', result
    assert 'test_after_production_mutation' not in result['failures']
    assert sum(r['kind']=='source_baseline' for r in runner.event_payloads(task)) == 1


def test_failure_case_contract_characterization_must_precede_initial_red(contract):
    run(contract,'red')
    run(contract,'characterization')
    (contract[1]/'module.py').write_text('VALUE = 2\n')
    run(contract,'green')
    run(contract,'refactor')

    assert verdict(contract)['tdd_verified'] is False


def test_boundary_case_contract_changed_fingerprint_alone_is_not_semantic_contradiction(contract):
    run(contract,'characterization')
    run(contract,'red')
    (contract[1]/'tests/change.py').write_text((contract[1]/'tests/change.py').read_text()+'\n')
    (contract[1]/'module.py').write_text('VALUE = 2\n')
    run(contract,'green')
    run(contract,'refactor')

    result = verdict(contract)

    assert result['tdd_verified'] is False
    assert result['status'] == 'unverified'
    assert 'red_test_changed' in result['failures']


def test_failure_case_contract_late_exception_cannot_hide_completed_cycle(contract):
    task, root, runner = contract
    cycle(contract)
    (root/'module.py').write_text('VALUE = 1\n')
    runner.record_exception(task,root,reason='환경 없음',alternative_evidence=['코드 검토'],residual_risk='미검증')

    assert verdict(contract)['status'] == 'contradicted'


def test_failure_case_contract_red_cannot_use_a_green_that_has_not_finished(contract):
    task,root,runner = contract
    cycle(contract)
    (root/'tests/change.py').write_text("import runpy\nassert runpy.run_path('module.py')['VALUE'] == 3\n")
    run(contract,'red')
    (root/'module.py').write_text('VALUE = 3\n')
    run(contract,'green')
    run(contract,'refactor')
    path=task/'tool-events.jsonl'
    rows=[json.loads(v) for v in path.read_text().splitlines()]
    reds=[r['tdd_execution'] for r in rows if r['tdd_execution'].get('phase')=='red']
    green=next(r['tdd_execution'] for r in rows if r['tdd_execution'].get('phase')=='green')
    reds[-1]['started_at']=green['started_at']
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))

    assert verdict(contract)['tdd_verified'] is False


@pytest.mark.parametrize('explicit_bypass',[False,True])
def test_boundary_case_contract_high_risk_exception_preserves_existing_bypass(contract, explicit_bypass):
    from types import SimpleNamespace
    task,root,runner=contract
    runner.record_exception(task,root,reason='offline 의존성 없음',alternative_evidence=['변경 전 코드 검토'],residual_risk='미실행')
    inline.runtime.write_current_session_execution_contract(task,'task','2026-11-19T00:00:00Z','Implement behavior','workspace_write')
    spec=json.loads((task/'context/current-session-execution.json').read_text())
    (task/'context/inline-execution.json').write_text(json.dumps({'execution_profile':'inline_tdd','gates':{v:'passed' for v in spec['required_quality_gates']}}))
    (task/'result.md').write_text('STATUS: handoff_ready\nHOST_BRIDGE: auto_completed\n')
    repair=fx.load_module(fx.REPAIR,'contract_exception_repair')
    args=SimpleNamespace(status='completed',quality_bypass_reason='explicit approved exception' if explicit_bypass else '')
    register=json.loads((task/'register.json').read_text())

    if not explicit_bypass:
        with pytest.raises(SystemExit):
            repair.enforce_quality_gate(args,task,register)
        return
    quality=repair.enforce_quality_gate(args,task,register)

    assert quality['bypassed'] is True
    assert quality['passed'] is False
    assert quality['tdd_verified'] is False
    assert quality['contract_tdd']['status'] == 'exception'


def selector_case(tmp_path, *, selected=True):
    root, task = tmp_path / 'project', tmp_path / 'task'
    (root / 'tests').mkdir(parents=True)
    (task / 'context').mkdir(parents=True)
    (root / 'module.py').write_text('VALUE = 1\n')
    (root / 'tests/test_preserved.py').write_text("import runpy\ndef test_preserved():\n    assert isinstance(runpy.run_path('module.py')['VALUE'], int)\n")
    requested = 'isinstance(runpy.run_path(\'module.py\')[\'VALUE\'], int)' if selected else "runpy.run_path('module.py')['VALUE'] == 2"
    (root / 'tests/test_change.py').write_text('import runpy\ndef test_requested():\n    assert ' + requested + "\ndef test_other():\n    assert runpy.run_path('module.py')['VALUE'] == 2\n")
    plan = {'applicable': True, 'production_paths': ['module.py'], 'contract_sources': ['request'],
            'preserved_test_targets': ['tests/test_preserved.py'],
            'change_test_targets': ['tests/test_change.py::test_requested']}
    (task / 'pipeline.json').write_text(json.dumps({'task': 'Implement behavior', 'stages': [
        {'agents': ['backend'], 'tdd_mode': 'inline', 'contract_preservation': plan}, ['reviewer']]}))
    (task / 'register.json').write_text(json.dumps({'project_root': str(root), 'task': 'Implement behavior'}))
    helper().capture_baseline(task, root, ['module.py'])
    return root, task


def execute(root, task, phase, declared, actual):
    return helper().execute_test(task, root, phase, declared,
        [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *actual])


def test_failure_case_other_selector_cannot_supply_required_red(tmp_path):
    root, task = selector_case(tmp_path)
    execute(root, task, 'characterization', ['tests/test_preserved.py'], ['tests/test_preserved.py'])
    execute(root, task, 'red', ['tests/test_change.py'], ['tests/test_change.py::test_other'])
    (root / 'module.py').write_text('VALUE = 2\n')
    both = ['tests/test_preserved.py', 'tests/test_change.py']
    execute(root, task, 'green', both, both)
    execute(root, task, 'refactor', both, both)

    result = fx.load_quality_lib().contract_tdd_evidence(task)

    assert result['tdd_verified'] is False, result


@pytest.mark.parametrize('filters', [
    ['-k', 'test_preserved'], ['-m', 'preserved'],
    ['--deselect=tests/test_change.py::test_requested', '--deselect=tests/test_change.py::test_other']])
def test_failure_case_filtered_green_cannot_skip_required_red(tmp_path, filters):
    root, task = selector_case(tmp_path, selected=False)
    if filters[0] == '-m':
        path = root / 'tests/test_preserved.py'
        path.write_text(path.read_text().replace('import runpy', 'import runpy\nimport pytest').replace('def test_preserved', '@pytest.mark.preserved\ndef test_preserved'))
    execute(root, task, 'characterization', ['tests/test_preserved.py'], ['tests/test_preserved.py'])
    execute(root, task, 'red', ['tests/test_change.py::test_requested'], ['tests/test_change.py::test_requested'])
    (root / 'module.py').write_text('VALUE = 3\n')
    both = ['tests/test_preserved.py', 'tests/test_change.py']
    execute(root, task, 'green', both, both + filters)
    execute(root, task, 'refactor', both, both + filters)

    result = fx.load_quality_lib().contract_tdd_evidence(task)

    assert result['tdd_verified'] is False, result


def test_failure_case_documentation_plan_cannot_require_contract_tdd_from_hint(tmp_path):
    _, task, _ = inline._write_task(tmp_path, selected_subagents=[])
    plan = {'task': '수정한 코드의 사용법만 README에 추가해', 'mutation_scope': 'workspace_write',
            'stages': [{'agents': ['documenter'], 'contract_preservation': {'applicable': False, 'reason': 'documentation-only'}},
                       {'agents': ['reviewer'], 'requires_test_execution': False}]}
    (task / 'pipeline.json').write_text(json.dumps(plan, ensure_ascii=False))
    register = json.loads((task / 'register.json').read_text())
    register['task'] = plan['task']
    (task / 'register.json').write_text(json.dumps(register, ensure_ascii=False))

    result = fx.load_quality_lib().contract_tdd_evidence(task)

    assert result['required'] is False, result


@pytest.mark.parametrize('auto_completed', [False, True])
def test_success_case_documentation_plan_preserves_inline_admission(tmp_path, auto_completed):
    from types import SimpleNamespace
    _, task, _ = inline._write_task(tmp_path, selected_subagents=[])
    text = '수정한 코드의 사용법만 README에 추가해'
    pipeline = {'task': text, 'mutation_scope': 'workspace_write', 'stages': [
        {'agents': ['documenter'], 'contract_preservation': {'applicable': False, 'reason': 'documentation-only'}},
        {'agents': ['reviewer'], 'requires_test_execution': False}]}
    (task / 'pipeline.json').write_text(json.dumps(pipeline))
    register = json.loads((task / 'register.json').read_text())
    register['task'] = text
    (task / 'register.json').write_text(json.dumps(register))
    if auto_completed:
        (task / 'result.md').write_text('HOST_BRIDGE: auto_completed\n')
    repair = fx.load_module(fx.REPAIR, 'documentation_contract_repair')

    result = repair.enforce_quality_gate(SimpleNamespace(status='completed', quality_bypass_reason=''), task, register)

    assert result['passed'] is True
    assert result['bypassed'] is False
    assert result['contract_tdd']['required'] is False
    assert result['tdd_verified'] is False
    assert result['pipeline_gate']['failures'] == []


def test_success_case_pytest_whole_modules_verify_requested_selector(tmp_path):
    root, task = selector_case(tmp_path, selected=False)
    execute(root, task, 'characterization', ['tests/test_preserved.py'], ['tests/test_preserved.py'])
    execute(root, task, 'red', ['tests/test_change.py'], ['tests/test_change.py'])
    (root / 'module.py').write_text('VALUE = 2\n')
    both = ['tests/test_preserved.py', 'tests/test_change.py']
    execute(root, task, 'green', both, both)
    execute(root, task, 'refactor', both, both)

    result = fx.load_quality_lib().contract_tdd_evidence(task)

    assert result['tdd_verified'] is True, result


@pytest.mark.parametrize('stage', ['supervisor', 'supervisor:variant', 'backend'])
def test_boundary_case_unresolved_or_code_plan_keeps_inline_tdd_required(tmp_path, stage):
    _, task, _ = inline._write_task(tmp_path, selected_subagents=[])
    pipeline = {'stages': [{'agents': [stage], 'contract_preservation': {'applicable': False, 'reason': 'new implementation'}}]}
    (task / 'pipeline.json').write_text(json.dumps(pipeline))

    result = fx.load_quality_lib().contract_tdd_evidence(task)

    assert result['required'] is True
    assert result['tdd_verified'] is False


def test_failure_case_whole_module_other_failure_cannot_supply_requested_red(tmp_path):
    root, task = selector_case(tmp_path)
    execute(root, task, 'characterization', ['tests/test_preserved.py'], ['tests/test_preserved.py'])
    execute(root, task, 'red', ['tests/test_change.py'], ['tests/test_change.py'])
    (root / 'module.py').write_text('VALUE = 2\n')
    both = ['tests/test_preserved.py', 'tests/test_change.py']
    execute(root, task, 'green', both, both)
    execute(root, task, 'refactor', both, both)

    result = fx.load_quality_lib().contract_tdd_evidence(task)

    assert result['red_phase_passed'] is False
    assert result['tdd_verified'] is False


def test_success_case_pytest_whole_module_preserves_parameterized_request(tmp_path):
    root, task = selector_case(tmp_path, selected=False)
    (root / 'tests/test_change.py').write_text("import runpy\nimport pytest\n@pytest.mark.parametrize('expected', [2, 2])\ndef test_requested(expected):\n    assert runpy.run_path('module.py')['VALUE'] == expected\n")
    execute(root, task, 'characterization', ['tests/test_preserved.py'], ['tests/test_preserved.py'])
    execute(root, task, 'red', ['tests/test_change.py'], ['tests/test_change.py'])
    (root / 'module.py').write_text('VALUE = 2\n')
    both = ['tests/test_preserved.py', 'tests/test_change.py']
    execute(root, task, 'green', both, both)
    execute(root, task, 'refactor', both, both)

    result = fx.load_quality_lib().contract_tdd_evidence(task)

    assert result['tdd_verified'] is True, result


def test_success_case_pytest_whole_module_preserves_class_scope(tmp_path):
    root, task = selector_case(tmp_path, selected=False)
    (root / 'tests/test_change.py').write_text("import runpy\nclass TestContract:\n    def test_requested(self):\n        assert runpy.run_path('module.py')['VALUE'] == 2\n")
    pipeline = json.loads((task / 'pipeline.json').read_text())
    pipeline['stages'][0]['contract_preservation']['change_test_targets'] = ['tests/test_change.py::TestContract']
    (task / 'pipeline.json').write_text(json.dumps(pipeline))
    execute(root, task, 'characterization', ['tests/test_preserved.py'], ['tests/test_preserved.py'])
    execute(root, task, 'red', ['tests/test_change.py'], ['tests/test_change.py'])
    (root / 'module.py').write_text('VALUE = 2\n')
    both = ['tests/test_preserved.py', 'tests/test_change.py']
    execute(root, task, 'green', both, both)
    execute(root, task, 'refactor', both, both)

    result = fx.load_quality_lib().contract_tdd_evidence(task)

    assert result['tdd_verified'] is True, result
