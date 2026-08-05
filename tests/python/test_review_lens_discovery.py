from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_SCRIPT = REPO_ROOT / "core" / "scripts" / "review-lens-discovery.py"
DISCOVERY_RULE = REPO_ROOT / "core" / "rules" / "review-lens-discovery.md"
REVIEW_SYNTHESIS_COMMAND = REPO_ROOT / "core" / "user" / "commands" / "review-synthesis.md"


def write_lens(
    path: Path,
    *,
    name: str,
    provider: str = "agent-crew",
    surface: str = "command",
    read_only: bool = True,
    mutates: bool = False,
    default_enabled: bool = True,
    mr: str = "none",
    remote_read: str = "none",
    supervisor_context: bool = False,
    duplicate_group: str = "",
) -> None:
    duplicate_line = f"duplicate_group: {duplicate_group}\n" if duplicate_group else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
name: {name}
kind: review-lens
loaded_by: review-synthesis
lens_id: {name}
provider: {provider}
surface: {surface}
read_only: {str(read_only).lower()}
mutates: {str(mutates).lower()}
default_enabled: {str(default_enabled).lower()}
requires_mr: {mr}
requires_remote_read: {remote_read}
requires_supervisor_context: {str(supervisor_context).lower()}
timeout_seconds: 60
{duplicate_line}---

# {name}

Fixture review lens.
""",
        encoding="utf-8",
    )


def run_discovery(
    root: Path,
    *,
    task: str = "review current changes",
    mr_id: str = "",
    parity_scope: str = "",
) -> dict:
    args = [
        "python3",
        str(DISCOVERY_SCRIPT),
        "--root",
        str(root),
        "--task",
        task,
        "--format",
        "json",
    ]
    if mr_id:
        args.extend(["--mr-id", mr_id])
    if parity_scope:
        args.extend(["--parity-scope", parity_scope])

    result = subprocess.run(args, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def lens_by_id(payload: dict, lens_id: str) -> dict:
    for lens in payload["lenses"]:
        if lens["lens_id"] == lens_id:
            return lens
    raise AssertionError(f"missing lens {lens_id}: {payload}")


def test_review_lens_discovery_script_and_rule_are_shipped() -> None:
    assert DISCOVERY_SCRIPT.is_file()
    assert DISCOVERY_RULE.is_file()
    assert REVIEW_SYNTHESIS_COMMAND.is_file()
    assert "`eligible`" in DISCOVERY_RULE.read_text(encoding="utf-8")
    assert "`eligible`" in REVIEW_SYNTHESIS_COMMAND.read_text(encoding="utf-8")


def test_discovery_completes_read_only_lens_and_blocks_supervisor_reviewer(
    tmp_path: Path,
) -> None:
    write_lens(tmp_path / "commands" / "review.md", name="generic-review")
    write_lens(
        tmp_path / "agents" / "reviewer.md",
        name="system-reviewer",
        surface="agent",
        supervisor_context=True,
        duplicate_group="final-reviewer",
    )

    payload = run_discovery(tmp_path)

    assert lens_by_id(payload, "generic-review")["status"] == "eligible"
    reviewer = lens_by_id(payload, "system-reviewer")
    assert reviewer["status"] == "blocked"
    assert reviewer["reason"] == "supervisor_context_required"


def test_mutating_lens_is_not_run_by_default(tmp_path: Path) -> None:
    write_lens(
        tmp_path / "commands" / "mr-review-note.md",
        name="mr-review-note",
        mutates=True,
        read_only=False,
    )

    lens = lens_by_id(run_discovery(tmp_path), "mr-review-note")

    assert lens["status"] == "blocked"
    assert lens["reason"] == "mutation_not_allowed"


def test_mr_and_parity_lenses_report_missing_scope_without_completion(
    tmp_path: Path,
) -> None:
    write_lens(
        tmp_path / "commands" / "mr-review-rate.md",
        name="mr-review-rate",
        mr="required",
        remote_read="optional",
    )
    write_lens(
        tmp_path / "commands" / "parity-check.md",
        name="parity-check",
        duplicate_group="parity",
    )

    payload = run_discovery(tmp_path, task="review current branch")

    assert lens_by_id(payload, "mr-review-rate")["status"] == "not-run"
    assert lens_by_id(payload, "mr-review-rate")["reason"] == "mr_context_unavailable"
    assert lens_by_id(payload, "parity-check")["status"] == "suggested"
    assert lens_by_id(payload, "parity-check")["reason"] == "parity_scope_missing"


def test_duplicate_lenses_suppress_lower_priority_candidate(tmp_path: Path) -> None:
    write_lens(
        tmp_path / "commands" / "review.md",
        name="generic-review",
        provider="agent-crew",
        duplicate_group="generic-review",
    )
    write_lens(
        tmp_path / "codex" / "skills" / "review" / "SKILL.md",
        name="codex-review-wrapper",
        provider="codex",
        surface="skill",
        duplicate_group="generic-review",
    )

    payload = run_discovery(tmp_path)

    assert lens_by_id(payload, "generic-review")["status"] == "eligible"
    suppressed = lens_by_id(payload, "codex-review-wrapper")
    assert suppressed["status"] == "duplicate-suppressed"
    assert suppressed["reason"] == "duplicate_group_represented"
