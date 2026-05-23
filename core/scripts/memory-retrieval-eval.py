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
SCORE_RE = re.compile(r"\b(?:score|relevance|rank_score)=([0-9]+(?:\.[0-9]+)?)\b", re.I)


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


def extract_scores(text: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("[mnemos]") or line.startswith("[memory]"):
            continue
        id_match = ID_RE.search(line)
        score_match = SCORE_RE.search(line)
        if not id_match or not score_match:
            continue
        mid = id_match.group(0).strip().rstrip(":")
        try:
            scores[mid] = float(score_match.group(1))
        except ValueError:
            continue
    return scores


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
    successors = {
        str(key): list(value)
        for key, value in fixture.get("accepted_successor_memory_ids", {}).items()
    }
    returned = extract_ids(output)
    scores = extract_scores(output)
    expected_set = set(expected)
    accepted_successor_ids = {
        successor
        for values in successors.values()
        for successor in values
    }
    accepted_context_ids = set(fixture.get("accepted_context_memory_ids", []))
    accepted_context_patterns = [
        re.compile(pattern)
        for pattern in fixture.get("accepted_context_memory_id_patterns", [])
    ]

    def is_accepted_context(mid: str) -> bool:
        return mid in accepted_context_ids or any(pattern.fullmatch(mid) for pattern in accepted_context_patterns)

    evaluation_returned = [
        mid for mid in returned
        if not is_accepted_context(mid)
    ]
    evaluation_returned_set = set(evaluation_returned)
    satisfied_by_successor = {
        mid: [successor for successor in successors.get(mid, []) if successor in evaluation_returned_set]
        for mid in expected
    }
    misses = [
        mid for mid in expected
        if mid not in evaluation_returned_set and not satisfied_by_successor.get(mid)
    ]
    noise = [
        mid for mid in evaluation_returned
        if mid not in expected_set
        and mid not in accepted_successor_ids
        and not is_accepted_context(mid)
    ]
    context_memory_ids = [
        mid for mid in returned
        if mid not in expected_set and mid not in accepted_successor_ids and is_accepted_context(mid)
    ]
    latency_budget_ms = int(fixture["latency_budget_ms"])
    noise_budget_count = int(fixture["noise_budget_count"])
    min_expected_score = fixture.get("min_expected_score")
    min_expected_score = float(min_expected_score) if min_expected_score is not None else None
    missing_scores: list[str] = []
    low_scores: dict[str, float] = {}
    if min_expected_score is not None:
        for mid in evaluation_returned:
            if mid in expected_set or mid in accepted_successor_ids:
                if mid not in scores:
                    missing_scores.append(mid)
                elif scores[mid] < min_expected_score:
                    low_scores[mid] = scores[mid]

    failures = {
        "misses": misses,
        "noise": noise if len(noise) > noise_budget_count else [],
        "latency_ms": elapsed_ms if elapsed_ms > latency_budget_ms else None,
        "missing_scores": missing_scores,
        "low_scores": low_scores,
    }
    passed = (
        not failures["misses"]
        and not failures["noise"]
        and failures["latency_ms"] is None
        and not failures["missing_scores"]
        and not failures["low_scores"]
    )
    return {
        "passed": passed,
        "query": fixture["query"],
        "expected_memory_ids": expected,
        "returned_memory_ids": returned,
        "returned_memory_scores": scores,
        "evaluated_memory_ids": evaluation_returned,
        "misses": misses,
        "noise": noise,
        "accepted_context_memory_ids": sorted(accepted_context_ids),
        "accepted_context_memory_id_patterns": fixture.get("accepted_context_memory_id_patterns", []),
        "context_memory_ids": context_memory_ids,
        "accepted_successor_memory_ids": successors,
        "satisfied_by_successor": {
            mid: values for mid, values in satisfied_by_successor.items() if values
        },
        "latency_ms": round(elapsed_ms, 3),
        "latency_budget_ms": latency_budget_ms,
        "min_expected_score": min_expected_score,
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
        search_limit = int(fixture.get("limit", len(fixture["expected_memory_ids"])))
        search_limit += int(fixture.get("accepted_context_headroom", 0))
        output, rc, elapsed_ms = run_memory(
            Path(args.memory_bin),
            str(fixture["query"]),
            search_limit,
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
