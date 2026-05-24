"""Tests for release checksum generation and verification."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "generate-release-checksums.py"


def test_generate_release_checksums_writes_json_and_sha256sums(tmp_path: Path):
    artifact = tmp_path / "installer.sh"
    artifact.write_text("#!/bin/sh\necho install\n", encoding="utf-8")
    manifest = tmp_path / "checksums.json"
    sums = tmp_path / "SHA256SUMS"

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--project-root",
            str(tmp_path),
            "--output",
            str(manifest),
            "--sha256sums",
            str(sums),
            str(artifact),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["algorithm"] == "sha256"
    assert payload["artifacts"][0]["path"] == "installer.sh"
    assert payload["artifacts"][0]["bytes"] == artifact.stat().st_size
    assert "installer.sh" in sums.read_text(encoding="utf-8")


def test_generate_release_checksums_verifies_manifest(tmp_path: Path):
    artifact = tmp_path / "crew"
    artifact.write_text("crew\n", encoding="utf-8")
    manifest = tmp_path / "checksums.json"
    generate = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--project-root",
            str(tmp_path),
            "--output",
            str(manifest),
            str(artifact),
        ],
        text=True,
        capture_output=True,
    )
    assert generate.returncode == 0, generate.stdout + generate.stderr

    verify = subprocess.run(
        ["python3", str(SCRIPT), "--project-root", str(tmp_path), "--verify", str(manifest)],
        text=True,
        capture_output=True,
    )

    assert verify.returncode == 0, verify.stdout + verify.stderr


def test_generate_release_checksums_detects_modified_artifact(tmp_path: Path):
    artifact = tmp_path / "crew"
    artifact.write_text("crew\n", encoding="utf-8")
    manifest = tmp_path / "checksums.json"
    generate = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--project-root",
            str(tmp_path),
            "--output",
            str(manifest),
            str(artifact),
        ],
        text=True,
        capture_output=True,
    )
    assert generate.returncode == 0, generate.stdout + generate.stderr
    artifact.write_text("changed\n", encoding="utf-8")

    verify = subprocess.run(
        ["python3", str(SCRIPT), "--project-root", str(tmp_path), "--verify", str(manifest)],
        text=True,
        capture_output=True,
    )

    assert verify.returncode == 1
    assert "sha256 mismatch" in verify.stdout
