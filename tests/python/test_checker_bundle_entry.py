"""두 checker의 source/installed 의존 경계와 공개 CLI 계약."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "core/scripts"
CHECKERS = ["pipeline-quality-plan-check.py", "quality-loop-check.py"]


@pytest.fixture(params=CHECKERS)
def checker(request):
    return request.param


def installed(tmp_path, name="crew", *, stale=True):
    root = tmp_path / name
    canonical = root / "system/scripts"
    discovery = root / "scripts"
    canonical.mkdir(parents=True)
    discovery.mkdir()
    (root / "bin").mkdir()
    (root / "bin/crew").write_text("# 합성 설치 구조\n")
    shutil.copytree(ROOT / "core/agents", root / "system/agents")
    shutil.copytree(ROOT / "core/rules", root / "system/rules")
    for source in SCRIPTS.glob("*.py"):
        shutil.copy2(source, canonical / source.name)
        shutil.copy2(source, discovery / source.name)
    if stale:
        (discovery / "quality_loop_lib.py").write_text("# 필수 API가 없는 오래된 사본\n")

    return root


def environment(tmp_path):
    home = tmp_path / "foreign-home"
    (home / "scripts").mkdir(parents=True, exist_ok=True)
    (home / "scripts/quality_loop_lib.py").write_text("raise RuntimeError('foreign bundle')\n")

    return dict(os.environ, HOME=str(home), AGENT_CREW_HOME=str(home),
                PYTHONDONTWRITEBYTECODE="1")


def input_args(tmp_path, checker, *, valid=True):
    task = tmp_path / ("정상 입력 공백" if valid else "거부 입력 공백")
    task.mkdir(exist_ok=True)
    task_text = "Review 한국어 원문\n공백 보존"
    if not valid:
        task_text = "Implement a backend feature"
    pipeline = {"task": task_text, "stages": ["analyst", "reviewer"],
                "mutation_scope": "read_only", "completed_stages": 0}
    if not valid:
        pipeline["stages"] = ["backend", "reviewer"]
        pipeline["mutation_scope"] = "workspace_write"
    path = task / "pipeline.json"
    path.write_text(json.dumps(pipeline, ensure_ascii=False))
    (task / "register.json").write_text(json.dumps({
        "task": task_text, "status": "completed", "mutation_scope": pipeline["mutation_scope"],
    }))
    if checker == CHECKERS[0]:
        return ["--pipeline", str(path), "--task", task_text]

    return ["--task-dir", str(task), "--target-status", "completed"]


def invoke(tmp_path, sut, args, *, output_format="json", label="run"):
    cwd = tmp_path / "unrelated-cwd"
    cwd.mkdir(exist_ok=True)
    result = subprocess.run([sys.executable, str(sut), *args, "--format", output_format],
                            cwd=cwd, env=environment(tmp_path), capture_output=True,
                            text=True, timeout=15)
    (tmp_path / (label + ".stdout.log")).write_text(result.stdout)
    (tmp_path / (label + ".stderr.log")).write_text(result.stderr)

    return result


def test_success_case_discovery_checker_uses_canonical_bundle(tmp_path, checker):
    """success-case(contract) - 오래된 discovery API 대신 정상 canonical에서 검사한다."""
    root = installed(tmp_path)
    sut = root / "scripts" / checker
    args = input_args(tmp_path, checker)

    result = invoke(tmp_path, sut, args)
    exit_code = result.returncode

    assert exit_code == 0, "정상 canonical bundle로 실제 검사를 실행해야 한다"
    assert json.loads(result.stdout)["passed"] is True


@pytest.mark.parametrize("name", ["crew", "core", "system"])
def test_boundary_case_checker_root_names_use_canonical_bundle(tmp_path, checker, name):
    """boundary-case(contract) - root basename과 외부 HOME/CWD가 bundle 선택을 바꾸지 않는다."""
    root = installed(tmp_path, name)
    sut = root / "scripts" / checker
    args = input_args(tmp_path, checker)

    result = invoke(tmp_path, sut, args)
    exit_code = result.returncode

    assert exit_code == 0, "설치 root 이름과 무관하게 같은-root canonical을 사용해야 한다"
    assert json.loads(result.stdout)["passed"] is True


@pytest.mark.parametrize("damage", ["missing", "api", "import", "recursive"])
def test_failure_case_checker_canonical_bundle_fails_closed(tmp_path, checker, damage):
    """failure-case(contract) - canonical 파손을 정상 discovery로 숨기지 않는다."""
    root = installed(tmp_path, stale=False)
    sut = root / "scripts" / checker
    canonical = root / "system/scripts" / checker
    if damage in {"missing", "recursive"}:
        canonical.unlink()
    if damage == "recursive":
        canonical.symlink_to(sut)
    if damage == "api":
        (canonical.parent / "quality_loop_lib.py").write_text("# 필수 API 부재\n")
    if damage == "import":
        (canonical.parent / "quality_loop_lib.py").write_text("raise RuntimeError('canonical broken')\n")
    args = input_args(tmp_path, checker)

    result = invoke(tmp_path, sut, args)

    assert result.returncode != 0
    assert not result.stdout.strip()
    expected = {"missing": "canonical", "recursive": "recursive",
                "api": "cannot import name", "import": "canonical broken"}
    assert expected[damage] in result.stderr


def test_boundary_case_source_checker_uses_own_bundle(tmp_path, checker):
    """boundary-case(contract) - source는 파손된 외부 설치 환경과 독립적으로 실행한다."""
    sut = SCRIPTS / checker
    args = input_args(tmp_path, checker)

    result = invoke(tmp_path, sut, args)

    assert result.returncode == 0
    assert json.loads(result.stdout)["passed"] is True


@pytest.mark.parametrize("valid", [True, False])
@pytest.mark.parametrize("output_format", ["json", "text"])
def test_success_case_checker_preserves_cli_result(tmp_path, checker, valid, output_format):
    """success-case(regression) - 정상/거부 판정, 원문 argv와 반복 실행의 비변경을 보존한다."""
    root = installed(tmp_path)
    args = input_args(tmp_path, checker, valid=valid)
    inputs = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    scripts = {path: path.read_bytes() for path in root.rglob("*.py")}
    expected_exit = 0 if valid else 1
    results = []
    entries = [(SCRIPTS / checker, SCRIPTS),
               (root / "system/scripts" / checker, root / "system/scripts"),
               (root / "scripts" / checker, root / "system/scripts"),
               (root / "scripts" / checker, root / "system/scripts")]
    for index, (sut, bundle) in enumerate(entries):
        result = invoke(tmp_path, sut, args, output_format=output_format, label=str(index))
        assert result.returncode == expected_exit
        if output_format == "json":
            payload = json.loads(result.stdout)
            assert payload["passed"] is valid
            if checker == CHECKERS[1]:
                assert payload["skill_content_audit"]["script"] == str(bundle / "skill-content-audit.py")
                payload["skill_content_audit"]["script"] = "<selected bundle>/skill-content-audit.py"
            results.append(payload)
        if output_format == "text":
            assert result.stdout.startswith("PASS" if valid else "FAIL")
            results.append(result.stdout)

    assert all(result == results[0] for result in results)
    assert all(path.read_bytes() == content for path, content in inputs.items())
    assert all(path.read_bytes() == content for path, content in scripts.items())


@pytest.mark.parametrize("entry", ["source", "system", "discovery"])
@pytest.mark.parametrize("error", ["required", "format", "missing"])
def test_boundary_case_checker_preserves_argument_errors(tmp_path, checker, entry, error):
    """boundary-case(contract) - 정상 bundle에서 parser와 입력 오류의 exit 2를 보존한다."""
    root = installed(tmp_path)
    entries = {"source": SCRIPTS / checker, "system": root / "system/scripts" / checker,
               "discovery": root / "scripts" / checker}
    sut = entries[entry]
    args = []
    if error != "required":
        args = input_args(tmp_path, checker)
    if error == "format":
        args += ["--format", "unsupported"]
    if error == "missing":
        args[1] = str(tmp_path / "not-found")
    output_format = "unsupported" if error == "format" else "json"

    result = invoke(tmp_path, sut, args, output_format=output_format)

    assert result.returncode == 2
    assert not result.stdout.strip()
    assert ("error:" in result.stderr) or ("not found:" in result.stderr)
