"""Focused Python coverage for auto-issue-reporter.py edge cases."""

from __future__ import annotations

import argparse
import io
import importlib.util
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "auto-issue-reporter.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reporter = _load_module(SCRIPT, "auto_issue_reporter")


def _signal(summary: str = "agent-crew failed with traceback"):
    return reporter.Signal(
        source="UserPromptSubmit",
        summary=summary,
        evidence=summary,
        classification="user_reported_error",
    )


def _base_record(fingerprint: str = "abc123") -> dict:
    return {
        "fingerprint": fingerprint,
        "repo": "woogiekim/agent-crew",
        "source": "UserPromptSubmit",
        "classification": "user_reported_error",
        "title": "title",
        "reported_at_epoch": time.time(),
    }


def test_state_dir_defaults_to_home_reports(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AGENT_CREW_REPORT_STATE_DIR", raising=False)
    monkeypatch.delenv("AGENT_CREW_AUTO_ISSUE_STATE_DIR", raising=False)
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))

    assert reporter.state_dir() == tmp_path / "home" / "state" / "reports"


def test_state_dir_uses_auto_issue_override(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AGENT_CREW_REPORT_STATE_DIR", raising=False)
    monkeypatch.setenv("AGENT_CREW_AUTO_ISSUE_STATE_DIR", str(tmp_path / "reports"))

    assert reporter.state_dir() == tmp_path / "reports"


def test_payload_and_text_helpers_cover_fallbacks():
    assert reporter.load_payload("{bad json") == {}
    assert reporter.flatten_strings(["x" * 12000, "ignored"]) == ["x" * 12000]
    assert reporter.flatten_strings({"b": [1, True], "a": {"nested": "text"}}) == [
        "text",
        "1",
        "True",
    ]
    assert reporter.compact_text("x" * 4100).endswith("[truncated by auto reporter]")
    assert reporter.first_line("\n\n") == "agent-crew bug/error signal"


def test_signal_detection_infrastructure_bash_and_ignored():
    assert reporter.has_infrastructure_failure_signal("STATUS: blocked\nBLOCKER: host_bridge")
    assert reporter.is_normal_host_bridge_blocker("Host AI bridge has not completed this handoff")

    supervisor = reporter.detect_signal({
        "source": "supervisor_blocked",
        "status": "blocked",
        "blocker": "host_bridge missing",
        "detail": ["agent-crew host bridge failure"],
    })
    assert supervisor is not None
    assert supervisor.classification == "infrastructure_blocker"

    bash = reporter.detect_signal({
        "tool_name": "Bash",
        "tool_input": {"cmd": "crew run task"},
        "stderr": "Traceback: failed",
    })
    assert bash is not None
    assert bash.source == "PostToolUse:Bash"
    assert bash.classification == "crew_command_failure"

    assert reporter.detect_signal({"prompt": "ordinary text"}) is None


def test_title_truncates_and_unknown_backend_is_returned():
    title = reporter.issue_title(_signal("agent-crew " + ("x" * 120)))

    assert title.endswith("...")
    assert len(title) <= len("[auto-report] agent-crew error: ") + 82
    assert reporter.publish_backend("custom-backend") == "custom-backend"


def test_duplicate_record_ignores_expired_or_unknown_status(tmp_path: Path):
    path = tmp_path / "reported" / "abc.json"
    reporter.write_json(path, {"status": "recorded", "reported_at_epoch": 1})
    assert reporter.duplicate_record(path, ttl_seconds=1) is None

    reporter.write_json(path, {"status": "other", "reported_at_epoch": time.time()})
    assert reporter.duplicate_record(path, ttl_seconds=1000) is None


def test_duplicate_record_returns_recent_known_status(tmp_path: Path):
    path = tmp_path / "reported" / "abc.json"
    reporter.write_json(path, {"status": "recorded", "reported_at_epoch": time.time(), "url": ""})

    assert reporter.duplicate_record(path, ttl_seconds=1000)["status"] == "recorded"


def test_remove_outbox_ignores_missing_file(tmp_path: Path):
    reporter.remove_outbox(tmp_path, "missing")


def test_publish_backend_reads_environment_in_order(monkeypatch):
    monkeypatch.setenv("AGENT_CREW_REPORT_PUBLISH", "github")
    monkeypatch.setenv("AGENT_CREW_AUTO_ISSUE_PUBLISH", "none")
    assert reporter.publish_backend() == "github"

    monkeypatch.delenv("AGENT_CREW_REPORT_PUBLISH")
    assert reporter.publish_backend() == "none"

    monkeypatch.delenv("AGENT_CREW_AUTO_ISSUE_PUBLISH")
    assert reporter.publish_backend() == "none"


def test_gh_and_remote_duplicate_failure_paths(monkeypatch):
    def raise_run(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(reporter.subprocess, "run", raise_run)
    rc, stdout, stderr = reporter.gh_json(["issue", "list"], timeout=1)
    assert rc == 127
    assert stdout == ""
    assert "boom" in stderr

    monkeypatch.setattr(reporter, "gh_json", lambda *_args, **_kwargs: (1, "", "bad"))
    assert reporter.remote_duplicate("repo/name", "abc", timeout=1) is None

    monkeypatch.setattr(reporter, "gh_json", lambda *_args, **_kwargs: (0, "{bad", ""))
    assert reporter.remote_duplicate("repo/name", "abc", timeout=1) is None

    monkeypatch.setattr(reporter, "gh_json", lambda *_args, **_kwargs: (0, '[{"url": "https://example.test/1"}]', ""))
    assert reporter.remote_duplicate("repo/name", "abc", timeout=1) == "https://example.test/1"

    monkeypatch.setattr(reporter, "gh_json", lambda *_args, **_kwargs: (0, "[]", ""))
    assert reporter.remote_duplicate("repo/name", "abc", timeout=1) is None


def test_gh_json_success_strips_output(monkeypatch):
    class Proc:
        returncode = 5
        stdout = " out \n"
        stderr = " err \n"

    monkeypatch.setattr(reporter.subprocess, "run", lambda *_args, **_kwargs: Proc())

    assert reporter.gh_json(["issue", "list"], timeout=1) == (5, "out", "err")


def test_create_issue_failure_uses_stderr(monkeypatch):
    monkeypatch.setattr(reporter, "gh_json", lambda *_args, **_kwargs: (1, "", "not authorized"))

    assert reporter.create_issue("repo/name", "title", "body", timeout=1) == ("failed", "not authorized")


def test_create_issue_success_strips_url(monkeypatch):
    monkeypatch.setattr(reporter, "gh_json", lambda *_args, **_kwargs: (0, "https://example.test/1\n", ""))

    assert reporter.create_issue("repo/name", "title", "body", timeout=1) == (
        "created",
        "https://example.test/1",
    )


def test_publish_github_queues_when_gh_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(reporter.shutil, "which", lambda _name: None)
    record_path = tmp_path / "reported" / "abc123.json"

    result = reporter.publish_github(
        tmp_path,
        record_path,
        _base_record(),
        "title",
        "body",
        timeout=1,
    )

    assert result["status"] == "queued_missing_gh"
    assert (tmp_path / "queued" / "abc123.md").is_file()
    assert json.loads(record_path.read_text())["status"] == "queued_missing_gh"


def test_publish_github_remote_duplicate_removes_outbox(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(reporter.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(reporter, "remote_duplicate", lambda *_args, **_kwargs: "https://example.test/1")
    fingerprint = "abc123"
    outbox_path = tmp_path / "outbox" / f"{fingerprint}.json"
    outbox_path.parent.mkdir(parents=True)
    outbox_path.write_text("{}", encoding="utf-8")

    result = reporter.publish_github(
        tmp_path,
        tmp_path / "reported" / f"{fingerprint}.json",
        _base_record(fingerprint),
        "title",
        "body",
        timeout=1,
    )

    assert result["status"] == "remote_duplicate"
    assert not outbox_path.exists()


def test_publish_github_created_removes_outbox(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(reporter.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(reporter, "remote_duplicate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(reporter, "create_issue", lambda *_args, **_kwargs: ("created", "https://example.test/2"))
    fingerprint = "created123"
    outbox_path = tmp_path / "outbox" / f"{fingerprint}.json"
    outbox_path.parent.mkdir(parents=True)
    outbox_path.write_text("{}", encoding="utf-8")

    result = reporter.publish_github(
        tmp_path,
        tmp_path / "reported" / f"{fingerprint}.json",
        _base_record(fingerprint),
        "title",
        "body",
        timeout=1,
    )

    assert result["status"] == "created"
    assert result["url"] == "https://example.test/2"
    assert not outbox_path.exists()


def test_emit_text_prints_non_ignored_status(capsys):
    reporter.emit({"status": "recorded"}, "text")
    reporter.emit({"status": "ignored"}, "text")

    assert capsys.readouterr().out == "recorded\n"


def test_handle_auto_disabled_and_unsupported_backend(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_CREW_AUTO_ISSUE_REPORT_DISABLED", "1")
    assert reporter.handle_auto("{}") == {"status": "disabled"}

    monkeypatch.setenv("AGENT_CREW_AUTO_ISSUE_REPORT_DISABLED", "0")
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(tmp_path))
    payload = json.dumps({"prompt": "agent-crew error traceback"})
    result = reporter.handle_auto(payload, backend="custom-backend")

    assert result["status"] == "unsupported_backend"
    assert result["backend"] == "custom-backend"


def test_handle_auto_ignored_duplicate_dry_run_recorded_and_github(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(tmp_path / "ignored"))
    assert reporter.handle_auto("{}") == {"status": "ignored"}

    payload = json.dumps({"prompt": "agent-crew error traceback"})
    signal = reporter.detect_signal(reporter.load_payload(payload))
    fingerprint = reporter.fingerprint_for(signal)

    duplicate_root = tmp_path / "duplicate"
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(duplicate_root))
    reporter.write_json(
        duplicate_root / "reported" / f"{fingerprint}.json",
        {"status": "recorded", "reported_at_epoch": time.time(), "url": ""},
    )
    assert reporter.handle_auto(payload)["status"] == "skipped_duplicate"

    dry_root = tmp_path / "dry"
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(dry_root))
    monkeypatch.setenv("AGENT_CREW_AUTO_ISSUE_DRY_RUN", "1")
    assert reporter.handle_auto(payload)["status"] == "dry_run"

    monkeypatch.setenv("AGENT_CREW_AUTO_ISSUE_DRY_RUN", "0")
    recorded_root = tmp_path / "recorded"
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(recorded_root))
    assert reporter.handle_auto(payload, backend="none")["status"] == "recorded"

    github_root = tmp_path / "github"
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(github_root))
    monkeypatch.setattr(reporter, "publish_github", lambda *_args, **_kwargs: {"status": "created"})
    assert reporter.handle_auto(payload, backend="github")["status"] == "created"


def test_handle_publish_unsupported_empty_invalid_queued_and_failed(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(tmp_path))
    assert reporter.handle_publish("none") == {"status": "unsupported_backend", "backend": "none"}
    assert reporter.handle_publish("github")["status"] == "empty"

    outbox = tmp_path / "outbox"
    outbox.mkdir(parents=True)
    (outbox / "invalid.json").write_text("{bad json", encoding="utf-8")
    (outbox / "queued.json").write_text(json.dumps({
        "fingerprint": "queued",
        "title": "queued",
        "body": "body",
        "repo": "repo/name",
    }), encoding="utf-8")
    (outbox / "failed.json").write_text(json.dumps({
        "fingerprint": "failed",
        "title": "failed",
        "body": "body",
        "repo": "repo/name",
    }), encoding="utf-8")
    (outbox / "created.json").write_text(json.dumps({
        "fingerprint": "created",
        "title": "created",
        "body": "body",
        "repo": "repo/name",
    }), encoding="utf-8")

    def fake_publish(_root, _record_path, base_record, _title, _body, _timeout):
        if base_record["fingerprint"] == "queued":
            return {"status": "queued_missing_gh"}
        if base_record["fingerprint"] == "created":
            return {"status": "created", "url": "https://example.test/3"}
        return {"status": "failed"}

    monkeypatch.setattr(reporter, "publish_github", fake_publish)
    result = reporter.handle_publish("github")

    assert result["status"] == "partial"
    assert result["published"] == 1
    assert result["queued"] == 1
    assert result["failed"] == 2
    assert {"path": str(outbox / "invalid.json"), "status": "invalid"} in result["reports"]


def test_parse_args_defaults_and_publish(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["auto-issue-reporter.py", "--format", "json"])
    args = reporter.parse_args()
    assert args.command == "auto"
    assert args.format == "json"

    monkeypatch.setattr(sys, "argv", ["auto-issue-reporter.py", "publish", "--format", "text"])
    args = reporter.parse_args()
    assert args.command == "publish"
    assert args.format == "text"


def test_main_auto_and_publish_commands(monkeypatch, capsys):
    monkeypatch.setattr(
        reporter,
        "parse_args",
        lambda: argparse.Namespace(command="auto", payload="-", publish=None, format="json"),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setattr(reporter, "handle_auto", lambda raw, backend=None: {"status": "ignored", "raw": raw})
    assert reporter.main() == 0
    assert json.loads(capsys.readouterr().out)["raw"] == "{}"

    monkeypatch.setattr(
        reporter,
        "parse_args",
        lambda: argparse.Namespace(command="publish", backend="github", format="json"),
    )
    monkeypatch.setattr(reporter, "handle_publish", lambda backend=None: {"status": "empty", "backend": backend})
    assert reporter.main() == 0
    assert json.loads(capsys.readouterr().out)["backend"] == "github"


def test_main_handles_unknown_command_and_exceptions(monkeypatch, capsys):
    monkeypatch.setattr(
        reporter,
        "parse_args",
        lambda: argparse.Namespace(command="other", format="json"),
    )
    assert reporter.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "failed"

    monkeypatch.setattr(
        reporter,
        "parse_args",
        lambda: argparse.Namespace(
            command="auto",
            payload="/path/does/not/exist",
            publish=None,
            format="json",
        ),
    )
    assert reporter.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "does/not/exist" in payload["detail"]
