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
AGENT_MAKER_PROPOSAL_TYPES = {
    "create_skill": "skill",
    "create_agent": "agent",
    "create_command": "command",
}


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


def safe_request_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    return f"{name}.md" if name else ""


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


def render_agent_maker_request(proposal: dict[str, Any], asset_type: str) -> str:
    candidate_id = str(proposal.get("candidate_id") or "")
    asset_name = str(proposal.get("asset_name") or proposal.get("target_asset") or "").strip()
    asset_purpose = str(proposal.get("asset_purpose") or proposal.get("promotion_reason") or "").strip()
    evidence_refs = [
        str(item)
        for item in proposal.get("evidence_refs") or []
        if str(item).strip()
    ]
    lines = [
        "# crew:agent-maker Request",
        "",
        "Use `crew:agent-maker` to design and create the requested agent-crew asset.",
        "Do not bypass the agent-maker command definition or its approval/deploy rules.",
        "",
        f"PROPOSAL_ID: {candidate_id}",
        f"ASSET_TYPE: {asset_type}",
        f"ASSET_NAME: {asset_name}",
        f"PURPOSE: {asset_purpose}",
        "",
        "## Evidence",
    ]
    if evidence_refs:
        lines.extend(f"- {item}" for item in evidence_refs)
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Requirements",
        "- Preserve provider-neutral agent-crew boundaries.",
        "- Use the smallest asset that satisfies the repeated learning signal.",
        "- Keep generated assets approval-gated and deploy through the existing agent-maker finalization helpers.",
        "- Do not create unrelated agents, skills, commands, hooks, or rules.",
        "",
    ])
    return "\n".join(lines)


def write_agent_maker_request_once(
    request_dir: Path,
    proposal: dict[str, Any],
    asset_type: str,
) -> tuple[Path, bool]:
    request_name = safe_request_name(str(proposal.get("candidate_id") or ""))
    if not request_name:
        raise ValueError("invalid_candidate_id")
    request_dir.mkdir(parents=True, exist_ok=True)
    request_path = request_dir / request_name
    if request_path.exists():
        return request_path, False
    request_path.write_text(render_agent_maker_request(proposal, asset_type), encoding="utf-8")
    return request_path, True


def apply_proposals(proposals_path: Path, skill_dir: Path, request_dir: Path) -> dict[str, Any]:
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
        if proposal_type in AGENT_MAKER_PROPOSAL_TYPES:
            try:
                request_path, changed = write_agent_maker_request_once(
                    request_dir,
                    proposal,
                    AGENT_MAKER_PROPOSAL_TYPES[proposal_type],
                )
            except ValueError as exc:
                skipped.append({"candidate_id": candidate_id, "reason": str(exc)})
                continue
            applied.append({
                "candidate_id": candidate_id,
                "target": str(request_path),
                "status": "agent_maker_request_created" if changed else "agent_maker_request_exists",
            })
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
            "asset_creation": "agent_maker_only",
            "agent_creation": "agent_maker_only",
            "skill_creation": "agent_maker_only",
            "command_creation": "agent_maker_only",
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
    parser.add_argument("--agent-maker-request-dir")
    args = parser.parse_args()

    audit_output = Path(args.audit_output)
    request_dir = (
        Path(args.agent_maker_request_dir)
        if args.agent_maker_request_dir
        else audit_output.parent / "agent-maker-requests"
    )
    audit = apply_proposals(Path(args.proposals), Path(args.skill_dir), request_dir)
    write_json(audit_output, audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
