"""Start coverage.py inside child Python processes during coverage tests."""
from __future__ import annotations

import os


if os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage
    except ModuleNotFoundError:
        coverage = None

    if coverage is not None:
        coverage.process_startup()
