#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from typing import Dict, List, Optional, Tuple


PRESET_ORDER = [
    "ticket-resolve",
    "review-fix",
    "debug",
    "bugfix",
    "parity",
    "closeout",
    "default",
]

ANALYSIS_ADEQUACY_STATES = [
    "READY",
    "NEEDS_ANALYSIS",
    "NEEDS_USER_INPUT",
    "BLOCKED",
]

EXPLICIT_PRESET_RE = re.compile(
    r"^\s*(ticket-resolve|review-fix|debug|bugfix|parity|closeout|default)\b",
    re.IGNORECASE,
)
TRACKER_RE = re.compile(r"(?:^|\b)([A-Z][A-Z0-9]+-\d+|#\d+)(?:\b|$)")

KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "review-fix": (
        "review",
        "finding",
        "feedback",
        "code review",
        "코드리뷰",
        "리뷰",
        "피드백",
        "반영",
    ),
    "debug": (
        "debug",
        "diagnose",
        "root cause",
        "stacktrace",
        "stack trace",
        "로그",
        "원인",
        "진단",
        "왜",
    ),
    "bugfix": (
        "bugfix",
        "bug",
        "regression",
        "reproduce",
        "exception",
        "오류",
        "회귀",
        "재현",
        "깨짐",
        "실패",
        "예외",
    ),
    "parity": (
        "parity",
        "producer",
        "consumer",
        "legacy",
        "migration",
        "마이그레이션",
        "동등",
        "계약",
        "호환",
    ),
    "closeout": (
        "closeout",
        "summary",
        "note",
        "status summary",
        "마무리",
        "검증 요약",
        "리뷰 노트",
        "정리",
    ),
}

DESCRIPTIONS = {
    "ticket-resolve": "Tracker issue를 기준으로 요구사항 충분성을 확인하고 구현, 검증, 리뷰 반영 루프를 진행합니다.",
    "review-fix": "리뷰 finding과 현재 diff를 대조해 반영 범위, 테스트, 잔여 리스크를 닫습니다.",
    "debug": "증상과 로그에서 원인을 먼저 좁힌 뒤 수정 여부를 결정합니다.",
    "bugfix": "재현 조건과 regression test를 먼저 세우고 결함을 수정합니다.",
    "parity": "producer/consumer 또는 legacy/new 계약 차이를 확인하고 맞춥니다.",
    "closeout": "현재 작업 상태, 검증 결과, note draft, 후속 대기 항목을 정리합니다.",
    "default": "일반 구현/수정 요청으로 보고 기존 supervisor 실행 흐름을 사용합니다.",
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def add_signal(signals: List[dict], preset: str, signal: str, evidence: str) -> None:
    signals.append({"preset": preset, "signal": signal, "evidence": evidence})


def keyword_hit(text_lc: str, keyword: str) -> bool:
    if re.search(r"[a-z0-9]", keyword):
        pattern = r"(?:^|\W)" + re.escape(keyword) + r"(?:\W|$)"
        return re.search(pattern, text_lc) is not None

    return keyword in text_lc


def collect_signals(task: str) -> List[dict]:
    signals: List[dict] = []
    text = normalize(task)
    text_lc = text.lower()

    explicit = EXPLICIT_PRESET_RE.search(text)
    if explicit:
        preset = explicit.group(1).lower()
        add_signal(signals, preset, "explicit_preset", explicit.group(1))

    tracker = TRACKER_RE.search(text)
    if tracker:
        add_signal(signals, "ticket-resolve", "tracker_issue_id", tracker.group(1))

    for preset, keywords in KEYWORDS.items():
        for keyword in keywords:
            if keyword_hit(text_lc, keyword):
                add_signal(signals, preset, "keyword", keyword)
                break

    return signals


def score_signals(signals: List[dict]) -> Dict[str, int]:
    scores: Dict[str, int] = {}
    for signal in signals:
        preset = signal["preset"]
        weight = 3 if signal["signal"] in {"explicit_preset", "tracker_issue_id"} else 1
        scores[preset] = scores.get(preset, 0) + weight

    return scores


def recommend(scores: Dict[str, int]) -> Tuple[Optional[str], str]:
    if not scores:
        return "default", "low"

    ranked = sorted(scores.items(), key=lambda item: (-item[1], PRESET_ORDER.index(item[0])))
    top_preset, top_score = ranked[0]
    confidence = "high" if top_score >= 3 else "medium"

    return top_preset, confidence


def build_options(recommended: Optional[str], include_all: bool = False) -> List[dict]:
    presets = PRESET_ORDER if include_all else [preset for preset in PRESET_ORDER if preset != "default"]
    options = []
    for preset in presets:
        options.append(
            {
                "preset": preset,
                "label": preset,
                "description": DESCRIPTIONS[preset],
                "recommended": preset == recommended,
            }
        )

    if not include_all:
        options.append(
            {
                "preset": "default",
                "label": "default",
                "description": DESCRIPTIONS["default"],
                "recommended": recommended == "default",
            }
        )

    options.append(
        {
            "preset": "cancel",
            "label": "취소",
            "description": "아무 작업도 시작하지 않습니다.",
            "recommended": False,
        }
    )

    return options


def classify(task: str) -> dict:
    normalized = normalize(task)
    if not normalized:
        return {
            "recommended": None,
            "confidence": "none",
            "auto_select": False,
            "selection_required": True,
            "conflicts": [],
            "signals": [],
            "options": [
                {
                    "action": "tracker_issue_id",
                    "label": "Tracker issue id 입력",
                    "description": "이슈 id를 받아 ticket-resolve 후보로 다시 분류합니다.",
                },
                {
                    "action": "recent_prompt",
                    "label": "최근 prompt 실행",
                    "description": "최근에 생성한 prompt를 실행 후보로 사용합니다.",
                },
                {
                    "action": "current_branch",
                    "label": "현재 작업 브랜치 기준으로 이어서 실행",
                    "description": "현재 diff와 브랜치 상태를 바탕으로 이어서 진행합니다.",
                },
                {
                    "action": "direct_input",
                    "label": "직접 작업 내용 입력",
                    "description": "작업 내용을 새로 입력합니다.",
                },
                {
                    "action": "cancel",
                    "label": "취소",
                    "description": "아무 작업도 시작하지 않습니다.",
                },
            ],
            "reason": "작업 내용이 비어 있어 실행할 workflow를 결정할 수 없습니다.",
            "caution": "",
            "analysis_adequacy_states": ANALYSIS_ADEQUACY_STATES,
        }

    signals = collect_signals(normalized)
    scores = score_signals(signals)
    recommended, confidence = recommend(scores)
    if "review-fix" in scores and "ticket-resolve" in scores:
        recommended = "review-fix"
        confidence = "high"

    conflicts = [
        preset
        for preset in PRESET_ORDER
        if preset != recommended and preset in scores and preset != "default"
    ]
    selection_required = confidence != "high" or bool(conflicts)
    auto_select = not selection_required

    if recommended == "review-fix" and "ticket-resolve" in scores:
        selection_required = True
        auto_select = False
        if "ticket-resolve" not in conflicts:
            conflicts.append("ticket-resolve")

    if not signals:
        reason = "명확한 preset 신호가 없어 일반 실행 후보로 분류했습니다."
    else:
        leading = next(signal for signal in signals if signal["preset"] == recommended)
        reason = f"{leading['signal']} 신호({leading['evidence']})가 {recommended} 후보를 가리킵니다."

    caution = ""
    if conflicts:
        caution = "다른 workflow 신호도 감지되어 사용자 선택 후 진행해야 합니다: " + ", ".join(conflicts)
    elif confidence != "high":
        caution = "신호 강도가 높지 않아 사용자 선택을 권장합니다."

    return {
        "recommended": recommended,
        "confidence": confidence,
        "auto_select": auto_select,
        "selection_required": selection_required,
        "conflicts": conflicts,
        "signals": signals,
        "options": build_options(recommended),
        "reason": reason,
        "caution": caution,
        "analysis_adequacy_states": ANALYSIS_ADEQUACY_STATES,
    }


def render_text(payload: dict) -> str:
    if payload["recommended"] is None:
        lines = ["무엇을 실행할까요?", ""]
        for idx, option in enumerate(payload["options"], start=1):
            lines.append(f"{idx}. {option['label']}")

        return "\n".join(lines) + "\n"

    if payload["auto_select"]:
        return (
            f"선택된 workflow: {payload['recommended']}\n"
            f"이유: {payload['reason']}\n"
        )

    lines = [
        "실행할 workflow를 선택해 주세요.",
        "",
        f"추천: {payload['recommended']}",
        f"이유: {payload['reason']}",
    ]
    if payload["caution"]:
        lines.append(f"주의: {payload['caution']}")
    else:
        lines.append("주의: 선택 전에는 workflow를 시작하지 않습니다.")

    lines.append("")
    for idx, option in enumerate(payload["options"], start=1):
        suffix = " (추천)" if option.get("recommended") else ""
        lines.append(f"{idx}. {option['label']}{suffix} - {option['description']}")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify crew:run workflow preset.")
    parser.add_argument("positional_task", nargs="*", help="Task text when --task is omitted.")
    parser.add_argument("--task", default=None, help="Task text to classify.")
    parser.add_argument("--format", choices=("json", "text"), default="json")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task = args.task if args.task is not None else " ".join(args.positional_task)
    payload = classify(task)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload), end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
