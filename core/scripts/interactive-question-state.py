#!/usr/bin/env python3
"""Persist provider-neutral interactive question decisions.

This helper is intentionally small: host adapters own the actual UI surface,
while core owns deterministic question ids, cached decisions, and audit files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_options(raw: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise SystemExit(f"interactive-question-state: invalid options JSON: {exc}")

    if not isinstance(value, list) or not value:
        raise SystemExit("interactive-question-state: options JSON must be a non-empty list")

    options: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise SystemExit(f"interactive-question-state: option {idx} must be an object")
        label = str(item.get("label") or "").strip()
        if not label:
            raise SystemExit(f"interactive-question-state: option {idx} missing label")
        options.append(
            {
                "label": label,
                "value": str(item.get("value") or label),
                "description": str(item.get("description") or ""),
            }
        )
    return options


def question_id(prompt: str, options: list[dict[str, Any]]) -> str:
    canonical = {
        "prompt": " ".join(prompt.split()),
        "options": [
            {
                "label": option["label"],
                "value": option.get("value", option["label"]),
            }
            for option in options
        ],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def question_dir(args: argparse.Namespace) -> Path:
    if args.task_dir:
        return Path(args.task_dir).expanduser() / "context" / "interactive-questions"
    if args.state_dir:
        return Path(args.state_dir).expanduser() / "interactive-questions"
    raise SystemExit("interactive-question-state: --task-dir or --state-dir is required")


def decision_path(args: argparse.Namespace) -> Path:
    return question_dir(args) / f"{args.question_id}.json"


def cmd_key(args: argparse.Namespace) -> int:
    options = load_options(args.options_json)
    print(question_id(args.prompt, options))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    options = load_options(args.options_json)
    labels = {option["label"] for option in options}
    chosen_label = str(args.chosen_label).strip()
    if chosen_label != "__cancelled__" and chosen_label not in labels:
        raise SystemExit(
            "interactive-question-state: chosen label must match an option label "
            "or __cancelled__"
        )

    record = {
        "schema_version": 1,
        "question_id": args.question_id,
        "prompt": args.prompt,
        "options": options,
        "chosen_label": chosen_label,
        "chosen_value": args.chosen_value or chosen_label,
        "source": args.source,
        "adapter": args.adapter,
        "created_at": utc_now_z(),
        "cancelled": chosen_label == "__cancelled__",
    }
    path = decision_path(args)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    path = decision_path(args)
    if not path.is_file():
        print(json.dumps({"found": False, "question_id": args.question_id}, sort_keys=True))
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["found"] = True
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_render_markdown(args: argparse.Namespace) -> int:
    options = load_options(args.options_json)
    print(args.prompt)
    print()
    print("Pick one (reply with the option number):")
    print()
    for idx, option in enumerate(options, start=1):
        desc = option.get("description") or ""
        suffix = f" — {desc}" if desc else ""
        print(f"{idx}. **{option['label']}**{suffix}")
    print("0. **cancel**")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist and resolve interactive question choices."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    key = sub.add_parser("key", help="compute deterministic question id")
    key.add_argument("--prompt", required=True)
    key.add_argument("--options-json", required=True)
    key.set_defaults(func=cmd_key)

    record = sub.add_parser("record", help="record a resolved question choice")
    record.add_argument("--task-dir")
    record.add_argument("--state-dir")
    record.add_argument("--question-id", required=True)
    record.add_argument("--prompt", required=True)
    record.add_argument("--options-json", required=True)
    record.add_argument("--chosen-label", required=True)
    record.add_argument("--chosen-value", default="")
    record.add_argument("--source", default="unknown")
    record.add_argument("--adapter", default="unknown")
    record.set_defaults(func=cmd_record)

    resolve = sub.add_parser("resolve", help="resolve cached question choice")
    resolve.add_argument("--task-dir")
    resolve.add_argument("--state-dir")
    resolve.add_argument("--question-id", required=True)
    resolve.set_defaults(func=cmd_resolve)

    markdown = sub.add_parser("render-markdown", help="render markdown fallback")
    markdown.add_argument("--prompt", required=True)
    markdown.add_argument("--options-json", required=True)
    markdown.set_defaults(func=cmd_render_markdown)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
