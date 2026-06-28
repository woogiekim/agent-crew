#!/usr/bin/env python3
"""CI-ready E2E SLO checks for agent-crew commercialization readiness."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
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


def aggregate_elapsed(values: list[float], mode: str) -> float:
    if not values:
        return 0.0
    if mode == "max":
        return max(values)
    ordered = sorted(values)
    if mode == "p95":
        index = max(0, math.ceil(len(ordered) * 0.95) - 1)
        return ordered[index]

    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def run_sampled(command: list[str], *, cwd: Path, env: dict[str, str], samples: int) -> list[dict]:
    return [run_timed(command, cwd=cwd, env=env) for _ in range(samples)]


def check_sampled_budget(
    name: str,
    results: list[dict],
    budget_ms: int,
    *,
    warmup_samples: int,
    aggregation: str,
    allowed_rc: set[int] | None = None,
) -> dict:
    allowed = allowed_rc or {0}
    measured = results[warmup_samples:] or results
    sample_ms = [float(result["elapsed_ms"]) for result in results]
    measured_ms = [float(result["elapsed_ms"]) for result in measured]
    aggregate_ms = round(aggregate_elapsed(measured_ms, aggregation), 3)
    returncodes = [int(result["returncode"]) for result in results]
    failures = []
    if any(returncode not in allowed for returncode in returncodes):
        failures.append("returncode")
    if aggregate_ms > budget_ms:
        failures.append("latency")

    return {
        "name": name,
        "passed": not failures,
        "elapsed_ms": aggregate_ms,
        "aggregate_elapsed_ms": aggregate_ms,
        "budget_ms": budget_ms,
        "returncode": returncodes[-1] if returncodes else None,
        "returncodes": returncodes,
        "failures": failures,
        "sample_count": len(results),
        "warmup_samples": warmup_samples,
        "aggregation": aggregation,
        "samples_ms": sample_ms,
        "measured_samples_ms": measured_ms,
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


def prepare_isolated_agent_crew_home(*, repo_root: Path, project_root: Path) -> tempfile.TemporaryDirectory[str]:
    temp_home = tempfile.TemporaryDirectory(prefix="agent-crew-slo-")
    resolved = subprocess.run(
        [
            sys.executable,
            str(repo_root / "core" / "scripts" / "project_state.py"),
            "resolve",
            "--agent-crew-home",
            temp_home.name,
            "--project-root",
            str(project_root),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )
    state_dir = None
    if resolved.returncode == 0:
        payload = load_json_text(resolved.stdout)
        if payload.get("state_dir"):
            state_dir = Path(str(payload["state_dir"]))
    if state_dir is None:
        state_dir = Path(temp_home.name) / "state" / project_root.name
    state_dir.mkdir(parents=True, exist_ok=True)
    return temp_home


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
    parser.add_argument("--samples", type=int)
    parser.add_argument("--warmup-samples", type=int)
    parser.add_argument("--aggregation", choices=["median", "p95", "max"])
    parser.add_argument("--isolated-agent-crew-home", action="store_true", help="Measure status/telemetry against a temporary AGENT_CREW_HOME with an empty project state.")
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
    samples = max(1, args.samples or int(fixture.get("samples", 1)))
    warmup_samples = max(0, args.warmup_samples if args.warmup_samples is not None else int(fixture.get("warmup_samples", 0)))
    if samples > 1:
        warmup_samples = min(warmup_samples, samples - 1)
    else:
        warmup_samples = 0
    aggregation = args.aggregation or str(fixture.get("aggregation", "median"))
    env = os.environ.copy()
    env["PROJECT_ROOT"] = str(project_root)
    isolated_home: tempfile.TemporaryDirectory[str] | None = None
    if args.isolated_agent_crew_home:
        isolated_home = prepare_isolated_agent_crew_home(repo_root=repo_root, project_root=project_root)
        env["AGENT_CREW_HOME"] = isolated_home.name

    checks = []
    status = run_sampled([args.crew_bin, "status", "--json"], cwd=project_root, env=env, samples=samples)
    checks.append(check_sampled_budget(
        "crew_status_json",
        status,
        status_budget_ms,
        warmup_samples=warmup_samples,
        aggregation=aggregation,
    ))

    telemetry = run_sampled(
        [args.crew_bin, "telemetry", "--format", "json", "--recent", "10"],
        cwd=project_root,
        env=env,
        samples=samples,
    )
    checks.append(check_sampled_budget(
        "crew_telemetry_json",
        telemetry,
        telemetry_budget_ms,
        warmup_samples=warmup_samples,
        aggregation=aggregation,
    ))

    if not args.skip_memory_search:
        memory = run_sampled(
            [args.memory_bin, "search", "commercialization e2e telemetry memory", "--limit", "5"],
            cwd=project_root,
            env=env,
            samples=samples,
        )
        checks.append(check_sampled_budget(
            "memory_search",
            memory,
            memory_search_budget_ms,
            warmup_samples=warmup_samples,
            aggregation=aggregation,
            allowed_rc={0, 124},
        ))

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
        update = run_sampled(
            ["bash", str(repo_root / "core" / "scripts" / "verify-update-dry-run.sh")],
            cwd=project_root,
            env=env,
            samples=samples,
        )
        checks.append(check_sampled_budget(
            "update_dry_run",
            update,
            update_dry_run_budget_ms,
            warmup_samples=warmup_samples,
            aggregation=aggregation,
        ))

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
        "isolated_agent_crew_home": bool(args.isolated_agent_crew_home),
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

    if isolated_home is not None:
        isolated_home.cleanup()

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
