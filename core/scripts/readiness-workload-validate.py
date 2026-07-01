#!/usr/bin/env python3
"""Run a deterministic readiness workload and emit workload evidence.

Inputs:
  --crew-bin PATH       crew CLI to exercise
  --output PATH         optional JSON output path
  --format text|json    output format
  --keep-temp           retain the temporary state/project directory

Outputs:
  Workload evidence JSON compatible with readiness-metrics.py and
  readiness-gate.py.

Exit codes:
  0 - validation workload completed and evidence generated
  1 - one or more validation scenarios failed
  2 - invalid arguments or missing helper
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_state import resolve_project_state


SCENARIOS = [
    {
        "id": "workflow_host_bridge_auto_completion",
        "args": [
            "run",
            "--host-bridge-command",
            "bash -c 'printf \"%s\\n\" readiness-workload-completed'",
            "Read-only readiness workload workflow validation.",
        ],
        "expected": ["STATUS: completed", "HOST_BRIDGE: auto_completed"],
    },
    {
        "id": "direct_agent_bridge_auto_completion",
        "args": [
            "agent",
            "--host-bridge-command",
            "printf '%s\\n' readiness-direct-agent-completed",
            "analyst",
            "Explain the readiness workload validation state in one concise sentence.",
        ],
        "expected": ["STATUS: completed", "HOST_BRIDGE: auto_completed"],
    },
]


def load_script_module(script_name: str, module_name: str):
    path = Path(__file__).resolve().with_name(script_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise ValueError(f"cannot load helper script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_scenario(crew_bin: Path, args: list[str], *, home: Path, project_root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env.update({
        "AGENT_CREW_HOME": str(home),
        "PROJECT_ROOT": str(project_root),
        "AGENT_CREW_AUTO_SYNC_RUNTIME_ON_RUN": "0",
        "AGENT_CREW_AUTO_SYNC_HOOKS_ON_RUN": "0",
    })
    completed = subprocess.run(
        [str(crew_bin), *args],
        cwd=str(project_root),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    output = completed.stdout + completed.stderr
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output": output,
        "passed": completed.returncode == 0,
    }


def build_validation_evidence(crew_bin: Path, *, keep_temp: bool = False) -> tuple[dict[str, Any], bool]:
    if not crew_bin.is_file():
        raise ValueError(f"crew CLI not found: {crew_bin}")

    workload = load_script_module("hosted-workload-evidence.py", "hosted_workload_evidence")
    temp_root = Path(tempfile.mkdtemp(prefix="agent-crew-readiness-workload-"))
    home = temp_root / "home"
    project_root = temp_root / "project"
    project_root.mkdir(parents=True)
    home.mkdir(parents=True)
    scenario_results: list[dict[str, Any]] = []
    all_passed = True

    try:
        for scenario in SCENARIOS:
            result = run_scenario(crew_bin, scenario["args"], home=home, project_root=project_root)
            output = str(result["output"])
            expected_present = all(token in output for token in scenario["expected"])
            passed = bool(result["passed"] and expected_present)
            all_passed = all_passed and passed
            scenario_results.append({
                "id": scenario["id"],
                "args": scenario["args"],
                "returncode": result["returncode"],
                "passed": passed,
                "expected": scenario["expected"],
                "stdout_tail": result["stdout"][-2000:],
                "stderr_tail": result["stderr"][-2000:],
            })

        state_info = resolve_project_state(
            home=home,
            project_root=project_root,
            prefer_existing_legacy=True,
        )
        state_dir = Path(state_info["state_dir"])
        evidence = workload.build_evidence(state_dir, adapter="validation-workload", include_agent_requests=True)
        evidence.update({
            "source": "agent-crew-readiness-validation-workload",
            "validation_mode": "deterministic_host_bridge_smoke",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "crew_bin": str(crew_bin),
            "scenario_count": len(SCENARIOS),
            "scenario_successes": sum(1 for item in scenario_results if item["passed"]),
            "scenarios": scenario_results,
            "passed": all_passed and evidence.get("tasks") == len(SCENARIOS),
            "ephemeral_state_root": str(temp_root),
            "ephemeral_state_retained": keep_temp,
        })
        all_passed = bool(evidence["passed"])
        return evidence, all_passed
    finally:
        if not keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crew-bin", default=str(Path(__file__).resolve().parent.parent / "bin" / "crew"))
    parser.add_argument("--output", help="Write workload evidence JSON to this path.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--keep-temp", action="store_true", help="Retain temporary state/project directory.")
    args = parser.parse_args()

    try:
        evidence, passed = build_validation_evidence(Path(args.crew_bin).expanduser().resolve(), keep_temp=args.keep_temp)
    except (ValueError, subprocess.TimeoutExpired) as exc:
        print(f"readiness-workload-validate: {exc}", file=sys.stderr)
        return 2

    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    else:
        print("PASS: readiness workload validation" if passed else "FAIL: readiness workload validation")
        print(
            f"tasks={evidence['tasks']} successes={evidence['successes']} "
            f"host_bridge_completed={evidence['host_bridge_completed']} "
            f"human_interventions={evidence['human_interventions']} "
            f"scenario_successes={evidence['scenario_successes']}/{evidence['scenario_count']}"
        )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
