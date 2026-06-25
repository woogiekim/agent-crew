"""Infer specialized task capabilities from task text."""

from __future__ import annotations

import re


ENGLISH_NEGATED_CAPABILITY_CLAUSE_RE = re.compile(
    r"\b(?P<prefix>do\s+not|don't|dont|must\s+not|should\s+not|never|without|no)"
    r"(?P<body>[^.;\n]*)",
    re.IGNORECASE,
)
ENGLISH_CAPABILITY_ACTION_RE = re.compile(
    r"\b("
    r"git\s+commit|commit(?:ting)?|amend(?:ing)?|reword(?:ing)?|squash(?:ing)?|"
    r"git\s+push|push(?:ing)?|"
    r"git\s+merge|merge|merging|"
    r"deploy(?:ing)?|release|releasing|rollback|rolling\s+back|"
    r"publish(?:ing)?|close|closing|update\s+issue|comment\s+on\s+issue"
    r")\b",
    re.IGNORECASE,
)
KOREAN_NEGATED_CAPABILITY_ACTION_RE = re.compile(
    r"(?:커밋|푸시|머지|병합|배포|릴리즈|롤백|발행|게시|이슈\s*(?:발행|닫|종료|수정|댓글))"
    r"\s*(?:하지\s*마|하지\s*말고|하지\s*않고|하지\s*않으며|않고|없이|금지)",
    re.IGNORECASE,
)
CAPABILITY_GOVERNANCE_CONTEXT_RE = re.compile(
    r"\b(?:preserv(?:e|es|ing)|keep(?:s|ing)?|maintain(?:s|ing)?|"
    r"document(?:s|ing)?|test(?:s|ing)?|validat(?:e|es|ing)|"
    r"verif(?:y|ies|ying)|enforc(?:e|es|ing)|cover(?:s|ing)?|"
    r"improv(?:e|es|ing)|implement(?:s|ing)?|add(?:s|ing)?|"
    r"updat(?:e|es|ing)|apply|applies|applying)\b"
    r"[^.;\n]*\b(?:gate|gates|guard|guards|policy|policies|check|checker|"
    r"validation|detector|rule|rules|handling)\b"
    r"[^.;\n]*\b(?:commit|push|merge|deploy|release|rollback|destructive)\b"
    r"[^.;\n]*",
    re.IGNORECASE,
)


def _normalize_task_text(task: str) -> str:
    return " ".join((task or "").strip().lower().split())


def strip_negative_capability_constraints(task: str) -> str:
    value = _normalize_task_text(task)

    def strip_english_action(match: re.Match[str]) -> str:
        body = ENGLISH_CAPABILITY_ACTION_RE.sub(" ", match.group("body"))
        return f" {body} "

    value = ENGLISH_NEGATED_CAPABILITY_CLAUSE_RE.sub(strip_english_action, value)
    value = KOREAN_NEGATED_CAPABILITY_ACTION_RE.sub(" ", value)
    value = CAPABILITY_GOVERNANCE_CONTEXT_RE.sub(" ", value)
    return " ".join(value.split())


def required_capabilities_for_task(task: str) -> list[str]:
    value = strip_negative_capability_constraints(task)
    capabilities: list[str] = []

    def add(capability: str) -> None:
        if capability not in capabilities:
            capabilities.append(capability)

    if re.search(r"\b(git\s+commit|commit|amend|reword|squash)\b|커밋", value):
        add("vcs.commit.message.compose")
        add("vcs.history.local_mutation")
    if re.search(r"\b(git\s+push|push)\b|푸시", value):
        add("vcs.remote_mutation")
    if re.search(r"\b(git\s+merge|merge)\b|머지|병합", value):
        add("vcs.history.local_mutation")
    if re.search(r"\b(deploy|release|rollback)\b|배포|릴리즈|롤백", value):
        add("deployment.mutate")
    if re.search(r"\b(publish|close|update\s+issue|comment\s+on\s+issue)\b|이슈.*(발행|닫|종료|수정|댓글)", value):
        add("tracker.issue.mutate")

    return capabilities
