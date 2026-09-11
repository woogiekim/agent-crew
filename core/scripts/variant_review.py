"""v2 리뷰의 구조와 고정 증거 정합성 검사. 의미 및 AI 실행 증명은 아니다."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

SCHEMA = Path(__file__).resolve().parents[1] / "schemas/variant-review.schema.json"
FIELDS = ("who", "when", "where", "what", "how", "why")


def _structure(value, schema, path="$"):
    """이 계약 스키마가 사용하는 JSON Schema 키워드만 검사한다."""
    errors = []
    if "oneOf" in schema:
        matches = sum(not _structure(value, option, path) for option in schema["oneOf"])
        return [] if matches == 1 else [f"{path}: invalid evidence shape"]
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int}
    if kind and type(value) is not types[kind]:
        return [f"{path}: expected {kind}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected {schema['const']}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: invalid value")
    if kind == "object":
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                errors.extend(_structure(item, properties[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: unexpected field")
    elif kind == "array":
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: missing entries")
        for index, item in enumerate(value):
            errors.extend(_structure(item, schema["items"], f"{path}[{index}]"))
    elif kind == "string":
        if len(value.strip()) < schema.get("minLength", 0):
            errors.append(f"{path}: empty text")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            errors.append(f"{path}: invalid hash")
    elif kind == "integer" and value < schema.get("minimum", value):
        errors.append(f"{path}: below minimum")
    return errors


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, timeout=10, check=True
    ).stdout


def _relative(path):
    parts = PurePosixPath(path)
    return (not parts.is_absolute() and ".." not in parts.parts
            and "\\" not in path and "\x00" not in path and path not in ("", "."))


def _evidence(evidence, candidates, owner):
    task_id = evidence["task_id"]
    if task_id not in candidates or task_id != owner:
        return "evidence task_id must match its candidate"
    candidate = candidates[task_id]
    task = candidate["task"]
    path = evidence.get("path", evidence.get("artifact"))
    if not _relative(path):
        return "evidence path must be a safe relative path"
    try:
        if "path" in evidence:
            commit = evidence["commit"]
            if commit != candidate.get("commit"):
                return "evidence commit does not match pinned candidate"
            # blob에서 직접 읽어 dirty worktree와 symlink 대상 파일을 신뢰하지 않는다.
            tree = _git(task["project_root"], "ls-tree", commit, "--", path)
            entries = [row.split(b"\t", 1) for row in tree.splitlines()]
            if not any(len(row) == 2 and row[1] == path.encode()
                       and row[0].split()[0] in (b"100644", b"100755") for row in entries):
                return "evidence path is not a regular committed file"
            data = _git(task["project_root"], "show", f"{commit}:{path}")
            if evidence["line"] > len(data.splitlines()):
                return "evidence line outside pinned file"
        else:
            digest = evidence["sha256"]
            if candidate["evidence"].get(path) != digest:
                return "artifact sha256 does not match pinned manifest"
            root = Path(task["task_dir"]).resolve()
            artifact = (root / path).resolve()
            if not artifact.is_relative_to(root):
                return "artifact escapes task_dir"
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
                return "artifact sha256 does not match actual bytes"
    except (OSError, ValueError, subprocess.SubprocessError):
        return "evidence cannot be read at pinned source"
    return None


def validate_review(document: dict, inputs: dict) -> list[str]:
    """오류 목록을 반환한다. 빈 목록은 구조/참조 검사 통과만 뜻한다."""
    errors = _structure(document, json.loads(SCHEMA.read_text()))
    if errors:
        return errors
    if not isinstance(inputs, dict):
        return ["inputs: expected object"]
    for key in ("input_hash", "base_task", "base_commit"):
        if document[key] != inputs.get(key):
            errors.append(f"{key}: does not match pinned inputs")

    candidates = {}
    try:
        for candidate in inputs["candidates"]:
            task = candidate["task"]
            task_id = task["task_id"]
            if task_id in candidates:
                errors.append(f"inputs: duplicate candidate {task_id}")
            candidates[task_id] = candidate
            for key in ("status", "task_dir", "project_root"):
                if not isinstance(task[key], str) or not task[key]:
                    raise ValueError(key)
            completed = task["status"] == "completed"
            if completed and not (candidate.get("commit") and candidate.get("base_commit")):
                raise ValueError("completed candidate requires commit/base_commit")
            if task["status"] not in ("completed", "failed", "blocked", "cancelled"):
                raise ValueError("candidate is not terminal")
            if candidate.get("base_commit") is not None and candidate["base_commit"] != inputs["base_commit"]:
                errors.append(f"{task_id}: base_commit mismatch")
            if not isinstance(candidate["evidence"], dict):
                raise ValueError("evidence")
            for key in ("commit", "base_commit"):
                if key in candidate:
                    if re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", candidate[key]) is None:
                        raise ValueError(key)
                    _git(task["project_root"], "cat-file", "-e", candidate[key] + "^{commit}")
        if not candidates:
            errors.append("inputs: candidates required")
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return errors + ["inputs: invalid candidate or unavailable pinned commit"]

    if not any(item["task"]["status"] == "completed" for item in candidates.values()):
        errors.append("inputs: no completed candidates; synthesis blocked")

    def ids(items, key, label):
        values = [item[key] for item in items]
        if len(set(values)) != len(values):
            errors.append(f"{label}: duplicate {key}")
        return set(values)

    requirements = ids(document["requirements"], "requirement_id", "requirements")
    units = ids(document["units"], "unit_id", "units")
    covered = set()
    for unit in document["units"]:
        references = set(unit["requirement_ids"])
        if not references <= requirements:
            errors.append(f"{unit['unit_id']}: unknown requirement_ids")
        covered.update(references)
    if covered != requirements:
        errors.append("requirements: missing unit coverage")

    evidence_results = {}

    def five_w_one_h(fields, owner, label, diagnostic=False):
        for name in FIELDS:
            field = fields[name]
            basis = field["basis"]
            if basis != "observed" and not field["reason"].strip():
                errors.append(f"{label}.{name}: {basis} requires reason")
            if basis in ("observed", "inferred") and not field["evidence"]:
                errors.append(f"{label}.{name}: {basis} requires evidence")
            if not diagnostic and basis == "unknown" and name in ("when", "what", "how"):
                errors.append(f"{label}.{name}: unknown critical contract")
            for evidence in field["evidence"]:
                key = (owner, json.dumps(evidence, sort_keys=True))
                if key not in evidence_results:
                    evidence_results[key] = _evidence(evidence, candidates, owner)
                error = evidence_results[key]
                if error:
                    errors.append(f"{label}.{name}: {error}")

    analyses = document["candidate_analyses"]
    if ids(analyses, "task_id", "candidate_analyses") != set(candidates):
        errors.append("candidate_analyses: candidate coverage mismatch")
    for analysis in analyses:
        task_id = analysis["task_id"]
        candidate = candidates.get(task_id)
        if candidate is None or analysis.get("commit") != candidate.get("commit"):
            errors.append(f"{task_id}: candidate commit mismatch")
        if ids(analysis["units"], "unit_id", task_id) != units:
            errors.append(f"{task_id}: unit coverage mismatch")
        for unit in analysis["units"]:
            diagnostic = candidate is not None and candidate["task"]["status"] != "completed"
            five_w_one_h(unit["five_w_one_h"], task_id, f"{task_id}.{unit['unit_id']}", diagnostic)

    if ids(document["comparison"], "unit_id", "comparison") != units:
        errors.append("comparison: unit coverage mismatch")
    for comparison in document["comparison"]:
        if (set(comparison["candidate_ids"]) != set(candidates)
                or len(comparison["candidate_ids"]) != len(candidates)):
            errors.append(f"{comparison['unit_id']}: comparison candidate coverage mismatch")

    ids(document["decisions"], "decision_id", "decisions")
    if {decision["unit_id"] for decision in document["decisions"]} != units:
        errors.append("decisions: unit coverage mismatch")
    for decision in document["decisions"]:
        owner = decision["source_task_id"]
        candidate = candidates.get(owner)
        if candidate is None or decision.get("source_commit") != candidate.get("commit"):
            errors.append(f"{decision['decision_id']}: source commit mismatch")
        elif decision["action"] in ("adopt", "adapt", "retain") and candidate["task"]["status"] != "completed":
            errors.append(f"{decision['decision_id']}: unverified failed candidate adoption")
        diagnostic = (candidate is not None and candidate["task"]["status"] != "completed"
                      and decision["action"] == "reject")
        five_w_one_h(decision["five_w_one_h"], owner, decision["decision_id"], diagnostic)

    semantic = document["semantic_review"]
    if semantic["verdict"] != "approved" or semantic["unresolved_findings"]:
        errors.append("semantic_review: approved verdict with no unresolved_findings required")
    return errors


def render_review(document: dict) -> str:
    """JSON 정본을 Markdown으로 표시하며 검증이나 AI 실행을 수행하지 않는다."""
    lines = ["# Variants 구현 분석", "",
             "구조/참조 검사와 의미 판단 및 AI 실행 증명은 별개입니다.", "",
             f"원문: {document['base_task']}", f"기준 commit: {document['base_commit']}",
             f"input_hash: {document['input_hash']}", "", "## 요구사항"]
    for item in document["requirements"]:
        lines.append(f"- {item['requirement_id']}: {item['text']}")
    lines.extend(["", "## 공통 단위"])
    for unit in document["units"]:
        lines.append(f"- {unit['unit_id']} ({', '.join(unit['requirement_ids'])}): {unit['description']}")

    def render_fields(fields):
        for name in FIELDS:
            field = fields[name]
            lines.append(f"- {name} [{field['basis']}]: {field['statement']}")
            lines.append(f"  근거 설명: {field['reason']}")
            for evidence in field["evidence"]:
                if "path" in evidence:
                    location = f"{evidence['commit']}:{evidence['path']}:{evidence['line']}"
                else:
                    location = f"{evidence['artifact']} (sha256={evidence['sha256']})"
                lines.append(f"  증거: {evidence['task_id']} {location}")

    for candidate in document["candidate_analyses"]:
        lines.extend(["", f"## 후보 {candidate['task_id']} ({candidate.get('commit', 'SHA 없음')})"])
        for unit in candidate["units"]:
            lines.extend(["", f"### {unit['unit_id']}"])
            render_fields(unit["five_w_one_h"])
            lines.append("장점: " + "; ".join(unit["strengths"]))
            lines.append("단점: " + "; ".join(unit["weaknesses"]))
    lines.extend(["", "## 비교"])
    for item in document["comparison"]:
        lines.extend([f"- {item['unit_id']} ({', '.join(item['candidate_ids'])}): {item['summary']}",
                      f"  호환성: {item['compatibility']}"])
    lines.extend(["", "## 결정"])
    for item in document["decisions"]:
        lines.extend([f"### {item['decision_id']} / {item['unit_id']}: {item['action']}",
                      f"출처: {item['source_task_id']} {item.get('source_commit', 'SHA 없음')}",
                      f"대상: {item['target']}", f"검증: {item['validation']}",
                      f"호환성: {item['compatibility']}"])
        render_fields(item["five_w_one_h"])
    semantic = document["semantic_review"]
    lines.extend(["", f"검토자: {semantic['reviewer_id']}", f"판정: {semantic['verdict']}",
                  "미해결: " + "; ".join(semantic["unresolved_findings"])])
    return "\n".join(lines) + "\n"
