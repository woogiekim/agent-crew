#!/usr/bin/env python3
"""Verify installed source-owned assets match the source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def dest_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def compare_tree(src: Path, dest: Path, *, prune_extra: bool) -> dict:
    return compare_trees([src], dest, prune_extra=prune_extra)


def compare_trees(src_roots: list[Path], dest: Path, *, prune_extra: bool) -> dict:
    src_map: dict[str, Path] = {}
    for src in src_roots:
        src_map.update(source_files(src))
    dest_map = dest_files(dest)
    missing = []
    mismatched = []
    extra = []

    for rel, src_path in src_map.items():
        dest_path = dest / rel
        if not dest_path.is_file():
            missing.append(rel)
            continue
        if sha256_file(src_path) != sha256_file(dest_path):
            mismatched.append(rel)

    for rel, dest_path in dest_map.items():
        if rel in src_map:
            continue
        extra.append(rel)
        if prune_extra:
            dest_path.unlink()

    return {
        "source": ", ".join(str(src) for src in src_roots),
        "destination": str(dest),
        "missing": missing,
        "mismatched": mismatched,
        "extra": extra,
        "passed": not missing and not mismatched and (not extra or prune_extra),
    }


def compare_file(src: Path, dest: Path) -> dict:
    missing = []
    mismatched = []
    if not src.is_file():
        missing.append(str(src))
    elif not dest.is_file():
        missing.append(str(dest))
    elif sha256_file(src) != sha256_file(dest):
        mismatched.append(str(dest))
    return {
        "source": str(src),
        "destination": str(dest),
        "missing": missing,
        "mismatched": mismatched,
        "extra": [],
        "passed": not missing and not mismatched,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--agent-crew-home", default=os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew")))
    parser.add_argument("--path-bin", default=os.environ.get("AGENT_CREW_PATH_BIN", str(Path.home() / ".local" / "bin")))
    parser.add_argument("--skip-path-bin", action="store_true")
    parser.add_argument("--prune-extra", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve()
    home = Path(args.agent_crew_home).expanduser().resolve()
    path_bin = Path(args.path_bin).expanduser().resolve()

    checks = []
    for rel in ("hooks", "scripts", "evaluations", "policies"):
        src = source_root / "core" / rel
        for dest in (home / "system" / rel, home / rel):
            checks.append(compare_tree(src, dest, prune_extra=args.prune_extra))

    checks.append(
        compare_tree(
            source_root / "core" / "commands",
            home / "system" / "commands",
            prune_extra=args.prune_extra,
        )
    )
    checks.append(
        compare_trees(
            [
                source_root / "core" / "commands",
                source_root / "core" / "user" / "commands",
            ],
            home / "commands",
            prune_extra=args.prune_extra,
        )
    )

    checks.append(compare_tree(source_root / "core" / "bin", home / "bin", prune_extra=args.prune_extra))
    if not args.skip_path_bin:
        checks.append(compare_file(source_root / "core" / "bin" / "crew", path_bin / "crew"))

    payload = {
        "schema_version": 1,
        "source_root": str(source_root),
        "agent_crew_home": str(home),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["passed"] else "FAIL") + ": install drift check")
        for check in checks:
            if check["passed"]:
                continue
            print(f"- {check['destination']}")
            if check["missing"]:
                print("  missing: " + ", ".join(check["missing"]))
            if check["mismatched"]:
                print("  mismatched: " + ", ".join(check["mismatched"]))
            if check["extra"] and not args.prune_extra:
                print("  extra: " + ", ".join(check["extra"]))

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
