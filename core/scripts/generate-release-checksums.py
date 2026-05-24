#!/usr/bin/env python3
"""Generate SHA-256 integrity metadata for release, install, and update files."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def default_artifacts(root: Path) -> list[Path]:
    candidates = [
        root / "install.sh",
        root / "core" / "bin" / "crew",
        root / "core" / "commands" / "update.md",
        root / "core" / "scripts" / "sync-local-install.sh",
    ]

    return [path for path in candidates if path.is_file()]


def build_manifest(root: Path, artifacts: list[Path]) -> dict[str, Any]:
    entries = []
    for path in artifacts:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"artifact not found: {path}")

        try:
            rel = resolved.relative_to(root)
            artifact_path = rel.as_posix()
        except ValueError:
            artifact_path = str(resolved)

        entries.append({
            "path": artifact_path,
            "sha256": sha256(resolved),
            "bytes": resolved.stat().st_size,
        })

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "algorithm": "sha256",
        "project_root": str(root),
        "artifacts": entries,
    }


def write_sha256sums(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        f"{entry['sha256']}  {entry['path']}"
        for entry in manifest["artifacts"]
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def verify_manifest(root: Path, manifest_path: Path) -> tuple[bool, list[str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for entry in manifest.get("artifacts", []):
        artifact = Path(entry["path"])
        if not artifact.is_absolute():
            artifact = root / artifact
        if not artifact.is_file():
            mismatches.append(f"missing: {entry['path']}")
            continue

        observed = sha256(artifact)
        if observed != entry.get("sha256"):
            mismatches.append(f"sha256 mismatch: {entry['path']}")

    return not mismatches, mismatches


def main() -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="*", help="Files to include; defaults to installer/update artifacts.")
    parser.add_argument("--project-root", default=str(root))
    parser.add_argument("--output", help="Write JSON manifest to this path.")
    parser.add_argument("--sha256sums", help="Write sha256sum-compatible text to this path.")
    parser.add_argument("--verify", help="Verify an existing JSON manifest instead of generating one.")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()

    if args.verify:
        ok, mismatches = verify_manifest(project_root, Path(args.verify).expanduser())
        if args.format == "json":
            json.dump({"passed": ok, "mismatches": mismatches}, sys.stdout, indent=2)
            print()
        else:
            print("PASS: release checksums verified" if ok else "FAIL: release checksum verification")
            for mismatch in mismatches:
                print(f"- {mismatch}")

        return 0 if ok else 1

    artifacts = [Path(item) for item in args.artifacts]
    if not artifacts:
        artifacts = default_artifacts(project_root)
    artifacts = [path if path.is_absolute() else project_root / path for path in artifacts]

    manifest = build_manifest(project_root, artifacts)

    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.sha256sums:
        write_sha256sums(Path(args.sha256sums).expanduser(), manifest)

    if args.format == "json":
        json.dump(manifest, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(f"generated {len(manifest['artifacts'])} sha256 checksums")
        for entry in manifest["artifacts"]:
            print(f"- {entry['sha256']}  {entry['path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
