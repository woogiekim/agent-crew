#!/usr/bin/env python3
"""CLI wrapper around ``quality_loop_lib.auto_record_minor_findings``.

Used by the reviewer's Step 4.5 MINOR auto-promotion flow when the entire
review's findings are MINOR severity. The wrapper exists so any host
(Claude, Codex, generic) can invoke a single, provider-neutral entry point
to upsert MINOR findings into ``finding-register.json`` with
``status: deferred-minor`` before emitting ``REVIEW: APPROVED``.

Two equivalent input shapes are accepted so reviewers can pick the call
form that fits their host best:

1. **Combined stdin payload** (no CLI flags required) — the wrapper reads a
   single JSON object from stdin carrying both the register path and the
   findings list:

   ```json
   {
     "register_path": "/path/to/finding-register.json",
     "findings": [
       {"id": "F-101", "title": "...", "affected": [...], "recommended_fix": "..."}
     ]
   }
   ```

2. **Flag-based shape** with the findings list on stdin (or in a file):

   ```bash
   python3 auto-record-minor-findings.py --register "${REGISTER}" --findings - <<'JSON'
   [
     {"id": "F-101", "title": "...", "affected": [...], "recommended_fix": "..."}
   ]
   JSON
   ```

The script forces ``status="deferred-minor"`` and ``severity="P3"`` on every
upserted entry and writes the updated register back to disk. Existing entries
matched by ``id`` are updated in place; unknown ids are appended.

Exit code 0 on success; non-zero on argument or I/O errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_lib():
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import quality_loop_lib  # noqa: WPS433 — local import is intentional

    return quality_loop_lib


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Upsert MINOR findings into finding-register.json with "
            "status=deferred-minor severity=P3."
        ),
    )
    parser.add_argument(
        "--register",
        default=None,
        help=(
            "Path to finding-register.json (created if missing). When omitted, "
            "the wrapper expects a JSON object on stdin containing both "
            "'register_path' and 'findings'."
        ),
    )
    parser.add_argument(
        "--findings",
        default=None,
        help=(
            "Path to a JSON file with a list of MINOR findings, or '-' to "
            "read JSON from stdin. When omitted, the wrapper reads the "
            "combined stdin payload described above."
        ),
    )
    return parser.parse_args(argv)


def _extract_findings(payload) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("findings"), list):
        return [item for item in payload["findings"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(
        "findings input must be a JSON list or an object with a 'findings' list"
    )


def _resolve_inputs(args: argparse.Namespace) -> tuple[Path, list[dict]]:
    # Combined stdin shape: no flags → read the whole payload from stdin.
    if args.register is None and args.findings is None:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError(
                "stdin payload must be a JSON object with 'register_path' "
                "and 'findings' keys"
            )
        register_path = payload.get("register_path") or payload.get("register")
        if not register_path:
            raise ValueError("stdin payload missing 'register_path'")
        return Path(register_path), _extract_findings(payload)

    if args.register is None:
        raise ValueError(
            "--register is required when --findings is provided "
            "(or omit both and pass a combined JSON object on stdin)"
        )

    findings_source = args.findings or "-"
    if findings_source == "-":
        text = sys.stdin.read()
    else:
        text = Path(findings_source).read_text(encoding="utf-8")
    return Path(args.register), _extract_findings(json.loads(text))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    register_path, findings = _resolve_inputs(args)

    lib = _load_lib()
    updated = lib.auto_record_minor_findings(register_path, findings)

    json.dump({"register": str(register_path), "count": len(updated)}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
