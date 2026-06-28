#!/usr/bin/env python3
"""Extract host bridge token usage into agent-crew cost JSONL records.

This script is intentionally adapter-neutral at the output boundary: Claude,
Codex, and future hosts can all append to the same
``${STATE_DIR}/cost/${TASK_ID}.jsonl`` contract consumed by ``crew cost`` and
``crew telemetry``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODEX_TOKENS_USED_RE = re.compile(
    r"(?is)\btokens\s+used\b\s*(?::|\r?\n|\s)+\s*([0-9][0-9,]*)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="record host bridge token usage")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--format", choices=("auto", "claude-json", "codex-text"), default="auto")
    parser.add_argument("--agent", default="host-bridge")
    parser.add_argument("--stage", default="host_bridge")
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--tier", default="unknown")
    parser.add_argument("--timestamp", default="")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def session_id_for(task_id: str) -> str:
    return task_id.rsplit("-", 1)[0] if "-" in task_id else task_id


def state_dir_for(task_dir: Path) -> Path:
    env_state = os.environ.get("AGENT_CREW_STATE_DIR")
    if env_state:
        return Path(env_state)
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent
    return task_dir.parent


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def load_json_payload(text: str) -> Any:
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            continue
    return None


def integer_field(payload: dict[str, Any], *names: str) -> int:
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        try:
            return int(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return 0


def float_field(payload: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def base_record(args: argparse.Namespace, model: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ts": args.timestamp or now_iso(),
        "task_id": args.task_id,
        "session_id": session_id_for(args.task_id),
        "agent": args.agent,
        "stage": args.stage,
        "provider": args.provider,
        "source": args.source,
        "model": model or args.model or "unknown",
        "tier": args.tier,
    }


def claude_usage_record(
    args: argparse.Namespace,
    model: str,
    usage: dict[str, Any],
) -> dict[str, Any] | None:
    input_tokens = integer_field(usage, "inputTokens", "input_tokens", "prompt_tokens")
    output_tokens = integer_field(usage, "outputTokens", "output_tokens", "completion_tokens")
    cache_creation_tokens = integer_field(
        usage,
        "cacheCreationInputTokens",
        "cache_creation_input_tokens",
        "cache_creation_tokens",
    )
    cache_read_tokens = integer_field(
        usage,
        "cacheReadInputTokens",
        "cache_read_input_tokens",
        "cache_read_tokens",
    )
    if not any((input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens)):
        return None

    record = base_record(args, model)
    record.update(
        {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "cache_read_tokens": cache_read_tokens,
        }
    )
    cost_usd = float_field(usage, "costUSD", "cost_usd")
    if cost_usd is not None:
        record["cost_usd"] = cost_usd
    return record


def extract_claude_json(args: argparse.Namespace, text: str) -> list[dict[str, Any]]:
    payload = load_json_payload(text)
    if not isinstance(payload, dict):
        return []

    records: list[dict[str, Any]] = []
    model_usage = payload.get("modelUsage") or payload.get("model_usage")
    if isinstance(model_usage, dict):
        for model, usage in model_usage.items():
            if not isinstance(usage, dict):
                continue
            record = claude_usage_record(args, str(model), usage)
            if record:
                records.append(record)
        if records:
            return records

    usage = payload.get("usage")
    if isinstance(usage, dict):
        model = str(payload.get("model") or args.model or "unknown")
        record = claude_usage_record(args, model, usage)
        return [record] if record else []
    return []


def extract_codex_text(args: argparse.Namespace, text: str) -> list[dict[str, Any]]:
    match = CODEX_TOKENS_USED_RE.search(text)
    if not match:
        return []

    total_tokens = int(match.group(1).replace(",", ""))
    if total_tokens <= 0:
        return []

    record = base_record(args, args.model)
    record.update(
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "total_tokens": total_tokens,
            "usage_granularity": "total_only",
        }
    )
    return [record]


def extract_records(args: argparse.Namespace, text: str) -> list[dict[str, Any]]:
    fmt = args.format
    if fmt == "auto":
        provider = args.provider.lower()
        fmt = "claude-json" if provider == "claude" else "codex-text"
    if fmt == "claude-json":
        return extract_claude_json(args, text)
    if fmt == "codex-text":
        return extract_codex_text(args, text)
    return []


def append_records(state_dir: Path, task_id: str, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    cost_dir = state_dir / "cost"
    cost_dir.mkdir(parents=True, exist_ok=True)
    cost_file = cost_dir / f"{task_id}.jsonl"
    with cost_file.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def main() -> int:
    args = parse_args()
    task_dir = Path(args.task_dir)
    source_path = Path(args.source)
    text = read_text(source_path)
    records = extract_records(args, text)
    append_records(state_dir_for(task_dir), args.task_id, records)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception as exc:  # Non-blocking bridge helper: log and continue.
        print(f"[host-bridge-token-usage] warning: {exc}", file=sys.stderr)
        raise SystemExit(0)
