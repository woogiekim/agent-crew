#!/usr/bin/env python3
"""Deterministic local runtime helpers for the crew CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from quality_loop_lib import check_quality_loop, looks_mutating_task


SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key)=\S+"),
]

HANGUL_PATTERN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]")
JAPANESE_PATTERN = re.compile(r"[\u3040-\u30ff]")
HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04ff]")
ARABIC_PATTERN = re.compile(r"[\u0600-\u06ff]")
LATIN_EXTENDED_PATTERN = re.compile(r"[\u00c0-\u024f]")
NON_ASCII_PATTERN = re.compile(r"[^\x00-\x7f]")
AMBIGUOUS_TASKS = {
    "go",
    "yes",
    "ok",
    "okay",
    "continue",
    "proceed",
    "resume",
    "do it",
    "fix this",
    "do the thing",
    "do the thing from before",
}


def utc_now_z() -> str:
    """Return the progress-buffer timestamp format used by supervisor."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def trace_id_for(register: dict, task_dir: Path, stage: int = 0, attempt: int = 0) -> str:
    session_id = register.get("session_id", task_dir.name)
    return f"{session_id}.{task_dir.name}.{stage}.{attempt}"


def git_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return Path.cwd().resolve()


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return value[:48] or "task"


def append_jsonl(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path, fallback: dict | None = None) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback or {})
    return data if isinstance(data, dict) else dict(fallback or {})


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def append_progress(task_dir: Path, row: dict) -> None:
    append_jsonl(task_dir / "progress.buffer.jsonl", row)


def agent_uuid_for_display() -> str:
    for name in (
        "AGENT_CREW_AGENT_UUID",
        "AGENT_CREW_HOST_AGENT_UUID",
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return "unavailable"


def render_start_banner(register: dict, task_dir: Path) -> str:
    task = str(register.get("task") or "").strip()
    if len(task) > 96:
        task = task[:93].rstrip() + "..."
    agent_uuid = agent_uuid_for_display()
    task_id = register.get("task_id", task_dir.name)
    lines = [
        "[crew] START",
        f"  mapping:    {agent_uuid} -> {task_id}",
        f"  agent_uuid: {agent_uuid}",
        f"  task_id:    {task_id}",
        f"  title:      {task or '(untitled)'}",
        f"  branch:     {register.get('branch', '')}",
        f"  state:      {task_dir}",
        "  monitor:    crew:status (CLI: crew status)",
    ]
    return "\n".join(lines)


def latest_progress_event(task_dir: Path) -> dict:
    buffer = task_dir / "progress.buffer.jsonl"
    if buffer.is_file():
        for line in reversed(buffer.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                row = json.loads(line)
            except Exception:
                continue
            return {
                "ts": row.get("ts", ""),
                "event": row.get("event", ""),
                "stage": row.get("stage", 0),
                "agent": row.get("agent", ""),
                "detail": row.get("detail", ""),
            }

    log = task_dir / "progress.log"
    if log.is_file():
        for line in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()):
            parts = [p.strip() for p in line.split("|", 2)]
            if len(parts) == 3:
                return {"ts": parts[0], "event": parts[1], "stage": 0, "agent": "", "detail": parts[2]}
            if line.strip():
                return {"ts": "", "event": "LOG", "stage": 0, "agent": "", "detail": line.strip()}

    return {"ts": "", "event": "", "stage": 0, "agent": "", "detail": "no progress events yet"}


def progress_age_seconds(event: dict) -> int | None:
    ts = str(event.get("ts") or "").strip().rstrip("Z")
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
        except ValueError:
            continue
    return None


def render_wait_progress(register: dict, task_dir: Path) -> str:
    latest = latest_progress_event(task_dir)
    age = progress_age_seconds(latest)
    stage_value = latest.get("agent") or latest.get("stage")
    stage = f"stage={stage_value}" if stage_value not in ("", None) else "stage=0"
    age_text = "unknown" if age is None else f"{age}s"
    detail = str(latest.get("detail") or "").strip()
    if len(detail) > 120:
        detail = detail[:117].rstrip() + "..."
    return (
        f"[crew] WAIT | task_id={register.get('task_id', task_dir.name)} "
        f"phase={latest.get('event') or 'unknown'} {stage} "
        f"last_update_age={age_text} detail={detail}"
    )


def append_delegation(
    task_dir: Path,
    *,
    trace_id: str,
    span_id: str,
    parent_span_id: str,
    agent_role: str,
    unit_id: str,
    delegated_by: str,
    status: str,
) -> None:
    append_jsonl(
        task_dir / "delegation.jsonl",
        {
            "ts": utc_now_z(),
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "agent_role": agent_role,
            "unit_id": unit_id,
            "delegated_by": delegated_by,
            "status": status,
        },
    )


def append_tool_event(
    task_dir: Path,
    *,
    trace_id: str,
    tool_name: str,
    action_summary: str,
    started_at: str,
    ended_at: str,
    status: str,
    exit_code: int | None,
    failure_class: str,
) -> None:
    append_jsonl(
        task_dir / "tool-events.jsonl",
        {
            "schema_version": 1,
            "trace_id": trace_id,
            "tool_name": tool_name,
            "action_summary": redact(action_summary)[:500],
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "exit_code": exit_code,
            "token_usage_ref": f"cost/{task_dir.name}.jsonl",
            "failure_class": failure_class,
        },
    )


def render_completed_result(task: str, task_id: str, completion_path: str, note: str) -> str:
    lines = [
        f"# {task}",
        "",
        "STATUS: completed",
        f"TASK_ID: {task_id}",
        "MEASUREMENTS: host bridge completion recorded 1 automatic completion event",
        f"EVIDENCE: {completion_path}",
        "UNCERTAINTY: Host bridge command success indicates handoff delivery completed; downstream host prompt quality still depends on the active runtime.",
    ]
    if note:
        lines.append(f"NOTE: {note}")
    return "\n".join(lines).rstrip() + "\n"


def render_quality_loop_blocked_result(
    task: str,
    task_id: str,
    failures: list[str],
    evidence_path: str,
) -> str:
    return (
        f"# {task}\n\n"
        "STATUS: blocked\n"
        f"TASK_ID: {task_id}\n"
        "MEASUREMENTS: runtime quality-loop validation ran 1 check, 0 retries\n"
        "BLOCKER: missing_quality_loop_pipeline\n"
        f"EVIDENCE: {evidence_path}\n"
        "EVIDENCE: context/quality-loop-runtime-check.json\n"
        "DETAIL: Host bridge or fake-host completion cannot mark a mutating "
        "implementation task completed until the pipeline trace proves TDD, "
        "review, remediation/refactor after rejection, and reviewer approval.\n"
        "FAILURES: " + ", ".join(failures) + "\n"
        "UNCERTAINTY: Host bridge execution may have run outside this process, "
        "but it did not leave the required provider-neutral quality-loop state.\n"
    )


def host_bridge_next_line(task_dir: Path, task_id: str, bridge_command_present: bool) -> str:
    handoff_path = str(task_dir / "handoff.md")
    lines = [
        f"NEXT: Continue with {handoff_path}, then run "
        f"`crew repair {task_id} --status completed --note \"<summary>\"`.",
    ]
    if not bridge_command_present:
        lines.append(
            "DETAIL: no external bridge command is required for this state; "
            "agent-crew recorded a resumable internal handoff."
        )
    else:
        lines.append("DETAIL: the configured host bridge did not complete this handoff.")
    return "\n".join(lines) + "\n"


def mark_quality_loop_blocked(
    task_dir: Path,
    register: dict,
    pipeline: dict,
    quality_result: dict,
    evidence_path: str,
) -> None:
    now = utc_now_z()
    failures = list(quality_result.get("failures", []))
    check_path = task_dir / "context" / "quality-loop-runtime-check.json"
    write_json(check_path, quality_result)

    register.update({
        "current_phase": "blocked",
        "blocked_by": ["missing_quality_loop_pipeline"],
        "host_bridge_status": "quality_blocked",
        "host_bridge_completion_path": str(task_dir / evidence_path),
        "host_bridge_completed_at": now,
    })
    pipeline.setdefault("completed_stages", 0)

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    (task_dir / "result.md").write_text(
        render_quality_loop_blocked_result(
            register.get("task", task_dir.name),
            register.get("task_id", task_dir.name),
            failures,
            evidence_path,
        ),
        encoding="utf-8",
    )

    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now} | QUALITY_BLOCKED | missing_quality_loop_pipeline\n")
        handle.write(f"{now} | STATUS | blocked\n")

    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "QUALITY_BLOCKED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "failed",
            "detail": "missing_quality_loop_pipeline",
            "files": [evidence_path, "context/quality-loop-runtime-check.json", "result.md"],
        },
    )


def mark_auto_completed(task_dir: Path, register: dict, pipeline: dict,
                        bridge_record: dict, note: str,
                        preserve_quality_state: bool = False) -> None:
    now = utc_now_z()
    completion_path = task_dir / "context" / "host-bridge-completion.json"
    write_json(completion_path, bridge_record)

    register.update({
        "current_phase": "completed",
        "blocked_by": [],
        "host_bridge_status": "auto_completed",
        "host_bridge_completion_path": str(completion_path),
        "host_bridge_completed_at": now,
    })

    stages = pipeline.get("stages") or ["supervisor"]
    pipeline["completed_stages"] = len(stages)
    if preserve_quality_state:
        pipeline.setdefault("stage_agent_status", {})
    else:
        pipeline["stage_agent_status"] = {
            "1": {"supervisor": "completed"}
        }

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    existing_result = load_text(task_dir / "result.md")
    if preserve_quality_state and re.search(r"^STATUS\s*:\s*completed\b", existing_result, re.I | re.M):
        marker = "HOST_BRIDGE: auto_completed"
        addition = (
            "\n" + marker + "\n"
            "EVIDENCE: context/host-bridge-completion.json\n"
        )
        if marker not in existing_result:
            (task_dir / "result.md").write_text(existing_result.rstrip() + addition, encoding="utf-8")
    else:
        (task_dir / "result.md").write_text(
            render_completed_result(
                register.get("task", task_dir.name),
                register.get("task_id", task_dir.name),
                "context/host-bridge-completion.json",
                note,
            ),
            encoding="utf-8",
        )

    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now} | HOST_BRIDGE | auto completed\n")
        handle.write(f"{now} | STATUS | completed\n")

    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "HOST_BRIDGE",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "completed",
            "detail": "auto host bridge completed",
            "files": ["context/host-bridge-completion.json", "result.md"],
        },
    )
    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "COMPLETED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "completed",
            "detail": "completed",
            "files": [],
        },
    )


def invoke_host_bridge(
    command: str,
    *,
    task_dir: Path,
    register: dict,
    project_root: Path,
    extra_env: dict | None = None,
) -> dict:
    env = os.environ.copy()
    env.update({
        "AGENT_CREW_TASK_ID": register["task_id"],
        "AGENT_CREW_TASK_DIR": str(task_dir),
        "AGENT_CREW_HANDOFF_PATH": str(task_dir / "handoff.md"),
        "AGENT_CREW_RESULT_PATH": str(task_dir / "result.md"),
        "AGENT_CREW_PROJECT_ROOT": str(project_root),
    })
    if extra_env:
        env.update(extra_env)
    started = datetime.now(timezone.utc)
    interval_raw = os.environ.get("AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS", "10")
    try:
        interval = max(0.0, float(interval_raw))
    except ValueError:
        interval = 10.0

    if interval <= 0:
        proc = subprocess.run(command, shell=True, text=True, capture_output=True, env=env)
        stdout = proc.stdout
        stderr = proc.stderr
        returncode = proc.returncode
    else:
        proc = subprocess.Popen(
            command,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=interval)
                returncode = proc.returncode
                break
            except subprocess.TimeoutExpired:
                print(render_wait_progress(register, task_dir), file=sys.stderr)

    finished = datetime.now(timezone.utc)
    append_tool_event(
        task_dir,
        trace_id=trace_id_for(register, task_dir),
        tool_name="host_bridge_command",
        action_summary=command,
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ended_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        status="completed" if returncode == 0 else "failed",
        exit_code=returncode,
        failure_class="" if returncode == 0 else "host_bridge_command_failed",
    )
    return {
        "schema_version": 1,
        "task_id": register["task_id"],
        "command": command,
        "command_display": shlex.split(command)[0] if command.strip() else "",
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "returncode": returncode,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
    }


def host_bridge_reported_blocked(bridge_record: dict) -> bool:
    output = "\n".join(
        str(bridge_record.get(key, "") or "")
        for key in ("stdout", "stderr")
    )
    return bool(re.search(r"(?im)^\s*(STATUS\s*:\s*blocked\b|BLOCKER\s*:)", output))


def asset_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def read_agent_registry(root: Path) -> dict[str, dict]:
    registry_path = root / "rules" / "agent-routing.md"
    agents: dict[str, dict] = {}
    if not registry_path.exists():
        return agents

    in_registry = False
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "## Agent Registry":
            in_registry = True
            continue
        if in_registry and line.startswith("## ") and line.strip() != "## Agent Registry":
            break
        if not in_registry or not line.startswith("|"):
            continue
        if "---" in line or line.startswith("| Agent "):
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        name, scope, keywords, safe, reason = cells[:5]
        agents[name] = {
            "scope": scope,
            "keywords": keywords,
            "safe": safe.lower() == "yes",
            "reason": "" if reason == "—" else reason,
        }
    return agents


def looks_mutating(task: str) -> bool:
    return bool(
        re.search(
            r"\b(build|implement|create|add|update|fix|remove|move|change|migrate|"
            r"refactor|replace|extend|integrate|test|deploy|merge|rollback|write|"
            r"save|edit|publish|commit)\b|"
            r"구현|개발|추가|수정|개선|보완|변경|삭제|이동|마이그레이션|"
            r"리팩터|테스트|배포|머지|롤백|반영|저장|발행|고쳐",
            task,
            re.IGNORECASE,
        )
    )


def contains_hangul(text: str) -> bool:
    return bool(HANGUL_PATTERN.search(text or ""))


def detect_issue_references(text: str) -> list[str]:
    refs: list[str] = []
    for pattern in (r"(?<![\w/])#(\d+)\b", r"/issues/(\d+)\b"):
        for match in re.finditer(pattern, text or ""):
            value = match.group(1)
            if value not in refs:
                refs.append(value)
    return refs


def detect_source_language(text: str) -> str:
    value = text or ""
    if HANGUL_PATTERN.search(value):
        return "ko"
    if JAPANESE_PATTERN.search(value):
        return "ja"
    if HAN_PATTERN.search(value):
        return "zh"
    if CYRILLIC_PATTERN.search(value):
        return "cyrillic"
    if ARABIC_PATTERN.search(value):
        return "arabic"
    if LATIN_EXTENDED_PATTERN.search(value):
        return "latin-extended"
    if NON_ASCII_PATTERN.search(value):
        return "unknown"
    return "en"


def ambiguous_input_reason(text: str) -> str:
    value = " ".join((text or "").strip().lower().split())
    if value in AMBIGUOUS_TASKS:
        return "short conversational shorthand requires prior-context binding"
    if len(value.split()) <= 3 and re.search(r"\b(this|that|it|before|again)\b", value):
        return "short ambiguous reference requires missing-context annotation"
    return ""


def input_normalization_metadata(raw_task: str, *, next_target: str) -> dict:
    source_language = detect_source_language(raw_task)
    ambiguity = ambiguous_input_reason(raw_task)
    translation_required = source_language != "en"
    normalization_required = translation_required or bool(ambiguity)
    confidence = 0.9 if source_language == "en" and not ambiguity else 0.55
    reason = []
    if translation_required:
        reason.append(f"source_language={source_language}")
    if ambiguity:
        reason.append(ambiguity)
    return {
        "schema_version": 1,
        "normalization_required": normalization_required,
        "source_language": source_language,
        "translation_required": translation_required,
        "ambiguity_flags": [ambiguity] if ambiguity else [],
        "confidence": confidence,
        "raw_input_ref": "handoff.md#RAW_INPUT",
        "downstream_route_hint": next_target,
        "normalization_sources": [
            "OpenAI prompting guide",
            "Anthropic prompt engineering overview",
            "Google Gemini prompting intro",
            "Microsoft Azure OpenAI prompt engineering",
        ],
        "reason": "; ".join(reason) if reason else "input is already a specific English instruction",
    }


def needs_input_normalization(raw_task: str) -> bool:
    return bool(input_normalization_metadata(raw_task, next_target="").get("normalization_required"))


def input_normalization_task(raw_task: str, *, next_target: str) -> str:
    metadata = input_normalization_metadata(raw_task, next_target=next_target)
    return (
        "Normalize raw user input into a canonical English agent-crew workflow "
        "instruction. Return structured NORMALIZED_TASK metadata with objective, "
        "scope, constraints, acceptance criteria, missing context, risk flags, "
        f"and confidence, then re-route the normalized instruction to {next_target}. "
        f"Detected source_language={metadata['source_language']}; "
        f"translation_required={str(metadata['translation_required']).lower()}."
    )


def input_normalization_handoff(
    *,
    request_id: str,
    project_root: Path,
    normalized_task: str,
    raw_task: str,
    next_target: str,
    status: str,
    metadata: dict,
) -> str:
    raw_label = "RAW_TASK" if metadata.get("source_language") == "ko" else "RAW_INPUT"
    return (
        "# Input Normalization Handoff\n\n"
        f"REQUEST_ID: {request_id}\n"
        "AGENT: input-normalizer\n"
        f"TASK: {normalized_task}\n"
        f"PROJECT_ROOT: {project_root}\n"
        "MODE: normalization-gate\n"
        f"STATUS: {status}\n\n"
        "NORMALIZATION_GATE: required\n"
        f"SOURCE_LANGUAGE: {metadata.get('source_language', 'unknown')}\n"
        f"TRANSLATION_REQUIRED: {str(bool(metadata.get('translation_required'))).lower()}\n"
        f"CONFIDENCE: {metadata.get('confidence', 0.0)}\n"
        f"INTENDED_TARGET_AFTER_NORMALIZATION: {next_target}\n"
        f"{raw_label}: {raw_task}\n"
        "OUTPUT_CONTRACT: Return JSON with source_language, translation_required, "
        "raw_input_ref, normalized_task, objective, scope, out_of_scope, "
        "constraints, acceptance_criteria, missing_context, risk_flags, "
        "downstream_route_hint, confidence, and normalization_sources. Do not "
        "execute the downstream workflow until the normalized English instruction "
        "is available.\n"
    )


def korean_normalization_task(raw_task: str, *, next_target: str) -> str:
    return input_normalization_task(raw_task, next_target=next_target)


def korean_normalization_handoff(**kwargs) -> str:
    if "metadata" not in kwargs:
        kwargs["metadata"] = input_normalization_metadata(
            kwargs.get("raw_task", ""),
            next_target=kwargs.get("next_target", ""),
        )
    return input_normalization_handoff(**kwargs)


def extract_comment_requirements(comments: list[dict]) -> list[str]:
    requirements: list[str] = []
    for comment in comments:
        body = str(comment.get("body", ""))
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("-", "*")):
                continue
            text = stripped.lstrip("-* ").strip()
            lowered = text.lower()
            if any(token in lowered for token in ("must", "should", "acceptance", "required", "supports", "records", "handles")):
                requirements.append(text)
    return requirements[:50]


def build_issue_ingestion_evidence(issue: dict, issue_number: str) -> dict:
    import hashlib

    all_comments = issue.get("comments") if isinstance(issue.get("comments"), list) else []
    comments = [
        comment
        for comment in all_comments
        if not comment.get("isMinimized") and not comment.get("minimizedReason")
    ]
    latest_comment_at = ""
    for comment in comments:
        created_at = str(comment.get("createdAt", ""))
        if created_at > latest_comment_at:
            latest_comment_at = created_at

    return {
        "schema_version": 1,
        "issue_number": issue.get("number", issue_number),
        "issue_url": issue.get("url", ""),
        "issue_title": issue.get("title", ""),
        "comments_ingested": True,
        "comment_count": len(comments),
        "latest_comment_at": latest_comment_at,
        "labels": [label.get("name", "") for label in issue.get("labels", []) if isinstance(label, dict)],
        "body_sha256": hashlib.sha256(str(issue.get("body", "")).encode("utf-8")).hexdigest(),
        "comment_urls": [comment.get("url", "") for comment in comments if comment.get("url")],
        "comment_derived_requirements": extract_comment_requirements(comments),
        "contradiction_review_required": len(comments) > 0,
        "planning_gate": "issue body and all non-minimized comments ingested before planning",
    }


def load_issue_payload(issue_number: str, repo: str = "") -> tuple[dict | None, str]:
    cmd = [
        "gh",
        "issue",
        "view",
        str(issue_number),
        "--comments",
        "--json",
        "number,title,body,comments,labels,url",
    ]
    if repo:
        cmd.extend(["--repo", repo])
    try:
        raw = subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE)
        data = json.loads(raw)
    except FileNotFoundError:
        return None, "gh executable not found"
    except subprocess.CalledProcessError as exc:
        return None, exc.stderr.strip() or "gh issue view failed"
    except Exception as exc:
        return None, f"failed to parse issue payload: {exc}"
    return data if isinstance(data, dict) else {}, ""


def record_issue_ingestion_evidence(task_dir: Path, raw_task: str) -> list[dict]:
    records: list[dict] = []
    for issue_number in detect_issue_references(raw_task):
        issue, error = load_issue_payload(issue_number)
        if issue is None:
            evidence = {
                "schema_version": 1,
                "issue_number": issue_number,
                "comments_ingested": False,
                "error": error,
                "planning_gate": "issue comment ingestion attempted before planning",
            }
        else:
            evidence = build_issue_ingestion_evidence(issue, issue_number)
        evidence_path = task_dir / "context" / f"issue-{issue_number}-ingestion.json"
        write_json(evidence_path, evidence)
        records.append({
            "issue_number": str(issue_number),
            "path": str(evidence_path),
            "comments_ingested": bool(evidence.get("comments_ingested")),
            "comment_count": int(evidence.get("comment_count") or 0),
        })
    return records


def auto_route_agent(task: str, agents: dict[str, dict]) -> tuple[str | None, str]:
    lowered = task.lower()
    route_patterns = [
        ("historian", ["어떤 에이전트", "방금", "what just", "what ran", "what agent", "this session", "this branch"]),
        ("backend", ["api", "endpoint", "server", "database", "schema", "domain", "service", "repository", "entity"]),
        ("frontend", ["component", " page", " ui ", " css", "style", "layout", "button", "form", "modal", "react", "vue"]),
        ("designer", ["wireframe", "mockup", "figma", "prototype", "sketch"]),
        ("planner", ["design", "architecture", "plan", "decompose", "structure", "diagram"]),
        ("analyst", ["explain", "investigate", "understand", "trace", "audit", "explore", "리뷰", "검토", "평가"]),
        ("documenter", ["docs", "readme", "documentation", "guide", "reference", "changelog"]),
        ("learning-mentor", ["teach", "learn", "concept", "pattern", "tutorial", "example"]),
    ]
    for name, tokens in route_patterns:
        if name in agents and any(token in lowered or token in task for token in tokens):
            return name, f"matched {name} keywords"
    return None, "no direct-agent routing rule matched"


def command_run(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    project_name = project_root.name
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    state_dir = agent_crew_home / "state" / project_name
    tasks_dir = state_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    now_z = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    session_id = now.strftime("%Y%m%d-%H%M%S")
    task_id = f"{session_id}-0"
    index = 0
    while (tasks_dir / task_id).exists():
        index += 1
        task_id = f"{session_id}-{index}"

    task_dir = tasks_dir / task_id
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    raw_task = args.task
    normalization_metadata = input_normalization_metadata(raw_task, next_target="crew run supervisor")
    normalization_required = bool(normalization_metadata["normalization_required"])
    task = input_normalization_task(raw_task, next_target="crew run supervisor") if normalization_required else raw_task

    fake_completed_requested = args.fake_host_result == "completed"
    fake_quality_blocked = fake_completed_requested and looks_mutating_task(task)
    bridge_command = args.host_bridge_command or os.environ.get("AGENT_CREW_HOST_BRIDGE_COMMAND", "")
    if fake_completed_requested and not fake_quality_blocked:
        result_status = "completed"
    elif bridge_command or fake_quality_blocked:
        result_status = "blocked"
    else:
        result_status = "handoff_ready"
    current_phase = result_status
    blocked_by = []
    if fake_quality_blocked:
        blocked_by = ["missing_quality_loop_pipeline"]
    elif result_status == "blocked":
        blocked_by = ["host_bridge_not_invoked"]
    quality_next = (
        "NEXT: A mutating implementation task can only be auto-completed after "
        "the host runtime leaves pipeline-level quality-loop evidence in "
        "pipeline.json and progress.buffer.jsonl.\n"
    )

    if fake_quality_blocked:
        host_bridge_status = "quality_blocked"
    elif result_status == "completed":
        host_bridge_status = "fake_completed"
    elif result_status == "handoff_ready":
        host_bridge_status = "internal_handoff_ready"
    else:
        host_bridge_status = "pending" if bridge_command else "not_invoked"
    blocked_next = host_bridge_next_line(task_dir, task_id, bool(bridge_command))

    register = {
        "schema_version": 1,
        "task_id": task_id,
        "session_id": session_id,
        "task": task,
        "branch": f"crew/{slug(task)}",
        "project_root": str(project_root),
        "task_dir": str(task_dir),
        "execution_mode": "single",
        "current_phase": current_phase,
        "approval_status": "not_required",
        "verification_status": "failed" if fake_quality_blocked else "skipped",
        "pipeline_path": str(task_dir / "pipeline.json"),
        "handoff_path": str(task_dir / "handoff.md"),
        "progress_log_path": str(task_dir / "progress.log"),
        "progress_buffer_path": str(task_dir / "progress.buffer.jsonl"),
        "result_path": str(task_dir / "result.md"),
        "blocked_by": blocked_by,
        "host_bridge_status": host_bridge_status,
        "repair_command": f"crew repair {task_id} --status completed --note \"<summary>\"",
    }

    pipeline = {
        "schema_version": 1,
        "task": task,
        "stages": ["input-normalizer"] if normalization_required else ["supervisor"],
        "completed_stages": 1 if result_status == "completed" else 0,
        "stage_agent_status": {
            "1": {
                ("input-normalizer" if normalization_required else "supervisor"):
                    "completed" if result_status == "completed" else "blocked"
            }
        },
    }

    if normalization_required:
        handoff = input_normalization_handoff(
            request_id=task_id,
            project_root=project_root,
            normalized_task=task,
            raw_task=raw_task,
            next_target="crew run supervisor",
            status=result_status,
            metadata=normalization_metadata,
        )
    else:
        handoff = (
            f"# Supervisor Handoff\n\n"
            f"TASK_ID: {task_id}\n"
            f"TASK: {task}\n"
            f"PROJECT_ROOT: {project_root}\n"
            f"MODE: fake-host\n" if args.fake_host_result else
            f"# Supervisor Handoff\n\n"
            f"TASK_ID: {task_id}\n"
            f"TASK: {task}\n"
            f"PROJECT_ROOT: {project_root}\n"
            f"MODE: native-cli\n"
            f"STATUS: {result_status}\n"
            f"REPAIR: crew repair {task_id} --status completed --note \"<summary>\"\n"
        )
    if result_status == "blocked":
        handoff += "BLOCKER: host AI bridge has not completed this handoff\n"

    result = (
        f"# {task}\n\n"
        f"STATUS: {result_status}\n"
        f"TASK_ID: {task_id}\n"
        f"BRANCH: {register['branch']}\n"
    )
    if normalization_required:
        result += "NORMALIZATION_GATE: required\n"
    if result_status == "handoff_ready":
        result += "HOST_BRIDGE: internal_handoff_ready\n"
        result += blocked_next
    elif result_status == "blocked":
        if fake_quality_blocked:
            result += "BLOCKER: missing_quality_loop_pipeline\n"
            result += (
                "DETAIL: fake-host completion for mutating implementation "
                "tasks is blocked unless the quality loop is actually recorded.\n"
            )
            result += quality_next
        else:
            result += "BLOCKER: host AI bridge has not completed this handoff\n"
        result += blocked_next

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    if normalization_required:
        write_json(task_dir / "context" / "input-normalization.json", normalization_metadata)
    issue_ingestions = record_issue_ingestion_evidence(task_dir, raw_task)
    if issue_ingestions:
        register["issue_comment_ingestion"] = issue_ingestions
        write_json(task_dir / "register.json", register)
    (task_dir / "handoff.md").write_text(handoff, encoding="utf-8")
    (task_dir / "result.md").write_text(result, encoding="utf-8")
    progress_status = "completed" if result_status == "completed" else "in_progress"
    if result_status == "blocked":
        progress_status = "failed"
    (task_dir / "progress.log").write_text(
        f"{now_z} | STARTED | {task}\n"
        f"{now_z} | STATUS | {result_status}\n",
        encoding="utf-8",
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": now_z,
            "trace_id": f"{session_id}.{task_id}.0.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STARTED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "started",
            "detail": task,
            "files": [],
        },
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": utc_now_z(),
            "trace_id": f"{session_id}.{task_id}.0.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STATUS",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": progress_status,
            "detail": result_status,
            "files": [],
        },
    )
    append_delegation(
        task_dir,
        trace_id=f"{session_id}.{task_id}.0.0",
        span_id=f"{task_id}:supervisor",
        parent_span_id="",
        agent_role="supervisor",
        unit_id=task_id,
        delegated_by="crew-runtime",
        status=result_status,
    )

    print(render_start_banner(register, task_dir), flush=True)

    if fake_quality_blocked:
        quality_result = check_quality_loop(task_dir, target_status="completed")
        mark_quality_loop_blocked(
            task_dir,
            register,
            pipeline,
            quality_result,
            "pipeline.json",
        )

    if result_status == "blocked" and bridge_command:
        bridge_record = invoke_host_bridge(
            bridge_command,
            task_dir=task_dir,
            register=register,
            project_root=project_root,
        )
        write_json(task_dir / "context" / "host-bridge-invocation.json", bridge_record)
        if bridge_record["returncode"] == 0 and not host_bridge_reported_blocked(bridge_record):
            latest_register = load_json(task_dir / "register.json", register)
            latest_pipeline = load_json(task_dir / "pipeline.json", pipeline)
            if looks_mutating_task(str(latest_register.get("task", args.task))):
                quality_result = check_quality_loop(task_dir, target_status="completed")
                if not quality_result["passed"]:
                    mark_quality_loop_blocked(
                        task_dir,
                        latest_register,
                        latest_pipeline,
                        quality_result,
                        "context/host-bridge-invocation.json",
                    )
                    print(f"TASK_ID: {task_id}")
                    print(f"TASK_DIR: {task_dir}")
                    print("STATUS: blocked")
                    print("BLOCKER: missing_quality_loop_pipeline")
                    print("HOST_BRIDGE: quality_blocked")
                    return 3

                write_json(task_dir / "context" / "quality-loop-runtime-check.json", quality_result)
                latest_register = load_json(task_dir / "register.json", latest_register)
                latest_pipeline = load_json(task_dir / "pipeline.json", latest_pipeline)
                mark_auto_completed(
                    task_dir,
                    latest_register,
                    latest_pipeline,
                    bridge_record,
                    "Automatic host bridge command completed successfully after quality-loop validation.",
                    preserve_quality_state=True,
                )
                print(f"TASK_ID: {task_id}")
                print(f"TASK_DIR: {task_dir}")
                print("STATUS: completed")
                print("HOST_BRIDGE: auto_completed")
                return 0

            mark_auto_completed(
                task_dir,
                register,
                pipeline,
                bridge_record,
                "Automatic host bridge command completed successfully.",
            )
            print(f"TASK_ID: {task_id}")
            print(f"TASK_DIR: {task_dir}")
            print("STATUS: completed")
            print("HOST_BRIDGE: auto_completed")
            return 0

        register["host_bridge_status"] = "failed"
        if bridge_record["returncode"] == 0:
            register["host_bridge_failure_reason"] = "bridge_reported_blocked"
        register["host_bridge_completion_path"] = str(task_dir / "context" / "host-bridge-invocation.json")
        write_json(task_dir / "register.json", register)

    print(f"TASK_ID: {task_id}")
    print(f"TASK_DIR: {task_dir}")
    print(f"STATUS: {result_status}")
    if result_status == "handoff_ready":
        print("HOST_BRIDGE: internal_handoff_ready")
        print(blocked_next.rstrip())
        return 0
    if result_status == "blocked":
        if fake_quality_blocked:
            print("BLOCKER: missing_quality_loop_pipeline")
            print(quality_next.rstrip())
        else:
            print("BLOCKER: host AI bridge has not completed this handoff")
            print(blocked_next.rstrip())
        return 3
    return 0


def command_agent(args: argparse.Namespace) -> int:
    root = asset_root(args.asset_root)
    agents = read_agent_registry(root)
    raw_args = list(args.agent_args or [])

    if not raw_args and not args.list and not args.routing:
        print("usage: crew-runtime.py agent [--list|--routing|agent-name task|task]")
        return 0

    if args.list:
        print(f"Available direct agents (source: {root / 'rules' / 'agent-routing.md'})")
        for name in sorted(agents):
            if agents[name]["safe"]:
                print(f"  {name}: {agents[name]['scope']}")
        return 0

    if args.routing:
        registry_path = root / "rules" / "agent-routing.md"
        text = registry_path.read_text(encoding="utf-8")
        start = text.find("## Auto-Routing Rules")
        end = text.find("### Matching semantics", start)
        print(text[start:end].rstrip() if start >= 0 and end > start else text)
        return 0

    if raw_args[0] in agents:
        agent_name = raw_args[0]
        task = " ".join(raw_args[1:]).strip()
        route_reason = "explicit direct-agent request"
    else:
        task = " ".join(raw_args).strip()
        agent_name, route_reason = auto_route_agent(task, agents)

    if not task:
        print("crew agent: task description is required", file=sys.stderr)
        return 2

    intended_agent_name = agent_name
    normalization_metadata = input_normalization_metadata(
        task,
        next_target=intended_agent_name or "direct-agent auto-routing",
    )
    normalization_required = (
        bool(normalization_metadata["normalization_required"])
        and agent_name not in {"input-normalizer", "korean-normalizer"}
    )
    raw_task_for_normalizer = task if normalization_required else ""
    if normalization_required:
        if looks_mutating(raw_task_for_normalizer):
            print("crew agent: direct invocation is read-only. Use crew run for mutating work.", file=sys.stderr)
            return 2

        normalization_metadata = input_normalization_metadata(task, next_target=intended_agent_name or "direct-agent auto-routing")
        route_reason = (
            "inline input normalization before "
            f"{intended_agent_name or 'direct-agent auto-routing'}"
        )
        task = (
            "Complete this direct-agent request after inline input normalization. "
            f"First normalize RAW_TASK from the handoff into a canonical English read-only request, "
            f"then answer it as the {intended_agent_name or 'selected'} agent. "
            "Do not spawn utility agents."
        )

    if looks_mutating(task):
        print("crew agent: direct invocation is read-only. Use crew run for mutating work.", file=sys.stderr)
        return 2

    if agent_name is None:
        print("crew agent: cannot auto-route this read-only task; specify an agent name or use crew run", file=sys.stderr)
        return 2

    info = agents.get(agent_name)
    if not info:
        print(f"crew agent: unknown agent '{agent_name}'", file=sys.stderr)
        return 2
    if not info["safe"]:
        reason = info["reason"] or "agent requires supervisor context"
        print(f"crew agent: '{agent_name}' cannot be invoked directly. Reason: {reason}", file=sys.stderr)
        return 2

    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    project_name = project_root.name
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    state_dir = agent_crew_home / "state" / project_name
    requests_dir = state_dir / "agent-requests"
    requests_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    request_id = f"agent-{now.strftime('%Y%m%d-%H%M%S')}-0"
    index = 0
    while (requests_dir / request_id).exists():
        index += 1
        request_id = f"agent-{now.strftime('%Y%m%d-%H%M%S')}-{index}"

    request_dir = requests_dir / request_id
    bridge_command = args.host_bridge_command or os.environ.get("AGENT_CREW_HOST_BRIDGE_COMMAND", "")
    request = {
        "schema_version": 1,
        "request_id": request_id,
        "agent": agent_name,
        "task": task,
        "route_reason": route_reason,
        "project_root": str(project_root),
        "request_dir": str(request_dir),
        "status": "handoff_ready",
        "host_bridge_status": "pending" if bridge_command else "not_invoked",
        "created_at": now.isoformat(),
    }
    if normalization_required:
        request.update(
            {
                "normalization_status": "required",
                "source_language": normalization_metadata.get("source_language", "unknown"),
                "translation_required": normalization_metadata.get("translation_required", False),
                "confidence": normalization_metadata.get("confidence", 0.0),
                "normalization_mode": "inline_direct_bridge",
                "normalization_agent": "input-normalizer",
                "intended_agent_after_normalization": intended_agent_name or "",
            }
        )
    handoff = (
        f"# Direct Agent Handoff\n\n"
        f"REQUEST_ID: {request_id}\n"
        f"AGENT: {agent_name}\n"
        f"TASK: {task}\n"
        f"PROJECT_ROOT: {project_root}\n"
        f"MODE: host-prompt-bridge\n"
        f"STATUS: handoff_ready\n"
        f"NEXT: Invoke crew:agent {agent_name!r} with this task inside the host prompt runtime.\n"
    )
    if normalization_required:
        handoff += (
            "\nNORMALIZATION_GATE: required\n"
            "NORMALIZATION_MODE: inline_direct_bridge\n"
            "NORMALIZATION_AGENT: input-normalizer\n"
            f"SOURCE_LANGUAGE: {normalization_metadata.get('source_language', 'unknown')}\n"
            f"TRANSLATION_REQUIRED: {str(bool(normalization_metadata.get('translation_required'))).lower()}\n"
            f"INTENDED_AGENT_AFTER_NORMALIZATION: {intended_agent_name or 'auto-route'}\n"
            f"RAW_TASK: {raw_task_for_normalizer}\n"
            "OUTPUT_CONTRACT: Return JSON with source_language, translation_required, "
            "raw_input_ref, normalized_task, objective, scope, constraints, "
            "acceptance_criteria, missing_context, risk_flags, downstream_route_hint, "
            "confidence, and normalization_sources. Perform this normalization inline "
            "inside the direct-agent bridge session. Do not spawn input-normalizer, "
            "korean-normalizer, a background agent, or a nested crew:agent command.\n"
        )

    write_json(request_dir / "request.json", request)
    if normalization_required:
        write_json(request_dir / "context" / "input-normalization.json", normalization_metadata)
    (request_dir / "handoff.md").write_text(handoff, encoding="utf-8")

    print(f"AGENT_REQUEST_ID: {request_id}")
    print(f"AGENT: {agent_name}")
    print(f"REQUEST_DIR: {request_dir}")

    bridge_invocation_path = request_dir / "context" / "host-bridge-invocation.json"
    bridge_completion_path = request_dir / "context" / "host-bridge-completion.json"
    if bridge_command:
        bridge_record = invoke_host_bridge(
            bridge_command,
            task_dir=request_dir,
            register={"task_id": request_id},
            project_root=project_root,
            extra_env={
                "AGENT_CREW_AGENT_NAME": agent_name,
                "AGENT_CREW_AGENT_REQUEST_ID": request_id,
                "AGENT_CREW_REQUEST_DIR": str(request_dir),
            },
        )
        write_json(bridge_invocation_path, bridge_record)
        if bridge_record["returncode"] == 0 and not host_bridge_reported_blocked(bridge_record):
            now = utc_now_z()
            write_json(bridge_completion_path, bridge_record)
            result_path = request_dir / "result.md"
            if not result_path.exists():
                bridge_stdout = str(bridge_record.get("stdout", "")).strip()
                result_path.write_text(
                    "# Direct Agent Result\n\n"
                    f"REQUEST_ID: {request_id}\n"
                    f"AGENT: {agent_name}\n"
                    "STATUS: completed\n"
                    f"COMPLETED_AT: {now}\n"
                    "FILES: none\n\n"
                    "## Bridge Output\n\n"
                    f"{bridge_stdout or 'No bridge stdout was captured.'}\n",
                    encoding="utf-8",
                )
            request.update(
                {
                    "status": "auto_completed",
                    "host_bridge_status": "auto_completed",
                    "host_bridge_completion_path": str(bridge_completion_path),
                    "host_bridge_completed_at": now,
                }
            )
            write_json(request_dir / "request.json", request)
            print("STATUS: completed")
            print("HOST_BRIDGE: auto_completed")
            return 0

        request.update(
            {
                "host_bridge_status": "failed",
                "host_bridge_completion_path": str(bridge_invocation_path),
                "host_bridge_completed_at": utc_now_z(),
            }
        )
        if bridge_record["returncode"] == 0:
            request["host_bridge_failure_reason"] = "bridge_reported_blocked"
        write_json(request_dir / "request.json", request)
        print("STATUS: blocked")
        print("BLOCKER: host AI bridge has not completed this agent request")
        print(
            "NEXT: Continue with "
            f"{request_dir / 'handoff.md'} using your host bridge or run --host-bridge-command for one-off execution."
        )
        return 3

    print("STATUS: handoff_ready")
    return 0


def command_issue_ingest(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    project_name = project_root.name
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    state_dir = agent_crew_home / "state" / project_name

    issue, error = load_issue_payload(str(args.issue_number), repo=args.repo)
    if issue is None:
        print(f"crew issue-ingest: {error}", file=sys.stderr)
        return 1

    evidence = build_issue_ingestion_evidence(issue, str(args.issue_number))

    output_path = None
    if args.task_id:
        output_path = state_dir / "tasks" / args.task_id / "context" / f"issue-{args.issue_number}-ingestion.json"
        write_json(output_path, evidence)
    elif args.output:
        output_path = Path(args.output)
        write_json(output_path, evidence)

    if args.format == "json":
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    else:
        print(f"ISSUE: {evidence['issue_number']}")
        print(f"COMMENTS_INGESTED: {str(evidence['comments_ingested']).lower()}")
        print(f"COMMENT_COUNT: {evidence['comment_count']}")
        print(f"LATEST_COMMENT_AT: {evidence['latest_comment_at']}")
        if output_path:
            print(f"EVIDENCE: {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="agent-crew deterministic runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="create deterministic crew run state")
    run.add_argument("task")
    run.add_argument("--project-root")
    run.add_argument("--fake-host-result", choices=["completed"], default=None)
    run.add_argument("--host-bridge-command", default=None)
    run.set_defaults(func=command_run)

    agent = sub.add_parser("agent", help="create deterministic direct-agent handoff")
    agent.add_argument("--project-root")
    agent.add_argument("--asset-root")
    agent.add_argument("--host-bridge-command", default=None)
    agent.add_argument("--list", action="store_true")
    agent.add_argument("--routing", action="store_true")
    agent.add_argument("agent_args", nargs=argparse.REMAINDER)
    agent.set_defaults(func=command_agent)

    issue_ingest = sub.add_parser("issue-ingest", help="record issue body/comment ingestion evidence")
    issue_ingest.add_argument("issue_number")
    issue_ingest.add_argument("--project-root")
    issue_ingest.add_argument("--task-id", default="")
    issue_ingest.add_argument("--repo", default="")
    issue_ingest.add_argument("--output", default="")
    issue_ingest.add_argument("--format", choices=["text", "json"], default="text")
    issue_ingest.set_defaults(func=command_issue_ingest)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
