#!/usr/bin/env python3
"""Publish a complete crew executable without changing its readers' file."""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path


def publish(source: Path, destination: Path) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise OSError(f"expected a regular CLI at {destination}")

    temporary = None
    try:
        with source.open("rb") as executable, tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as staged:
            temporary = Path(staged.name)
            shutil.copyfileobj(executable, staged)
            os.fchmod(staged.fileno(), 0o755)

        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        publish(args.source, args.destination)
    except OSError as error:
        print(f"publish-crew-cli: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
