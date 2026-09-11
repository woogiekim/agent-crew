"""종합 수명주기. 호출자가 .variants.lock을 소유하며 AI 실행은 하지 않는다.

파일/커밋/로그의 정합성만 검사한다. 진술의 의미, 명령 실행 사실, host 신원은
이 모듈의 attestation으로 보증할 수 없으며 호스트의 독립 검토가 필요하다.
"""
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from variant_state import read_state, load_json, write_json, write_bytes, fingerprint, git_output
from variant_review import validate_review

STATE = "variant-synthesis-state.json"
FIELDS = ("who", "when", "where", "what", "how", "why")


def _save(root, state):
    write_json(root / STATE, state)
    return _response(state)


def _response(state):
    action = {"released": "synthesis_required", "running": "synthesis_in_progress",
              "preparing": "synthesis_in_progress", "validating": "validation_required",
              "needs_changes": "validation_required", "ready_for_apply": "ready_for_apply",
              "stale": "stale", "failed": "synthesis_failed",
              "blocked": "blocked"}.get(state.get("status"), "synthesis_required")
    return dict(state, next_action=action)


def _review(root, inputs):
    document = read_state(root / "variant-review.json")
    receipt = read_state(root / "variant-review-state.json")
    if (receipt.get("status") != "completed" or receipt.get("input_hash") != inputs["input_hash"]
            or receipt.get("document_hash") != fingerprint(document)):
        raise ValueError("review receipt/hash mismatch")
    errors = validate_review(document, inputs)
    if errors:
        raise ValueError("review invalid: " + "; ".join(errors))
    return document


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(inputs):
    snapshots = {}
    for candidate in inputs["candidates"]:
        task = candidate["task"]
        for relative, digest in candidate["evidence"].items():
            path = _inside(Path(task["task_dir"]), relative)
            if _digest(path) != digest:
                raise ValueError("candidate evidence changed")
        if task["status"] != "completed":
            continue
        root = Path(task["project_root"]).resolve()
        git_output(root, "cat-file", "-e", inputs["base_commit"] + "^{commit}")
        if git_output(root, "rev-parse", "HEAD") != candidate["commit"]:
            raise ValueError("candidate HEAD changed")
        if git_output(root, "branch", "--show-current") != task["branch"]:
            raise ValueError("candidate branch changed")
        # 원본 HEAD 이동은 부모 apply 승인 해시가 담당한다. 후보 변경만 고정한다.
        dirty = git_output(root, "status", "--porcelain=v1", "--untracked-files=all")
        untracked = git_output(root, "ls-files", "--others", "--exclude-standard", "-z")
        files = {}
        for name in untracked.split("\0"):
            if name:
                files[name] = _digest(root / name)
        snapshots[str(root)] = {
            "head": candidate["commit"], "branch": task["branch"],
            "status": dirty, "untracked": files,
            "diff": fingerprint(git_output(root, "diff", "HEAD", "--binary")),
            "index": fingerprint(git_output(root, "diff", "--cached", "--binary")),
        }
    return snapshots


def _inside(root, name):
    root = root.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("evidence/log must be a file inside its task/worktree")
    return path


def _fresh(root, state, inputs):
    if state["input_hash"] != inputs["input_hash"] or state["inputs_hash"] != fingerprint(inputs):
        raise ValueError("synthesis inputs changed")
    document = _review(root, inputs)
    if state["document_hash"] != fingerprint(document):
        raise ValueError("synthesis decisions changed")
    if state["snapshots"] != _snapshot(inputs):
        raise ValueError("base/candidate snapshot changed")
    if state["status"] not in ("preparing", "failed"):
        task = Path(state["task_dir"])
        if (fingerprint(read_state(task / "inputs.json")) != state["inputs_hash"]
                or fingerprint(read_state(task / "variant-review.json")) != state["document_hash"]):
            raise ValueError("frozen synthesis inputs changed")
    return document


def synthesis_readiness(state_dir: Path, inputs: dict, *, persist: bool = True) -> dict:
    state = read_state(state_dir / STATE)
    if not state:
        _review(state_dir, inputs)
        return {"status": "pending", "next_action": "synthesis_required", "artifact_kind": "synthesis"}
    if state["status"] in ("released", "stale"):
        return _response(state)
    try:
        document = _fresh(state_dir, state, inputs)
        if state["status"] == "ready_for_apply":
            hashes = _validate_result(state, state["result"], document)
            if hashes != state["log_hashes"]:
                raise ValueError("acceptance logs changed")
    except (ValueError, OSError, KeyError, TypeError) as error:
        state.update(status="stale", error=str(error))
        return _save(state_dir, state) if persist else _response(state)
    return _response(state)


def prepare_synthesis(state_dir: Path, approved_input_hash: str, inputs: dict) -> dict:
    if approved_input_hash != inputs["input_hash"]:
        raise ValueError("approved input hash mismatch")
    completed = [c for c in inputs["candidates"] if c["task"]["status"] == "completed"]
    if not completed:
        raise ValueError("at least one completed candidate required")
    document = _review(state_dir, inputs)
    previous = read_state(state_dir / STATE)
    if previous and previous["status"] != "released":
        return synthesis_readiness(state_dir, inputs)
    same_input = previous.get("inputs_hash") == fingerprint(inputs)
    validation_attempts = previous.get("validation_attempts", 0) if same_input else 0
    execution_attempts = previous.get("execution_attempts", 0) if same_input else 0
    if validation_attempts >= 3 or execution_attempts >= 5:
        previous.update(status="blocked", error="synthesis retry budget exhausted")
        return _save(state_dir, previous)

    snapshots = _snapshot(inputs)
    session = load_json(state_dir / "session.json")
    session_id = inputs.get("session_id") or session.get("session_id", state_dir.name)
    slug = re.sub(r"[^a-zA-Z0-9-]", "-", session_id).strip("-")[:60] or "session"
    attempt = previous.get("attempt", 0) + 1
    directory = state_dir.resolve() / "synthesis" / f"attempt-{attempt}"
    worktree, task_dir = directory / "worktree", directory / "task"
    original = Path(completed[0]["task"]["base_project_root"]).resolve()
    if directory.is_relative_to(original):
        raise ValueError("synthesis state_dir must be outside original worktree")
    branch = f"codex/variants-{slug}-final-{attempt}"
    if git_output(original, "rev-parse", inputs["base_commit"] + "^{commit}") != inputs["base_commit"]:
        raise ValueError("base must be a full pinned commit")
    common = git_output(original, "rev-parse", "--path-format=absolute", "--git-common-dir")
    for candidate in completed:
        if git_output(Path(candidate["task"]["project_root"]), "rev-parse",
                      "--path-format=absolute", "--git-common-dir") != common:
            raise ValueError("candidate must belong to same repository")

    history = previous.get("history", [])
    state = {"schema_version": 1, "artifact_kind": "synthesis", "status": "preparing",
             "input_hash": inputs["input_hash"], "inputs_hash": fingerprint(inputs),
             "document_hash": fingerprint(document), "base_commit": inputs["base_commit"],
             "snapshots": snapshots, "attempt": attempt, "token": str(uuid4()),
             "task_id": f"{slug}-final-{attempt}", "task_dir": str(task_dir),
             "project_root": str(worktree), "base_project_root": str(original), "branch": branch,
             "validation_attempts": validation_attempts, "max_validation_attempts": 3,
             "execution_attempts": execution_attempts + 1, "max_execution_attempts": 5,
             "history": history}
    _save(state_dir, state)
    try:
        task_dir.mkdir(parents=True, exist_ok=False)
        write_json(task_dir / "inputs.json", inputs)
        write_json(task_dir / "variant-review.json", document)
        git_output(original, "worktree", "add", "-b", branch, str(worktree), inputs["base_commit"])
        register = {"schema_version": 1, "session_id": session_id, "task": inputs["base_task"],
                    **{key: state[key] for key in ("task_id", "task_dir", "project_root",
                                                  "base_project_root", "branch")},
                    "execution_mode": "single", "mutation_scope": "workspace_write",
                    "current_phase": "handoff_ready", "host_bridge_status": "not_invoked",
                    "pipeline_path": str(task_dir / "pipeline.json")}
        write_json(task_dir / "register.json", register)
        write_json(task_dir / "pipeline.json", {"schema_version": 1, "task": inputs["base_task"],
                   "planning_required": True,
                   "mutation_scope": "workspace_write", "stages": ["supervisor"],
                   "completed_stages": 0, "stage_agent_status": {"1": {"supervisor": "pending"}}})
        handoff = (f"# Supervisor Handoff\n\nTASK_ID: {state['task_id']}\n"
                   f"TASK: {inputs['base_task']}\nPROJECT_ROOT: {worktree}\nTASK_DIR: {task_dir}\n"
                   "MUTATION_SCOPE: workspace_write\nMODE: supervisor\nVARIANT_SYNTHESIS: true\n"
                   "PLANNING_REQUIRED: true\nSTATUS: handoff_ready\n\n"
                   "고정 inputs.json과 variant-review.json을 따라 TDD 및 독립 reviewer 검증을 수행한다.\n"
                   "원본/후보는 읽기 전용이다. 전체 후보 merge와 숨겨진 AI 실행은 금지한다.\n"
                   "구조 검사와 host 진술은 의미 품질이나 실행 사실을 보증하지 않는다.\n\n"
                   + json.dumps(document["decisions"], ensure_ascii=False, indent=2) + "\n")
        write_bytes(task_dir / "handoff.md", handoff.encode())
        state.update(status="running")
        return _save(state_dir, state)
    except (ValueError, OSError) as error:
        state.update(status="failed", error=str(error))
        _save(state_dir, state)
        raise


def _token(root, token):
    state = read_state(root / STATE)
    if not token or state.get("token") != token or state.get("status") == "released":
        raise ValueError("invalid synthesis token")
    return state


def release_synthesis(state_dir: Path, token: str) -> dict:
    """호출자가 기존 host 종료를 확인한 뒤 명시적으로 해제한다."""
    state = _token(state_dir, token)
    state["history"].append({key: state.get(key) for key in
                             ("attempt", "token", "status", "task_dir", "project_root", "branch",
                              "host_id", "last_result", "result", "error", "validation_attempts")})
    state.update(status="released", token=None)
    return _save(state_dir, state)


def _coverage(items, key, expected):
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError(f"{key}: list required")
    actual = [item.get(key) for item in items]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ValueError(f"{key}: missing/duplicate/unknown coverage")


def _code_evidence(state, evidence, commit):
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("code evidence required")
    root = Path(state["project_root"])
    for item in evidence:
        name = item["path"]
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("unsafe evidence path")
        path = _inside(root, name)
        if item["commit"] != commit or type(item["line"]) is not int or item["line"] < 1:
            raise ValueError("evidence commit/line mismatch")
        tree = git_output(root, "ls-tree", commit, "--", name)
        if not tree.startswith(("100644 blob ", "100755 blob ")):
            raise ValueError("evidence must be a committed regular file")
        if item["line"] > len(path.read_bytes().splitlines()):
            raise ValueError("evidence line outside file")


def _validate_result(state, result, document):
    root = Path(state["project_root"])
    commit = result["commit"]
    if (git_output(root, "rev-parse", "HEAD") != commit
            or git_output(root, "branch", "--show-current") != state["branch"]
            or git_output(root, "status", "--porcelain", "--untracked-files=all")):
        raise ValueError("final HEAD/branch/clean worktree mismatch")
    git_output(root, "merge-base", "--is-ancestor", state["base_commit"], commit)
    implementer, reviewer = result["implementer_id"], result["reviewer_id"]
    if (not isinstance(implementer, str) or not implementer.strip()
            or not isinstance(reviewer, str) or not reviewer.strip() or reviewer == implementer
            or (state.get("host_id") and state["host_id"] != implementer)):
        raise ValueError("independent reviewer and bound implementer required")
    if result["verdict"] != "approved" or result["unresolved_findings"] != []:
        raise ValueError("independent review needs changes")
    _coverage(result["acceptance"], "requirement_id", [r["requirement_id"] for r in document["requirements"]])
    hashes = {}

    def validate_check(check):
        if check["passed"] is not True or not isinstance(check["command"], str) or not check["command"].strip():
            raise ValueError("validation failed or command missing")
        log = _inside(Path(state["task_dir"]), check["log"])
        if not log.stat().st_size:
            raise ValueError("validation log empty")
        hashes[str(log)] = _digest(log)

    for check in result["acceptance"]:
        validate_check(check)
    accepted = {d["decision_id"] for d in document["decisions"] if d["action"] != "reject"}
    decisions = result["decision_results"]
    _coverage(decisions, "decision_id", accepted)
    for decision in decisions:
        if decision["implemented"] is not True:
            raise ValueError("decision not implemented")
        _code_evidence(state, decision["evidence"], commit)
        validate_check(decision["validation"])
    composition = result["composition_checks"]
    if not isinstance(composition, list) or not composition:
        raise ValueError("composition regression checks required")
    _coverage(composition, "name", [check["name"] for check in composition])
    for check in composition:
        if not isinstance(check["name"], str) or not check["name"].strip():
            raise ValueError("composition check name missing")
        validate_check(check)
    _coverage(result["analysis"], "unit_id", [u["unit_id"] for u in document["units"]])
    for unit in result["analysis"]:
        for key in FIELDS:
            field = unit["five_w_one_h"][key]
            if not isinstance(field["statement"], str) or not field["statement"].strip():
                raise ValueError("analysis statement missing")
            basis = field["basis"]
            if basis not in ("observed", "inferred", "unknown", "not_applicable"):
                raise ValueError("analysis basis invalid")
            if basis != "observed" and not field.get("reason", "").strip():
                raise ValueError("analysis reason missing")
            if basis == "unknown" and key in ("when", "what", "how"):
                raise ValueError("unknown critical final contract")
            if basis in ("observed", "inferred") or field.get("evidence"):
                _code_evidence(state, field["evidence"], commit)
    return hashes


def record_synthesis_result(state_dir: Path, token: str, result: dict, inputs: dict) -> dict:
    state = _token(state_dir, token)
    if state["status"] not in ("running", "validating", "needs_changes"):
        raise ValueError("synthesis is not accepting validation")
    try:
        document = _fresh(state_dir, state, inputs)
    except (ValueError, OSError, KeyError, TypeError) as error:
        state.update(status="stale", error=str(error))
        _save(state_dir, state)
        raise ValueError(str(error)) from error
    state.update(status="validating", validation_attempts=state["validation_attempts"] + 1,
                 last_result=result)
    _save(state_dir, state)
    try:
        hashes = _validate_result(state, result, document)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        state.update(status="needs_changes", error=str(error))
        if state["validation_attempts"] >= state["max_validation_attempts"]:
            state["status"] = "blocked"
        return _save(state_dir, state)
    state.pop("error", None)
    state.update(status="ready_for_apply", commit=result["commit"], result=result, log_hashes=hashes)
    return _save(state_dir, state)


def final_artifact(state_dir: Path, inputs: dict) -> dict:
    state = synthesis_readiness(state_dir, inputs, persist=False)
    if state["status"] != "ready_for_apply":
        raise ValueError("final artifact is not ready: " + state["status"])
    validation_fingerprint = fingerprint({key: state[key] for key in
        ("inputs_hash", "input_hash", "document_hash", "base_commit", "commit",
         "result", "log_hashes", "snapshots")})
    return {**state, "status": "completed", "validation_fingerprint": validation_fingerprint}
