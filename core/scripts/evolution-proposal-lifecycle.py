#!/usr/bin/env python3
"""Operate explicitly on approved self-evolution proposals."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {
    "applied",
    "rejected",
    "superseded",
    "cancelled",
}
CREATE_PROPOSAL_TYPES = {
    "create_skill",
    "create_agent",
    "create_command",
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def proposals_path(state_dir: Path) -> Path:
    return state_dir / "learning-candidates" / "proposals.json"


def learning_dir(state_dir: Path) -> Path:
    return state_dir / "learning-candidates"


def proposals(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in payload.get("proposals") or [] if isinstance(item, dict)]


def find_proposal(payload: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    matches = [
        item
        for item in proposals(payload)
        if str(item.get("candidate_id") or "") == candidate_id
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def evidence_count(proposal: dict[str, Any]) -> int:
    occurrence_count = proposal.get("occurrence_count")
    if isinstance(occurrence_count, int) and occurrence_count >= 0:
        return occurrence_count

    evidence_refs = proposal.get("evidence_refs")
    if isinstance(evidence_refs, list):
        return len(evidence_refs)
    return 0


def render_status(path: Path, limit: int) -> str:
    payload = read_json(path)
    pending = [
        item
        for item in proposals(payload)
        if str(item.get("status") or "") == "approval_required"
    ]
    if not pending:
        return "SELF_EVOLUTION_PROPOSALS: 0 pending\n"

    lines = [f"SELF_EVOLUTION_PROPOSALS: {len(pending)} pending"]
    for proposal in pending[:max(0, limit)]:
        candidate_id = str(proposal.get("candidate_id") or "(unknown)")
        proposal_type = str(proposal.get("proposal_type") or "(unknown)")
        target_assets = proposal.get("target_assets")
        target = str(
            proposal.get("target_asset")
            or proposal.get("target_skill")
            or proposal.get("asset_name")
            or ""
        )
        lines.extend([
            f"- {candidate_id}",
            f"  type: {proposal_type}",
            f"  evidence: {evidence_count(proposal)} tasks",
            "  status: approval_required",
        ])
        if isinstance(target_assets, list) and target_assets:
            lines.append(f"  target: {', '.join(str(item) for item in target_assets)}")
        elif target:
            lines.append(f"  target: {target}")

        principle = str(proposal.get("review_principle") or "")
        if principle:
            lines.append(f"  principle: {principle}")

        reason = str(proposal.get("promotion_reason") or "")
        if reason:
            lines.append(f"  reason: {reason}")

        if proposal_type in CREATE_PROPOSAL_TYPES:
            lines.append("  next: review and approve; approved creation proposals are handed to crew:agent-maker")
        else:
            lines.append("  next: review and approve before apply")
    return "\n".join(lines) + "\n"


def cmd_status(args: argparse.Namespace) -> int:
    print(render_status(proposals_path(args.state_dir), args.limit), end="")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    path = proposals_path(args.state_dir)
    payload = read_json(path)
    proposal = find_proposal(payload, args.candidate_id)
    if proposal is None:
        print(f"proposal not found: {args.candidate_id}", file=sys.stderr)
        return 2

    status = str(proposal.get("status") or "")
    if status == "approved":
        print(f"STATUS: already approved\nCANDIDATE_ID: {args.candidate_id}")
        return 0
    if status != "approval_required":
        print(f"cannot approve proposal in status {status}", file=sys.stderr)
        return 2
    if status in TERMINAL_STATUSES:
        print(f"cannot approve proposal in status {status}", file=sys.stderr)
        return 2

    proposal["status"] = "approved"
    proposal["approved_by"] = args.approved_by
    proposal["approved_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    proposal["decision_reason"] = args.reason
    write_json(path, payload)
    print(f"STATUS: approved\nCANDIDATE_ID: {args.candidate_id}")
    return 0


def apply_script_path() -> Path:
    return Path(__file__).resolve().with_name("evolution-proposal-apply.py")


def cmd_apply(args: argparse.Namespace) -> int:
    path = proposals_path(args.state_dir)
    payload = read_json(path)
    proposal = find_proposal(payload, args.candidate_id)
    if proposal is None:
        print(f"proposal not found: {args.candidate_id}", file=sys.stderr)
        return 2
    if str(proposal.get("status") or "") != "approved":
        print("proposal must be approved before apply", file=sys.stderr)
        return 2

    base_dir = learning_dir(args.state_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    audit_path = base_dir / "apply-audit.json"
    request_dir = base_dir / "agent-maker-requests"
    filtered = {
        "schema_version": payload.get("schema_version", 1),
        "proposals": [proposal],
    }

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix="proposal-apply-",
        suffix=".json",
        dir=str(base_dir),
        delete=False,
    ) as tmp:
        json.dump(filtered, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(apply_script_path()),
                "--proposals",
                str(tmp_path),
                "--skill-dir",
                str(args.skill_dir),
                "--audit-output",
                str(audit_path),
                "--agent-maker-request-dir",
                str(request_dir),
            ],
            text=True,
            capture_output=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        return result.returncode

    if str(proposal.get("proposal_type") or "") in CREATE_PROPOSAL_TYPES:
        print("NEXT: crew:agent-maker")
    return 0


def default_state_dir() -> Path:
    state_dir = os.environ.get("AGENT_CREW_STATE_DIR")
    if state_dir:
        return Path(state_dir)
    home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew"))
    project = os.environ.get("AGENT_CREW_PROJECT", "default")
    return home / "state" / project


def default_skill_dir() -> Path:
    home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew"))
    return home / "skills"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage self-evolution proposals through an explicit operator command"
    )
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--skill-dir", type=Path, default=default_skill_dir())
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Show pending proposals without recomputing them")
    status.add_argument("--limit", type=int, default=20)
    status.set_defaults(func=cmd_status)

    approve = subparsers.add_parser("approve", help="Approve one exact proposal id")
    approve.add_argument("candidate_id")
    approve.add_argument("--approved-by", default=os.environ.get("USER", "operator"))
    approve.add_argument("--reason", default="operator approved")
    approve.set_defaults(func=cmd_approve)

    apply = subparsers.add_parser("apply", help="Apply one approved proposal")
    apply.add_argument("candidate_id")
    apply.set_defaults(func=cmd_apply)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
