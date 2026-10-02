"""자기개선 제안의 관찰과 승인 가능한 수정안을 구분한다."""

import re
from typing import Any


STATIC_PATTERNS = {"skill_content_depth", "skill_format_warning", "skill_content_contract"}


def patch_readiness_gaps(proposal: dict[str, Any]) -> list[str]:
    if proposal.get("proposal_type") != "patch_existing_skill":
        return []

    gaps = []
    target = proposal.get("target_skill")
    if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9._-]+\.md", target):
        gaps.append("target_skill")
    for field in ("patch_body", "expected_impact"):
        value = proposal.get(field)
        if not isinstance(value, str) or not value.strip():
            gaps.append(field)
    refs = proposal.get("evidence_refs")
    if (
        not isinstance(refs, list)
        or not refs
        or not all(isinstance(ref, str) and ref.strip() for ref in refs)
    ):
        gaps.append("evidence_refs")
    return gaps


def classify_proposal(proposal: dict[str, Any], *, static: bool = False) -> None:
    if static:
        proposal["observation_count"] = proposal.get("observation_count", proposal.get("occurrence_count", 0))
        proposal["occurrence_count"] = 0
        proposal["evidence_kind"] = "static_observation"
        proposal["promotion_reason"] = "정적 감사의 반복 관찰이며 독립적인 작업 실패 근거가 아닙니다."

    gaps = patch_readiness_gaps(proposal)
    if gaps:
        proposal["readiness_gaps"] = gaps
    else:
        proposal.pop("readiness_gaps", None)

    needs_investigation = static or gaps or proposal.get("proposal_type") == "investigate_reusable_asset"
    if proposal.get("status") in {"approval_required", "investigation_required", "approved"} and needs_investigation:
        if proposal.get("status") == "approved":
            proposal["previous_status"] = "approved"
        proposal["status"] = "investigation_required"
    elif proposal.get("status") == "investigation_required":
        proposal["status"] = "approval_required"
