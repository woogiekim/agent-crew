"""Focused coverage for crew sessions/interact UX."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
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
            prompt=["방금", "relay", "변경사항", "클로드한테", "리뷰", "받아줘"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "전송할 AI 세션 후보를 찾았습니다." in out
    assert "요청:" in out
    assert "방금 relay 변경사항 클로드한테 리뷰 받아줘" in out
    assert "① Claude · agent-crew · main" in out
    assert "그대로 보낼까요? 아니면 번호를 선택하세요." in out


def test_interact_select_one_chooses_recommended_candidate(monkeypatch, tmp_path: Path, capsys):
    """success-case - selecting 1 chooses the recommended first candidate."""
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
            prompt=["리뷰", "부탁"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "선택한 세션:" in out
    assert "① Claude · agent-crew · main" in out
    assert "STATUS: selected" in out
    assert "c1" not in out


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
            prompt=["리뷰해줘"],
        )
    ) == 0

    out = capsys.readouterr().out
    assert "최근 AI 세션을 찾지 못했습니다." in out
    assert "Codex 작업" not in out


def test_parser_accepts_sessions_and_interact_commands():
    """success-case - runtime parser exposes sessions and interact commands."""
    parser = runtime.build_parser()

    sessions = parser.parse_args(["sessions", "--limit", "5"])
    interact = parser.parse_args(["interact", "--to", "claude", "--select", "1", "리뷰해줘"])

    assert sessions.func is runtime.command_sessions
    assert sessions.limit == 5
    assert interact.func is runtime.command_interact
    assert interact.to == "claude"
    assert interact.select == "1"
    assert interact.prompt == ["리뷰해줘"]


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
