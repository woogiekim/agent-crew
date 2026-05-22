#!/usr/bin/env python3
"""Evaluate deterministic memory retrieval fixtures.

The checker separates expected-ID misses, noise, and latency failures so a
retrieval regression points at the right failure mode.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


ID_RE = re.compile(r"\b(?:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9][a-z0-9_.:-]{5,})\b", re.I)


def load_fixture(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("query", "expected_memory_ids", "latency_budget_ms", "noise_budget_count"):
        if key not in data:
            raise ValueError(f"fixture missing required key: {key}")
    return data


def extract_ids(text: str) -> list[str]:
    ids: list[str] = []
    seen = set()
    for line in text.splitlines():
        if line.startswith("[mnemos]") or line.startswith("[memory]"):
            continue
        for match in ID_RE.findall(line):
            value = match.strip().rstrip(":")
            if value not in seen:
                seen.add(value)
                ids.append(value)
                break
    return ids


def run_memory(memory_bin: Path, query: str, limit: int) -> tuple[str, int, float]:
    started = time.perf_counter()
    proc = subprocess.run(
        [str(memory_bin), "search", query, "--limit", str(limit)],
        text=True,
        capture_output=True,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    return proc.stdout + proc.stderr, proc.returncode, elapsed_ms


def evaluate(fixture: dict, output: str, elapsed_ms: float) -> dict:
    expected = list(fixture["expected_memory_ids"])
    returned = extract_ids(output)
    returned_set = set(returned)
    expected_set = set(expected)
    misses = [mid for mid in expected if mid not in returned_set]
    noise = [mid for mid in returned if mid not in expected_set]
    latency_budget_ms = int(fixture["latency_budget_ms"])
    noise_budget_count = int(fixture["noise_budget_count"])

    failures = {
        "misses": misses,
        "noise": noise if len(noise) > noise_budget_count else [],
        "latency_ms": elapsed_ms if elapsed_ms > latency_budget_ms else None,
    }
    passed = not failures["misses"] and not failures["noise"] and failures["latency_ms"] is None
    return {
        "passed": passed,
        "query": fixture["query"],
        "expected_memory_ids": expected,
        "returned_memory_ids": returned,
        "misses": misses,
        "noise": noise,
        "latency_ms": round(elapsed_ms, 3),
        "latency_budget_ms": latency_budget_ms,
        "noise_budget_count": noise_budget_count,
        "failures": failures,
    }


def main() -> int:
    default_fixture = Path(__file__).resolve().parent.parent / "evaluations" / "memory-retrieval.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(default_fixture))
    parser.add_argument("--results-file", help="Read captured memory search output instead of invoking memory")
    parser.add_argument("--memory-bin", default="core/bin/memory")
    parser.add_argument("--elapsed-ms", type=float, help="Latency to use with --results-file")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    fixture = load_fixture(Path(args.fixture))
    if args.results_file:
        output = Path(args.results_file).read_text(encoding="utf-8")
        elapsed_ms = 0.0 if args.elapsed_ms is None else args.elapsed_ms
        rc = 0
    else:
        output, rc, elapsed_ms = run_memory(
            Path(args.memory_bin),
            str(fixture["query"]),
            int(fixture.get("limit", len(fixture["expected_memory_ids"]))),
        )
    result = evaluate(fixture, output, elapsed_ms)
    result["memory_rc"] = rc

    if args.format == "json":
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status}: memory retrieval evaluation")
        print(f"latency={result['latency_ms']}ms budget={result['latency_budget_ms']}ms")
        print(f"misses={len(result['misses'])} noise={len(result['noise'])}/{result['noise_budget_count']}")
        if result["misses"]:
            print("missing: " + ", ".join(result["misses"]))
        if result["failures"]["noise"]:
            print("noise: " + ", ".join(result["failures"]["noise"]))

    return 0 if result["passed"] and rc in (0, 124) else 1


if __name__ == "__main__":
    raise SystemExit(main())
