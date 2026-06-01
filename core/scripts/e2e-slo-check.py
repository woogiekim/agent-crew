#!/usr/bin/env python3
"""CI-ready E2E SLO checks for agent-crew commercialization readiness."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def run_timed(command: list[str], *, cwd: Path, env: dict[str, str]) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=str(cwd), env=env, text=True, capture_output=True)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "command": command,
        "returncode": proc.returncode,
        "elapsed_ms": round(elapsed_ms, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def check_budget(name: str, result: dict, budget_ms: int, allowed_rc: set[int] | None = None) -> dict:
    allowed = allowed_rc or {0}
    failures = []
    if result["returncode"] not in allowed:
        failures.append("returncode")
    if result["elapsed_ms"] > budget_ms:
        failures.append("latency")
    return {
        "name": name,
        "passed": not failures,
        "elapsed_ms": result["elapsed_ms"],
        "budget_ms": budget_ms,
        "returncode": result["returncode"],
        "failures": failures,
    }


def load_json_text(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        return {}


def load_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_fixture_path(value: str | None, *, fixture_path: Path, repo_root: Path) -> Path | None:
    if not value:
        return None

    path = Path(value).expanduser()
    if path.is_absolute():
        return path

    fixture_relative = fixture_path.parent / path
    if fixture_relative.exists():
        return fixture_relative.resolve()

    return (repo_root / path).resolve()


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    default_fixture = repo_root / "core" / "evaluations" / "e2e-slo.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(repo_root))
    parser.add_argument("--fixture", default=str(default_fixture))
    parser.add_argument("--crew-bin", default=str(repo_root / "core" / "bin" / "crew"))
    parser.add_argument("--memory-bin", default=str(repo_root / "core" / "bin" / "memory"))
    parser.add_argument("--status-budget-ms", type=int)
    parser.add_argument("--telemetry-budget-ms", type=int)
    parser.add_argument("--memory-search-budget-ms", type=int)
    parser.add_argument("--retrieval-fixture")
    parser.add_argument("--retrieval-results-file")
    parser.add_argument("--retrieval-elapsed-ms", type=float)
    parser.add_argument("--update-dry-run-budget-ms", type=int)
    parser.add_argument("--update-noop-local-budget-ms", type=int)
    parser.add_argument("--update-cold-local-budget-ms", type=int)
    parser.add_argument("--update-remote-budget-ms", type=int)
    parser.add_argument("--skip-memory-search", action="store_true")
    parser.add_argument("--skip-retrieval-eval", action="store_true")
    parser.add_argument("--skip-update-dry-run", action="store_true")
    parser.add_argument("--include-update-benchmark", action="store_true")
    parser.add_argument("--include-remote-update", action="store_true")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    fixture_path = Path(args.fixture).expanduser().resolve()
    fixture = load_json_file(fixture_path)
    status_budget_ms = args.status_budget_ms or int(fixture.get("status_budget_ms", 500))
    telemetry_budget_ms = args.telemetry_budget_ms or int(fixture.get("telemetry_budget_ms", 500))
    memory_search_budget_ms = args.memory_search_budget_ms or int(fixture.get("memory_search_budget_ms", 500))
    update_dry_run_budget_ms = args.update_dry_run_budget_ms or int(fixture.get("update_dry_run_budget_ms", 5000))
    update_noop_local_budget_ms = args.update_noop_local_budget_ms or int(fixture.get("update_noop_local_budget_ms", 1000))
    update_cold_local_budget_ms = args.update_cold_local_budget_ms or int(fixture.get("update_cold_local_budget_ms", 10000))
    update_remote_budget_ms = args.update_remote_budget_ms or int(fixture.get("update_remote_budget_ms", 30000))
    env = os.environ.copy()
    env["PROJECT_ROOT"] = str(project_root)

    checks = []
    status = run_timed([args.crew_bin, "status", "--json"], cwd=project_root, env=env)
    checks.append(check_budget("crew_status_json", status, status_budget_ms))

    telemetry = run_timed([args.crew_bin, "telemetry", "--format", "json", "--recent", "10"], cwd=project_root, env=env)
    checks.append(check_budget("crew_telemetry_json", telemetry, telemetry_budget_ms))

    if not args.skip_memory_search:
        memory = run_timed(
            [args.memory_bin, "search", "commercialization e2e telemetry memory", "--limit", "5"],
            cwd=project_root,
            env=env,
        )
        checks.append(check_budget("memory_search", memory, memory_search_budget_ms, allowed_rc={0, 124}))

    if not args.skip_retrieval_eval:
        retrieval_command = [
            sys.executable,
            str(repo_root / "core" / "scripts" / "memory-retrieval-eval.py"),
            "--format",
            "json",
        ]
        retrieval_fixture = resolve_fixture_path(
            args.retrieval_fixture or fixture.get("memory_retrieval_fixture"),
            fixture_path=fixture_path,
            repo_root=repo_root,
        )
        retrieval_results = resolve_fixture_path(
            args.retrieval_results_file or fixture.get("memory_retrieval_results_file"),
            fixture_path=fixture_path,
            repo_root=repo_root,
        )
        retrieval_elapsed_ms = (
            args.retrieval_elapsed_ms
            if args.retrieval_elapsed_ms is not None
            else fixture.get("memory_retrieval_elapsed_ms")
        )
        if retrieval_fixture is not None:
            retrieval_command.extend(["--fixture", str(retrieval_fixture)])
        if retrieval_results is not None:
            retrieval_command.extend(["--results-file", str(retrieval_results)])
        if retrieval_elapsed_ms is not None:
            retrieval_command.extend(["--elapsed-ms", str(retrieval_elapsed_ms)])

        retrieval = run_timed(retrieval_command, cwd=project_root, env=env)
        retrieval_payload = load_json_text(retrieval["stdout"])
        retrieval_failures = []
        if retrieval["returncode"] != 0 or not retrieval_payload.get("passed"):
            retrieval_failures.append("retrieval_eval")
        checks.append({
            "name": "memory_retrieval_eval",
            "passed": not retrieval_failures,
            "elapsed_ms": retrieval.get("elapsed_ms"),
            "budget_ms": retrieval_payload.get("latency_budget_ms"),
            "returncode": retrieval["returncode"],
            "failures": retrieval_failures,
            "retrieval": {
                "latency_ms": retrieval_payload.get("latency_ms"),
                "noise": retrieval_payload.get("noise", []),
                "noise_budget_count": retrieval_payload.get("noise_budget_count"),
                "misses": retrieval_payload.get("misses", []),
            },
        })

    if not args.skip_update_dry_run:
        update = run_timed(
            ["bash", str(repo_root / "core" / "scripts" / "verify-update-dry-run.sh")],
            cwd=project_root,
            env=env,
        )
        checks.append(check_budget("update_dry_run", update, update_dry_run_budget_ms))

    if args.include_update_benchmark:
        benchmark_modes = ["noop-local", "cold-local"]
        if args.include_remote_update:
            benchmark_modes.append("remote")
        command = [
            sys.executable,
            str(repo_root / "core" / "scripts" / "update-slo-benchmark.py"),
            "--project-root",
            str(project_root),
            "--source-root",
            str(repo_root),
            "--crew-bin",
            args.crew_bin,
            "--noop-local-budget-ms",
            str(update_noop_local_budget_ms),
            "--cold-local-budget-ms",
            str(update_cold_local_budget_ms),
            "--remote-budget-ms",
            str(update_remote_budget_ms),
            "--format",
            "json",
        ]
        for mode in benchmark_modes:
            command.extend(["--mode", mode])
        benchmark = run_timed(command, cwd=project_root, env=env)
        benchmark_payload = load_json_text(benchmark["stdout"])
        benchmark_failures = []
        if benchmark["returncode"] != 0 or not benchmark_payload.get("passed"):
            benchmark_failures.append("update_benchmark")
        checks.append({
            "name": "update_benchmark",
            "passed": not benchmark_failures,
            "elapsed_ms": benchmark.get("elapsed_ms"),
            "budget_ms": None,
            "returncode": benchmark["returncode"],
            "failures": benchmark_failures,
            "benchmark": benchmark_payload.get("checks", []),
        })

    payload = {
        "schema_version": 1,
        "fixture": str(Path(args.fixture).expanduser()),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }

    if args.format == "json":
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(("PASS" if payload["passed"] else "FAIL") + ": e2e slo check")
        for check in checks:
            status_text = "PASS" if check["passed"] else "FAIL"
            print(f"- {status_text} {check['name']}: {check['elapsed_ms']}ms / budget {check.get('budget_ms')}ms")

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
