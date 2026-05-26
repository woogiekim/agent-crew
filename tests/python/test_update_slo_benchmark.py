"""Tests for update latency SLO benchmarking."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BENCHMARK = REPO_ROOT / "core" / "scripts" / "update-slo-benchmark.py"
E2E_SLO = REPO_ROOT / "core" / "scripts" / "e2e-slo-check.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _load_module(BENCHMARK, "update_slo_benchmark")
e2e_slo = _load_module(E2E_SLO, "e2e_slo_check")


def fake_crew(path: Path, *, sleep_script: str = "") -> Path:
    content = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{sleep_script}\n"
        "printf 'update_phase: fingerprint_check=1ms\\n'\n"
        "printf 'update_phase: adapter_setup=2ms\\n'\n"
        "printf 'update_phase: total=3ms\\n'\n"
    )
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_update_slo_benchmark_measures_noop_cold_and_remote_modes(tmp_path: Path):
    crew = fake_crew(tmp_path / "crew")
    result = subprocess.run(
        [
            "python3",
            str(BENCHMARK),
            "--project-root",
            str(tmp_path),
            "--source-root",
            str(tmp_path),
            "--crew-bin",
            str(crew),
            "--mode",
            "noop-local",
            "--mode",
            "cold-local",
            "--mode",
            "remote",
            "--noop-local-budget-ms",
            "1000",
            "--cold-local-budget-ms",
            "1000",
            "--remote-budget-ms",
            "1000",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert [check["mode"] for check in payload["checks"]] == ["noop-local", "cold-local", "remote"]
    assert payload["checks"][0]["phases_ms"]["fingerprint_check"] == 1


def test_update_slo_benchmark_fails_budget(tmp_path: Path):
    crew = fake_crew(tmp_path / "crew", sleep_script="python3 - <<'PY'\nimport time\ntime.sleep(0.03)\nPY")
    result = subprocess.run(
        [
            "python3",
            str(BENCHMARK),
            "--project-root",
            str(tmp_path),
            "--source-root",
            str(tmp_path),
            "--crew-bin",
            str(crew),
            "--mode",
            "noop-local",
            "--noop-local-budget-ms",
            "1",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "latency" in payload["checks"][0]["failures"]


def test_update_slo_benchmark_helpers_cover_failures_and_fixture_defaults(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert benchmark.load_json(invalid) == {}

    try:
        benchmark.mode_command("invalid", "crew", tmp_path)
    except ValueError as exc:
        assert "unsupported mode" in str(exc)
    else:
        raise AssertionError("unsupported benchmark mode should fail")

    args = type(
        "Args",
        (),
        {
            "noop_local_budget_ms": None,
            "cold_local_budget_ms": None,
            "remote_budget_ms": None,
        },
    )()
    assert benchmark.budget_for("noop-local", args, {"update_noop_local_budget_ms": 123}) == 123

    check = benchmark.evaluate(
        "noop-local",
        {"returncode": 1, "elapsed_ms": 2000, "phases_ms": {}},
        1000,
        warmup={"returncode": 1, "elapsed_ms": 10},
    )
    assert check["failures"] == [
        "warmup_returncode",
        "returncode",
        "latency",
        "missing_phase_timings",
    ]


def test_update_slo_benchmark_warms_noop_local_before_timing(tmp_path: Path):
    calls = tmp_path / "calls"
    crew = tmp_path / "crew"
    crew.write_text(
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"calls_file={str(calls)!r}\n"
            "calls=0\n"
            "[ -f \"${calls_file}\" ] && calls=$(cat \"${calls_file}\")\n"
            "calls=$((calls + 1))\n"
            "printf '%s\\n' \"${calls}\" > \"${calls_file}\"\n"
            "if [ \"${calls}\" = 1 ]; then\n"
            "  python3 - <<'PY'\n"
            "import time\n"
            "time.sleep(0.15)\n"
            "PY\n"
            "  printf 'update_phase: adapter_setup=150ms\\n'\n"
            "else\n"
            "  printf 'update_phase: fingerprint_check=1ms\\n'\n"
            "fi\n"
            "printf 'update_phase: total=1ms\\n'\n"
        ),
        encoding="utf-8",
    )
    crew.chmod(crew.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        [
            "python3",
            str(BENCHMARK),
            "--project-root",
            str(tmp_path),
            "--source-root",
            str(tmp_path),
            "--crew-bin",
            str(crew),
            "--mode",
            "noop-local",
            "--noop-local-budget-ms",
            "100",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    check = payload["checks"][0]
    assert check["passed"] is True
    assert check["warmup_returncode"] == 0
    assert check["warmup_elapsed_ms"] > check["elapsed_ms"]
    assert calls.read_text(encoding="utf-8").strip() == "2"


def test_update_slo_benchmark_text_output_lists_phase_timings(tmp_path: Path):
    crew = fake_crew(tmp_path / "crew")

    result = subprocess.run(
        [
            "python3",
            str(BENCHMARK),
            "--project-root",
            str(tmp_path),
            "--source-root",
            str(tmp_path),
            "--crew-bin",
            str(crew),
            "--mode",
            "cold-local",
            "--cold-local-budget-ms",
            "1000",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: update slo benchmark" in result.stdout
    assert "- PASS cold-local:" in result.stdout
    assert "phases:" in result.stdout


def test_e2e_slo_can_include_update_benchmark_without_remote(tmp_path: Path):
    crew = fake_crew(tmp_path / "crew")
    memory = tmp_path / "memory"
    memory.write_text("#!/usr/bin/env bash\nprintf '[fts] none: none\\n'\n", encoding="utf-8")
    memory.chmod(memory.stat().st_mode | stat.S_IXUSR)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps({
            "status_budget_ms": 1000,
            "telemetry_budget_ms": 1000,
            "memory_search_budget_ms": 1000,
            "update_dry_run_budget_ms": 1000,
            "update_noop_local_budget_ms": 1000,
            "update_cold_local_budget_ms": 1000,
            "update_remote_budget_ms": 1000,
        }),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["AGENT_CREW_HOME"] = str(tmp_path / "agent-home")
    (tmp_path / "agent-home" / "state" / tmp_path.name / "tasks").mkdir(parents=True)

    result = subprocess.run(
        [
            "python3",
            str(E2E_SLO),
            "--project-root",
            str(tmp_path),
            "--fixture",
            str(fixture),
            "--crew-bin",
            str(crew),
            "--memory-bin",
            str(memory),
            "--skip-memory-search",
            "--skip-retrieval-eval",
            "--skip-update-dry-run",
            "--include-update-benchmark",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    update = next(check for check in payload["checks"] if check["name"] == "update_benchmark")
    assert [check["mode"] for check in update["benchmark"]] == ["noop-local", "cold-local"]


def test_e2e_slo_helpers_cover_invalid_json_and_budget_failures(tmp_path: Path):
    assert e2e_slo.load_json_text("not json") == {}
    assert e2e_slo.load_json_file(tmp_path / "missing.json") == {}
    check = e2e_slo.check_budget(
        "probe",
        {"returncode": 2, "elapsed_ms": 2000},
        1000,
    )

    assert check["failures"] == ["returncode", "latency"]


def test_e2e_slo_runs_memory_search_and_retrieval_eval(tmp_path: Path):
    crew = tmp_path / "crew"
    crew.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    crew.chmod(crew.stat().st_mode | stat.S_IXUSR)
    memory = tmp_path / "memory"
    memory.write_text("#!/usr/bin/env bash\nprintf '[fts] none: none\\n'\n", encoding="utf-8")
    memory.chmod(memory.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        [
            "python3",
            str(E2E_SLO),
            "--project-root",
            str(tmp_path),
            "--crew-bin",
            str(crew),
            "--memory-bin",
            str(memory),
            "--skip-update-dry-run",
            "--status-budget-ms",
            "10000",
            "--telemetry-budget-ms",
            "10000",
            "--memory-search-budget-ms",
            "10000",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode in {0, 1}, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    names = {check["name"] for check in payload["checks"]}
    assert "memory_search" in names
    assert "memory_retrieval_eval" in names


def test_e2e_slo_runs_update_dry_run_and_remote_benchmark_failure(tmp_path: Path):
    crew = tmp_path / "crew"
    crew.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"${1:-}\" = status ] || [ \"${1:-}\" = telemetry ]; then exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    crew.chmod(crew.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        [
            "python3",
            str(E2E_SLO),
            "--project-root",
            str(tmp_path),
            "--crew-bin",
            str(crew),
            "--skip-memory-search",
            "--skip-retrieval-eval",
            "--include-update-benchmark",
            "--include-remote-update",
            "--status-budget-ms",
            "10000",
            "--telemetry-budget-ms",
            "10000",
            "--update-dry-run-budget-ms",
            "100000",
            "--update-noop-local-budget-ms",
            "10000",
            "--update-cold-local-budget-ms",
            "10000",
            "--update-remote-budget-ms",
            "10000",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    names = {check["name"] for check in payload["checks"]}
    assert "update_dry_run" in names
    update = next(check for check in payload["checks"] if check["name"] == "update_benchmark")
    assert "update_benchmark" in update["failures"]


def test_e2e_slo_text_output_lists_checks(tmp_path: Path):
    crew = tmp_path / "crew"
    crew.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    crew.chmod(crew.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        [
            "python3",
            str(E2E_SLO),
            "--project-root",
            str(tmp_path),
            "--crew-bin",
            str(crew),
            "--skip-memory-search",
            "--skip-retrieval-eval",
            "--skip-update-dry-run",
            "--status-budget-ms",
            "10000",
            "--telemetry-budget-ms",
            "10000",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: e2e slo check" in result.stdout
    assert "- PASS crew_status_json:" in result.stdout
    assert "- PASS crew_telemetry_json:" in result.stdout
