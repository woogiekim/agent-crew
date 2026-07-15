#!/usr/bin/env python3
"""Apply approved self-evolution proposals without creating new assets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


START_MARKER = "<!-- agent-crew-evolution:{candidate_id}:start -->"
END_MARKER = "<!-- agent-crew-evolution:{candidate_id}:end -->"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def safe_skill_name(value: str) -> str:
    name = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.md", name):
        return ""
    return name


def append_patch_once(path: Path, candidate_id: str, body: str) -> bool:
    text = path.read_text(encoding="utf-8")
    start = START_MARKER.format(candidate_id=candidate_id)
    if start in text:
        return False

    end = END_MARKER.format(candidate_id=candidate_id)
    block = "\n".join([
        "",
        start,
        body.strip(),
        end,
        "",
    ])
    path.write_text(text.rstrip() + "\n" + block, encoding="utf-8")
    return True


def apply_proposals(proposals_path: Path, skill_dir: Path) -> dict[str, Any]:
    payload = read_json(proposals_path)
    applied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for proposal in payload.get("proposals") or []:
        if not isinstance(proposal, dict):
            continue
        candidate_id = str(proposal.get("candidate_id") or "")
        proposal_type = str(proposal.get("proposal_type") or "")
        status = str(proposal.get("status") or "")
        if status != "approved":
            skipped.append({"candidate_id": candidate_id, "reason": "not_approved"})
            continue
        if proposal_type != "patch_existing_skill":
            skipped.append({"candidate_id": candidate_id, "reason": "unsupported_proposal_type"})
            continue

        skill_name = safe_skill_name(str(proposal.get("target_skill") or ""))
        if not skill_name:
            skipped.append({"candidate_id": candidate_id, "reason": "invalid_target_skill"})
            continue
        target = skill_dir / skill_name
        if not target.is_file():
            skipped.append({"candidate_id": candidate_id, "reason": "target_skill_missing"})
            continue

        patch_body = str(proposal.get("patch_body") or "").strip()
        if not patch_body:
            skipped.append({"candidate_id": candidate_id, "reason": "missing_patch_body"})
            continue

        changed = append_patch_once(target, candidate_id, patch_body)
        applied.append({
            "candidate_id": candidate_id,
            "target": str(target),
            "status": "applied" if changed else "already_applied",
        })

    return {
        "schema_version": 1,
        "applied": applied,
        "skipped": skipped,
        "guardrails": {
            "asset_creation": "disabled",
            "agent_creation": "disabled",
            "needs_creation_writes": "disabled",
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply approved self-evolution skill patch proposals"
    )
    parser.add_argument("--proposals", required=True)
    parser.add_argument("--skill-dir", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    audit = apply_proposals(Path(args.proposals), Path(args.skill_dir))
    write_json(Path(args.audit_output), audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
