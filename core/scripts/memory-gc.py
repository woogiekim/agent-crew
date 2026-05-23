#!/usr/bin/env python3
"""Plan and apply governed memory GC for agent-crew retrieval.

The command is intentionally conservative. A dry run is the default; `--apply`
archives candidate metadata and writes an agent-crew eviction list used by the
memory fast-search path. It does not delete the underlying mnemos vault.

Lifecycle:
  capture -> classify -> summarize -> score -> archive -> evict

Exit codes:
  0 - GC completed or memory backend is unavailable
  2 - invalid arguments or unreadable archive/eviction paths
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MAX_AGE_DAYS = 180
DEFAULT_MIN_SCORE = 30
LOW_VALUE_PATTERNS = [
    re.compile(r"^\s*(probe|test|tmp|temporary)\b", re.I),
    re.compile(r"^\s*(merged and pushed|push completed)\b", re.I),
    re.compile(r"\b(no substantive|placeholder|dummy)\b", re.I),
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_json(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value or "{}")
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def created_time(metadata: dict[str, Any]) -> datetime | None:
    for key in ("created_at", "created", "timestamp", "ts", "updated_at"):
        parsed = parse_time(metadata.get(key))
        if parsed is not None:
            return parsed
    return None


def normalize_content(content: str) -> str:
    folded = content.lower()
    folded = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", " ", folded)
    folded = re.sub(r"\d{4}-\d{2}-\d{2}[t\s]\d{2}:\d{2}:\d{2}(?:z|[+-]\d{2}:\d{2})?", " ", folded)
    folded = re.sub(r"[^a-z0-9가-힣]+", " ", folded)
    return " ".join(folded.split())


def trust_score(layer: str) -> int:
    return {
        "global": 75,
        "project": 65,
        "session": 45,
        "ephemeral": 25,
        "volatile": 15,
    }.get(layer, 35)


def low_value(content: str) -> bool:
    text = content.strip()
    if len(text) < 24:
        return True
    return any(pattern.search(text) for pattern in LOW_VALUE_PATTERNS)


def load_rows(db_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not db_path.is_file():
        return [], "fts_db_missing"
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT item_id, content, metadata FROM items_fts").fetchall()
    except sqlite3.Error as exc:
        return [], f"fts_db_error:{exc}"

    items: list[dict[str, Any]] = []
    for row in rows:
        metadata = read_json(row["metadata"] or "{}")
        content = row["content"] or ""
        created = created_time(metadata)
        layer = str(metadata.get("layer") or "unknown")
        age_days = (utc_now() - created).days if created is not None else None
        score = trust_score(layer)
        score += min(len(content) // 80, 15)
        if str(row["item_id"]).startswith("req-"):
            score += 15
        if low_value(content):
            score -= 30
        if age_days is not None and age_days > DEFAULT_MAX_AGE_DAYS:
            score -= 10

        items.append(
            {
                "id": row["item_id"],
                "content": content,
                "metadata": metadata,
                "layer": layer,
                "created_at": created.isoformat() if created else None,
                "age_days": age_days,
                "score": score,
                "fingerprint": normalize_content(content),
            }
        )
    return items, None


def build_candidates(items: list[dict[str, Any]], *, max_age_days: int, min_score: int) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    by_fingerprint: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        fingerprint = item["fingerprint"]
        if fingerprint:
            by_fingerprint.setdefault(fingerprint, []).append(item)

    for group in by_fingerprint.values():
        if len(group) <= 1:
            continue
        keep = sorted(group, key=lambda row: (-int(row["score"]), row["id"]))[0]
        for item in group:
            if item["id"] == keep["id"]:
                continue
            candidates[item["id"]] = candidate(item, "duplicate", f"duplicate_of={keep['id']}")

    for item in items:
        reasons: list[str] = []
        if low_value(item["content"]):
            reasons.append("low_value")
        if item["age_days"] is not None and item["age_days"] > max_age_days and item["layer"] in {"ephemeral", "session", "volatile"}:
            reasons.append("stale_low_trust")
        if int(item["score"]) < min_score:
            reasons.append("low_score")
        if not reasons:
            continue
        existing = candidates.get(item["id"])
        if existing is None:
            candidates[item["id"]] = candidate(item, reasons[0], ",".join(reasons))
        else:
            existing["reasons"] = sorted(set(existing["reasons"] + reasons))

    return sorted(candidates.values(), key=lambda row: (row["score"], row["id"]))


def candidate(item: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    return {
        "id": item["id"],
        "layer": item["layer"],
        "score": item["score"],
        "age_days": item["age_days"],
        "reasons": [reason],
        "detail": detail,
        "summary": item["content"].strip()[:160],
        "lifecycle": {
            "capture": "observed",
            "classify": item["layer"],
            "summarize": "summary",
            "score": item["score"],
            "archive": "pending",
            "evict": "pending",
        },
    }


def apply_gc(candidates: list[dict[str, Any]], archive_path: Path, evicted_path: Path) -> tuple[int, int]:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    evicted_path.parent.mkdir(parents=True, exist_ok=True)

    now = utc_now().isoformat()
    with archive_path.open("a", encoding="utf-8") as archive:
        for item in candidates:
            record = dict(item)
            record["archived_at"] = now
            record["lifecycle"] = dict(record["lifecycle"])
            record["lifecycle"]["archive"] = "archived"
            record["lifecycle"]["evict"] = "evicted_from_agent_crew_fast_retrieval"
            archive.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    existing = set()
    if evicted_path.is_file():
        existing = {line.strip() for line in evicted_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    updated = sorted(existing | {str(item["id"]) for item in candidates})
    evicted_path.write_text("\n".join(updated) + ("\n" if updated else ""), encoding="utf-8")
    return len(candidates), len(updated)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.fts_db).expanduser().resolve() if args.fts_db else Path(args.mnemos_root).expanduser().resolve() / ".agent" / "state" / "fts.db"
    items, warning = load_rows(db_path)
    candidates = build_candidates(items, max_age_days=args.max_age_days, min_score=args.min_score) if not warning else []

    applied = False
    archived = 0
    evicted_total = 0
    if args.apply and candidates:
        archived, evicted_total = apply_gc(candidates, Path(args.archive_path).expanduser().resolve(), Path(args.evicted_path).expanduser().resolve())
        applied = True

    reason_counts: dict[str, int] = {}
    for item in candidates:
        for reason in item["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "schema_version": 1,
        "passed": True,
        "mode": "apply" if args.apply else "dry-run",
        "source_db": str(db_path),
        "archive_path": str(Path(args.archive_path).expanduser()),
        "evicted_path": str(Path(args.evicted_path).expanduser()),
        "warning": warning,
        "summary": {
            "items": len(items),
            "candidates": len(candidates),
            "reason_counts": reason_counts,
            "applied": applied,
            "archived": archived,
            "evicted_total": evicted_total,
        },
        "candidates": candidates,
    }


def main() -> int:
    home = Path.home()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mnemos-root", default=str(home / ".mnemos"))
    parser.add_argument("--fts-db", default="")
    parser.add_argument("--archive-path", default=str(home / ".agent-crew" / "memory-gc" / "archive.jsonl"))
    parser.add_argument("--evicted-path", default=str(home / ".agent-crew" / "memory-gc" / "evicted-ids.txt"))
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    if args.max_age_days < 0 or args.min_score < 0:
        print("max-age-days and min-score must be non-negative", file=sys.stderr)
        return 2
    if args.apply and args.dry_run:
        print("--apply and --dry-run are mutually exclusive", file=sys.stderr)
        return 2

    result = evaluate(args)
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        summary = result["summary"]
        print(("APPLY" if args.apply else "DRY-RUN") + ": memory gc")
        if result["warning"]:
            print(f"warning={result['warning']}")
        print(f"items={summary['items']} candidates={summary['candidates']} archived={summary['archived']}")
        for item in result["candidates"]:
            print(f"- {item['id']}: {','.join(item['reasons'])} score={item['score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
