#!/usr/bin/env python3
"""Deterministic minimum classification and approval-boundary hashing."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
CLASSIFIER_VERSION = 1
ORDER = {"Spike": 0, "Bounded": 1, "Architectural": 2}
HARD_RULES = {
    "new_subsystem": "Architectural",
    "backward_incompatible_public_contract": "Architectural",
    "persistent_data_migration": "Architectural",
    "security_boundary_change": "Architectural",
    "multi_repository_contract": "Architectural",
    "workflow_governance_change": "Architectural",
    "destructive_or_hard_to_reverse": "Architectural",
    "post_approval_scope_expansion": "Architectural",
}
BOUND_FIELDS = (
    "classification",
    "downgrade",
    "goals",
    "non_goals",
    "interfaces",
    "responsibility_boundaries",
    "data_model",
    "repositories",
    "modules",
    "security_risks",
    "operational_risks",
    "pipeline",
)


class InputReadError(ValueError):
    """Raised when a declared JSON input cannot be read as an object."""


def classify_minimum(task: str, requirements: str = "", evidence: dict | None = None) -> dict:
    """Apply only explicit hard-rule evidence; text alone cannot raise minimums."""
    del task, requirements
    supplied_evidence = evidence or {}
    matched_rules = _matched_hard_rules(supplied_evidence)
    classification = _minimum_classification(supplied_evidence, matched_rules)
    return {
        "classification": classification,
        "matched_rules": matched_rules,
        "rule_version": CLASSIFIER_VERSION,
        "evidence": supplied_evidence,
    }


def _matched_hard_rules(evidence: dict) -> list[str]:
    return [rule for rule in HARD_RULES if evidence.get(rule) is True]


def _minimum_classification(evidence: dict, matched_rules: list[str]) -> str:
    if matched_rules:
        return "Architectural"
    if evidence.get("analysis_only") is True:
        return "Spike"
    return "Bounded"


def resolve_classification(rule_result: dict, semantic_result: dict | None) -> dict:
    """Keep the deterministic result as a floor while allowing semantic raises."""
    rule_classification = rule_result.get("classification")
    if rule_classification not in ORDER:
        raise ValueError("rule_result must contain a known classification")

    if not isinstance(semantic_result, dict):
        return _rule_minimum(rule_classification, "degraded")

    semantic_classification = semantic_result.get("classification")
    if semantic_classification not in ORDER:
        return _rule_minimum(rule_classification, "degraded")

    if ORDER[semantic_classification] > ORDER[rule_classification]:
        return {
            "classification": semantic_classification,
            "resolution": "semantic_raise",
            "semantic_status": "accepted",
        }

    resolution = (
        "semantic_confirmed"
        if semantic_classification == rule_classification
        else "rule_minimum_preserved"
    )
    return {
        "classification": rule_classification,
        "resolution": resolution,
        "semantic_status": "accepted",
    }


def _rule_minimum(classification: str, semantic_status: str) -> dict:
    return {
        "classification": classification,
        "resolution": "rule_minimum_preserved",
        "semantic_status": semantic_status,
    }


def canonical_hash(fields: dict) -> str:
    """Hash only approval-bound fields, excluding display-only text."""
    bound = {key: fields.get(key) for key in BOUND_FIELDS if key in fields}
    payload = json.dumps(bound, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_text(path: str | None) -> str:
    if path is None:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputReadError(f"cannot read {path}: {exc}") from exc


def load_json_object(path: str | None) -> dict | None:
    if path is None:
        return None
    try:
        decoded: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputReadError(f"cannot read {path}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise InputReadError(f"cannot read {path}: JSON object required")
    return decoded


def build_payload(
    task: str,
    requirements: str,
    semantic_result: dict | None,
    evidence: dict | None,
    stage: str,
) -> dict:
    rule_result = classify_minimum(task, requirements, evidence)
    resolution = resolve_classification(rule_result, semantic_result)
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "rule_result": rule_result,
        "semantic_result": semantic_result,
        "final_classification": resolution["classification"],
        "resolution": resolution["resolution"],
        "classifier_version": CLASSIFIER_VERSION,
    }


def format_text(payload: dict) -> str:
    return "\n".join(
        (
            f"stage: {payload['stage']}",
            f"classification: {payload['final_classification']}",
            f"resolution: {payload['resolution']}",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="raw task text")
    parser.add_argument("--stage", choices=("preliminary", "final"), default="preliminary")
    parser.add_argument("--requirements-file")
    parser.add_argument("--semantic-file")
    parser.add_argument("--evidence-file")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = build_payload(
            task=args.task,
            requirements=load_text(args.requirements_file),
            semantic_result=load_json_object(args.semantic_file),
            evidence=load_json_object(args.evidence_file),
            stage=args.stage,
        )
    except InputReadError as exc:
        print(json.dumps({"error": "input_read_error", "message": str(exc)}), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
