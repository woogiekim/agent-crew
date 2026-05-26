from __future__ import annotations

import json


OPTIONS = json.dumps([
    {"label": "Approve", "description": "Proceed"},
    {"label": "Cancel", "description": "Stop"},
])


def test_question_key_is_stable(script_runner):
    first = script_runner(
        "interactive-question-state.py",
        "key",
        "--prompt", "Proceed with push?",
        "--options-json", OPTIONS,
    )
    second = script_runner(
        "interactive-question-state.py",
        "key",
        "--prompt", "Proceed   with   push?",
        "--options-json", OPTIONS,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout.strip() == second.stdout.strip()
    assert len(first.stdout.strip()) == 16


def test_record_and_resolve_task_scoped_choice(script_runner, task_dir):
    key = script_runner(
        "interactive-question-state.py",
        "key",
        "--prompt", "Proceed with push?",
        "--options-json", OPTIONS,
    ).stdout.strip()

    record = script_runner(
        "interactive-question-state.py",
        "record",
        "--task-dir", str(task_dir),
        "--question-id", key,
        "--prompt", "Proceed with push?",
        "--options-json", OPTIONS,
        "--chosen-label", "Approve",
        "--source", "codex_plan_mode",
        "--adapter", "codex",
    )
    assert record.returncode == 0, record.stderr
    payload = json.loads(record.stdout)
    assert payload["chosen_label"] == "Approve"
    assert payload["source"] == "codex_plan_mode"

    path = task_dir / "context" / "interactive-questions" / f"{key}.json"
    assert path.is_file()

    resolved = script_runner(
        "interactive-question-state.py",
        "resolve",
        "--task-dir", str(task_dir),
        "--question-id", key,
    )
    assert resolved.returncode == 0, resolved.stderr
    cached = json.loads(resolved.stdout)
    assert cached["found"] is True
    assert cached["chosen_label"] == "Approve"


def test_resolve_missing_choice_exits_nonzero(script_runner, task_dir):
    result = script_runner(
        "interactive-question-state.py",
        "resolve",
        "--task-dir", str(task_dir),
        "--question-id", "missing",
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["found"] is False


def test_record_rejects_unknown_choice(script_runner, task_dir):
    result = script_runner(
        "interactive-question-state.py",
        "record",
        "--task-dir", str(task_dir),
        "--question-id", "bad-choice",
        "--prompt", "Proceed with push?",
        "--options-json", OPTIONS,
        "--chosen-label", "Maybe",
    )

    assert result.returncode != 0
    assert "chosen label" in result.stderr


def test_render_markdown_fallback(script_runner):
    result = script_runner(
        "interactive-question-state.py",
        "render-markdown",
        "--prompt", "Proceed with push?",
        "--options-json", OPTIONS,
    )

    assert result.returncode == 0, result.stderr
    assert "Pick one" in result.stdout
    assert "1. **Approve**" in result.stdout
    assert "0. **cancel**" in result.stdout


def test_options_json_validation_errors_are_explicit(script_runner):
    cases = [
        ("{", "invalid options JSON"),
        ("[]", "non-empty list"),
        (json.dumps(["Approve"]), "option 0 must be an object"),
        (json.dumps([{"description": "Proceed"}]), "option 0 missing label"),
    ]

    for options, message in cases:
        result = script_runner(
            "interactive-question-state.py",
            "key",
            "--prompt", "Proceed with push?",
            "--options-json", options,
        )

        assert result.returncode != 0
        assert message in result.stderr


def test_record_and_resolve_state_scoped_cancelled_choice(script_runner, tmp_path):
    state_dir = tmp_path / "state"
    key = script_runner(
        "interactive-question-state.py",
        "key",
        "--prompt", "Proceed with push?",
        "--options-json", OPTIONS,
    ).stdout.strip()

    record = script_runner(
        "interactive-question-state.py",
        "record",
        "--state-dir", str(state_dir),
        "--question-id", key,
        "--prompt", "Proceed with push?",
        "--options-json", OPTIONS,
        "--chosen-label", "__cancelled__",
        "--source", "markdown",
        "--adapter", "codex",
    )
    assert record.returncode == 0, record.stderr
    assert json.loads(record.stdout)["cancelled"] is True

    resolved = script_runner(
        "interactive-question-state.py",
        "resolve",
        "--state-dir", str(state_dir),
        "--question-id", key,
    )

    assert resolved.returncode == 0, resolved.stderr
    assert json.loads(resolved.stdout)["chosen_label"] == "__cancelled__"


def test_record_requires_task_or_state_scope(script_runner):
    result = script_runner(
        "interactive-question-state.py",
        "record",
        "--question-id", "missing-scope",
        "--prompt", "Proceed with push?",
        "--options-json", OPTIONS,
        "--chosen-label", "Approve",
    )

    assert result.returncode != 0
    assert "--task-dir or --state-dir is required" in result.stderr
