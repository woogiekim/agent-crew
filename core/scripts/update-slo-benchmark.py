#!/usr/bin/env python3
"""Benchmark crew:update modes against explicit latency SLOs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


PHASE_RE = re.compile(r"^update_phase:\s*([a-z_]+)=([0-9]+)ms\s*$", re.M)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_timed(command: list[str], *, cwd: Path, env: dict[str, str]) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=str(cwd), env=env, text=True, capture_output=True)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    phases = {name: int(value) for name, value in PHASE_RE.findall(proc.stdout + proc.stderr)}
    return {
        "command": command,
        "returncode": proc.returncode,
        "elapsed_ms": elapsed_ms,
        "phases_ms": phases,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def mode_command(mode: str, crew_bin: str, source_root: Path) -> list[str]:
    if mode in {"noop-local", "cold-local"}:
        return [crew_bin, "update", "--local", str(source_root)]
    if mode == "remote":
        return [crew_bin, "update"]
    raise ValueError(f"unsupported mode: {mode}")


def budget_for(mode: str, args: argparse.Namespace, fixture: dict) -> int:
    explicit = {
        "noop-local": args.noop_local_budget_ms,
        "cold-local": args.cold_local_budget_ms,
        "remote": args.remote_budget_ms,
    }[mode]
    if explicit:
        return explicit
    keys = {
        "noop-local": "update_noop_local_budget_ms",
        "cold-local": "update_cold_local_budget_ms",
        "remote": "update_remote_budget_ms",
    }
    defaults = {
        "noop-local": 1000,
        "cold-local": 10000,
        "remote": 30000,
    }
    return int(fixture.get(keys[mode], defaults[mode]))


def evaluate(mode: str, result: dict, budget_ms: int) -> dict:
    failures = []
    if result["returncode"] != 0:
        failures.append("returncode")
    if result["elapsed_ms"] > budget_ms:
        failures.append("latency")
    if mode in {"noop-local", "cold-local"} and not result["phases_ms"]:
        failures.append("missing_phase_timings")
    return {
        "mode": mode,
        "passed": not failures,
        "elapsed_ms": result["elapsed_ms"],
        "budget_ms": budget_ms,
        "returncode": result["returncode"],
        "failures": failures,
        "phases_ms": result["phases_ms"],
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    default_fixture = repo_root / "core" / "evaluations" / "e2e-slo.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(repo_root))
    parser.add_argument("--source-root", default=str(repo_root))
    parser.add_argument("--fixture", default=str(default_fixture))
    parser.add_argument("--crew-bin", default=str(repo_root / "core" / "bin" / "crew"))
    parser.add_argument("--mode", action="append", choices=["noop-local", "cold-local", "remote"])
    parser.add_argument("--noop-local-budget-ms", type=int)
    parser.add_argument("--cold-local-budget-ms", type=int)
    parser.add_argument("--remote-budget-ms", type=int)
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    source_root = Path(args.source_root).expanduser().resolve()
    fixture = load_json(Path(args.fixture).expanduser().resolve())
    modes = args.mode or ["noop-local"]
    env = os.environ.copy()
    env["PROJECT_ROOT"] = str(project_root)

    checks = []
    for mode in modes:
        mode_env = env.copy()
        if mode == "cold-local":
            mode_env["AGENT_CREW_DISABLE_FAST_NOOP_UPDATE"] = "1"
        result = run_timed(mode_command(mode, args.crew_bin, source_root), cwd=project_root, env=mode_env)
        checks.append(evaluate(mode, result, budget_for(mode, args, fixture)))

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
        print(("PASS" if payload["passed"] else "FAIL") + ": update slo benchmark")
        for check in checks:
            status = "PASS" if check["passed"] else "FAIL"
            print(f"- {status} {check['mode']}: {check['elapsed_ms']}ms / budget {check['budget_ms']}ms")
            if check["phases_ms"]:
                phase_text = ", ".join(f"{k}={v}ms" for k, v in sorted(check["phases_ms"].items()))
                print(f"  phases: {phase_text}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
