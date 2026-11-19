"""명시적 테스트 실행과 변경 전 소스 관찰을 기존 tool-events에 연결한다."""
from __future__ import annotations

import argparse
import ast
import datetime
import fcntl
import hashlib
import json
import os
import re
import subprocess
import uuid
from pathlib import Path


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def event_payloads(task_dir: Path) -> list[dict]:
    path = Path(task_dir) / 'tool-events.jsonl'
    if not path.exists():
        return []
    with path.open() as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        return _payloads(stream.read())


def _payloads(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        try:
            value = json.loads(line).get('tdd_execution')
        except (ValueError, AttributeError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _event_row(task_dir: Path, payload: dict) -> dict:
    timestamp = payload.get('started_at') or payload.get('captured_at') or payload.get('recorded_at')
    return {'schema_version': 1, 'trace_id': Path(task_dir).name,
            'tool_name': 'test-runner' if payload['kind'] == 'test_run' else 'source-observer',
            'action_summary': _redact(' '.join(payload.get('argv', [])))[:500] or payload['kind'],
            'started_at': timestamp, 'ended_at': payload.get('ended_at', timestamp),
            'status': 'ok' if payload.get('outcome', 'passed') == 'passed' else 'error',
            'exit_code': payload.get('exit_code'), 'failure_class': '',
            'token_usage_ref': 'cost/' + Path(task_dir).name + '.jsonl', 'tdd_execution': payload}


def append_event(task_dir: Path, payload: dict) -> None:
    with (Path(task_dir) / 'tool-events.jsonl').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(_event_row(task_dir, payload), ensure_ascii=False) + '\n')


def snapshot(root: Path, paths: list[str]) -> dict:
    root = Path(root).resolve()
    result = {}
    budget = 20_000_000
    for name in paths:
        path = Path(os.path.abspath(root / str(name).split('::')[0]))
        try:
            relative = path.relative_to(root)
        except ValueError:
            raise ValueError('관찰 대상이 project root 밖입니다: ' + str(name))
        if not relative.parts:
            raise ValueError('관찰 대상은 파일이어야 합니다')
        key = relative.as_posix()
        if any((root / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)):
            result[key] = {'state': 'unsupported'}
            continue
        try:
            if not path.exists():
                result[key] = {'state': 'missing'}
                continue
            size = path.stat().st_size
            if not path.is_file() or size > 2_000_000 or size > budget:
                result[key] = {'state': 'unsupported'}
                continue
            content = path.read_bytes()
            budget -= len(content)
            result[key] = {'state': 'file', 'sha256': hashlib.sha256(content).hexdigest()}
        except OSError:
            result[key] = {'state': 'unreadable'}
    return result


def capture_baseline(task_dir: Path, project_root: Path, paths: list[str] | None = None) -> dict:
    task_dir, root = Path(task_dir), Path(project_root).resolve()
    task_dir.mkdir(parents=True, exist_ok=True)
    with (task_dir / 'tool-events.jsonl').open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        previous = next((v for v in _payloads(stream.read()) if v.get('kind') == 'source_baseline'), None)
        if previous:
            return previous
        limitations = []
        if paths is None:
            try:
                proc = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                                      capture_output=True, check=True, timeout=10)
                paths = sorted(set(proc.stdout.decode('utf-8').strip('\0').split('\0')) - {''})
            except (OSError, subprocess.SubprocessError, UnicodeError, AttributeError):
                paths, limitations = [], ['git_inventory_unavailable']
        if len(paths) > 10000:
            paths, limitations = paths[:10000], limitations + ['file_count_limit']
        files = snapshot(root, paths)
        if any(v['state'] not in {'file', 'missing'} for v in files.values()):
            limitations.append('source_snapshot_incomplete')
        payload = {'kind': 'source_baseline', 'baseline_id': str(uuid.uuid4()), 'project_root': str(root),
                   'captured_at': now(), 'files': files, 'complete': not limitations, 'limitations': limitations}
        stream.write(json.dumps(_event_row(task_dir, payload), ensure_ascii=False) + '\n')

    return payload


def production_paths(task_dir: Path) -> list[str]:
    pipeline = json.loads((Path(task_dir) / 'pipeline.json').read_text())
    return sorted({p for stage in pipeline.get('stages', []) if isinstance(stage, dict)
                   for p in stage.get('contract_preservation', {}).get('production_paths', [])})


def _redact(text: str) -> str:
    return re.sub(r'(?i)(?:\b(?:token|password|secret|api[_-]?key)=\S+|\bbearer\s+\S+|\b(?:sk-|ghp_)[\w-]+)', '[REDACTED]', text)


def runner_selection(argv: list[str]) -> tuple[str, list[str]]:
    """지원하는 명시 실행 형식만 해석한다. 임의 코드의 문자열 언급은 실행 증거가 아니다."""
    if not argv:
        return '', []
    args = list(argv[1:])
    python = Path(argv[0]).name.startswith('python')
    if Path(argv[0]).name in {'pytest', 'py.test'} or (python and args[:2] == ['-m', 'pytest']):
        args = args[2:] if python else args
        return 'pytest', [a for a in args if not a.startswith('-') and '.py' in a
                          and a.split('::')[0].endswith('.py')]
    if not python:
        return '', []
    if len(args) == 1 and args[0].endswith('.py'):
        return 'script', args
    if len(args) != 2 or args[0] != '-c':
        return '', []
    try:
        statements = ast.parse(args[1]).body
        paths = []
        for statement in statements:
            literals = [node.value for node in ast.walk(statement)
                        if isinstance(node, ast.Constant) and isinstance(node.value, str)]
            if len(literals) != 1 or not literals[0].endswith('.py'):
                return '', []
            path = literals[0]
            expected = ast.parse('exec(open(%r).read())' % path).body[0]
            if ast.dump(statement) != ast.dump(expected):
                return '', []
            paths.append(path)
        return 'script', paths
    except (SyntaxError, ValueError, TypeError):
        return '', []


def targets_bound(test_targets: list[str], argv: list[str]) -> bool:
    _, selected = runner_selection(argv)
    return bool(test_targets) and all(any(t == a or t.startswith(a + '::') or a.startswith(t + '::')
                                        for a in selected) for t in test_targets)


def execution_targets(argv: list[str], output: str, outcome: str) -> list[str]:
    """선택 범위와 실제 결과를 결합한다. 미지원 runner/불명확한 실패 위치는 미검증이다."""
    kind, selected = runner_selection(argv)
    if kind == 'script':
        return selected if outcome == 'passed' or (outcome == 'failed' and len(selected) == 1) else []
    if kind != 'pytest':
        return []
    status = 'PASSED' if outcome == 'passed' else 'FAILED'
    nodes = re.findall(r'^([^\s]+::[^\s]+)\s+' + status + r'(?:\s|$)', output, re.MULTILINE)
    nodes = [n for n in nodes if any(n == s or n.startswith(s + '::') or n.startswith(s + '[') for s in selected)]
    if outcome == 'passed' and nodes and not re.search(r'\b(?:deselected|skipped|xfailed)\b', output):
        # 전체 모듈/클래스 범위는 필터가 없는 실제 성공에만 부여한다.
        args = argv[3:] if Path(argv[0]).name.startswith('python') else argv[1:]
        if not any(a in {'-k', '-m', '--deselect', '--lf', '--ff', '--last-failed', '--stepwise'}
                   or a.startswith(('-k', '-m', '--deselect=', '--ignore')) for a in args):
            parents = {n.split('[', 1)[0] for n in nodes}
            parents.update('::'.join(n.split('::')[:i]) for n in nodes
                           for i in range(1, len(n.split('::'))))
            nodes += [p for p in parents if any(p == s or p.startswith(s + '::') for s in selected)]
            nodes += [s for s in selected if any(n == s or n.startswith(s + '::') or n.startswith(s + '[') for n in nodes)]
    return sorted(set(nodes))


def execute_test(task_dir: Path, project_root: Path, phase: str, test_targets: list[str],
                 argv: list[str], *, timeout: float = 60) -> dict:
    if phase not in {'characterization', 'red', 'green', 'refactor'} or not argv or not test_targets:
        raise ValueError('phase, 실제 argv와 테스트 대상이 필요합니다')
    task_dir, root = Path(task_dir), Path(project_root).resolve()
    paths = production_paths(task_dir)
    if not paths:
        raise ValueError('계획의 production_paths가 필요합니다')
    baseline = capture_baseline(task_dir, root, paths)
    before, tests = snapshot(root, paths), snapshot(root, test_targets)
    if runner_selection(argv)[0] == 'pytest':
        argv = list(argv) + ['--verbosity=1', '--color=no']
    started, exit_code, outcome, output = now(), None, 'error', ''
    try:
        proc = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=timeout)
        exit_code, output = proc.returncode, proc.stdout + proc.stderr
        outcome = 'passed' if exit_code == 0 else 'error'
        if exit_code == 1 and ('AssertionError' in output or re.search(r'\b[1-9]\d* failed\b', output)) and not re.search(r'\b(?:ERROR|ImportError|ModuleNotFoundError|SyntaxError)\b', output):
            outcome = 'failed'
    except subprocess.TimeoutExpired as exc:
        outcome, output = 'timeout', str(exc)
    except OSError as exc:
        output = str(exc)
    if outcome in {'passed', 'failed'} and (not targets_bound(test_targets, argv)
                                           or not execution_targets(argv, output, outcome)):
        outcome = 'unverified'
    ended, run_id = now(), str(uuid.uuid4())
    output = _redact(output)
    output = output[:120000] + ('\n[bounded output]\n' + output[-8000:] if len(output) > 120000 else '')
    relative = 'context/test-run-' + run_id + '.log'
    (task_dir / 'context').mkdir(exist_ok=True)
    (task_dir / relative).write_text(output)
    payload = {'kind': 'test_run', 'run_id': run_id, 'phase': phase, 'baseline_id': baseline['baseline_id'],
               'test_targets': test_targets, 'argv': [_redact(str(a)) for a in argv], 'cwd': str(root),
               'source_before': before, 'source_after': snapshot(root, paths), 'tests_before': tests,
               'tests_after': snapshot(root, test_targets), 'started_at': started, 'ended_at': ended,
               'exit_code': exit_code, 'outcome': outcome, 'output_ref': relative,
               'output_sha256': hashlib.sha256(output.encode()).hexdigest()}
    append_event(task_dir, payload)

    return payload


def record_exception(task_dir: Path, project_root: Path, *, reason: str,
                     alternative_evidence: list[str], residual_risk: str) -> dict:
    paths = production_paths(task_dir)
    baseline = capture_baseline(task_dir, project_root, paths)
    payload = {'kind': 'execution_exception', 'baseline_id': baseline['baseline_id'], 'recorded_at': now(),
               'source_state': snapshot(project_root, paths), 'reason': reason,
               'alternative_evidence': alternative_evidence, 'residual_risk': residual_risk}
    append_event(task_dir, payload)
    context = Path(task_dir) / 'context'
    context.mkdir(exist_ok=True)
    (context / 'tdd-exception.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-dir', required=True)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--phase', required=True, choices=['characterization', 'red', 'green', 'refactor'])
    parser.add_argument('--test-target', action='append', required=True)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
    event = execute_test(Path(args.task_dir), Path(args.project_root), args.phase, args.test_target, argv, timeout=args.timeout)
    print(json.dumps(event, ensure_ascii=False))

    return event['exit_code'] if isinstance(event['exit_code'], int) else 2


if __name__ == '__main__':
    raise SystemExit(main())
