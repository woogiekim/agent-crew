#!/usr/bin/env python3
"""Collect completed crew run variants into a comparison summary."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


STATUS_RE = re.compile(
    r"^(?:\*\*)?status:\*{0,2}\s+\*{0,2}(\w+)\*{0,2}",
    re.IGNORECASE | re.MULTILINE,
)
FIELD_RE = re.compile(
    r"^(?:\*\*)?(summary|description|branch|blocker):\*{0,2}\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def operation_lock(root: Path, name: str):
    lock = root / name
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise ValueError(f"작업 잠금이 있습니다: {lock}. 실행 중인 작업 또는 중단 상태를 확인하세요.") from error
    try:
        yield
    finally:
        lock.rmdir()


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def session_fingerprint(session: dict) -> str:
    receipt_fields = {"apply_status", "apply_record", "apply_history", "applied_branch", "applied_task_id", "applied_at"}
    return fingerprint({key: value for key, value in session.items() if key not in receipt_fields})


def result_fields(task_dir: Path) -> dict:
    path = task_dir / "result.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"status": "running", "summary": "result.md not available yet", "blockers": []}

    fields: dict[str, object] = {"status": "running", "summary": "", "blockers": []}
    status_match = STATUS_RE.search(text)
    if status_match:
        status = status_match.group(1).strip().lower()
        fields["status"] = status if status in {"completed", "blocked", "cancelled"} else status

    blockers: list[str] = []
    for key, value in FIELD_RE.findall(text):
        normalized_key = key.lower()
        normalized_value = value.strip().strip("*").strip()
        if normalized_key in {"summary", "description"} and normalized_value:
            fields["summary"] = normalized_value
        elif normalized_key == "branch" and normalized_value:
            fields["branch"] = normalized_value
        elif normalized_key == "blocker" and normalized_value:
            blockers.append(normalized_value)

    fields["blockers"] = blockers
    if not fields["summary"]:
        fields["summary"] = "No summary recorded in result.md"
    return fields


def render_summary(session: dict) -> str:
    lines = [
        "# Candidate Variants",
        "",
        f"Session: {session.get('session_id', 'Unknown')}",
        f"Base task: {session.get('base_task') or 'Unknown'}",
        "session_type: \"variants\"",
        f"selection_status: {session.get('selection_status') or 'pending'}",
        "",
        "| # | Task | Strategy | Branch | Status | Summary |",
        "|---|---|---|---|---|---|",
    ]

    for task in session.get("tasks", []):
        summary = str(task.get("summary") or "").replace("|", "\\|")
        lines.append(
            "| {index} | {task_id} | {strategy} | {branch} | {status} | {summary} |".format(
                index=task.get("variant_index") or "?",
                task_id=task.get("task_id") or "Unknown",
                strategy=task.get("variant_strategy") or task.get("variant_id") or "variant",
                branch=task.get("branch") or "Unknown",
                status=task.get("status") or "running",
                summary=summary or "No summary recorded",
            )
        )

    lines.extend(
        [
            "",
            "Do not merge all completed branches. Select one candidate implementation first.",
            "",
        ]
    )
    return "\n".join(lines)


def require_variants_session(state_dir: Path) -> tuple[dict | None, Path, str | None]:
    session_path = state_dir / "session.json"
    session = load_json(session_path)
    if not session:
        return None, session_path, "No session.json found.\n"
    if session.get("session_type") != "variants":
        return None, session_path, "No variants session found.\n"
    return session, session_path, None


def collect_variants(state_dir: Path) -> tuple[int, str]:
    session, session_path, message = require_variants_session(state_dir)
    if session is None:
        return 0, message or "No variants session to collect.\n"

    changed = False
    terminal_count = 0
    for task in session.get("tasks", []):
        task_dir_value = str(task.get("task_dir") or "").strip()
        fields = (
            result_fields(Path(task_dir_value))
            if task_dir_value
            else {"status": "running", "summary": "task_dir not recorded", "blockers": []}
        )
        status = str(fields.get("status") or "running")
        if task.get("status") != status:
            task["status"] = status
            changed = True
        if fields.get("branch") and task.get("branch") != fields["branch"]:
            task["branch"] = fields["branch"]
            changed = True
        summary = str(fields.get("summary") or "")
        if task.get("summary") != summary:
            task["summary"] = summary
            changed = True
        blockers = fields.get("blockers") or []
        if blockers and task.get("blockers") != blockers:
            task["blockers"] = blockers
            changed = True
        if status in {"completed", "blocked", "cancelled"}:
            terminal_count += 1

    tasks = session.get("tasks", [])
    if tasks and terminal_count == len(tasks) and session.get("status") != "completed":
        session["status"] = "completed"
        changed = True
    session["selection_status"] = session.get("selection_status") or "pending"
    if "selected_task_id" not in session:
        session["selected_task_id"] = None
        changed = True

    summary = render_summary(session)
    (state_dir / "variant-summary.md").write_text(summary, encoding="utf-8")
    if changed:
        write_json(session_path, session)

    return 0, summary


def select_variant(state_dir: Path, task_id: str) -> tuple[int, str]:
    session, session_path, message = require_variants_session(state_dir)
    if session is None:
        return 2, message or "No variants session to select.\n"

    selected = None
    for task in session.get("tasks", []):
        if str(task.get("task_id") or "") == task_id:
            selected = task
            break
    if selected is None:
        return 2, f"Variant task not found: {task_id}\n"

    session["selection_status"] = "selected"
    session["selected_task_id"] = task_id
    session["selected_variant_id"] = selected.get("variant_id")
    session["selected_variant_strategy"] = selected.get("variant_strategy")
    write_json(session_path, session)

    lines = [
        "Variant selected",
        f"selection_status: {session['selection_status']}",
        f"selected_task_id: {session['selected_task_id']}",
        f"selected_variant: {session.get('selected_variant_strategy') or session.get('selected_variant_id') or 'variant'}",
        f"branch: {selected.get('branch') or 'Unknown'}",
        "",
        "No branch mutation was performed.",
        "",
    ]
    return 0, "\n".join(lines)


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        text=True, capture_output=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git 검증 실패")
    return result.stdout.strip()


def require_finished_git_operation(root: Path) -> None:
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        marker_path = git_output(root, "rev-parse", "--path-format=absolute", "--git-path", marker)
        if Path(marker_path).exists():
            raise ValueError(f"진행 중인 Git 작업을 먼저 복구하세요: {marker_path}")


def preview_merge(selected: dict, target: str) -> tuple[int, list[str], dict]:
    if selected.get("status") != "completed":
        raise ValueError("후보 상태가 completed여야 합니다. 먼저 collect 결과를 확인하세요.")
    if not selected.get("base_project_root") or not selected.get("project_root"):
        raise ValueError("독립 worktree와 base_project_root 정보가 필요합니다.")
    base = Path(selected["base_project_root"]).resolve()
    worktree = Path(selected["project_root"]).resolve()
    if base == worktree:
        raise ValueError("후보는 독립 worktree여야 합니다.")
    for root in (base, worktree):
        if Path(git_output(root, "rev-parse", "--show-toplevel")).resolve() != root:
            raise ValueError("기록된 경로가 독립 worktree 루트와 다릅니다.")
    common = git_output(base, "rev-parse", "--path-format=absolute", "--git-common-dir")
    candidate_common = git_output(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if Path(common).resolve() != Path(candidate_common).resolve():
        raise ValueError("후보와 대상은 동일한 저장소에 속해야 합니다.")

    branch = str(selected.get("branch") or "")
    try:
        git_output(base, "check-ref-format", f"refs/heads/{target}")
        target_sha = git_output(base, "rev-parse", "--verify", f"refs/heads/{target}^{{commit}}")
    except ValueError as error:
        raise ValueError(f"대상 브랜치를 확인할 수 없습니다: {target}") from error
    if not branch or git_output(worktree, "symbolic-ref", "--quiet", "HEAD") != f"refs/heads/{branch}":
        raise ValueError("후보 브랜치와 worktree의 현재 브랜치가 다릅니다.")
    candidate_sha = git_output(worktree, "rev-parse", "--verify", "HEAD^{commit}")
    for root in (base, worktree):
        if git_output(root, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError(f"미커밋 변경이 있습니다: {root}")
        require_finished_git_operation(root)
    merge_base = git_output(base, "merge-base", target_sha, candidate_sha)
    changes = git_output(base, "diff", "--stat", merge_base, candidate_sha, "--")

    # 사용자 정의 merge driver는 외부 명령을 실행할 수 있어 미리보기에서 제외한다.
    drivers = subprocess.run(
        ["git", "-C", str(base), "config", "--get-regexp", r"^merge\..*\.driver$"],
        text=True, capture_output=True,
    )
    if drivers.returncode != 1:
        raise ValueError("사용자 정의 merge driver 설정을 해제해야 미리보기를 실행할 수 있습니다.")

    # merge-tree가 생성하는 객체는 임시 디렉터리에만 기록한다.
    objects = git_output(base, "rev-parse", "--path-format=absolute", "--git-path", "objects")
    with tempfile.TemporaryDirectory(prefix="crew-variant-merge-") as object_dir:
        env = {
            **os.environ,
            "GIT_OBJECT_DIRECTORY": object_dir,
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": json.dumps(objects, ensure_ascii=False),
        }
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(base), "merge-tree", "--write-tree",
             target_sha, candidate_sha],
            env=env, text=True, capture_output=True,
        )
    merge_lines = result.stdout.splitlines()
    if (result.returncode not in (0, 1) or not merge_lines
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", merge_lines[0])):
        raise ValueError(result.stderr.strip() or "Git merge-tree 실행 실패")

    lines = [
        f"target_branch: {target}", f"target_commit: {target_sha}",
        f"candidate_commit: {candidate_sha}", f"merge_base: {merge_base}",
        "mode: dry-run", f"merge_status: {'clean' if result.returncode == 0 else 'conflict'}",
        "", "후보 변경 범위:", changes or "변경 없음",
    ]
    if result.returncode == 1:
        lines.extend(["", "충돌 상세:", "\n".join(merge_lines[1:])])
    hooks = Path(git_output(base, "rev-parse", "--path-format=absolute", "--git-path", "hooks"))
    hook_fingerprints = {}
    for name in ("pre-merge-commit", "prepare-commit-msg", "commit-msg", "post-merge"):
        hook = hooks / name
        if hook.is_file():
            hook_fingerprints[name] = [hashlib.sha256(hook.read_bytes()).hexdigest(), hook.stat().st_mode]
    plan = {
        "target_branch": target, "target_commit": target_sha,
        "candidate_branch": branch, "candidate_commit": candidate_sha,
        "project_root": str(worktree), "base_project_root": str(base),
        "merged_tree": merge_lines[0], "operation": "merge --no-ff --strategy=ort",
        "runtime_fingerprint": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "config_fingerprint": fingerprint(git_output(base, "config", "--null", "--list")),
        "hooks_fingerprint": fingerprint(hook_fingerprints),
    }
    return result.returncode, lines, plan


def confirm_merge(state_dir: Path, session: dict, selected: dict, target: str, approved: str) -> tuple[int, str]:
    base = Path(str(selected.get("base_project_root") or "")).resolve()
    record = session.get("apply_record") or {}
    if session.get("apply_status") == "applied":
        old_plan = record.get("plan") or {}
        if (record.get("plan_hash") == approved and old_plan.get("target_branch") == target
                and old_plan.get("session_fingerprint") == session_fingerprint(session)
                and git_output(base, "symbolic-ref", "HEAD") == f"refs/heads/{target}"
                and git_output(base, "rev-parse", "HEAD") == record.get("applied_commit")
                and git_output(base, "rev-parse", f"refs/heads/{selected['branch']}") == old_plan.get("candidate_commit")
                and not git_output(base, "status", "--porcelain")):
            return 0, f"apply_status: applied\nalready_applied: {record['applied_commit']}\n"
        raise ValueError("이미 반영된 세션입니다. 반영 이력을 확인하고 새 작업은 새 세션에서 진행하세요.")
    common = Path(git_output(base, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    with operation_lock(common, "crew-variants-apply.lock"):
        if session.get("apply_status") in {"applying", "failed", "conflict"}:
            old_plan = record.get("plan") or {}
            require_finished_git_operation(base)
            if (old_plan.get("base_project_root") != str(base)
                    or git_output(base, "rev-parse", "HEAD") != old_plan.get("target_commit")
                    or git_output(base, "status", "--porcelain")):
                raise ValueError("이전 반영이 중단되었습니다. Git 상태와 apply_record를 확인하고 수동 복구하세요.")
        code, details, plan = preview_merge(selected, target)
        plan["session_fingerprint"] = session_fingerprint(session)
        if fingerprint(plan) != approved:
            raise ValueError("plan_hash가 현재 계획과 다릅니다. --dry-run으로 다시 확인하세요.")
        if code:
            return code, "\n".join(details) + "\n반영하지 않았습니다.\n"
        if git_output(base, "symbolic-ref", "--quiet", "HEAD") != f"refs/heads/{target}":
            raise ValueError("원본 worktree에 대상 브랜치를 먼저 checkout해야 합니다.")
        if git_output(base, "rev-parse", "HEAD") != plan["target_commit"]:
            raise ValueError("대상 커밋이 변경되었습니다. --dry-run으로 다시 확인하세요.")

        if record:
            session.setdefault("apply_history", []).append({"status": session.get("apply_status"), **record})
        record = {"plan_hash": approved, "plan": plan,
                  "started_at": datetime.now(timezone.utc).isoformat()}
        session["apply_status"] = "applying"
        session["apply_record"] = record
        session_path = state_dir / "session.json"
        write_json(session_path, session)
        try:
            result = subprocess.run(
                ["git", "-C", str(base), "merge", "--no-ff", "--no-edit", "--strategy=ort",
                 "-m", f"merge: apply crew variant {session['selected_task_id']}", plan["candidate_commit"]],
                stdin=subprocess.DEVNULL, text=True, capture_output=True,
            )
            if result.returncode:
                raise ValueError(result.stderr.strip() or result.stdout.strip() or "Git merge 실패")
            applied_commit = git_output(base, "rev-parse", "HEAD")
            if (git_output(base, "rev-parse", "HEAD^{tree}") != plan["merged_tree"]
                    or git_output(base, "symbolic-ref", "HEAD") != f"refs/heads/{target}"):
                raise ValueError("병합 결과가 승인된 계획과 다릅니다. Git 상태를 확인하세요.")
            git_output(base, "merge-base", "--is-ancestor", plan["candidate_commit"], applied_commit)
            if (applied_commit != plan["target_commit"]
                    and git_output(base, "show", "-s", "--format=%P", applied_commit).split()
                    != [plan["target_commit"], plan["candidate_commit"]]):
                raise ValueError("병합 부모 커밋이 승인된 계획과 다릅니다. Git 상태를 확인하세요.")
        except (ValueError, OSError) as error:
            session["apply_status"] = "conflict" if git_output(base, "ls-files", "--unmerged") else "failed"
            record["error"] = str(error)
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            write_json(session_path, session)
            return 2, (f"apply_status: {session['apply_status']}\n{error}\n"
                       "원본 worktree의 git status를 확인하세요. 병합을 취소하려면 git merge --abort로 복구하세요.\n")

        session["apply_status"] = "applied"
        session["applied_branch"] = target
        session["applied_task_id"] = session["selected_task_id"]
        session["applied_at"] = datetime.now(timezone.utc).isoformat()
        record["applied_commit"] = applied_commit
        write_json(session_path, session)
        return 0, f"apply_status: applied\napplied_branch: {target}\napplied_commit: {applied_commit}\n"


def apply_variant(state_dir: Path, target: str | None = None, confirmed: str | None = None) -> tuple[int, str]:
    session, _session_path, message = require_variants_session(state_dir)
    if session is None:
        return 2, message or "No variants session to apply.\n"
    if session.get("selection_status") != "selected" or not session.get("selected_task_id"):
        return 2, "No selected variant. Run crew variants select TASK_ID first.\n"

    selected_task_id = str(session.get("selected_task_id"))
    selected = None
    for task in session.get("tasks", []):
        if str(task.get("task_id") or "") == selected_task_id:
            selected = task
            break
    if selected is None:
        return 2, f"Selected variant task not found: {selected_task_id}\n"

    if confirmed is not None:
        try:
            return confirm_merge(state_dir, session, selected, target, confirmed)
        except (ValueError, OSError) as error:
            return 2, f"반영 실패: {error}\n"

    code = 0
    details: list[str] = []
    if target is not None:
        try:
            code, details, plan = preview_merge(selected, target)
            plan["session_fingerprint"] = session_fingerprint(session)
            details.append(f"plan_hash: {fingerprint(plan)}")
        except (ValueError, OSError) as error:
            return 2, f"미리보기 실패: {error}\n"

    lines = [
        "Variant apply plan",
        f"session_id: {session.get('session_id') or 'Unknown'}",
        f"selected_task_id: {selected_task_id}",
        f"selected_variant: {selected.get('variant_strategy') or selected.get('variant_id') or 'variant'}",
        f"branch: {selected.get('branch') or 'Unknown'}",
        f"project_root: {selected.get('project_root') or 'Unknown'}",
        f"base_project_root: {selected.get('base_project_root') or selected.get('project_root') or 'Unknown'}",
        *details,
        "",
        "No branch mutation was performed.",
        "반영하려면 --target BRANCH --confirm PLAN_HASH로 출력된 계획을 승인하세요.",
        "",
    ]
    return code, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="manage crew run variants")
    parser.add_argument("action", nargs="?", default="collect", choices=["collect", "select", "apply"])
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--target")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm", metavar="PLAN_HASH")
    args = parser.parse_args(argv)

    if args.target is not None or args.dry_run or args.confirm is not None:
        if args.action != "apply" or not args.target or not (args.dry_run or args.confirm):
            parser.error("apply requires --target BRANCH and --dry-run or --confirm PLAN_HASH")

    if args.action == "select":
        if not args.task_id:
            parser.error("select requires --task-id")
        action = lambda: select_variant(Path(args.state_dir), args.task_id)
    elif args.action == "apply":
        action = lambda: apply_variant(Path(args.state_dir), args.target, args.confirm)
    else:
        action = lambda: collect_variants(Path(args.state_dir))

    try:
        if Path(args.state_dir).is_dir() and (args.action != "apply" or args.confirm):
            with operation_lock(Path(args.state_dir), ".variants.lock"):
                code, output = action()
        else:
            code, output = action()
    except (ValueError, OSError) as error:
        code, output = 2, f"variants 작업 실패: {error}\n"
    print(output, end="" if output.endswith("\n") else "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
