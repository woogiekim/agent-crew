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


def learning_event_path(state_dir: Path) -> Path:
    return state_dir / "learning" / "events.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def proposal_keys(report: dict[str, Any]) -> list[str]:
    patterns = report.get("observed_patterns") or []
    keys: list[str] = []
    for item in patterns:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "mistake_correction":
            pattern_key = str(item.get("pattern_key") or "")
            if pattern_key:
                keys.append(f"mistake_correction:{pattern_key}")
            continue
        if item.get("kind") != "review_principle":
            continue
        principle_key = str(item.get("principle_key") or "")
        if principle_key:
            keys.append(f"review_principle:{principle_key}")

    kinds = [
        str(item.get("kind"))
        for item in patterns
        if (
            isinstance(item, dict)
            and item.get("kind")
            and item.get("kind") not in {"review_principle", "mistake_correction"}
        )
    ]
    if kinds:
        keys.append("+".join(sorted(set(kinds))))

    if not keys:
        for item in report.get("rejected_candidates") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            if name:
                keys.append(name)
                break

    return sorted(set(keys))


def proposal_key(report: dict[str, Any]) -> str:
    keys = proposal_keys(report)
    return keys[0] if keys else ""


def candidate_source(report: dict[str, Any], key: str = "") -> str:
    if key.startswith("review_principle:"):
        return "reviewer_finding"
    if key.startswith("mistake_correction:"):
        return "user_feedback"

    for pattern in report.get("observed_patterns") or []:
        if isinstance(pattern, dict) and pattern.get("kind") == "review_loop_back":
            return "reviewer_finding"
    return "aar_memo"


def review_principle_metadata(report: dict[str, Any], key: str) -> dict[str, Any]:
    if not key.startswith("review_principle:"):
        return {}

    principle_key = key.split(":", 1)[1]
    for pattern in report.get("observed_patterns") or []:
        if not isinstance(pattern, dict):
            continue
        if pattern.get("kind") != "review_principle":
            continue
        if str(pattern.get("principle_key") or "") != principle_key:
            continue

        metadata: dict[str, Any] = {}
        principle = pattern.get("principle")
        target_assets = pattern.get("target_assets")
        if isinstance(principle, str) and principle.strip():
            metadata["review_principle"] = principle.strip()
        if isinstance(target_assets, list):
            assets = [str(item) for item in target_assets if str(item).strip()]
            if assets:
                metadata["target_assets"] = assets
        return metadata

    return {}


def target_assets_for_pattern(report: dict[str, Any], *, kind: str, key_field: str, key_value: str) -> list[str]:
    assets: list[str] = []
    seen: set[str] = set()
    for pattern in report.get("observed_patterns") or []:
        if not isinstance(pattern, dict):
            continue
        if pattern.get("kind") != kind:
            continue
        if str(pattern.get(key_field) or "") != key_value:
            continue

        target_assets = pattern.get("target_assets")
        if not isinstance(target_assets, list):
            continue
        for item in target_assets:
            asset = str(item).strip()
            if asset and asset not in seen:
                seen.add(asset)
                assets.append(asset)
    return assets


def mistake_correction_metadata(reports: list[dict[str, Any]], key: str) -> dict[str, Any]:
    if not key.startswith("mistake_correction:"):
        return {}

    pattern_key = key.split(":", 1)[1]
    assets: list[str] = []
    seen: set[str] = set()
    for report in reports:
        for asset in target_assets_for_pattern(
            report,
            kind="mistake_correction",
            key_field="pattern_key",
            key_value=pattern_key,
        ):
            if asset not in seen:
                seen.add(asset)
                assets.append(asset)

    return {"target_assets": assets} if assets else {}


def proposal_reason_label(key: str) -> str:
    if key.startswith("review_principle:"):
        return "repeated review principle"
    if key.startswith("mistake_correction:"):
        return "corrected mistake pattern"
    return "reusable-work signal"


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
    events_path = learning_event_path(state_dir)
    event_proposals = build_event_proposals(state_dir, minimum_occurrences, existing)
    if events_path.is_file():
        return event_proposals

    existing = existing or {}
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in report_paths(state_dir):
        report = read_json(path)
        if report.get("generation_mode") != "report_only":
            continue
        if report.get("asset_candidates"):
            continue
        for key in proposal_keys(report):
            groups[key].append(path)

    proposals: list[dict[str, Any]] = []
    for key, paths in sorted(groups.items()):
        if len(paths) < minimum_occurrences:
            continue
        reports = [read_json(path) for path in paths]
        first_report = reports[0]
        evidence_refs = [
            str(path.relative_to(state_dir))
            for path in paths
        ]
        is_skill_patch_signal = (
            key.startswith("review_principle:")
            or key in {"existing-skill-patch-suggestion", "skill_content_depth"}
        )
        proposal_type = "patch_existing_skill" if is_skill_patch_signal else "investigate_reusable_asset"
        preserved = existing_proposal_for_key(existing, key)
        candidate_id = str(preserved.get("candidate_id") or f"{slug(key)}-{len(paths)}x")
        proposal = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "source": candidate_source(first_report, key),
            "memory_layer": "project",
            "evidence_refs": evidence_refs,
            "promotion_reason": (
                f"{len(paths)} independent evolution reports recorded the same "
                f"{proposal_reason_label(key)}: {key}."
            ),
            "trust_boundary": "advisory_until_rule_promotion",
            "proposal_type": proposal_type,
            "status": "approval_required",
            "target_asset": key,
            "occurrence_count": len(paths),
            "approval_gate": "crew:run_or_supervisor_approval_required",
            "guardrail": "proposal_only_no_needs_creation_write",
        }
        proposal.update(review_principle_metadata(first_report, key))
        proposal.update(mistake_correction_metadata(reports, key))
        preserve_decision_fields(proposal, preserved)
        proposals.append(proposal)
    return proposals


def event_is_feedback_backed(event: dict[str, Any]) -> bool:
    reviewer_status = str(event.get("reviewer_status") or "").lower()
    outcome = str(event.get("outcome") or "").lower()
    return reviewer_status in {"approved", "corrected"} or outcome in {"corrected", "reviewer_approved"}


def event_group_key(event: dict[str, Any]) -> str:
    repository_key = str(event.get("repository_key") or "").strip()
    signature = str(event.get("failure_signature") or event.get("pattern_key") or "").strip()
    if not (repository_key and signature):
        return ""
    return f"{repository_key}\x1f{signature}"


def build_event_proposals(
    state_dir: Path,
    minimum_occurrences: int,
    existing: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    events = read_jsonl(learning_event_path(state_dir))
    if not events:
        return []

    existing = existing or {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if str(event.get("schema_version") or "") != "agent-crew.learning-event.v1":
            continue
        if not event_is_feedback_backed(event):
            continue
        key = event_group_key(event)
        if key:
            groups[key].append(event)

    proposals: list[dict[str, Any]] = []
    for group_key, group_events in sorted(groups.items()):
        unique_task_ids = sorted({
            str(event.get("task_id") or "")
            for event in group_events
            if str(event.get("task_id") or "").strip()
        })
        if len(unique_task_ids) < minimum_occurrences:
            continue

        repository_key, signature = group_key.split("\x1f", 1)
        ordered_events = sorted(group_events, key=lambda item: str(item.get("evidence_ref") or ""))
        evidence_refs = []
        for event in ordered_events:
            evidence_ref = str(event.get("evidence_ref") or "").strip()
            if evidence_ref and evidence_ref not in evidence_refs:
                evidence_refs.append(evidence_ref)

        target_assets: list[str] = []
        seen_assets: set[str] = set()
        for event in ordered_events:
            for asset in event.get("target_assets") or []:
                value = str(asset).strip()
                if value and value not in seen_assets:
                    seen_assets.add(value)
                    target_assets.append(value)

        preserved = existing_proposal_for_key(existing, signature)
        is_skill_patch_signal = (
            signature.startswith("review_principle:")
            or signature in {"existing-skill-patch-suggestion", "skill_content_depth"}
        )
        proposal_type = "patch_existing_skill" if is_skill_patch_signal else "investigate_reusable_asset"
        candidate_id = str(preserved.get("candidate_id") or f"{slug(signature)}-{len(unique_task_ids)}x")
        proposal = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "source": "learning_event",
            "memory_layer": "project",
            "repository_key": repository_key,
            "evidence_refs": evidence_refs,
            "promotion_reason": (
                f"{len(unique_task_ids)} independent learning events recorded the same "
                f"{proposal_reason_label(signature)}: {signature}."
            ),
            "trust_boundary": "advisory_until_rule_promotion",
            "proposal_type": proposal_type,
            "status": "approval_required",
            "target_asset": signature,
            "occurrence_count": len(unique_task_ids),
            "approval_gate": "crew:run_or_supervisor_approval_required",
            "guardrail": "proposal_only_no_needs_creation_write",
        }
        if target_assets:
            proposal["target_assets"] = target_assets
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
