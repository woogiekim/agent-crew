#!/usr/bin/env python3
"""Summarize pending self-evolution proposals for run/status output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def pending_proposals(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    proposals = [
        item
        for item in payload.get("proposals") or []
        if isinstance(item, dict) and item.get("status") == "approval_required"
    ]
    return proposals[:max(0, limit)]


def evidence_count(proposal: dict[str, Any]) -> int:
    occurrence_count = proposal.get("occurrence_count")
    if isinstance(occurrence_count, int) and occurrence_count >= 0:
        return occurrence_count

    evidence_refs = proposal.get("evidence_refs")
    if isinstance(evidence_refs, list):
        return len(evidence_refs)
    return 0


def build_summary(proposals_path: Path, limit: int) -> dict[str, Any]:
    payload = read_json(proposals_path)
    all_pending = [
        item
        for item in payload.get("proposals") or []
        if isinstance(item, dict) and item.get("status") == "approval_required"
    ]
    visible = pending_proposals(payload, limit)

    return {
        "schema_version": 1,
        "proposals_path": str(proposals_path),
        "pending_count": len(all_pending),
        "shown_count": len(visible),
        "proposals": [
            {
                "candidate_id": str(item.get("candidate_id") or ""),
                "proposal_type": str(item.get("proposal_type") or ""),
                "status": str(item.get("status") or ""),
                "target_asset": str(item.get("target_asset") or item.get("target_skill") or ""),
                "evidence_count": evidence_count(item),
            }
            for item in visible
        ],
    }


def render_text(summary: dict[str, Any]) -> str:
    pending_count = int(summary.get("pending_count") or 0)
    if pending_count <= 0:
        return "SELF_EVOLUTION_PROPOSALS: 0 pending\n"

    lines = [f"SELF_EVOLUTION_PROPOSALS: {pending_count} pending"]
    for proposal in summary.get("proposals") or []:
        candidate_id = proposal.get("candidate_id") or "(unknown)"
        proposal_type = proposal.get("proposal_type") or "(unknown)"
        evidence = int(proposal.get("evidence_count") or 0)
        lines.extend([
            f"- {candidate_id}",
            f"  type: {proposal_type}",
            f"  evidence: {evidence} tasks",
            "  status: approval_required",
            "  next: review and approve before apply",
        ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize pending self-evolution proposals"
    )
    parser.add_argument("--proposals", required=True)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    summary = build_summary(Path(args.proposals), args.limit)
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(render_text(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
