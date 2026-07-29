#!/usr/bin/env python3
"""Delegate memory GC to the configured Mnemos provider.

Agent Crew no longer owns provider-internal retention, scoring, or index
eviction, and it does not read provider FTS indexes. This shim remains only for
installed-asset compatibility and forwards arguments to `mnemos gc` through the
configured binary.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def mnemos_binary() -> str | None:
    configured = os.environ.get("MNEMOS_BIN")
    if configured:
        return configured

    default = Path.home() / ".local" / "bin" / "mnemos"
    if default.is_file() and os.access(default, os.X_OK):
        return str(default)

    return shutil.which("mnemos")


def parse_args(argv: list[str]) -> list[str]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    known, unknown = parser.parse_known_args(argv)

    if unknown:
        parser.error("unrecognized arguments: " + " ".join(unknown))
    if known.apply and known.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")

    provider_args = ["gc", "--format", known.format]
    if known.apply:
        provider_args.append("--apply")
    if known.dry_run:
        provider_args.append("--dry-run")
    return provider_args


def main(argv: list[str] | None = None) -> int:
    provider_args = parse_args(sys.argv[1:] if argv is None else argv)
    binary = mnemos_binary()
    if not binary:
        print("[memory] no backend installed - skipping memory gc", file=sys.stderr)
        return 0

    completed = subprocess.run([binary, *provider_args], check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
