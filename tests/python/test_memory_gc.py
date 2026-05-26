"""Tests for governed memory GC."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import subprocess
from datetime import timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "memory-gc.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


memory_gc = _load_module(SCRIPT, "memory_gc")


def _write_fts(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE items_fts (item_id TEXT, content TEXT, metadata TEXT)")
    conn.execute(
        "INSERT INTO items_fts VALUES (?, ?, ?)",
        (
            "req-old",
            "temporary duplicate memory content with enough substance to score and normalize",
            json.dumps({"layer": "session", "created_at": "2020-01-01T00:00:00Z"}),
        ),
    )
    conn.execute(
        "INSERT INTO items_fts VALUES (?, ?, ?)",
        (
            "tmp-old",
            "temporary duplicate memory content with enough substance to score and normalize",
            json.dumps({"layer": "volatile", "created_at": "2020-01-01T00:00:00Z"}),
        ),
    )
    conn.commit()
    conn.close()


def test_memory_gc_helpers_cover_invalid_json_and_time_edges(tmp_path: Path):
    assert memory_gc.read_json("not json") == {}
    assert memory_gc.parse_time(None) is None
    assert memory_gc.parse_time("not a date") is None
    parsed = memory_gc.parse_time("2026-01-01T00:00:00")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc
    assert memory_gc.created_time({}) is None

    missing_rows, missing_warning = memory_gc.load_rows(tmp_path / "missing.db")
    assert missing_rows == []
    assert missing_warning == "fts_db_missing"

    broken = tmp_path / "broken.db"
    sqlite3.connect(broken).close()
    rows, warning = memory_gc.load_rows(broken)
    assert rows == []
    assert warning and warning.startswith("fts_db_error:")


def test_memory_gc_candidate_builder_skips_short_groups_and_healthy_items():
    item = {
        "id": "stable",
        "content": "Durable project memory with enough context for future retrieval and reuse.",
        "metadata": {},
        "layer": "project",
        "created_at": "2026-01-01T00:00:00+00:00",
        "age_days": 1,
        "score": 80,
        "fingerprint": "durable project memory",
    }

    assert memory_gc.low_value("short") is True
    assert memory_gc.build_candidates([item], max_age_days=180, min_score=30) == []


def test_memory_gc_loads_rows_scores_req_ids_and_applies_existing_evictions(tmp_path: Path):
    db = tmp_path / "fts.db"
    _write_fts(db)

    rows, warning = memory_gc.load_rows(db)
    assert warning is None
    req = next(row for row in rows if row["id"] == "req-old")
    assert req["score"] > 0

    candidates = memory_gc.build_candidates(rows, max_age_days=1, min_score=100)
    archive = tmp_path / "archive.jsonl"
    evicted = tmp_path / "evicted.txt"
    evicted.write_text("already-evicted\n", encoding="utf-8")

    archived, evicted_total = memory_gc.apply_gc(candidates, archive, evicted)

    assert archived == len(candidates)
    assert evicted_total == len({candidate["id"] for candidate in candidates} | {"already-evicted"})
    assert "already-evicted" in evicted.read_text(encoding="utf-8")


def test_memory_gc_evaluate_apply_mode_archives_candidates(tmp_path: Path):
    db = tmp_path / "fts.db"
    _write_fts(db)
    args = argparse.Namespace(
        fts_db=str(db),
        mnemos_root=str(tmp_path),
        archive_path=str(tmp_path / "archive.jsonl"),
        evicted_path=str(tmp_path / "evicted.txt"),
        max_age_days=1,
        min_score=100,
        apply=True,
    )

    result = memory_gc.evaluate(args)

    assert result["mode"] == "apply"
    assert result["summary"]["applied"] is True
    assert result["summary"]["archived"] == len(result["candidates"])


def test_memory_gc_argument_errors(tmp_path: Path):
    negative = subprocess.run(
        ["python3", str(SCRIPT), "--fts-db", str(tmp_path / "missing.db"), "--max-age-days", "-1"],
        text=True,
        capture_output=True,
    )
    assert negative.returncode == 2
    assert "non-negative" in negative.stderr

    conflict = subprocess.run(
        ["python3", str(SCRIPT), "--apply", "--dry-run"],
        text=True,
        capture_output=True,
    )
    assert conflict.returncode == 2
    assert "mutually exclusive" in conflict.stderr


def test_memory_gc_json_output_reports_summary(tmp_path: Path):
    result = subprocess.run(
        ["python3", str(SCRIPT), "--fts-db", str(tmp_path / "missing.db"), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["candidates"] == 0
    assert payload["warning"] == "fts_db_missing"


def test_memory_gc_text_output_reports_warning_and_candidates(tmp_path: Path):
    missing = subprocess.run(
        ["python3", str(SCRIPT), "--fts-db", str(tmp_path / "missing.db")],
        text=True,
        capture_output=True,
    )
    assert missing.returncode == 0
    assert "DRY-RUN: memory gc" in missing.stdout
    assert "warning=fts_db_missing" in missing.stdout

    db = tmp_path / "fts.db"
    _write_fts(db)
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--fts-db",
            str(db),
            "--max-age-days",
            "1",
            "--min-score",
            "100",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "candidates=" in result.stdout
    assert "- tmp-old:" in result.stdout or "- req-old:" in result.stdout
