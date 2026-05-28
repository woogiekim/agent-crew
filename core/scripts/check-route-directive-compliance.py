#!/usr/bin/env python3
"""
check-route-directive-compliance.py — Detect ignored STOP/ROUTE directives.

The UserPromptSubmit auto-route hook can only inject advisory context. This
validator runs on Agent/PostToolUse payloads and catches a delegated agent that
received a STOP/ROUTE directive but returned a normal inline answer instead of
entering the required crew workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


STOP_PAT = re.compile(r"\[agent-crew\]\s+STOP\b", re.IGNORECASE)
ROUTE_PAT = re.compile(r"\[agent-crew\]\s+ROUTE\b", re.IGNORECASE)

STOP_COMPLIANCE_PAT = re.compile(
    r"\bcrew\s*:?\s*run\b|Skill\([\"']crew-run[\"']\)|"
    r"\bTASK_ID:|\bSUPERVISOR_HANDOFF\b|\bHOST_BRIDGE:|"
    r"\bSTATUS:\s*handoff_ready\b|Background Session Started",
    re.IGNORECASE,
)
ROUTE_COMPLIANCE_PAT = re.compile(
    r"\bcrew\s*:?\s*agent\b|Skill\([\"']crew-agent[\"']\)|"
    r"\bAGENT_REQUEST_ID:|\bHOST_BRIDGE:|"
    r"\bSTATUS:\s*handoff_ready\b",
    re.IGNORECASE,
)


def _text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(_text_from_value(item.get("text") or item.get("content")))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        parts = []
        for key in ("prompt", "message", "description", "content", "text", "output"):
            part = _text_from_value(value.get(key))
            if part:
                parts.append(part)
        return "\n".join(parts)
    return ""


def extract_prompt(payload: dict[str, Any]) -> str:
    values = [
        payload.get("prompt"),
        payload.get("additionalContext"),
        payload.get("system_context"),
        payload.get("tool_input"),
    ]
    return "\n".join(part for part in (_text_from_value(v) for v in values) if part)


def extract_response(payload: dict[str, Any]) -> str:
    return _text_from_value(payload.get("tool_response"))


def directive_type(text: str) -> str:
    if STOP_PAT.search(text):
        return "STOP"
    if ROUTE_PAT.search(text):
        return "ROUTE"
    return ""


def is_compliant(kind: str, response: str) -> bool:
    if kind == "STOP":
        return bool(STOP_COMPLIANCE_PAT.search(response))
    if kind == "ROUTE":
        return bool(ROUTE_COMPLIANCE_PAT.search(response))
    return True


def excerpt(text: str, limit: int = 220) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect Agent responses that ignore agent-crew STOP/ROUTE directives."
    )
    parser.add_argument("--text", help="diagnostic response text to scan")
    parser.add_argument(
        "--directive",
        choices=("auto", "STOP", "ROUTE"),
        default="auto",
        help="diagnostic directive type when --text is used",
    )
    parser.add_argument(
        "--tool",
        default="Agent",
        help="tool_name to filter on when reading a hook payload (default: Agent; '*' scans all)",
    )
    args = parser.parse_args()

    if args.text is not None:
        kind = "" if args.directive == "auto" else args.directive
        response = args.text
    else:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return 0
        if not isinstance(payload, dict):
            return 0
        if args.tool != "*" and payload.get("tool_name", "") != args.tool:
            return 0

        prompt = extract_prompt(payload)
        kind = directive_type(prompt)
        response = extract_response(payload)

    if not kind or not response or is_compliant(kind, response):
        return 0

    expected = "crew:run / Skill(\"crew-run\")" if kind == "STOP" else "crew:agent / Skill(\"crew-agent\")"
    print(
        "agent-crew: routed Agent response ignored an auto-route directive.\n"
        f"  Directive: {kind}\n"
        f"  Expected first action evidence: {expected}\n"
        f"  Response excerpt: {excerpt(response)!r}\n"
        "  Rule: STOP/ROUTE directives are route locks. Do not answer inline;\n"
        "        invoke the required crew workflow and return its handoff/result.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
