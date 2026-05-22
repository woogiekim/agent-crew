"""Tests for update latency SLO benchmarking."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BENCHMARK = REPO_ROOT / "core" / "scripts" / "update-slo-benchmark.py"
E2E_SLO = REPO_ROOT / "core" / "scripts" / "e2e-slo-check.py"


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
