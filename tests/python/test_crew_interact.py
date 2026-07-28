"""Focused coverage for crew sessions/interact UX."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNTIME = REPO_ROOT / "core" / "scripts" / "crew-runtime.py"
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load_module(RUNTIME, "crew_runtime_interact")


def _write_task(
    state_dir: Path,
    task_id: str,
    *,
    project: str,
    branch: str,
    task: str,
    mtime: int,
) -> None:
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "project_name": project,
                "branch": branch,
                "task": task,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text(f"STATUS: completed\nSUMMARY: {task}\n", encoding="utf-8")
    os.utime(task_dir / "register.json", (mtime, mtime))
    os.utime(task_dir / "result.md", (mtime, mtime))


def _session_home(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    state_dir = home / "state" / "agent-crew-abc"
    state_dir.mkdir(parents=True)
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    codex_home.mkdir()
    claude_home.mkdir()
    monkeypatch.setenv("AGENT_CREW_HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_HOME", str(claude_home))
    monkeypatch.setenv("AGENT_CREW_INTERACT_AOE_ENABLED", "0")
    return state_dir, codex_home, claude_home


def _write_codex_session(
    codex_home: Path,
    *,
    session_id: str,
    thread_name: str,
    updated_at: str,
    project: str = "unknown",
    branch: str = "unknown",
) -> None:
    index_path = codex_home / "session_index.jsonl"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "id": session_id,
                    "thread_name": thread_name,
                    "updated_at": updated_at,
                    "project": project,
                    "branch": branch,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _write_codex_rollout(
    codex_home: Path,
    *,
    session_id: str,
    cwd: Path,
    timestamp: str,
    mtime: int,
    last_message: str = "",
) -> Path:
    rollout_path = codex_home / "sessions" / "2026" / "07" / "25" / f"rollout-{session_id}.jsonl"
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "timestamp": timestamp,
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "session_id": session_id,
                "cwd": str(cwd),
                "originator": "codex-tui",
                "thread_source": "user",
            },
        },
        {
            "timestamp": timestamp,
            "type": "turn_context",
            "payload": {
                "cwd": str(cwd),
                "workspace_roots": [str(cwd)],
                "current_date": "2026-07-25",
                "model": "gpt-5.5",
            },
        },
    ]
    if last_message:
        rows.append(
            {
                "timestamp": timestamp,
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": last_message},
            }
        )
    rollout_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    os.utime(rollout_path, (mtime, mtime))
    return rollout_path


def _write_claude_session(
    claude_home: Path,
    *,
    session_id: str,
    cwd: Path,
    updated_at: int,
    branch: str = "main",
    name: str = "claude-session",
) -> None:
    sessions_dir = claude_home / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / f"{session_id}.json").write_text(
        json.dumps(
            {
                "sessionId": session_id,
                "cwd": str(cwd),
                "updatedAt": updated_at,
                "branch": branch,
                "status": "idle",
                "name": name,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_claude_project_log(claude_home: Path, *, cwd: Path, session_id: str, text: str) -> None:
    project_dir = claude_home / "projects" / str(cwd).replace("/", "-")
    project_dir.mkdir(parents=True)
    (project_dir / f"{session_id}.jsonl").write_text(
        json.dumps({"type": "user", "message": {"content": text}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


class _Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_aoe_run(calls: list[list[str]], *, list_stdout: str):
    def fake_run(argv, **kwargs):
        argv = list(argv)
        calls.append(argv)
        if argv[:2] == ["aoe", "list"]:
            return _Completed(stdout=list_stdout)
        if argv[:2] == ["aoe", "send"]:
            return _Completed(stdout=f"Sent message to '{argv[2]}'\n")
        return _Completed(returncode=127, stderr="unexpected command")

    return fake_run


def test_sessions_render_recommended_card_without_internal_ids(monkeypatch, tmp_path: Path, capsys):
    """success-case - sessions output hides ids and shows friendly card fields."""
    _, _, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    _write_claude_session(claude_home, session_id="claude-1", cwd=project, branch="main", updated_at=1000)
    _write_claude_project_log(claude_home, cwd=project, session_id="claude-1", text="relay 명령 구현 리뷰")

    assert runtime.command_sessions(argparse.Namespace(project_root=str(project), limit=10)) == 0

    out = capsys.readouterr().out
    assert "추천:" in out
    assert "① Claude · project · main" in out
    assert "relay 명령 구현 리뷰" in out
    assert "번호나 설명으로 선택하세요" in out
    assert "claude-1" not in out


def test_sessions_include_aoe_registered_ai_sessions(monkeypatch, tmp_path: Path, capsys):
    """success-case - AoE-registered sessions are usable session candidates."""
    _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    list_stdout = (
        "Profile: main\n\n"
        "TITLE                GROUP           PATH                                     ID\n"
        "--------------------------------------------------------------------------------------------\n"
        f"agent-crew claude    99. ETC         {project}      f59dec8ab2bd\n"
        f"agent-crew codex     99. ETC         {project}      525f6f52f1a7\n"
        "\nTotal: 2 sessions\n"
    )
    calls: list[list[str]] = []
    monkeypatch.setenv("AGENT_CREW_INTERACT_AOE_ENABLED", "1")
    monkeypatch.setattr(runtime.subprocess, "run", _fake_aoe_run(calls, list_stdout=list_stdout))

    assert runtime.command_sessions(argparse.Namespace(project_root=str(project), limit=10)) == 0

    out = capsys.readouterr().out
    assert "Claude · agent-crew · unknown" in out
    assert "Codex · agent-crew · unknown" in out
    assert "AoE registered session" in out
    assert "f59dec8ab2bd" not in out


def test_sessions_group_by_project_when_many_candidates(monkeypatch, tmp_path: Path, capsys):
    """success-case - many sessions are grouped by project while numbering stays global."""
    _, codex_home, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    contents = tmp_path / "contents-systsem"
    project.mkdir()
    contents.mkdir()
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1004)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 구현")
    _write_codex_session(
        codex_home,
        session_id="x1",
        thread_name="E2E 테스트",
        updated_at="1970-01-01T00:16:43Z",
        project="agent-crew",
        branch="feature-a",
    )
    _write_claude_session(claude_home, session_id="c2", cwd=contents, branch="feature-b", updated_at=1002)
    _write_claude_project_log(claude_home, cwd=contents, session_id="c2", text="계약 분석")
    _write_codex_session(
        codex_home,
        session_id="x2",
        thread_name="스코프 체크",
        updated_at="1970-01-01T00:16:41Z",
        project="contents-systsem",
        branch="feature-c",
    )

    assert runtime.command_sessions(argparse.Namespace(project_root=str(project), limit=10)) == 0

    out = capsys.readouterr().out
    assert "agent-crew" in out
    assert "contents-systsem" in out
    assert "② Codex · feature-a" in out
    assert "④ Codex · feature-c" in out


def test_interact_shows_candidates_for_natural_language_request(monkeypatch, tmp_path: Path, capsys):
    """success-case - interact uses natural language and asks the user to choose a session."""
    _, _, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1000)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 명령 구현 리뷰")

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="",
            limit=10,
            select="",
            send=False,
            copy=False,
            prompt=["방금", "relay", "변경사항", "클로드한테", "리뷰", "받아줘"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "전송할 AI 세션 후보를 찾았습니다." in out
    assert "요청:" in out
    assert "방금 relay 변경사항 클로드한테 리뷰 받아줘" in out
    assert "① Claude · agent-crew · main" in out
    assert "그대로 보낼까요? 아니면 번호를 선택하세요." in out


def test_interact_select_one_sends_to_recommended_candidate_by_default(monkeypatch, tmp_path: Path, capsys):
    """success-case - selecting 1 attempts delivery by default."""
    _, codex_home, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1002)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 리뷰")
    _write_codex_session(
        codex_home,
        session_id="x1",
        thread_name="E2E 테스트",
        updated_at="1970-01-01T00:16:41Z",
        project="agent-crew",
        branch="feature-a",
    )

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="",
            select="1",
            limit=10,
            send=True,
            copy=False,
            prompt=["리뷰", "부탁"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "선택한 세션:" in out
    assert "① Claude · agent-crew · main" in out
    assert "STATUS: packaged" in out
    assert "PROMPT:" in out
    assert "session c1" not in out


def test_interact_no_send_selects_without_delivery(monkeypatch, tmp_path: Path, capsys):
    """success-case - --no-send keeps explicit selection-only behavior."""
    _, codex_home, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1002)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 리뷰")
    _write_codex_session(
        codex_home,
        session_id="x1",
        thread_name="E2E 테스트",
        updated_at="1970-01-01T00:16:41Z",
        project="agent-crew",
        branch="feature-a",
    )

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="",
            select="1",
            limit=10,
            send=False,
            copy=False,
            prompt=["리뷰", "부탁"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "선택한 세션:" in out
    assert "① Claude · agent-crew · main" in out
    assert "STATUS: selected" in out
    assert "STATUS: packaged" not in out
    assert "PROMPT:" not in out
    assert "session c1" not in out


def test_interact_selected_aoe_session_sends_with_aoe_without_env_config(monkeypatch, tmp_path: Path, capsys):
    """success-case - selected AoE sessions are delivered through aoe send by default."""
    _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    list_stdout = (
        "Profile: main\n\n"
        "TITLE                GROUP           PATH                                     ID\n"
        "--------------------------------------------------------------------------------------------\n"
        f"agent-crew claude    99. ETC         {project}      f59dec8ab2bd\n"
        "\nTotal: 1 sessions\n"
    )
    calls: list[list[str]] = []
    monkeypatch.setenv("AGENT_CREW_INTERACT_AOE_ENABLED", "1")
    monkeypatch.setattr(runtime.subprocess, "run", _fake_aoe_run(calls, list_stdout=list_stdout))

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="aoe agent-crew claude",
            select="1",
            limit=10,
            send=True,
            copy=False,
            prompt=["hi"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "STATUS: sent" in out
    assert "DELIVERY:" in out
    assert "PROMPT:" not in out
    send_calls = [call for call in calls if call[:3] == ["aoe", "send", "agent-crew claude"]]
    assert len(send_calls) == 1
    assert "hi" in send_calls[0][3]


def test_interact_select_send_uses_delivery_adapter_success(monkeypatch, tmp_path: Path, capsys):
    """success-case - --send reports sent only when the delivery adapter succeeds."""
    _, _, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1002)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 리뷰")

    deliveries: list[dict] = []

    def fake_deliver(candidate: dict, package: dict) -> dict:
        deliveries.append({"candidate": candidate, "package": package})
        return {"status": "sent"}

    monkeypatch.setattr(runtime, "deliver_relay_to_session", fake_deliver)

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="",
            select="1",
            limit=10,
            send=True,
            copy=False,
            prompt=["리뷰", "부탁"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "STATUS: sent" in out
    assert "① Claude · agent-crew · main" in out
    assert "STATUS: packaged" not in out
    assert "copy_fallback" not in out
    assert len(deliveries) == 1
    assert "리뷰 부탁" in deliveries[0]["package"]["prompt"]
    assert "session c1" not in out


def test_interact_select_send_executes_configured_delivery_command(monkeypatch, tmp_path: Path, capsys):
    """success-case - configured delivery command is real execution evidence for STATUS: sent."""
    _, _, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    runner = tmp_path / "delivery-runner.py"
    runner.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "prompt = Path(sys.argv[1]).read_text(encoding='utf-8')\n"
        "Path(sys.argv[2]).write_text('executed:' + prompt, encoding='utf-8')\n"
        "print('delivery-ok')\n",
        encoding="utf-8",
    )
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1002)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 리뷰")
    monkeypatch.setenv(
        "AGENT_CREW_INTERACT_DELIVERY_COMMAND_CLAUDE",
        f"{sys.executable} {runner} {{prompt_file}} {{output_file}}",
    )

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="",
            select="1",
            limit=10,
            send=True,
            copy=False,
            prompt=["진짜", "실행"],
        )
    ) == 0

    out = capsys.readouterr().out
    delivery_line = next(line for line in out.splitlines() if line.startswith("DELIVERY: "))
    delivery_path = Path(delivery_line.removeprefix("DELIVERY: "))
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    output = Path(delivery["output_file"]).read_text(encoding="utf-8")

    assert "STATUS: sent" in out
    assert "STATUS: packaged" not in out
    assert delivery["returncode"] == 0
    assert delivery["stdout"].strip() == "delivery-ok"
    assert "진짜 실행" in output
    assert "PROMPT:" not in out


def test_interact_select_send_reports_failed_when_configured_delivery_fails(monkeypatch, tmp_path: Path, capsys):
    """failure-case - configured delivery command failure must not be reported as sent."""
    _, _, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    runner = tmp_path / "delivery-fail.py"
    runner.write_text("import sys\nprint('delivery-failed', file=sys.stderr)\nsys.exit(7)\n", encoding="utf-8")
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1002)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 리뷰")
    monkeypatch.setenv("AGENT_CREW_INTERACT_DELIVERY_COMMAND_CLAUDE", f"{sys.executable} {runner}")

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="",
            select="1",
            limit=10,
            send=True,
            copy=False,
            prompt=["실패", "검증"],
        )
    ) == 1

    out = capsys.readouterr().out
    delivery_line = next(line for line in out.splitlines() if line.startswith("DELIVERY: "))
    delivery_path = Path(delivery_line.removeprefix("DELIVERY: "))
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))

    assert "STATUS: failed" in out
    assert "STATUS: sent" not in out
    assert delivery["returncode"] == 7
    assert "delivery-failed" in delivery["stderr"]
    assert "PROMPT:" in out


def test_interact_select_send_packages_when_delivery_is_unsupported(monkeypatch, tmp_path: Path, capsys):
    """success-case - unsupported direct delivery creates a relay package without pretending it was sent."""
    _, _, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1002)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 리뷰")

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="",
            select="1",
            limit=10,
            send=True,
            copy=False,
            prompt=["리뷰", "부탁"],
        )
    ) == 0

    out = capsys.readouterr().out
    prompt_line = next(line for line in out.splitlines() if line.startswith("PROMPT: "))
    prompt_path = Path(prompt_line.removeprefix("PROMPT: "))
    prompt = prompt_path.read_text(encoding="utf-8")
    manifest = json.loads((prompt_path.parent / "manifest.json").read_text(encoding="utf-8"))

    assert "STATUS: packaged" in out
    assert "STATUS: sent" not in out
    assert "copy_fallback" not in out
    assert "COPY:" not in out
    assert "① Claude · agent-crew · main" in out
    assert "리뷰 부탁" in prompt
    assert manifest["target_host"] == "claude"
    assert manifest["auto_execute"] is False
    assert "session c1" not in out


def test_interact_select_send_copy_fallback_requires_explicit_copy(monkeypatch, tmp_path: Path, capsys):
    """success-case - clipboard fallback is available only when --copy is explicit."""
    _, _, claude_home = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1002)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 리뷰")
    monkeypatch.setattr(runtime, "copy_to_clipboard", lambda text: True)

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="",
            select="1",
            limit=10,
            send=True,
            copy=True,
            prompt=["리뷰", "부탁"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "STATUS: copy_fallback" in out
    assert "STATUS: packaged" not in out
    assert "STATUS: sent" not in out
    assert "COPY: copied" in out
    assert "session c1" not in out


def test_agent_crew_tasks_are_enrichment_not_session_candidates(monkeypatch, tmp_path: Path, capsys):
    """regression-case - agent-crew task state alone must not appear as an AI session."""
    state_dir, _, _ = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_task(state_dir, "t1", project="agent-crew", branch="main", task="agent-crew task only", mtime=1000)

    assert runtime.command_sessions(argparse.Namespace(project_root=str(project), limit=10)) == 0

    out = capsys.readouterr().out
    assert "최근 AI 세션을 찾지 못했습니다." in out
    assert "agent-crew task only" not in out


def test_interact_to_without_match_does_not_fall_back_to_all(monkeypatch, tmp_path: Path, capsys):
    """regression-case - --to filters strictly instead of showing unrelated sessions."""
    _, codex_home, _ = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_codex_session(
        codex_home,
        session_id="x1",
        thread_name="Codex 작업",
        updated_at="1970-01-01T00:16:41Z",
        project="agent-crew",
        branch="main",
    )

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="claude",
            select="",
            limit=10,
            send=False,
            copy=False,
            prompt=["리뷰해줘"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "최근 AI 세션을 찾지 못했습니다." in out
    assert "Codex 작업" not in out


def test_sessions_include_recent_codex_rollout_worktree_candidates(monkeypatch, tmp_path: Path, capsys):
    """regression-case - Codex rollout logs expose cwd/branch when session_index lacks them."""
    _, codex_home, _ = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "contents-systsem-worktrees" / "feature-enrtc-878"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature/enrtc-878"], cwd=project, check=True)
    _write_codex_rollout(
        codex_home,
        session_id="rollout-878",
        cwd=project,
        timestamp="2026-07-25T15:24:16.078Z",
        mtime=int(time.time()),
        last_message="회원명 조회 서비스 커밋 완료",
    )

    assert runtime.command_sessions(argparse.Namespace(project_root=str(project), limit=10)) == 0

    out = capsys.readouterr().out
    assert "① Codex · feature-enrtc-878 · feature/enrtc-878" in out
    assert "회원명 조회 서비스 커밋 완료" in out
    assert "rollout-878" not in out


def test_sessions_ignore_stale_codex_rollouts(monkeypatch, tmp_path: Path, capsys):
    """regression-case - old rollout logs do not create noisy Codex candidates."""
    _, codex_home, _ = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "cnas-worktrees" / "feature-enrtc-879"
    project.mkdir(parents=True)
    _write_codex_rollout(
        codex_home,
        session_id="old-rollout-879",
        cwd=project,
        timestamp="2026-07-21T11:52:35.004Z",
        mtime=1000,
        last_message="오래된 세션",
    )

    assert runtime.command_sessions(argparse.Namespace(project_root=str(project), limit=10)) == 0

    out = capsys.readouterr().out
    assert "최근 AI 세션을 찾지 못했습니다." in out
    assert "오래된 세션" not in out


def test_interact_to_matches_multiple_natural_tokens(monkeypatch, tmp_path: Path, capsys):
    """regression-case - --to supports natural multi-token session descriptions."""
    _, codex_home, _ = _session_home(monkeypatch, tmp_path)
    project = tmp_path / "contents-systsem-worktrees" / "feature-enrtc-878"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature/enrtc-878"], cwd=project, check=True)
    _write_codex_rollout(
        codex_home,
        session_id="rollout-878",
        cwd=project,
        timestamp="2026-07-25T15:24:16.078Z",
        mtime=int(time.time()),
        last_message="contents-systsem worktree 작업",
    )

    assert runtime.command_interact(
        argparse.Namespace(
            project_root=str(project),
            to="Codex contents-systsem feature/enrtc-878",
            select="",
            limit=10,
            send=False,
            copy=False,
            prompt=["리뷰해줘"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "① Codex · feature-enrtc-878 · feature/enrtc-878" in out
    assert "contents-systsem worktree 작업" in out


def test_parser_accepts_sessions_and_interact_commands():
    """success-case - runtime parser exposes sessions and interact commands."""
    parser = runtime.build_parser()

    sessions = parser.parse_args(["sessions", "--limit", "5"])
    interact = parser.parse_args(["interact", "--to", "claude", "--select", "1", "리뷰해줘"])
    select_only = parser.parse_args(["interact", "--to", "claude", "--select", "1", "--no-send", "리뷰해줘"])

    assert sessions.func is runtime.command_sessions
    assert sessions.limit == 5
    assert interact.func is runtime.command_interact
    assert interact.to == "claude"
    assert interact.select == "1"
    assert interact.send is True
    assert interact.copy is False
    assert interact.prompt == ["리뷰해줘"]
    assert select_only.send is False


def test_e2e_case_crew_bin_interact_lists_friendly_candidates(tmp_path: Path):
    """e2e-case - core/bin/crew interact lists friendly candidates through the public shell entrypoint."""
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    for path in (home, codex_home, claude_home):
        path.mkdir(parents=True)
    project = tmp_path / "agent-crew"
    project.mkdir()
    _write_claude_session(claude_home, session_id="c1", cwd=project, branch="main", updated_at=1000)
    _write_claude_project_log(claude_home, cwd=project, session_id="c1", text="relay 명령 구현 리뷰")
    env = os.environ.copy()
    env.update(
        {
            "AGENT_CREW_HOME": str(home),
            "CODEX_HOME": str(codex_home),
            "CLAUDE_HOME": str(claude_home),
            "PROJECT_ROOT": str(project),
            "AGENT_CREW_INTERACT_AOE_ENABLED": "0",
        }
    )

    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "core" / "bin" / "crew"),
            "interact",
            "방금 relay 변경사항 클로드한테 리뷰 받아줘",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "요청: 방금 relay 변경사항 클로드한테 리뷰 받아줘" in result.stdout
    assert "추천:" in result.stdout
    assert "① Claude · agent-crew · main" in result.stdout
    assert "그대로 보낼까요? 아니면 번호를 선택하세요." in result.stdout
