#!/usr/bin/env python3
"""
check-verification-evidence.py — Validate the implementer self-verification line.

Purpose:
  Validate that an implementer's completion return block contains a
  well-formed `VERIFIED:` line per `core/rules/self-verification.md`.

  Shape grammar:
      VERIFIED: tests=<RESULT> cmd=<CMD> exit=<CODE>

      <RESULT> = <N>/<M>                (two non-negative integers, N <= M)
              | skipped:<reason>        (non-empty reason)
      <CMD>    = non-empty string (whitespace OK in the middle, never empty)
      <CODE>   = integer (parseable by int())

Inputs:
  - No argument            : read text from stdin.
  - --report PATH          : validate the file at PATH.
  - --require-passed       : additionally require N == M when RESULT is N/M
                             (full pass enforcement).

Outputs (stdout):
  exit 0 + "PASS: <reason>"   — valid VERIFIED line.
  exit 1 + "FAIL: <reason>"   — missing, malformed, or value-invalid line,
                                or --require-passed mode rejected a partial pass.
  exit 2 + "ERROR: <reason>"  — unreadable --report path, IO error.

The script depends only on the Python 3 stdlib — no pytest, no yaml,
no host-specific module. It must run on Codex / generic Python 3 hosts
identically.
"""

from __future__ import annotations

import argparse
import re
import sys


# --------------------------------------------------------------------------- #
# Grammar                                                                     #
# --------------------------------------------------------------------------- #
#
# The VERIFIED line is parsed in two passes:
#   1. Locate the line in the input (first line starting with "VERIFIED:").
#   2. Field-by-field validation: tests=, cmd=, exit= must all appear in
#      that order, separated by whitespace. Each field's value is validated
#      against its own micro-grammar.
#
# Two-pass parsing makes it possible to distinguish "missing field" from
# "malformed value", which the test contract requires.

VERIFIED_PREFIX = "VERIFIED:"

# Top-level structural regex — captures the three field bodies but
# does NOT validate them. Field-value validation lives in dedicated
# helpers so error messages can be specific.
_STRUCTURE_RE = re.compile(
    r"^VERIFIED:\s+"
    r"tests=(?P<tests>\S+)\s+"
    r"cmd=(?P<cmd>.*?)\s+"
    r"exit=(?P<exit>\S+)\s*$"
)


# --------------------------------------------------------------------------- #
# Validation primitives                                                       #
# --------------------------------------------------------------------------- #

def _validate_tests(value):
    """Return (ok, n_passed, n_total, is_skipped, error)."""
    if value.startswith("skipped:"):
        reason = value[len("skipped:"):]
        if not reason:
            return False, None, None, True, "empty skip reason"
        return True, None, None, True, None

    # N/M form
    if "/" not in value:
        return False, None, None, False, f"tests value missing '/': {value!r}"
    left, _, right = value.partition("/")
    if not left.isdigit() or not right.isdigit():
        return False, None, None, False, (
            f"tests N/M must be non-negative integers: {value!r}"
        )
    n, m = int(left), int(right)
    if n > m:
        return False, n, m, False, (
            f"passed ({n}) cannot exceed total ({m})"
        )
    return True, n, m, False, None


def _validate_cmd(value):
    """Cmd is the verbatim shell command. Must be non-empty (no whitespace-only)."""
    if value is None or value.strip() == "":
        return False, "cmd value is empty"
    return True, None


def _validate_exit(value):
    """Exit must parse as a Python int."""
    try:
        int(value)
        return True, None
    except (TypeError, ValueError):
        return False, f"exit value must be an integer: {value!r}"


# --------------------------------------------------------------------------- #
# Top-level validation                                                        #
# --------------------------------------------------------------------------- #

def _find_verified_line(text):
    """Return the first VERIFIED: line in text, or None.

    A two-pass design: locate the line by prefix, then run the strict
    field regex against it so we can distinguish missing-line from
    malformed-line.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(VERIFIED_PREFIX):
            return stripped
    return None


def validate(text, require_passed=False):
    """Validate the VERIFIED line in `text`.

    Returns (status, reason) where status is one of
    'pass' / 'fail' and reason is a human-readable string suitable
    for "PASS: <reason>" / "FAIL: <reason>" output.
    """
    line = _find_verified_line(text)

    if line is None:
        return "fail", "no VERIFIED line in input"

    match = _STRUCTURE_RE.match(line)
    if not match:
        return "fail", f"VERIFIED line is malformed: {line!r}"

    tests_value = match.group("tests")
    cmd_value = match.group("cmd")
    exit_value = match.group("exit")

    ok, n_passed, n_total, is_skipped, err = _validate_tests(tests_value)
    if not ok:
        return "fail", err

    ok, err = _validate_cmd(cmd_value)
    if not ok:
        return "fail", err

    ok, err = _validate_exit(exit_value)
    if not ok:
        return "fail", err

    if require_passed and not is_skipped:
        if n_passed != n_total:
            return "fail", (
                f"not all tests passed: {n_passed}/{n_total} "
                f"(require-passed mode)"
            )

    if is_skipped:
        return "pass", "VERIFIED line is well-formed (skipped form)"

    return "pass", f"VERIFIED line is well-formed ({n_passed}/{n_total})"


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def _read_text(args):
    """Resolve the input text. Returns (status, text_or_error).

    status is one of:
      - 'ok'    — text is the input
      - 'error' — text is the error reason (exit 2)
    """
    if args.report is not None:
        try:
            with open(args.report, "r", encoding="utf-8") as fh:
                return "ok", fh.read()
        except FileNotFoundError:
            return "error", f"--report path does not exist: {args.report}"
        except OSError as exc:
            return "error", f"cannot read --report {args.report}: {exc}"

    return "ok", sys.stdin.read()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate the implementer self-verification VERIFIED line "
            "(core/rules/self-verification.md)."
        ),
        prog="check-verification-evidence.py",
    )
    parser.add_argument(
        "--report",
        help="path to a completion-report file to validate "
             "(if omitted, read from stdin)",
    )
    parser.add_argument(
        "--require-passed",
        action="store_true",
        help="when RESULT is N/M, additionally require N == M",
    )
    args = parser.parse_args(argv)

    status, payload = _read_text(args)
    if status == "error":
        print(f"ERROR: {payload}")
        return 2

    result, reason = validate(payload, require_passed=args.require_passed)
    if result == "pass":
        print(f"PASS: {reason}")
        return 0

    print(f"FAIL: {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
