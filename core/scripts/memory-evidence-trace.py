#!/usr/bin/env python3
"""Record memory/evidence usage for answer-quality audits."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_evidence(task_dir: Path, values: list[str]) -> tuple[list[str], list[str]]:
    existing = []
    missing = []
    for value in values:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = task_dir / value
        if candidate.exists():
            existing.append(value)
        else:
            missing.append(value)
    return existing, missing


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def load_retrieval_eval(path_value: str | None) -> dict:
    if not path_value:
        return {}
    path = Path(path_value).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"path": str(path), "load_error": True}
    if not isinstance(data, dict):
        return {"path": str(path), "load_error": True}
    return data


def successor_ids(retrieval: dict) -> list[str]:
    values: list[str] = []
    satisfied = retrieval.get("satisfied_by_successor", {})
    if not isinstance(satisfied, dict):
        return values
    for successors in satisfied.values():
        if isinstance(successors, list):
            values.extend(str(item) for item in successors)
    return values


def memory_quality(retrieval: dict, *, memory_ids: list[str],
                   retrieved_ids: list[str], accepted_context_ids: list[str],
                   successor_memory_ids: list[str]) -> dict:
    expected_ids = [str(mid) for mid in retrieval.get("expected_memory_ids", [])] if retrieval else []
    misses = retrieval.get("misses", []) if isinstance(retrieval.get("misses", []), list) else []
    noise = retrieval.get("noise", []) if isinstance(retrieval.get("noise", []), list) else []
    latency_ms = retrieval.get("latency_ms") if retrieval else None
    latency_budget_ms = retrieval.get("latency_budget_ms") if retrieval else None
    noise_budget_count = retrieval.get("noise_budget_count") if retrieval else None
    expected_hit_count = len([mid for mid in expected_ids if mid in retrieved_ids or mid in memory_ids])
    successor_hit_count = len(successor_memory_ids)
    reusable_count = len(dedupe(memory_ids + accepted_context_ids + successor_memory_ids))
    miss_count = len(misses)
    noise_count = len(noise)
    denominator = max(1, len(expected_ids))
    precision_denominator = max(1, len(retrieved_ids))
    precision = round((len(retrieved_ids) - noise_count) / precision_denominator, 3)
    recall = round((expected_hit_count + successor_hit_count) / denominator, 3)
    score = round(max(0.0, min(1.0, (precision + recall) / 2)), 3)
    return {
        "expected_count": len(expected_ids),
        "retrieved_count": len(retrieved_ids),
        "expected_hit_count": expected_hit_count,
        "successor_hit_count": successor_hit_count,
        "accepted_context_count": len(accepted_context_ids),
        "reusable_memory_count": reusable_count,
        "miss_count": miss_count,
        "noise_count": noise_count,
        "noise_budget_count": noise_budget_count,
        "latency_ms": latency_ms,
        "latency_budget_ms": latency_budget_ms,
        "precision": precision,
        "recall": recall,
        "score": score,
    }


def write_markdown(path: Path, trace: dict) -> None:
    lines = [
        "# Memory Evidence Trace",
        "",
        f"CREATED_AT: {trace['created_at']}",
        f"MEMORY_CONTEXT_REUSED: {'yes' if trace['memory_context_reused'] else 'no'}",
    ]
    if trace["memory_ids"]:
        lines.append("MEMORY_IDS: " + ", ".join(trace["memory_ids"]))
    if trace["retrieved_memory_ids"]:
        lines.append("RETRIEVED_MEMORY_IDS: " + ", ".join(trace["retrieved_memory_ids"]))
    if trace["accepted_context_memory_ids"]:
        lines.append("ACCEPTED_CONTEXT_MEMORY_IDS: " + ", ".join(trace["accepted_context_memory_ids"]))
    if trace["satisfied_by_successor"]:
        lines.append("SATISFIED_BY_SUCCESSOR: " + json.dumps(trace["satisfied_by_successor"], sort_keys=True))
    if trace["retrieval_latency_ms"] is not None:
        lines.append(f"RETRIEVAL_LATENCY_MS: {trace['retrieval_latency_ms']}")
    quality = trace.get("memory_quality", {})
    if quality:
        lines.append(
            "MEMORY_QUALITY: "
            f"score={quality.get('score')} "
            f"precision={quality.get('precision')} "
            f"recall={quality.get('recall')} "
            f"misses={quality.get('miss_count')} "
            f"noise={quality.get('noise_count')}/{quality.get('noise_budget_count')}"
        )
    for evidence in trace["evidence_paths"]:
        lines.append(f"EVIDENCE: {evidence}")
    if trace["missing_evidence_paths"]:
        lines.append("MISSING_EVIDENCE: " + ", ".join(trace["missing_evidence_paths"]))
    if trace["note"]:
        lines.append(f"NOTE: {trace['note']}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--memory-id", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--reused", choices=["yes", "no"], required=True)
    parser.add_argument("--source", default="manual")
    parser.add_argument("--retrieval-eval-json", help="Optional memory-retrieval-eval JSON output to fold into the trace.")
    parser.add_argument("--note", default="")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    task_dir = Path(args.task_dir).expanduser().resolve()
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    evidence_paths, missing_paths = resolve_evidence(task_dir, args.evidence)
    retrieval = load_retrieval_eval(args.retrieval_eval_json)
    retrieved_ids = dedupe([str(mid) for mid in retrieval.get("returned_memory_ids", [])])
    accepted_context_ids = dedupe([str(mid) for mid in retrieval.get("context_memory_ids", [])])
    successor_memory_ids = dedupe(successor_ids(retrieval))
    memory_ids = dedupe(args.memory_id + accepted_context_ids + successor_memory_ids)
    quality = memory_quality(
        retrieval,
        memory_ids=memory_ids,
        retrieved_ids=retrieved_ids,
        accepted_context_ids=accepted_context_ids,
        successor_memory_ids=successor_memory_ids,
    )
    trace = {
        "schema_version": 1,
        "created_at": utc_now_z(),
        "task_dir": str(task_dir),
        "source": args.source,
        "memory_ids": memory_ids,
        "explicit_memory_ids": dedupe(args.memory_id),
        "retrieved_memory_ids": retrieved_ids,
        "accepted_context_memory_ids": accepted_context_ids,
        "satisfied_by_successor": retrieval.get("satisfied_by_successor", {}) if isinstance(retrieval.get("satisfied_by_successor", {}), dict) else {},
        "retrieval_passed": retrieval.get("passed") if retrieval else None,
        "retrieval_latency_ms": retrieval.get("latency_ms") if retrieval else None,
        "retrieval_noise": retrieval.get("noise", []) if isinstance(retrieval.get("noise", []), list) else [],
        "retrieval_misses": retrieval.get("misses", []) if isinstance(retrieval.get("misses", []), list) else [],
        "memory_quality": quality,
        "evidence_paths": evidence_paths,
        "missing_evidence_paths": missing_paths,
        "memory_context_reused": args.reused == "yes",
        "note": args.note,
    }

    json_path = context_dir / "memory-evidence.json"
    markdown_path = context_dir / "memory-evidence.md"
    json_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(markdown_path, trace)

    if args.format == "json":
        print(json.dumps(trace, ensure_ascii=False, indent=2))
    else:
        print(f"TRACE: {json_path}")
        print(f"MEMORY_CONTEXT_REUSED: {'yes' if trace['memory_context_reused'] else 'no'}")
        if missing_paths:
            print("MISSING_EVIDENCE: " + ", ".join(missing_paths))

    return 1 if missing_paths else 0


if __name__ == "__main__":
    raise SystemExit(main())
