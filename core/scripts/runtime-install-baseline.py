#!/usr/bin/env python3
"""Publish and resolve the source inputs used for a global installation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

GENERATION = re.compile(r"([0-9a-f]{64})(?:-[0-9a-f]{32})?")
INPUT_ROOTS = ("core", "adapters")


def source_files(root: Path) -> list[Path]:
    paths = [root / "install.sh"]
    for name in INPUT_ROOTS:
        tree = root / name
        if tree.is_symlink() or not tree.is_dir():
            raise ValueError(f"invalid installation input: {tree}")
        for directory, dirs, files in os.walk(tree):
            base = Path(directory)
            dirs[:] = [name for name in dirs if name != "__pycache__"]
            if any((base / name).is_symlink() for name in dirs):
                raise ValueError(f"linked installation directory: {base}")
            paths.extend(base / name for name in files if not name.endswith((".pyc", ".pyo")) and name != ".DS_Store")

    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"invalid installation input: {path}")
    return sorted(paths)


def identity(root: Path) -> str:
    entries = [
        (path.relative_to(root).as_posix(), path.stat().st_mode & 0o111, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in source_files(root)
    ]
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()


def location(home: Path) -> Path:
    base = home / "runtime-install-baseline"
    for path in (base, base / "generations", base / "active"):
        if path.is_symlink():
            raise ValueError(f"linked runtime baseline path: {path}")
    return base


def resolve(base: Path) -> tuple[Path, Path | None]:
    active = base / "active"
    if not active.is_file():
        raise ValueError("no published runtime baseline")
    lines = active.read_text(encoding="utf-8").splitlines()
    if not 1 <= len(lines) <= 2:
        raise ValueError("invalid runtime baseline receipt")
    name = lines[0]
    match = GENERATION.fullmatch(name)
    if not match:
        raise ValueError("invalid runtime baseline pointer")
    tree = base / "generations" / name
    if tree.is_symlink() or not tree.is_dir() or identity(tree) != match[1]:
        raise ValueError("runtime baseline source is missing or modified")
    return tree, managed_cli_path(lines[1]) if len(lines) == 2 else None


def managed_cli_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.name != "crew" or ".." in path.parts or len(value.splitlines()) != 1:
        raise ValueError("invalid managed PATH CLI in runtime baseline receipt")
    return path


def verify_projection(source: Path, home: Path, host: str, path_cli: Path | None) -> None:
    argv = [
        sys.executable, str(source / "core/scripts/verify-install-drift.py"),
        "--source-root", str(source), "--agent-crew-home", str(home),
        "--profile", "runtime-readonly", "--active-host", host,
    ]
    argv.extend(["--managed-path-cli", str(path_cli)] if path_cli else ["--skip-path-bin"])
    if subprocess.run(argv, check=False).returncode != 0:
        raise ValueError("cannot publish a baseline that differs from the installed runtime")


def publish(base: Path, home: Path, source: Path, digest: str, host: str, path_cli: Path | None) -> None:
    if identity(source) != digest:
        raise ValueError("installation inputs changed before baseline publication")

    try:
        current, previous_cli = resolve(base)
    except (OSError, ValueError):
        current, previous_cli = None, None
    path_cli = path_cli or previous_cli

    if current and GENERATION.fullmatch(current.name)[1] == digest:
        verify_projection(current, home, host, path_cli)
        if previous_cli == path_cli:
            return
        generation = current
    else:
        generations = base / "generations"
        generations.mkdir(mode=0o700, exist_ok=True, parents=True)
        with tempfile.TemporaryDirectory(prefix=".stage-", dir=generations) as temp:
            stage = Path(temp) / "source"
            for item in source_files(source):
                target = stage / item.relative_to(source)
                target.parent.mkdir(exist_ok=True, parents=True)
                shutil.copy2(item, target)

            validator = runpy.run_path(str(stage / "core/scripts/verify-install-drift.py"))["source_identity"]
            if identity(stage) != digest or not validator(stage)["valid"]:
                raise ValueError("cannot publish incomplete or changing installation inputs")
            verify_projection(stage, home, host, path_cli)
            generation = generations / f"{digest}-{uuid.uuid4().hex}"
            stage.rename(generation)

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=base, delete=False) as stream:
        pending = Path(stream.name)
        stream.write(generation.name + "\n")
        if path_cli:
            stream.write(str(path_cli) + "\n")
    try:
        os.replace(pending, base / "active")
    finally:
        pending.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fingerprint", "publish", "resolve"))
    parser.add_argument("--home", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--expected-digest")
    parser.add_argument("--active-host", choices=("none", "codex", "claude", "generic"), default="none")
    parser.add_argument("--managed-path-cli")
    parser.add_argument("--with-path-cli", action="store_true")
    args = parser.parse_args()

    try:
        if args.action == "fingerprint":
            if args.source is None:
                parser.error("fingerprint requires --source")
            print(identity(args.source.resolve()))
            return 0
        if args.home is None:
            parser.error("publish and resolve require --home")
        home = args.home.resolve()
        base = location(home)
        if args.action == "publish":
            if args.source is None or not args.expected_digest:
                parser.error("publish requires --source and --expected-digest")
            path = managed_cli_path(args.managed_path_cli) if args.managed_path_cli else None
            publish(base, home, args.source.resolve(), args.expected_digest, args.active_host, path)
        else:
            source, path = resolve(base)
            print(source)
            if args.with_path_cli and path:
                print(path)
    except (OSError, ValueError) as error:
        print(f"crew: {error}; use crew update to establish a verified runtime baseline", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
