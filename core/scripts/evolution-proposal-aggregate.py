#!/usr/bin/env python3
"""Aggregate report-only evolution signals into approval-gated proposals."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip(".-")
    return normalized or "proposal"


def stable_key(value: str) -> str:
    return re.sub(r"-\d+x$", "", value.strip())


def report_paths(state_dir: Path) -> list[Path]:
    return sorted((state_dir / "tasks").glob("*/context/evolution-report.json"))


def proposal_key(report: dict[str, Any]) -> str:
    patterns = report.get("observed_patterns") or []
    kinds = [
        str(item.get("kind"))
        for item in patterns
        if isinstance(item, dict) and item.get("kind")
    ]
    if kinds:
        return "+".join(sorted(set(kinds)))

    for item in report.get("rejected_candidates") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name:
            return name

    return ""


def candidate_source(report: dict[str, Any]) -> str:
    for pattern in report.get("observed_patterns") or []:
        if isinstance(pattern, dict) and pattern.get("kind") == "review_loop_back":
            return "reviewer_finding"
    return "aar_memo"


def existing_proposals(output_path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(output_path)
    proposals: dict[str, dict[str, Any]] = {}
    for item in payload.get("proposals") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("target_asset") or item.get("candidate_id") or "")
        if key:
            proposals[stable_key(key)] = item
    return proposals


def existing_proposal_for_key(
    existing: dict[str, dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    candidates = [stable_key(key)]
    if key == "skill_content_depth":
        candidates.extend([
            "existing-skill-patch-suggestion",
            "skill-content-hardening",
        ])
    for candidate in candidates:
        if candidate in existing:
            return existing[candidate]
    return {}


def preserve_decision_fields(proposal: dict[str, Any], existing: dict[str, Any]) -> None:
    for field in (
        "status",
        "target_skill",
        "patch_body",
        "decision_reason",
        "approved_by",
        "approved_at",
        "rejected_reason",
        "superseded_by",
    ):
        if field in existing:
            proposal[field] = existing[field]


def build_proposals(
    state_dir: Path,
    minimum_occurrences: int,
    existing: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    existing = existing or {}
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in report_paths(state_dir):
        report = read_json(path)
        if report.get("generation_mode") != "report_only":
            continue
        if report.get("asset_candidates"):
            continue
        key = proposal_key(report)
        if key:
            groups[key].append(path)

    proposals: list[dict[str, Any]] = []
    for key, paths in sorted(groups.items()):
        if len(paths) < minimum_occurrences:
            continue
        first_report = read_json(paths[0])
        evidence_refs = [
            str(path.relative_to(state_dir))
            for path in paths
        ]
        proposal_type = (
            "patch_existing_skill"
            if key in {"existing-skill-patch-suggestion", "skill_content_depth"}
            else "investigate_reusable_asset"
        )
        preserved = existing_proposal_for_key(existing, key)
        candidate_id = str(preserved.get("candidate_id") or f"{slug(key)}-{len(paths)}x")
        proposal = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "source": candidate_source(first_report),
            "memory_layer": "project",
            "evidence_refs": evidence_refs,
            "promotion_reason": (
                f"{len(paths)} independent evolution reports recorded the "
                f"same reusable-work signal: {key}."
            ),
            "trust_boundary": "advisory_until_rule_promotion",
            "proposal_type": proposal_type,
            "status": "approval_required",
            "target_asset": key,
            "occurrence_count": len(paths),
            "approval_gate": "crew:run_or_supervisor_approval_required",
            "guardrail": "proposal_only_no_needs_creation_write",
        }
        preserve_decision_fields(proposal, preserved)
        proposals.append(proposal)
    return proposals


def build_payload(state_dir: Path, minimum_occurrences: int, output_path: Path) -> dict[str, Any]:
    proposals = build_proposals(
        state_dir,
        minimum_occurrences,
        existing_proposals(output_path),
    )
    return {
        "schema_version": 1,
        "generation_mode": "approval_gated_proposal",
        "minimum_occurrences": minimum_occurrences,
        "proposals": proposals,
        "guardrails": {
            "asset_writes": "disabled",
            "generator_invoked": False,
            "needs_creation_writes": "disabled",
            "approval_required": True,
        },
    }


def write_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate evolution reports into approval-gated learning proposals"
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--minimum-occurrences", type=int, default=2)
    parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args()

    if args.minimum_occurrences < 2:
        parser.error("--minimum-occurrences must be at least 2")

    output_path = Path(args.output)
    payload = build_payload(Path(args.state_dir), args.minimum_occurrences, output_path)
    write_output(output_path, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
