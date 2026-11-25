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
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO


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


MAX_SNAPSHOT_FILE_BYTES = 8 * 1024 * 1024
SNAPSHOT_CHUNK_BYTES = 128 * 1024


def _hash_stream(stream: BinaryIO, limit: int) -> tuple[str | None, int]:
    digest = hashlib.sha256()
    remaining = limit
    while remaining:
        chunk = stream.read(min(SNAPSHOT_CHUNK_BYTES, remaining))
        if not chunk:
            return digest.hexdigest(), limit - remaining
        digest.update(chunk)
        remaining -= len(chunk)

    if stream.read(1):
        return None, limit
    return digest.hexdigest(), limit


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
            if not path.is_file() or size > min(MAX_SNAPSHOT_FILE_BYTES, budget):
                result[key] = {'state': 'unsupported'}
                continue

            with path.open('rb') as stream:
                digest, consumed = _hash_stream(stream, size)
            budget -= consumed
            if digest is None or consumed != size:
                result[key] = {'state': 'unsupported'}
                continue
            result[key] = {'state': 'file', 'sha256': digest}
        except OSError:
            result[key] = {'state': 'unreadable'}
    return result


def _git(root: Path, *args: str, output: BinaryIO | None = None) -> bytes:
    return subprocess.run(
        ['git', '--no-optional-locks', '-C', str(root), *args],
        stdout=output if output is not None else subprocess.PIPE,
        stderr=subprocess.PIPE, check=True, timeout=10,
    ).stdout or b''


def _git_changed_paths(root: Path, head: str) -> set[str]:
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', head):
        raise ValueError('invalid_git_baseline_head')
    changed = _git(root, 'diff', '--no-ext-diff', '--no-renames', '--relative', '--name-only', '-z', head, '--')
    untracked = _git(root, 'ls-files', '-z', '--others', '--exclude-standard')
    return {path.decode('utf-8') for data in (changed, untracked) for path in data.split(b'\0') if path}


def _checkout_blob_hash(root: Path, head: str, path: str, tree_path: str, oid: str) -> str | None:
    attr_source = '--attr-source=' + head
    try:
        attributes = _git(root, attr_source, 'check-attr', '-z', 'filter', '--', path)
    except subprocess.CalledProcessError as exc:
        if b'unknown option: --attr-source=' not in exc.stderr:
            raise
        args = ('cat-file', 'blob', oid)
    else:
        driver = attributes.split(b'\0')[2].decode('utf-8')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', driver):
            raise ValueError('unsupported_git_baseline_filter')
        # Git의 내장 체크아웃 변환만 사용하고 외부 필터는 호출하지 않는다.
        args = (
            attr_source,
            '-c', f'filter.{driver}.process=',
            '-c', f'filter.{driver}.smudge=',
            '-c', f'filter.{driver}.required=false',
            'cat-file', '--filters', '--path=' + tree_path, oid,
        )

    with tempfile.TemporaryFile() as output:
        _git(root, *args, output=output)
        output.seek(0)
        digest, _ = _hash_stream(output, MAX_SNAPSHOT_FILE_BYTES)
    return digest


def baseline_file_states(root: Path, baseline: dict, paths: list[str]) -> dict:
    """Resolve hashes for explicitly requested TDD targets from a saved baseline."""
    recorded = baseline.get('files', {})
    head = baseline.get('git_head')
    if head and not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', head):
        raise ValueError('invalid_git_baseline_head')
    states = {}
    prefix = None
    for name in paths:
        relative = Path(os.path.abspath(root / name.split('::')[0])).relative_to(root)
        path = relative.as_posix()
        if path in recorded:
            states[path] = recorded[path]
            continue
        if not head:
            states[path] = {'state': 'missing'}
            continue

        entry = _git(root, 'ls-tree', '-lz', head, '--', ':(literal)' + path)
        if not entry:
            states[path] = {'state': 'missing'}
            continue

        mode, kind, oid, size = entry.split(b'\t', 1)[0].split()
        if kind != b'blob' or mode not in {b'100644', b'100755'} or int(size) > MAX_SNAPSHOT_FILE_BYTES:
            states[path] = {'state': 'unsupported'}
            continue
        if prefix is None:
            prefix = _git(root, 'rev-parse', '--show-prefix').decode('utf-8').removesuffix('\n')
        digest = _checkout_blob_hash(root, head, path, prefix + path, oid.decode('ascii'))
        if digest is None:
            states[path] = {'state': 'unsupported'}
            continue
        states[path] = {'state': 'file', 'sha256': digest}
    return states


def capture_baseline(task_dir: Path, project_root: Path, paths: list[str] | None = None,
                     *, checklist_evidence_version: int | None = None) -> dict:
    task_dir, root = Path(task_dir), Path(project_root).resolve()
    task_dir.mkdir(parents=True, exist_ok=True)
    with (task_dir / 'tool-events.jsonl').open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        previous = next((v for v in _payloads(stream.read()) if v.get('kind') == 'source_baseline'), None)
        if previous:
            return previous
        limitations = []
        git_head = None
        if paths is None:
            try:
                git_head = _git(root, 'rev-parse', '--verify', 'HEAD').decode('ascii').strip()
                paths = sorted(_git_changed_paths(root, git_head))
            except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
                paths, limitations = [], ['git_inventory_unavailable']
        if len(paths) > 10000:
            paths, limitations = paths[:10000], limitations + ['file_count_limit']
        files = snapshot(root, paths)
        if any(v['state'] not in {'file', 'missing'} for v in files.values()):
            limitations.append('source_snapshot_incomplete')
        payload = {'kind': 'source_baseline', 'baseline_id': str(uuid.uuid4()), 'project_root': str(root),
                   'captured_at': now(), 'files': files, 'complete': not limitations, 'limitations': limitations}
        if git_head is not None:
            payload['git_head'] = git_head
        if checklist_evidence_version is not None:
            payload['checklist_evidence_version'] = checklist_evidence_version
        stream.write(json.dumps(_event_row(task_dir, payload), ensure_ascii=False) + '\n')

    return payload


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _task_file(task_dir: Path, name: str) -> Path:
    root = Path(task_dir).resolve()
    path = root / name
    if not name or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('invalid_task_reference')

    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _test_path(name: str) -> bool:
    return (name.startswith(('tests/', 'test/')) or '/tests/' in name
            or '/test/' in name or Path(name).name.startswith('test_'))


def _checklist_scope(root: Path, baseline: dict, stage: dict,
                     changed_paths: set[str] | None = None) -> tuple[list[str], list[str], list[str]]:
    contract = stage.get('contract_preservation', {})
    targets = contract.get('preserved_test_targets', []) + contract.get('change_test_targets', [])
    authorized = stage.get('authorized_test_paths', [])
    inventory = set(baseline.get('files', {}))
    if changed_paths is not None:
        inventory.update(changed_paths)
    elif (root / '.git').exists():
        proc = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                              capture_output=True, check=True, timeout=10)
        inventory.update(proc.stdout.decode().strip('\0').split('\0'))
    else:
        inventory.update(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
    paths = {p for p in inventory if _test_path(p)}
    paths.update(str(p).split('::')[0] for p in targets)
    paths.update(authorized)

    return sorted(paths), targets, authorized


def _checklist_states(root: Path, baseline: dict, stage: dict):
    head = baseline.get('git_head')
    changed = _git_changed_paths(root, head) if head else None
    paths, targets, authorized = _checklist_scope(root, baseline, stage, changed)
    recorded = baseline.get('files', {})
    default = {'state': 'missing'} if changed is None else {'state': 'git_head'}
    initial = {path: recorded.get(path, default) for path in paths}
    if changed is None:
        observed = snapshot(root, paths)
    else:
        # Explicit targets still count if an ignore rule hides an untracked file.
        declared = {target.split('::')[0] for target in targets} | set(authorized)
        if declared:
            ignored = _git(root, 'ls-files', '-z', '--others', '--ignored', '--exclude-standard',
                           '--', *(':(literal)' + path for path in sorted(declared)))
            changed.update(path.decode('utf-8') for path in ignored.split(b'\0') if path)
        observed = snapshot(root, [path for path in paths if path in changed])
        observed = {path: observed.get(path, default) for path in paths}
    return paths, targets, authorized, initial, observed


def _approved_checklist(text: str, *, require_must: bool = True) -> bool:
    return (bool(re.search(r'^\s*(?:(?:REVIEW|STATUS)\s*:\s*)?APPROVED\b', text, re.I | re.M))
            and (not require_must or bool(re.search(r'^\s*[-*]?\s*Missing\s+MUST\s*:\s*(?:none|no|n/a|na|0|\[\])\s*$', text, re.I | re.M)))
            and not re.search(r'^\s*CHECKLIST_REVIEW_RESULT\s*:\s*(?!approved\b)\S+', text, re.I | re.M))


def _host_review_errors(task_dir: Path, begin: dict, end: dict, opened: dict | None) -> list[str]:
    execution = end.get('execution', {})
    invocation, span = execution.get('host_invocation_id'), execution.get('span_id')
    identity = execution.get('reviewer_identity')
    reserved = begin.get('execution', {}).get('reviewer_invocation_reservation') or begin.get('execution', {}).get('host_invocation_id')
    lifecycle = _read_json(_task_file(task_dir, execution.get('lifecycle_ref', '')))
    errors = []
    reserved_execution = begin.get('execution', {})
    for key in ['lifecycle_ref', 'delegation_ref', 'review_output_ref', 'review_report_ref',
                'review_mode', 'implementation_stage_index', 'attempt']:
        if reserved_execution.get(key) != execution.get(key):
            errors.append('checklist_review_reference_mismatch')
    if not invocation or not span or identity != invocation or reserved != invocation:
        errors.append('checklist_reviewer_identity_mismatch')
    if (lifecycle.get('invocation_id') != invocation or lifecycle.get('agent') != 'reviewer'
            or lifecycle.get('attempt') != end.get('attempt')
            or lifecycle.get('stage_index') != execution.get('stage_index')
            or lifecycle.get('outcome', {}).get('terminal_state') != 'terminal_completed'
            or execution.get('review_mode') != 'test-checklist' or execution.get('status') != 'completed'
            or execution.get('implementation_stage_index') != end.get('implementation_stage_index')):
        errors.append('checklist_reviewer_lifecycle_mismatch')
    timing = lifecycle.get('timing', {})
    if not (begin.get('captured_at', '') <= timing.get('dispatched_at', '')
            <= timing.get('terminal_at', '') <= end.get('captured_at', '')
            and timing.get('dispatched_at') and timing.get('terminal_at')):
        errors.append('checklist_review_boundary_mismatch')
    delegation = _task_file(task_dir, execution.get('delegation_ref', ''))
    try:
        rows = [json.loads(line) for line in delegation.read_text().splitlines()]
    except (OSError, ValueError):
        rows = []
    matched = [r for r in rows if r.get('span_id') == span and r.get('agent_role') == 'reviewer'
               and r.get('host_invocation_id', r.get('invocation_id')) == invocation
               and r.get('review_mode') == 'test-checklist'
               and r.get('implementation_stage_index') == end.get('implementation_stage_index')
               and r.get('attempt') == end.get('attempt')]
    if not {'started', 'completed'}.issubset({r.get('status') for r in matched}):
        errors.append('checklist_review_span_missing')
    for key in ['review_output_ref', 'review_report_ref']:
        ref = end.get(key, '')
        path = _task_file(task_dir, ref)
        if (not path.is_file() or ref != execution.get(key) or _digest(path) != end.get(key.replace('_ref', '_digest'))
                or not _approved_checklist(path.read_text(), require_must=key == 'review_report_ref')):
            errors.append('checklist_review_output_mismatch')
    report_path = _task_file(task_dir, end.get('review_report_ref', ''))
    if report_path.is_file():
        report = report_path.read_text()
        bound = re.search(r'^reviewed_checklist_sha256:\s*(\S+)', report, re.M)
        if bound and bound.group(1) != begin.get('checklist_digest'):
            errors.append('checklist_reviewed_content_mismatch')
    if not opened:
        return errors
    actor = opened.get('execution', {})
    implementer = actor.get('implementer_identity')
    impl_lifecycle = _read_json(_task_file(task_dir, actor.get('implementer_lifecycle_ref', '')))
    if (not implementer or implementer == identity or actor.get('implementer_invocation_id') != implementer
            or actor.get('implementer_span_id') != impl_lifecycle.get('span_id', implementer)
            or impl_lifecycle.get('invocation_id') != implementer
            or impl_lifecycle.get('agent') in {None, 'reviewer'}
            or impl_lifecycle.get('stage_index') != end.get('implementation_stage_index')
            or impl_lifecycle.get('attempt') != end.get('attempt')
            or not end['captured_at'] <= impl_lifecycle.get('timing', {}).get('dispatched_at', '') <= opened['captured_at']):
        errors.append('checklist_implementer_identity_mismatch')
    for key in ['host_invocation_id', 'span_id', 'reviewer_identity', 'lifecycle_ref', 'review_mode', 'attempt', 'implementation_stage_index']:
        if actor.get(key) != execution.get(key):
            errors.append('checklist_write_execution_mismatch')
    for key in ['review_output_ref', 'review_report_ref', 'review_output_digest', 'review_report_digest']:
        if opened.get(key) != end.get(key):
            errors.append('checklist_write_review_mismatch')

    return errors


def checklist_preflight_status(task_dir: Path, *, for_test_write: bool = False) -> dict:
    """실제 관찰 사슬을 검사한다. legacy 완료 기록은 변경하거나 소급 인증하지 않는다."""
    task_dir = Path(task_dir)
    rows = event_payloads(task_dir)
    baseline = next((r for r in rows if r.get('kind') == 'source_baseline'), {})
    pipeline = _read_json(task_dir / 'pipeline.json')
    markers = [baseline.get('checklist_evidence_version'), pipeline.get('checklist_evidence_version')]
    markers.extend(s.get('checklist_evidence_version') for s in pipeline.get('stages', []) if isinstance(s, dict))
    markers.extend(r.get('evidence_version') for r in rows if r.get('kind') in {
        'checklist_review_begin', 'checklist_review_end', 'test_write_open'})
    versions = [v for v in markers if v is not None]
    result = {'required': bool(versions), 'version': 1 if versions else None, 'valid': True,
              'errors': [], 'begin_ref': None, 'end_ref': None, 'write_open_ref': None}
    if not versions:
        return result
    errors = result['errors']
    if any(type(v) is not int or v != 1 for v in versions) or pipeline.get('checklist_evidence_version') != 1:
        errors.append('checklist_evidence_version_mismatch')
    kinds = ['checklist_review_begin', 'checklist_review_end']
    if not for_test_write:
        kinds.append('test_write_open')
    selected = [next((r for r in rows if r.get('kind') == k), None) for k in kinds]
    if not all(selected):
        errors.append('missing_checklist_preflight_observation')
        result['valid'] = False
        return result
    begin, end = selected[:2]
    opened = selected[2] if len(selected) == 3 else None
    result.update(begin_ref=begin.get('event_id'), end_ref=end.get('event_id'),
                  write_open_ref=opened.get('event_id') if opened else None)
    try:
        root = Path(baseline['project_root']).resolve()
        stage_index = begin['implementation_stage_index']
        stage = pipeline['stages'][stage_index - 1]
        if not isinstance(stage, dict) or stage.get('attempt', 1) != begin.get('attempt'):
            raise ValueError('checklist_stage_mismatch')
        paths, targets, authorized, initial, current = _checklist_states(root, baseline, stage)
        if opened:
            result['authorized_test_paths'] = authorized
        if not baseline.get('complete') or baseline.get('limitations'):
            errors.append('checklist_baseline_incomplete')
        if any(v.get('state') not in {'file', 'missing', 'git_head'} for v in initial.values()):
            errors.append('checklist_baseline_incomplete')
        previous, position = None, rows.index(baseline)
        for event in selected:
            if (event.get('evidence_version') != 1 or event.get('baseline_id') != baseline.get('baseline_id')
                    or event.get('task_id') != task_dir.name or event.get('implementation_stage_index') != stage_index
                    or event.get('attempt') != begin.get('attempt') or event.get('review_mode') != 'test-checklist'
                    or not event.get('event_id') or event.get('previous_event_id') != previous
                    or rows.index(event) <= position or event.get('captured_at', '') < baseline.get('captured_at', '')):
                errors.append('checklist_observation_chain_mismatch')
            if (event.get('test_paths') != paths or event.get('test_targets') != targets
                    or event.get('authorized_test_paths') != authorized
                    or event.get('tests_before') != initial or event.get('tests_after') != initial):
                errors.append('checklist_tests_changed_before_write')
            checklist = _task_file(task_dir, event.get('checklist_ref', ''))
            if (not checklist.is_file() or _digest(checklist) != event.get('checklist_digest')
                    or event.get('checklist_digest') != begin.get('checklist_digest')):
                errors.append('checklist_content_changed')
            previous, position = event.get('event_id'), rows.index(event)
        errors.extend(_host_review_errors(task_dir, begin, end, opened))
        if any(v.get('state') not in {'file', 'missing', 'git_head'} for v in current.values()):
            errors.append('checklist_current_tests_incomplete')
        if any(current[p] != initial[p] for p in paths if not opened or p not in authorized):
            errors.append('checklist_test_change_outside_authorized_scope')
        if opened and any(rows.index(r) < rows.index(opened) or r.get('started_at', '') < opened['captured_at']
                          for r in rows if r.get('kind') == 'test_run'):
            errors.append('checklist_test_run_before_write_open')
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as exc:
        errors.append('checklist_observation_invalid:' + type(exc).__name__)
    result['errors'] = sorted(set(errors))
    result['valid'] = not errors

    return result


def observe_checklist_phase(task_dir: Path, project_root: Path, phase: str, execution: dict) -> dict:
    """현 상태를 직접 관찰한다. caller snapshot이나 시각을 인증으로 받지 않는다."""
    kinds = {'review_begin': 'checklist_review_begin', 'review_end': 'checklist_review_end', 'test_write_open': 'test_write_open'}
    if phase not in kinds:
        raise ValueError('invalid_checklist_phase')
    task_dir, root = Path(task_dir), Path(project_root).resolve()
    rows = event_payloads(task_dir)
    baseline = next((r for r in rows if r.get('kind') == 'source_baseline'), {})
    pipeline = _read_json(task_dir / 'pipeline.json')
    stage_index = execution['implementation_stage_index']
    stage = pipeline['stages'][stage_index - 1]
    paths, targets, authorized, initial, observed = _checklist_states(root, baseline, stage)
    if (not baseline.get('complete') or baseline.get('limitations') or observed != initial
            or str(root) != baseline.get('project_root')
            or any(v.get('state') not in {'file', 'missing', 'git_head'} for v in observed.values())):
        raise ValueError('checklist_preflight_failed:baseline_or_tests_changed')
    if phase == 'test_write_open':
        status = checklist_preflight_status(task_dir, for_test_write=True)
        if not status['required'] or not status['valid']:
            raise ValueError('checklist_preflight_failed:' + ','.join(status['errors']))
    previous = next((r for r in reversed(rows) if r.get('kind') in kinds.values()), {})
    payload = {'kind': kinds[phase], 'evidence_version': 1, 'event_id': str(uuid.uuid4()),
               'previous_event_id': previous.get('event_id'), 'baseline_id': baseline.get('baseline_id'),
               'task_id': task_dir.name, 'implementation_stage_index': stage_index,
               'attempt': execution['attempt'], 'review_mode': 'test-checklist', 'captured_at': now(),
               'checklist_ref': 'context/test-checklist.md', 'checklist_digest': _digest(task_dir / 'context/test-checklist.md'),
               'test_paths': paths, 'test_targets': targets, 'authorized_test_paths': authorized,
               'tests_before': observed, 'execution': dict(execution)}
    if phase != 'review_begin':
        for key in ['review_output_ref', 'review_report_ref']:
            payload[key] = execution[key]
            payload[key.replace('_ref', '_digest')] = _digest(_task_file(task_dir, execution[key]))

        begin = next((r for r in rows if r.get('kind') == 'checklist_review_begin'), {})
        end = payload
        opened = None
        if phase == 'test_write_open':
            end = next((r for r in rows if r.get('kind') == 'checklist_review_end'), {})
            opened = payload
        errors = _host_review_errors(task_dir, begin, end, opened)
        if errors:
            raise ValueError('checklist_preflight_failed:' + ','.join(errors))
    after_paths, _, _, _, after = _checklist_states(root, baseline, stage)
    if after_paths != paths or after != observed:
        raise ValueError('checklist_preflight_failed:baseline_or_tests_changed')
    payload['tests_after'] = after
    append_event(task_dir, payload)

    return payload


def _contract_paths(task_dir: Path, field: str) -> list[str]:
    pipeline = json.loads((Path(task_dir) / 'pipeline.json').read_text())
    return sorted({p for stage in pipeline.get('stages', []) if isinstance(stage, dict)
                   for p in stage.get('contract_preservation', {}).get(field, [])})


def production_paths(task_dir: Path) -> list[str]:
    return _contract_paths(task_dir, 'production_paths')


def _redact(text: str) -> str:
    return re.sub(r'(?i)(?:\b(?:token|password|passwd|secret|api[_-]?key)=\S+|\bbearer\s+\S+|(?:sk-|gh[pousr]_)[\w-]+)', '[REDACTED]', text)


def runner_selection(argv: list[str]) -> tuple[str, list[str]]:
    """지원하는 명시 실행 형식만 해석한다. 임의 코드의 문자열 언급은 실행 증거가 아니다."""
    if not argv:
        return '', []
    args = list(argv[1:])
    executable = Path(argv[0]).name
    if executable in {'mvn', 'mvnw'} and args[-1:] == ['test']:
        selectors = [arg[len('-Dtest='):] for arg in args if arg.startswith('-Dtest=')]
        if len(selectors) == 1 and re.fullmatch(r'[\w.]+(?:,[\w.]+)*', selectors[0]):
            return 'maven', selectors[0].split(',')
        return '', []

    python = executable.startswith('python')
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


def _maven_selected_class(target: str, selected: list[str]) -> str:
    match = re.fullmatch(r'src/test/java/([\w/]+)\.java', target)
    if not match:
        return ''
    name = match[1].replace('/', '.')
    return name if name in selected or name.rsplit('.', 1)[-1] in selected else ''


def targets_bound(test_targets: list[str], argv: list[str]) -> bool:
    kind, selected = runner_selection(argv)
    if kind == 'maven':
        return bool(test_targets) and all(_maven_selected_class(target, selected) for target in test_targets)
    return bool(test_targets) and all(any(t == a or t.startswith(a + '::') or a.startswith(t + '::')
                                        for a in selected) for t in test_targets)


_MAVEN_COLOR = re.compile(r'\x1b\[[0-9;]*m')
_SUREFIRE_GOAL = re.compile(r'^\[INFO\] --- (?:maven-)?surefire(?:-plugin)?:[^:]+:test ', re.MULTILINE)
_SUREFIRE_SUMMARY = re.compile(
    r'^\[(?:INFO|ERROR|WARNING)\] Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+),'
    r' Time elapsed: [^\n]+? -+ in ([\w.$]+)[^\S\n]*$', re.MULTILINE,
)
_SUREFIRE_FAILURE = re.compile(
    r'^\[ERROR\] Failed to execute goal org\.apache\.maven\.plugins:maven-surefire-plugin:[^:]+:test .*There are test failures\.',
    re.MULTILINE,
)
_MAVEN_BUILD = re.compile(r'^\[INFO\] BUILD (SUCCESS|FAILURE)[^\S\n]*$', re.MULTILINE)
_SUREFIRE_EVIDENCE = '\n[retained Surefire evidence]\n'


def _bounded_test_output(output: str, kind: str) -> str:
    output = _redact(output)
    if len(output) <= 120_000:
        return output

    bounded = output[:120_000] + '\n[bounded output]\n' + output[-8_000:]
    if kind != 'maven':
        return bounded

    lines = _MAVEN_COLOR.sub('', output).splitlines()
    evidence = '\n'.join(line for line in lines if any(
        pattern.match(line) for pattern in (_SUREFIRE_GOAL, _SUREFIRE_SUMMARY, _SUREFIRE_FAILURE, _MAVEN_BUILD)
    ))
    if len(evidence) > 32_000:
        evidence = '[Surefire evidence exceeds retention limit]'
    return bounded + _SUREFIRE_EVIDENCE + evidence + '\n'


def _maven_execution_targets(selected: list[str], output: str, outcome: str, targets: list[str]) -> list[str]:
    if _SUREFIRE_EVIDENCE in output:
        output = output.rsplit(_SUREFIRE_EVIDENCE, 1)[1]
    output = _MAVEN_COLOR.sub('', output)
    expected = {'passed': 'SUCCESS', 'failed': 'FAILURE'}.get(outcome)
    if not expected or expected not in _MAVEN_BUILD.findall(output) or not _SUREFIRE_GOAL.search(output):
        return []
    if outcome == 'failed' and not _SUREFIRE_FAILURE.search(output):
        return []

    summaries = _SUREFIRE_SUMMARY.findall(output)
    if any(int(errors) for _, _, errors, _, _ in summaries):
        return []
    verified = {name for count, failures, _, skipped, name in summaries
                if int(count) > 0 and int(skipped) == 0 and bool(int(failures)) == (outcome == 'failed')}
    return [target for target in targets if _maven_selected_class(target, selected) in verified]


def execution_targets(argv: list[str], output: str, outcome: str, targets: list[str] | None = None) -> list[str]:
    """선택 범위와 실제 결과를 결합한다. 미지원 runner/불명확한 실패 위치는 미검증이다."""
    kind, selected = runner_selection(argv)
    if kind == 'maven':
        return _maven_execution_targets(selected, output, outcome, targets or [])
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
    preflight = checklist_preflight_status(task_dir)
    if preflight['required'] and not preflight['valid']:
        raise ValueError('checklist_preflight_failed:' + ','.join(preflight['errors']))
    if phase == 'characterization' and preflight['required']:
        observed = snapshot(root, test_targets)
        initial = baseline_file_states(root, baseline, test_targets)
        authorized = set(preflight.get('authorized_test_paths', []))
        if any(value != initial[name]
               and (name not in authorized or initial[name]['state'] != 'missing' or value['state'] != 'file')
               for name, value in observed.items()):
            raise ValueError('checklist_preflight_failed:characterization_tests_changed')
    kind, _ = runner_selection(argv)
    if phase == 'green' and Path(argv[0]).name in {'mvn', 'mvnw'}:
        missing = [p for p in _contract_paths(task_dir, 'preserved_test_targets')
                   if p not in test_targets or not targets_bound([p], argv)]
        if missing:
            raise ValueError('maven_green_missing_preserved_tests: ' + ', '.join(missing))

    before, tests = snapshot(root, paths), snapshot(root, test_targets)
    if kind == 'pytest':
        argv = list(argv) + ['--verbosity=1', '--color=no']
    started, exit_code, outcome, output = now(), None, 'error', ''
    try:
        proc = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=timeout)
        exit_code, output = proc.returncode, proc.stdout + proc.stderr
        outcome = 'passed' if exit_code == 0 else 'error'
        if exit_code == 1 and kind == 'maven' and execution_targets(argv, output, 'failed', test_targets):
            outcome = 'failed'
        if exit_code == 1 and kind != 'maven' and ('AssertionError' in output or re.search(r'\b[1-9]\d* failed\b', output)) and not re.search(r'\b(?:ERROR|ImportError|ModuleNotFoundError|SyntaxError)\b', output):
            outcome = 'failed'
    except subprocess.TimeoutExpired as exc:
        outcome, output = 'timeout', str(exc)
    except OSError as exc:
        output = str(exc)
    if outcome in {'passed', 'failed'} and (not targets_bound(test_targets, argv)
                                           or not execution_targets(argv, output, outcome, test_targets)):
        outcome = 'unverified'
    ended, run_id = now(), str(uuid.uuid4())
    output = _bounded_test_output(output, kind)
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
