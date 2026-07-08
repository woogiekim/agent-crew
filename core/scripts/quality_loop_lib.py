"""Provider-neutral quality-loop validation helpers."""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


MUTATING_TASK_RE = re.compile(
    r"\b("
    r"build|implement|create|add|update|fix|remove|move|change|migrate|"
    r"refactor|replace|extend|integrate|test|deploy|merge|rollback|write|"
    r"save|edit|publish|commit|resolve|close"
    r")\b|"
    r"구현|개발|추가|수정|개선|보완|변경|삭제|이동|마이그레이션|"
    r"작성|생성|만들|"
    r"리팩터|배포|머지|롤백|반영|저장|발행|고쳐|해결",
    re.IGNORECASE,
)
STRONG_MUTATING_TASK_RE = re.compile(
    r"\b("
    r"build|implement|create|add|update|fix|remove|move|change|migrate|"
    r"refactor|replace|extend|integrate|deploy|merge|rollback|write|"
    r"save|edit|publish|commit|resolve|close"
    r")\b|"
    r"구현|개발|추가|수정|개선|보완|변경|삭제|이동|마이그레이션|"
    r"작성|생성|만들|"
    r"리팩터|배포|머지|롤백|반영|저장|발행|고쳐|해결",
    re.IGNORECASE,
)
READ_ONLY_TASK_RE = re.compile(
    r"\b("
    r"read-only|readonly|non-mutating|nonmutating|no[- ]write|"
    r"inspect|investigate|analyze|analyse|review|validate|validation|"
    r"check|audit|status|diagnostic|diagnostics"
    r")\b|"
    r"읽기\s*전용|조회|분석|검토|리뷰|확인|진단|딥다이브|계획|모색|방안",
    re.IGNORECASE,
)
READ_ONLY_HISTORY_QUERY_RE = re.compile(
    r"\b(?:what(?:'s|\s+is)\s+running|currently\s+running|recent\s+activity|"
    r"what\s+is\s+(?:the\s+)?latest\s+commit|latest\s+commit|"
    r"git\s+(?:log|history))\b|"
    r"(?:어떤|무슨)\s*commit",
    re.IGNORECASE,
)
READ_ONLY_METHOD_LEARNING_RE = re.compile(
    r"\b(?:how\s+to|learn\s+how\s+to|teach\s+me\s+how\s+to|"
    r"coach\s+me\s+on\s+how\s+to)\s+(?:write|test)\b|"
    r"\b(?:write|writing|test|testing)\s+"
    r"(?:method|methods|guide|guidance|strategy|strategies|concepts?)\b|"
    r"작성\s*(?:방법|법|가이드|전략|개념)|"
    r"테스트\s*(?:방법|법|가이드|전략|개념)",
    re.IGNORECASE,
)
GERUND_MUTATING_TASK_RE = re.compile(
    r"\b(?:while\s+)?(?:refactoring|removing|changing|testing)\s+"
    r"(?:this|that|the|my|our|a|an)\b",
    re.IGNORECASE,
)
KOREAN_TEST_EXECUTION_RE = re.compile(
    r"테스트\s*"
    r"(?:"
    r"(?:도|만)?(?=\s*(?:[.!?。]|$))|"
    r"(?:도|는|은|를|을|만)?\s*"
    r"(?:하고|돌리고|실행하고|수행하고)(?!\s*싶)|"
    r"(?:도|는|은|를|을|만)?\s*"
    r"(?:"
    r"돌리자|돌리세요|돌리십시오|돌려(?:줘|주세요|라|요)?|"
    r"실행(?:해(?:줘|주세요|라|자|요)?|하자|하세요|해라)?|"
    r"수행(?:해(?:줘|주세요|라|자|요)?|하자|하세요|해라)?|"
    r"해(?:줘|주세요|라|자|요)?|하자|하세요|해라"
    r")(?=\s*(?:[.!?。]|$))"
    r")",
    re.IGNORECASE,
)
KOREAN_PLAN_ONLY_CONTEXT_RE = re.compile(
    r"(?:구현|개선|수정|보완|해결)\s*(?:계획|전략|방안|우선순위)",
    re.IGNORECASE,
)
KOREAN_PLAN_EXECUTION_RE = re.compile(
    r"(?:구현|개선|수정|보완|해결)\s*(?:계획|전략|방안|우선순위)"
    r"\s*(?:을|를)?\s*(?:대로|그대로|에\s*따라)?\s*"
    r"(?:진행|실행|반영|수정|구현|개선)"
    r"\s*(?:해|해주세요|해줘|하자|하세요|해라)?\s*[.!?。]*\s*$",
    re.IGNORECASE,
)
KOREAN_READ_ONLY_BACKGROUND_RE = re.compile(
    r"(?:구현|개선|수정|보완|해결)\s*작업\s*(?:이후|후|관련)|"
    r"(?:구현|개선|수정|보완|해결)\s*(?:한\s*거|한\s*것|했던\s*것|된\s*것|된\s*거|한거)"
    r"[^.!?\n。]*(?:리뷰|검토|분석|확인)",
    re.IGNORECASE,
)
KOREAN_READ_ONLY_EXPLORATION_RE = re.compile(
    r"(?:구현|개선|수정|보완|해결)"
    r"[^.!?\n。]*(?:방법|방안|원인|이유|문제|양상)"
    r"[^.!?\n。]*(?:모색|분석|검토|확인|알려|설명)"
    r"(?:해|해줘|해주세요|하라|해봐)?|"
    r"(?:왜|어째서|무엇\s*때문에)"
    r"[^.!?\n。]*(?:구현|개선|수정|보완|해결)"
    r"[^.!?\n。]*(?:분석|검토|확인|알려|설명)"
    r"(?:해|해줘|해주세요|해봐)?|"
    r"(?:방법|방안)"
    r"[^.!?\n。]*(?:모색|분석|검토|확인|알려|설명)"
    r"(?:해|해줘|해주세요|해봐)?",
    re.IGNORECASE,
)
KOREAN_READ_ONLY_COMPLAINT_RE = re.compile(
    r"(?:방법|방안|계획|분석|검토|리뷰|확인|모색)"
    r"[^.!?\n。]*(?:하라고|요청했|부탁했)"
    r"[^.!?\n。]*(?:구현|개선|수정|보완|해결)"
    r"[^.!?\n。]*(?:해버리|했네|하네|됐네|되어버리|해\s*버리)",
    re.IGNORECASE,
)
REVIEW_OUTPUT_SECTION_LABEL_RE = re.compile(
    r"\b(?:must|should)\s+fix\b",
    re.IGNORECASE,
)
HIGH_RISK_TASK_RE = re.compile(
    r"\b("
    r"git\s+push|push|git\s+merge|merge|deploy|release|rollback|"
    r"destructive|delete|overwrite|branch\s+cleanup|rm\s+-rf"
    r")\b|"
    r"푸시|머지|병합|배포|릴리즈|롤백|파괴|삭제",
    re.IGNORECASE,
)
HIGH_RISK_NEGATED_CLAUSE_RE = re.compile(
    r"\b(?P<prefix>do\s+not|don't|dont|must\s+not|should\s+not|never|without|no)"
    r"(?P<body>[^.;\n]*)",
    re.IGNORECASE,
)
HIGH_RISK_GOVERNANCE_CONTEXT_RE = re.compile(
    r"\b(?:preserv(?:e|es|ing)|keep(?:s|ing)?|maintain(?:s|ing)?|"
    r"document(?:s|ing)?|test(?:s|ing)?|validat(?:e|es|ing)|"
    r"verif(?:y|ies|ying)|enforc(?:e|es|ing)|cover(?:s|ing)?|"
    r"improv(?:e|es|ing)|implement(?:s|ing)?|add(?:s|ing)?|"
    r"updat(?:e|es|ing)|apply|applies|applying)\b"
    r"[^.;\n]*\b(?:gate|gates|guard|guards|policy|policies|check|checker|"
    r"validation|detector|rule|rules|handling)\b"
    r"[^.;\n]*\b(?:push|merge|deploy|release|rollback|destructive)\b"
    r"[^.;\n]*",
    re.IGNORECASE,
)
KOREAN_HIGH_RISK_NEGATED_ACTION_RE = re.compile(
    r"(?:푸시|머지|병합|배포|릴리즈|롤백|삭제)"
    r"\s*(?:하지\s*마|하지\s*말고|하지\s*않고|하지\s*않으며|않고|없이|금지)",
    re.IGNORECASE,
)
AUTO_COMPLETION_RE = re.compile(
    r"\b("
    r"auto[-_ ]?completed|host_bridge:\s*auto_completed|automatic\s+host\s+bridge"
    r")\b",
    re.IGNORECASE,
)
SOFT_QUALITY_FAILURES = {
    "missing_progress_events",
    "missing_pipeline_implementation_completion",
    "missing_pipeline_tdd_event",
    "missing_tdd_red_phase_evidence",
    "missing_tdd_refactor_phase_evidence",
    "missing_reviewer_quality_metrics_artifact",
    "missing_pipeline_reviewer_approval",
}
NON_MUTATING_CONSTRAINT_RE = re.compile(
    r"\b("
    r"do\s+not|don't|dont|must\s+not|should\s+not|never|without|no"
    r")\s+("
    r"build|implement|create|add|update|fix|remove|move|change|migrate|"
    r"refactor|replace|extend|integrate|deploy|merge|rollback|write|"
    r"save|edit|publish|commit|push|resolve|close|mutate"
    r")\b",
    re.IGNORECASE,
)
KOREAN_NON_MUTATING_CONSTRAINT_RE = re.compile(
    r"((?:구현|개발|추가|수정|개선|보완|변경|편집|반영|저장|발행|커밋|푸시|배포|작성|생성|해결)하지|(?:고치|만들)지)"
    r"\s*(?:마|말고|않고|않으며|않기)?",
    re.IGNORECASE,
)
STATUS_COMPLETED_RE = re.compile(r"^STATUS\s*:\s*completed\b", re.I | re.M)
QUALITY_BYPASS_RE = re.compile(r"^QUALITY_BYPASS_REASON\s*:", re.I | re.M)
TDD_EVENT_RE = re.compile(
    r"\b(TDD|RED|GREEN|REFACTOR|pytest|JUnit|MockK|tests?\s+passed|"
    r"STAGE_TDD_PARALLEL_DONE)\b",
    re.I,
)
TC_ID_RE = re.compile(r"\bTC-\d{3,}\b", re.I)
MARKDOWN_TABLE_DELIMITER_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
# Split this placeholder so the fake-completion scanner does not flag its own
# scanner vocabulary.
NO_TEST_PLACEHOLDER = "to" "do"
NO_TEST_REFERENCE_VALUES = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "not applicable",
    NO_TEST_PLACEHOLDER,
    "tbd",
    "unknown",
}
COVERED_YES_VALUES = {"yes", "y", "true", "covered", "implemented", "pass", "passed"}
EXCEPTION_ACCEPTED_RE = re.compile(
    r"\b(accepted|approved|reviewer[- ]?accepted|exception|cannot|can't|not applicable because|n/a because|na because)\b",
    re.I,
)
NON_TEST_REFERENCE_RE = re.compile(
    rf"\b({NO_TEST_PLACEHOLDER}|tbd|unknown|not implemented|no test|missing test)\b",
    re.I,
)
REVIEW_APPROVED_RE = re.compile(
    r"\b(REVIEW:\s*APPROVED|APPROVED|REVIEW_APPROVED|final_verdict=ok)\b",
    re.I,
)
QUALITY_METRICS_RE = re.compile(r"\bQUALITY_METRICS\s*:\s*(\S+)", re.I)
REVIEW_REJECTED_RE = re.compile(
    r"\b(STATUS:\s*REJECTED|REVIEW:\s*NEEDS_CHANGES|NEEDS_CHANGES|"
    r"reviewer_rejected|CHANGES_REQUESTED)\b",
    re.I,
)
TDD_EXCEPTION_RE = re.compile(
    r"\b(TDD[-_ ]?EXCEPTION|red[-_ ]?phase\s+exception|"
    r"no\s+runnable\s+test\s+harness|cannot\s+produce\s+red|"
    r"red\s+failure\s+cannot)\b",
    re.I,
)
TDD_RED_PHASE_RE = re.compile(
    r"\b(TDD[-_ ]?RED|RED\s+PHASE|red[-_ ]?phase|"
    r"expected\s+fail(?:ing|ure)|fail(?:ed|ing)\s+as\s+expected|"
    r"failing\s+test)\b",
    re.I,
)
TDD_REFACTOR_PHASE_RE = re.compile(
    r"\b(TDD[-_ ]?REFACTOR|REFACTOR\s+PHASE|refactor[-_ ]?phase|"
    r"no[- ]op\s+refactor|post[- ]refactor|refactor\s+review)\b",
    re.I,
)
TEST_FILE_RE = re.compile(
    r"(^|/)(tests?|spec|__tests__)/|"
    r"(^|/)[^/]+(_test|_spec|\.test|\.spec)\.[A-Za-z0-9]+$|"
    r"(^|/)test_[^/]+\.py$|"
    r"(^|/)[^/]+Test\.(java|kt|kts|scala|go|swift)$"
)
FINDING_TERMINAL_STATUSES = {
    "fixed",
    "accepted-risk",
    "moved-to-issue",
    "out-of-scope",
    "false-positive",
    "deferred-minor",
}
FINDING_REQUIRED_FIELDS = (
    "id",
    "title",
    "severity",
    "status",
    "source",
    "affected",
    "recommended_fix",
)
FINDING_TEST_TARGET_KEYS = (
    "test_targets",
    "focused_tests",
    "tests",
    "verification_targets",
)
FINDING_EXCEPTION_KEYS = (
    "test_exception",
    "verification_exception",
    "coverage_exception",
)
FINDING_OWNER_STATUSES = {
    "accepted-risk",
    "moved-to-issue",
    "out-of-scope",
}

NON_IMPLEMENTER_AGENTS = {
    "analyst",
    "devops",
    "designer",
    "documenter",
    "historian",
    "issuer",
    "planner",
    "qa-owner",
    "requirements",
    "resolver",
    "reviewer",
    "scribe",
    "supervisor",
    "test-writer",
}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def looks_like_test_file(path: str) -> bool:
    return bool(TEST_FILE_RE.search(path or ""))


def has_tdd_exception(task_dir: Path) -> bool:
    return bool(tdd_exception_evidence_paths(task_dir))


def relative_evidence_name(task_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(task_dir))
    except ValueError:
        return str(path)


def phase_evidence_paths(task_dir: Path, candidates: list[Path], pattern: re.Pattern[str]) -> list[str]:
    paths: list[str] = []
    for path in candidates:
        if path.is_file() and pattern.search(load_text(path)):
            paths.append(relative_evidence_name(task_dir, path))

    return sorted(set(paths))


def tdd_exception_evidence_paths(task_dir: Path) -> list[str]:
    return phase_evidence_paths(
        task_dir,
        [
            task_dir / "context" / "tdd-exception.md",
            task_dir / "context" / "tdd-exception.json",
        ],
        TDD_EXCEPTION_RE,
    )


def tdd_red_phase_evidence_paths(task_dir: Path) -> list[str]:
    return phase_evidence_paths(
        task_dir,
        [
            task_dir / "context" / "tdd-red.md",
            task_dir / "context" / "tdd-red.json",
        ],
        TDD_RED_PHASE_RE,
    )


def tdd_refactor_phase_evidence_paths(task_dir: Path) -> list[str]:
    return phase_evidence_paths(
        task_dir,
        [
            task_dir / "context" / "tdd-refactor.md",
            task_dir / "context" / "tdd-refactor.json",
        ],
        TDD_REFACTOR_PHASE_RE,
    )


def has_tdd_red_or_exception(task_dir: Path) -> bool:
    return bool(tdd_red_phase_evidence_paths(task_dir) or tdd_exception_evidence_paths(task_dir))


def has_tdd_refactor_evidence(task_dir: Path) -> bool:
    return bool(tdd_refactor_phase_evidence_paths(task_dir))


def markdown_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_markdown_table_delimiter(cells: list[str]) -> bool:
    return bool(cells) and all(MARKDOWN_TABLE_DELIMITER_RE.match(cell) for cell in cells)


def normalize_table_header(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if normalized in {"tc_id", "tc"}:
        return "tc_id"
    if "must" in normalized and "should" in normalized:
        return "level"
    if normalized in {"level", "priority_level", "requirement_level"}:
        return "level"
    return normalized


def markdown_table_rows(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    rows: list[dict[str, str]] = []
    index = 0
    while index + 1 < len(lines):
        header_line = lines[index]
        delimiter_line = lines[index + 1]
        if "|" not in header_line or "|" not in delimiter_line:
            index += 1
            continue

        headers = markdown_table_cells(header_line)
        delimiter = markdown_table_cells(delimiter_line)
        if not is_markdown_table_delimiter(delimiter):
            index += 1
            continue

        normalized_headers = [normalize_table_header(header) for header in headers]
        index += 2
        while index < len(lines) and "|" in lines[index]:
            cells = markdown_table_cells(lines[index])
            if is_markdown_table_delimiter(cells):
                index += 1
                continue
            row: dict[str, str] = {}
            for cell_index, header in enumerate(normalized_headers):
                row[header] = cells[cell_index] if cell_index < len(cells) else ""
            rows.append(row)
            index += 1
        continue

    return rows


def row_tc_id(row: dict[str, str]) -> str:
    direct = row.get("tc_id", "")
    match = TC_ID_RE.search(direct)
    if match:
        return match.group(0).upper()

    for value in row.values():
        match = TC_ID_RE.search(value)
        if match:
            return match.group(0).upper()
    return ""


def is_must_checklist_row(row: dict[str, str]) -> bool:
    return bool(re.search(r"\bMUST\b", row.get("level", ""), re.I))


def is_covered_yes(value: str) -> bool:
    return value.strip().lower() in COVERED_YES_VALUES


def is_no_test_reference(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    return normalized in NO_TEST_REFERENCE_VALUES or bool(NON_TEST_REFERENCE_RE.search(normalized))


def has_reviewer_accepted_exception(row: dict[str, str]) -> bool:
    text = " ".join(row.get(key, "") for key in ("notes", "reason", "exception", "explanation"))
    return bool(EXCEPTION_ACCEPTED_RE.search(text))


def has_valid_must_mapping(row: dict[str, str]) -> bool:
    covered = is_covered_yes(row.get("covered", ""))
    if not covered:
        return False

    test_ref = row.get("test", "")
    if not is_no_test_reference(test_ref):
        return True

    return has_reviewer_accepted_exception(row)


def test_checklist_status(task_dir: Path) -> dict:
    checklist_path = task_dir / "context" / "test-checklist.md"
    review_path = task_dir / "context" / "test-checklist-review.md"
    mapping_path = task_dir / "context" / "test-case-mapping.md"
    checklist_text = load_text(checklist_path) if checklist_path.is_file() else ""
    review_text = load_text(review_path) if review_path.is_file() else ""
    mapping_text = load_text(mapping_path) if mapping_path.is_file() else ""
    checklist_ids = sorted({item.upper() for item in TC_ID_RE.findall(checklist_text)})
    mapping_ids = sorted({item.upper() for item in TC_ID_RE.findall(mapping_text)})
    checklist_rows = markdown_table_rows(checklist_text)
    mapping_rows = markdown_table_rows(mapping_text)
    must_ids = sorted({
        tc_id
        for row in checklist_rows
        if is_must_checklist_row(row)
        for tc_id in [row_tc_id(row)]
        if tc_id
    })
    mapping_rows_by_id: dict[str, list[dict[str, str]]] = {}
    for row in mapping_rows:
        tc_id = row_tc_id(row)
        if tc_id:
            mapping_rows_by_id.setdefault(tc_id, []).append(row)
    invalid_must_mapping_ids = [
        tc_id for tc_id in must_ids
        if not any(has_valid_must_mapping(row) for row in mapping_rows_by_id.get(tc_id, []))
    ]
    missing_must_match = re.search(
        r"^\s*[-*]?\s*Missing\s+MUST\s*:\s*(.+)$",
        review_text,
        re.I | re.M,
    )
    missing_must_value = missing_must_match.group(1).strip().lower() if missing_must_match else ""
    missing_must_none = missing_must_value in {"none", "no", "n/a", "na", "0", "[]"}
    approved = bool(REVIEW_APPROVED_RE.search(review_text)) and (
        bool(re.search(r"^\s*CHECKLIST_REVIEW_RESULT\s*:\s*approved\b", review_text, re.I | re.M))
        or "checklist_review_result" not in review_text.lower()
    )
    mapping_covers = bool(checklist_ids) and set(checklist_ids).issubset(set(mapping_ids))

    errors: list[str] = []
    if not checklist_path.is_file():
        errors.append("missing_test_checklist")
    if not review_path.is_file():
        errors.append("missing_test_checklist_review")
    if review_path.is_file() and not approved:
        errors.append("test_checklist_not_approved")
    if not mapping_path.is_file():
        errors.append("missing_test_case_mapping")
    if review_path.is_file() and not missing_must_none:
        errors.append("missing_test_checklist_must_resolution")
    if checklist_path.is_file() and mapping_path.is_file() and not mapping_covers:
        errors.append("missing_test_case_mapping_coverage")
    if checklist_path.is_file() and mapping_path.is_file() and invalid_must_mapping_ids:
        errors.append("missing_must_test_case_mapping")

    return {
        "required": False,
        "valid": not errors,
        "errors": errors,
        "checklist_present": checklist_path.is_file(),
        "review_present": review_path.is_file(),
        "mapping_present": mapping_path.is_file(),
        "review_approved": approved,
        "missing_must_none": missing_must_none,
        "mapping_covers_checklist": mapping_covers,
        "checklist_ids": checklist_ids,
        "mapping_ids": mapping_ids,
        "must_checklist_ids": must_ids,
        "invalid_must_mapping_ids": invalid_must_mapping_ids,
    }


def event_file_paths(events: list[dict]) -> list[str]:
    paths: list[str] = []
    for row in events:
        files = row.get("files") or []
        if isinstance(files, list):
            paths.extend(str(item) for item in files)
    return paths


def implementer_event_file_paths(events: list[dict]) -> list[str]:
    paths: list[str] = []
    for row in events:
        agent = str(row.get("agent") or "").strip().lower()
        if agent in NON_IMPLEMENTER_AGENTS:
            continue

        files = row.get("files") or []
        if isinstance(files, list):
            paths.extend(str(item) for item in files)
    return paths


def result_changed_paths(result_text: str) -> list[str]:
    paths: list[str] = []
    for line in result_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].split(":", 1)[0].strip()
        if value:
            paths.append(value)
    return paths


def register_modified_paths(register: dict) -> list[str]:
    paths = register.get("modified_files")
    if not isinstance(paths, list):
        return []
    return [str(item) for item in paths if isinstance(item, str) and item.strip()]


def register_project_root(register: dict) -> Path | None:
    value = register.get("project_root")
    if not isinstance(value, str) or not value.strip():
        return None

    path = Path(value).expanduser()
    return path if path.is_dir() else None


def load_fake_completion_scanner():
    script_path = Path(__file__).with_name("fake-completion-scan.py")
    if not script_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("fake_completion_scan", script_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_existing_scan_path(
    raw_path: str,
    task_dir: Path,
    *,
    project_root: Path | None = None,
) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        return path if path.is_file() else None

    roots = [
        root
        for root in (project_root, Path.cwd(), task_dir, task_dir / "context")
        if root
    ]
    for root in roots:
        candidate = root / path
        if candidate.is_file():
            return candidate
    return None


def fake_completion_status(
    task_dir: Path,
    register: dict,
    events: list[dict],
    result_text: str,
) -> dict:
    raw_paths = (
        register_modified_paths(register)
        + implementer_event_file_paths(events)
        + result_changed_paths(result_text)
    )
    project_root = register_project_root(register)
    resolved_paths = []
    seen = set()
    for raw_path in raw_paths:
        resolved = resolve_existing_scan_path(str(raw_path), task_dir, project_root=project_root)
        if resolved is None:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        resolved_paths.append(resolved)

    scanner = load_fake_completion_scanner()
    if scanner is None:
        return {
            "status": "skipped",
            "reason": "scanner_missing",
            "scanned": [],
            "findings": [],
        }

    report = scanner.scan_paths(resolved_paths)
    report["required"] = bool(resolved_paths)
    return report


def has_test_file_evidence(events: list[dict], result_text: str) -> bool:
    paths = event_file_paths(events) + result_changed_paths(result_text)
    return any(looks_like_test_file(path) for path in paths)


def finding_ref(finding: dict, index: int) -> str:
    value = finding.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"index:{index}"


def text_present(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def value_present(value) -> bool:
    if text_present(value):
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def finding_status(finding: dict) -> str:
    value = finding.get("status")
    return value.strip().lower() if isinstance(value, str) else ""


def has_target_value(value) -> bool:
    if text_present(value):
        return True
    return isinstance(value, list) and any(text_present(item) for item in value)


def has_exception_value(value) -> bool:
    if text_present(value):
        return True
    if isinstance(value, dict):
        reason = value.get("reason") or value.get("detail") or value.get("evidence")
        return text_present(reason)
    return False


def finding_has_test_mapping(finding: dict) -> bool:
    verification = finding.get("verification")
    candidates = [finding]
    if isinstance(verification, dict):
        candidates.append(verification)

    for candidate in candidates:
        if any(has_target_value(candidate.get(key)) for key in FINDING_TEST_TARGET_KEYS):
            return True
        if any(has_exception_value(candidate.get(key)) for key in FINDING_EXCEPTION_KEYS):
            return True

    return False


def finding_has_owner_or_followup(finding: dict) -> bool:
    for key in ("owner", "follow_up", "follow_up_issue", "follow_up_url", "resolution_note"):
        if value_present(finding.get(key)):
            return True

    resolution = finding.get("resolution")
    return isinstance(resolution, dict) and any(
        value_present(resolution.get(key))
        for key in ("owner", "follow_up", "follow_up_issue", "note")
    )


def finding_register_payload(path: Path) -> tuple[list[dict], list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], ["malformed_finding_register_json"]
    except Exception:
        return [], ["unreadable_finding_register"]

    findings = payload
    if isinstance(payload, dict):
        schema_version = payload.get("schema_version")
        if schema_version != 1 or isinstance(schema_version, bool):
            return [], ["invalid_finding_register_schema_version"]
        findings = payload.get("findings")
    if not isinstance(findings, list):
        return [], ["finding_register_findings_not_list"]
    if not all(isinstance(item, dict) for item in findings):
        return [], ["finding_register_entries_not_object"]

    return findings, []


def finding_register_status(task_dir: Path) -> dict:
    path = task_dir / "context" / "finding-register.json"
    if not path.is_file():
        return {
            "present": False,
            "valid": True,
            "errors": [],
            "count": 0,
            "open_ids": [],
            "terminal_count": 0,
            "missing_required_field_ids": [],
            "unknown_status_ids": [],
            "missing_test_mapping_ids": [],
            "missing_owner_or_followup_ids": [],
        }

    findings, errors = finding_register_payload(path)
    missing_required_field_ids: list[str] = []
    unknown_status_ids: list[str] = []
    open_ids: list[str] = []
    missing_test_mapping_ids: list[str] = []
    missing_owner_or_followup_ids: list[str] = []
    terminal_count = 0
    for index, finding in enumerate(findings):
        ref = finding_ref(finding, index)
        missing_fields = [
            field for field in FINDING_REQUIRED_FIELDS
            if field not in finding or finding[field] in ("", None, [], {})
        ]
        if missing_fields:
            missing_required_field_ids.append(ref)

        status = finding_status(finding)
        if status == "open":
            open_ids.append(ref)
        elif status in FINDING_TERMINAL_STATUSES:
            terminal_count += 1
        else:
            unknown_status_ids.append(ref)

        if not finding_has_test_mapping(finding):
            missing_test_mapping_ids.append(ref)
        if (
            status in FINDING_OWNER_STATUSES
            and not finding_has_owner_or_followup(finding)
        ):
            missing_owner_or_followup_ids.append(ref)

    return {
        "present": True,
        "valid": not errors and not missing_required_field_ids and not unknown_status_ids,
        "errors": sorted(set(errors)),
        "count": len(findings),
        "open_ids": open_ids,
        "terminal_count": terminal_count,
        "missing_required_field_ids": missing_required_field_ids,
        "unknown_status_ids": unknown_status_ids,
        "missing_test_mapping_ids": missing_test_mapping_ids,
        "missing_owner_or_followup_ids": missing_owner_or_followup_ids,
    }


def _utc_now_iso() -> str:
    """Return a UTC timestamp in ISO-8601 form with trailing Z."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def auto_record_minor_findings(
    register_path: Path | str,
    findings: list[dict],
) -> list[dict]:
    """Upsert MINOR findings into ``finding-register.json`` as ``deferred-minor``.

    This helper is invoked by the reviewer's Step 4.5 MINOR auto-promotion flow
    when the only findings in the review are MINOR severity. It is intentionally
    pure-Python and provider-neutral so the reviewer can call it from any host.

    For each entry in ``findings`` the helper:

    * Loads the existing register (or creates an empty schema-versioned payload).
    * Locates an existing finding by ``id`` and updates it in place when found,
      otherwise appends a new entry.
    * Forces ``status="deferred-minor"`` and ``severity="P3"`` on every upserted
      entry — the MINOR -> deferred-minor mapping is the contract.
    * Fills sensible defaults for ``owner`` and timestamp fields when missing
      so the persisted entry is well-formed without requiring the caller to
      compute them.

    Args:
        register_path: Path to ``finding-register.json``. Created if missing.
        findings: List of MINOR findings the reviewer wants to defer. Each
            entry SHOULD carry at least an ``id``, ``title``, ``affected``,
            ``recommended_fix``, and ``source``. Missing fields receive defaults.

    Returns:
        The updated list of findings persisted to disk.
    """
    path = Path(register_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {"schema_version": 1, "findings": []}
    else:
        payload = {"schema_version": 1, "findings": []}

    if not isinstance(payload, dict):
        payload = {"schema_version": 1, "findings": []}
    payload.setdefault("schema_version", 1)
    existing = payload.get("findings")
    if not isinstance(existing, list):
        existing = []
    payload["findings"] = existing

    now = _utc_now_iso()

    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        merged = dict(finding)
        merged["status"] = "deferred-minor"
        merged["severity"] = "P3"
        merged.setdefault("owner", "auto-promoted")
        merged.setdefault("created_at", now)
        merged["last_updated_at"] = now

        finding_id = merged.get("id")
        match_index = None
        if isinstance(finding_id, str) and finding_id.strip():
            for idx, candidate in enumerate(existing):
                if isinstance(candidate, dict) and candidate.get("id") == finding_id:
                    match_index = idx
                    break

        if match_index is None:
            existing.append(merged)
        else:
            updated = dict(existing[match_index])
            updated.update(merged)
            existing[match_index] = updated

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return existing


def looks_mutating_task(text: str) -> bool:
    value = text or ""
    if KOREAN_PLAN_EXECUTION_RE.search(value):
        return True
    if GERUND_MUTATING_TASK_RE.search(value):
        return True
    if KOREAN_TEST_EXECUTION_RE.search(value):
        return True

    constrained_value = NON_MUTATING_CONSTRAINT_RE.sub("", value)
    read_only_query_value = READ_ONLY_HISTORY_QUERY_RE.sub("", constrained_value)
    read_only_query_value = READ_ONLY_METHOD_LEARNING_RE.sub("", read_only_query_value)
    if (
        read_only_query_value != constrained_value
        and not STRONG_MUTATING_TASK_RE.search(read_only_query_value)
    ):
        return False

    has_read_only_signal = bool(
        READ_ONLY_TASK_RE.search(value)
        or KOREAN_PLAN_ONLY_CONTEXT_RE.search(value)
        or READ_ONLY_HISTORY_QUERY_RE.search(value)
        or READ_ONLY_METHOD_LEARNING_RE.search(value)
    )
    if has_read_only_signal:
        constrained_value = REVIEW_OUTPUT_SECTION_LABEL_RE.sub("", constrained_value)
        constrained_value = KOREAN_NON_MUTATING_CONSTRAINT_RE.sub("", constrained_value)
        constrained_value = KOREAN_READ_ONLY_BACKGROUND_RE.sub("", constrained_value)
        constrained_value = KOREAN_READ_ONLY_COMPLAINT_RE.sub("", constrained_value)
        constrained_value = KOREAN_READ_ONLY_EXPLORATION_RE.sub("", constrained_value)
        constrained_value = KOREAN_PLAN_ONLY_CONTEXT_RE.sub("", constrained_value)
        constrained_value = READ_ONLY_HISTORY_QUERY_RE.sub("", constrained_value)
        constrained_value = READ_ONLY_METHOD_LEARNING_RE.sub("", constrained_value)
    if has_read_only_signal and not STRONG_MUTATING_TASK_RE.search(constrained_value):
        return False
    return bool(MUTATING_TASK_RE.search(constrained_value))


def strip_high_risk_negative_constraints(text: str) -> str:
    value = " ".join((text or "").strip().lower().split())

    def strip_english_action(match: re.Match[str]) -> str:
        body = HIGH_RISK_TASK_RE.sub(" ", match.group("body"))
        return f" {body} "

    value = HIGH_RISK_NEGATED_CLAUSE_RE.sub(strip_english_action, value)
    value = KOREAN_HIGH_RISK_NEGATED_ACTION_RE.sub(" ", value)
    value = HIGH_RISK_GOVERNANCE_CONTEXT_RE.sub(" ", value)
    return " ".join(value.split())


def quality_gate_risk_level(task: str, result_text: str) -> str:
    if AUTO_COMPLETION_RE.search(result_text or ""):
        return "high"
    if HIGH_RISK_TASK_RE.search(strip_high_risk_negative_constraints(task)):
        return "high"
    return "standard"


def classify_quality_failures(
    failures: list[str],
    *,
    strict_gate_required: bool,
) -> tuple[list[str], list[str]]:
    unique = sorted(set(failures))
    if strict_gate_required:
        return unique, []

    hard = [failure for failure in unique if failure not in SOFT_QUALITY_FAILURES]
    soft = [failure for failure in unique if failure in SOFT_QUALITY_FAILURES]
    return hard, soft


def stage_agents(stage) -> list[str]:
    if isinstance(stage, str):
        return [stage]
    if isinstance(stage, list):
        return [str(agent) for agent in stage]
    if isinstance(stage, dict):
        agents = stage.get("agents") or []
        if isinstance(agents, list):
            return [str(agent) for agent in agents]
    return []


def is_implementer_agent(agent: str) -> bool:
    name = agent.split(":", 1)[0].strip()
    return bool(name) and name not in NON_IMPLEMENTER_AGENTS


def stage_implementer_agents(stage) -> list[str]:
    return [agent for agent in stage_agents(stage) if is_implementer_agent(agent)]


def is_implementation_stage(stage) -> bool:
    return bool(stage_implementer_agents(stage))


def is_reviewer_stage(stage) -> bool:
    return "reviewer" in stage_agents(stage)


def is_single_reviewer_stage(stage) -> bool:
    return stage_agents(stage) == ["reviewer"]


def is_qa_verify_stage(stage) -> bool:
    return (
        isinstance(stage, dict)
        and stage_agents(stage) == ["qa-owner"]
        and str(stage.get("qa_mode", "")).lower() == "verify"
    )


def is_qa_plan_stage(stage) -> bool:
    return (
        isinstance(stage, dict)
        and stage_agents(stage) == ["qa-owner"]
        and str(stage.get("qa_mode", "")).lower() == "plan"
    )


def has_quality_gate_after_implementer(stages: list, idx: int) -> bool:
    if idx + 1 >= len(stages):
        return False
    if is_single_reviewer_stage(stages[idx + 1]):
        return True
    return (
        is_qa_verify_stage(stages[idx + 1])
        and idx + 2 < len(stages)
        and is_single_reviewer_stage(stages[idx + 2])
    )


def is_tdd_capable_stage(stage) -> bool:
    agents = stage_agents(stage)
    if "test-writer" in agents:
        return True
    return (
        isinstance(stage, dict)
        and bool(stage.get("tdd_parallel"))
        and len(stage_implementer_agents(stage)) == 1
    )


def pipeline_shape(pipeline: dict) -> dict:
    stages = pipeline.get("stages") or []
    implementer_indexes = [idx for idx, stage in enumerate(stages) if is_implementation_stage(stage)]
    reviewer_indexes = [idx for idx, stage in enumerate(stages) if is_reviewer_stage(stage)]
    qa_plan_indexes = [idx for idx, stage in enumerate(stages) if is_qa_plan_stage(stage)]
    qa_verify_indexes = [idx for idx, stage in enumerate(stages) if is_qa_verify_stage(stage)]
    tdd_indexes = [idx for idx, stage in enumerate(stages) if is_tdd_capable_stage(stage)]
    implementer_indexes_without_immediate_reviewer = [
        idx for idx in implementer_indexes
        if idx + 1 >= len(stages) or not is_single_reviewer_stage(stages[idx + 1])
    ]
    implementer_indexes_without_quality_gate = [
        idx for idx in implementer_indexes
        if not has_quality_gate_after_implementer(stages, idx)
    ]
    qa_verify_indexes_without_following_reviewer = [
        idx for idx in qa_verify_indexes
        if idx + 1 >= len(stages) or not is_single_reviewer_stage(stages[idx + 1])
    ]

    reviewer_after_implementer = any(
        reviewer_idx > implementer_idx
        for reviewer_idx in reviewer_indexes
        for implementer_idx in implementer_indexes
    )
    return {
        "stage_count": len(stages),
        "implementer_indexes": implementer_indexes,
        "reviewer_indexes": reviewer_indexes,
        "qa_plan_indexes": qa_plan_indexes,
        "qa_verify_indexes": qa_verify_indexes,
        "tdd_indexes": tdd_indexes,
        "has_implementation_stage": bool(implementer_indexes),
        "has_reviewer_stage": bool(reviewer_indexes),
        "has_qa_plan_stage": bool(qa_plan_indexes),
        "has_qa_verify_stage": bool(qa_verify_indexes),
        "has_tdd_stage": bool(tdd_indexes),
        "has_reviewer_after_implementer": reviewer_after_implementer,
        "implementer_indexes_without_immediate_reviewer": implementer_indexes_without_immediate_reviewer,
        "has_reviewer_after_each_implementer": not implementer_indexes_without_immediate_reviewer,
        "implementer_indexes_without_quality_gate": implementer_indexes_without_quality_gate,
        "has_quality_gate_after_each_implementer": not implementer_indexes_without_quality_gate,
        "qa_verify_indexes_without_following_reviewer": qa_verify_indexes_without_following_reviewer,
        "has_reviewer_after_each_qa_verify": not qa_verify_indexes_without_following_reviewer,
    }


def event_text(row: dict) -> str:
    return " ".join(
        str(row.get(key, ""))
        for key in ("event", "status", "agent", "detail")
    )


def event_is_implementer_done(row: dict) -> bool:
    agent = str(row.get("agent", ""))
    return (
        is_implementer_agent(agent)
        and str(row.get("status", "")).lower() == "completed"
        and str(row.get("event", "")).startswith("STAGE")
    )


def event_is_tdd_done(row: dict) -> bool:
    agent = str(row.get("agent", ""))
    status = str(row.get("status", "")).lower()
    if agent == "test-writer" and status == "completed":
        return True
    return bool(TDD_EVENT_RE.search(event_text(row)))


def event_quality_metrics_path(row: dict) -> str:
    match = QUALITY_METRICS_RE.search(event_text(row))
    return match.group(1).strip() if match else ""


def resolve_event_quality_metrics_path(path_text: str, task_dir: Path | None) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    if task_dir is None:
        return None
    if path_text.startswith("context/"):
        return task_dir / path_text
    return task_dir / path.name


def quality_metrics_schema_errors(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["malformed_quality_metrics_json"]
    except Exception:
        return ["unreadable_quality_metrics_artifact"]

    if not isinstance(payload, dict):
        return ["quality_metrics_not_object"]

    allowed_fields = {
        "schema_version",
        "hallucination_detected",
        "rollback_performed",
        "human_intervention_required",
        "factuality_review",
        "evidence_paths",
        "notes",
    }
    errors: list[str] = []
    if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
        errors.append("invalid_quality_metrics_schema_version")

    unexpected = sorted(set(payload) - allowed_fields)
    if unexpected:
        errors.append("unexpected_quality_metrics_fields")

    for key in ("hallucination_detected", "rollback_performed", "human_intervention_required"):
        if key in payload and not isinstance(payload[key], bool):
            errors.append(f"invalid_quality_metrics_{key}")

    if "factuality_review" in payload and payload["factuality_review"] not in {
        "not_applicable",
        "passed",
        "failed",
        "inconclusive",
    }:
        errors.append("invalid_quality_metrics_factuality_review")

    if "evidence_paths" in payload:
        evidence_paths = payload["evidence_paths"]
        if not isinstance(evidence_paths, list) or not all(isinstance(item, str) for item in evidence_paths):
            errors.append("invalid_quality_metrics_evidence_paths")

    if "notes" in payload and not isinstance(payload["notes"], str):
        errors.append("invalid_quality_metrics_notes")

    return errors


def event_quality_metrics_errors(row: dict, task_dir: Path | None = None) -> list[str]:
    path_text = event_quality_metrics_path(row)
    if not path_text:
        return ["missing_quality_metrics_pointer"]
    resolved = resolve_event_quality_metrics_path(path_text, task_dir)
    if resolved is None:
        return []
    if not resolved.is_file():
        return ["missing_quality_metrics_artifact"]
    return quality_metrics_schema_errors(resolved)


def event_has_quality_metrics(row: dict, task_dir: Path | None = None) -> bool:
    return not event_quality_metrics_errors(row, task_dir)


def event_is_reviewer_approved(row: dict, task_dir: Path | None = None) -> bool:
    agent = str(row.get("agent", ""))
    text = event_text(row)
    approved = (
        (agent == "reviewer" and bool(REVIEW_APPROVED_RE.search(text)))
        or "STAGE_STREAMING_REVIEW_DONE" in text and "final_verdict=ok" in text
    )
    return approved and event_has_quality_metrics(row, task_dir)


def event_is_reviewer_rejected(row: dict) -> bool:
    agent = str(row.get("agent", ""))
    text = event_text(row)
    if "MODE=test-checklist" in text or "CHECKLIST_REVIEW_RESULT" in text:
        return False
    return (
        agent == "reviewer" and bool(REVIEW_REJECTED_RE.search(text))
    ) or "reviewer_rejected" in text


def skill_content_audit_script() -> Path:
    return Path(__file__).resolve().with_name("skill-content-audit.py")


def skill_content_audit_status(task_dir: Path) -> dict:
    artifact_path = task_dir / "context" / "skill-content-audit.json"
    relative_artifact = "context/skill-content-audit.json"
    script = skill_content_audit_script()
    status = {
        "required": False,
        "passed": False,
        "artifact": relative_artifact,
        "script": str(script),
        "errors": [],
        "inventory_count": 0,
        "effective_followup_count": 0,
        "shallow_finding_count": 0,
    }
    if not script.is_file():
        status["errors"].append("missing_skill_content_audit_script")
        return status

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--format",
            "json",
            "--output",
            str(artifact_path),
        ],
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        status["errors"].append("skill_content_audit_failed")
        if completed.stderr.strip():
            (task_dir / "context" / "skill-content-audit.stderr.txt").write_text(
                completed.stderr.strip() + "\n",
                encoding="utf-8",
            )

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        status["errors"].append("missing_skill_content_audit_artifact")
        return status
    except json.JSONDecodeError:
        status["errors"].append("invalid_skill_content_audit_artifact")
        return status
    except Exception:
        status["errors"].append("unreadable_skill_content_audit_artifact")
        return status

    inventory = payload.get("inventory") if isinstance(payload, dict) else None
    followups = payload.get("effective_followups") if isinstance(payload, dict) else None
    shallow = payload.get("shallow_findings") if isinstance(payload, dict) else None
    contracts = payload.get("content_contracts") if isinstance(payload, dict) else None
    status["inventory_count"] = len(inventory) if isinstance(inventory, list) else 0
    status["effective_followup_count"] = len(followups) if isinstance(followups, list) else 0
    status["shallow_finding_count"] = len(shallow) if isinstance(shallow, list) else 0
    contract_failures = [
        name
        for name, contract in (contracts or {}).items()
        if isinstance(contract, dict) and not contract.get("passed")
    ]
    if contract_failures:
        status["errors"].append("skill_content_audit_contract_failed")
        status["contract_failures"] = sorted(contract_failures)
    if not isinstance(inventory, list) or not inventory:
        status["errors"].append("missing_skill_content_audit_inventory")
    if not isinstance(followups, list):
        status["errors"].append("missing_skill_content_audit_effective_followups")

    status["errors"] = sorted(set(status["errors"]))
    status["passed"] = not status["errors"]
    return status


def event_stage(row: dict) -> int | None:
    try:
        return int(row.get("stage"))
    except Exception:
        return None


def event_attempt(row: dict) -> int:
    try:
        return int(row.get("attempt"))
    except Exception:
        return 0


def reviewer_rework_target_stage(pipeline: dict, reviewer_stage: int | None) -> int | None:
    if not reviewer_stage:
        return None
    stages = pipeline.get("stages") or []
    reviewer_idx = reviewer_stage - 1
    previous_idx = reviewer_idx - 1
    if previous_idx < 0 or previous_idx >= len(stages):
        return None
    if is_implementation_stage(stages[previous_idx]):
        return previous_idx + 1
    if is_qa_verify_stage(stages[previous_idx]):
        implementation_idx = previous_idx - 1
        if implementation_idx >= 0 and is_implementation_stage(stages[implementation_idx]):
            return implementation_idx + 1
    return previous_idx + 1 if reviewer_stage > 1 else None


def task_description(task_dir: Path, register: dict, pipeline: dict, result_text: str) -> str:
    if register.get("task"):
        return str(register["task"])
    if pipeline.get("task"):
        return str(pipeline["task"])
    match = re.search(r"^#\s+(.+)$", result_text, re.M)
    return match.group(1) if match else ""


def is_completed(target_status: str | None, register: dict, result_text: str) -> bool:
    if target_status is not None:
        return target_status == "completed"
    return register.get("current_phase") == "completed" or bool(STATUS_COMPLETED_RE.search(result_text))


def human_acceptance_matrix_status(task_dir: Path) -> dict:
    markdown = task_dir / "context" / "human-acceptance-matrix.md"
    payload = task_dir / "context" / "human-acceptance-matrix.json"
    paths = [
        relative_evidence_name(task_dir, path)
        for path in (markdown, payload)
        if path.is_file()
    ]

    return {
        "required": False,
        "present": bool(paths),
        "paths": paths,
    }


def evaluation_metrics_status(task_dir: Path) -> dict:
    path = task_dir / "context" / "evaluation-metrics.json"
    if not path.is_file():
        return {
            "required": False,
            "present": False,
            "errors": [],
            "path": relative_evidence_name(task_dir, path),
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "required": False,
            "present": True,
            "errors": ["malformed_evaluation_metrics_json"],
            "path": relative_evidence_name(task_dir, path),
        }
    except Exception:
        return {
            "required": False,
            "present": True,
            "errors": ["unreadable_evaluation_metrics"],
            "path": relative_evidence_name(task_dir, path),
        }

    errors: list[str] = []
    if not isinstance(payload, dict):
        errors.append("evaluation_metrics_not_object")
    else:
        if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
            errors.append("invalid_evaluation_metrics_schema_version")
        for key in ("command", "status"):
            if not text_present(payload.get(key)):
                errors.append(f"missing_evaluation_metrics_{key}")

    return {
        "required": False,
        "present": True,
        "errors": errors,
        "path": relative_evidence_name(task_dir, path),
    }


def delegation_fidelity_status(task_dir: Path) -> dict:
    delegation_events = load_jsonl(task_dir / "delegation.jsonl")
    tool_events = load_jsonl(task_dir / "tool-events.jsonl")

    return {
        "required": False,
        "delegation_events": len(delegation_events),
        "tool_events": len(tool_events),
        "has_delegation": bool(delegation_events),
        "has_tool_events": bool(tool_events),
    }


def rejection_followups(events: list[dict], rejected_index: int, pipeline: dict | None = None) -> dict:
    rejected = events[rejected_index]
    rejected_stage = event_stage(rejected)
    rejected_attempt = event_attempt(rejected)
    target_stage = reviewer_rework_target_stage(pipeline or {}, rejected_stage)
    later = events[rejected_index + 1:]
    implementer_candidates = [
        (idx, row)
        for idx, row in enumerate(later)
        if event_is_implementer_done(row)
        and (target_stage is None or event_stage(row) == target_stage)
        and event_attempt(row) > rejected_attempt
    ]
    tdd_candidates = [
        (idx, row)
        for idx, row in enumerate(later)
        if event_is_tdd_done(row)
        and (target_stage is None or event_stage(row) == target_stage)
        and event_attempt(row) > rejected_attempt
    ]
    approval_candidates = [
        (idx, row)
        for idx, row in enumerate(later)
        if event_is_reviewer_approved(row, None)
        and (rejected_stage is None or event_stage(row) == rejected_stage)
        and event_attempt(row) > rejected_attempt
    ]
    implementer_index = next(
        (idx for idx, _row in implementer_candidates),
        None,
    )
    tdd_index = next(
        (idx for idx, _row in tdd_candidates),
        None,
    )
    approval_index = next(
        (idx for idx, _row in approval_candidates),
        None,
    )
    ordered = (
        implementer_index is not None
        and tdd_index is not None
        and approval_index is not None
        and approval_index > max(implementer_index, tdd_index)
    )
    return {
        "implementer_retry": implementer_index is not None,
        "tdd_retry": tdd_index is not None,
        "reviewer_reapproval": approval_index is not None,
        "ordered": ordered,
        "rejected_stage": rejected_stage,
        "rejected_attempt": rejected_attempt,
        "target_implementation_stage": target_stage,
    }


def quality_coverage_dimension(name: str, points: int, checks: list[tuple[str, bool]]) -> dict:
    if not checks:
        return {
            "name": name,
            "points": points,
            "earned": points,
            "passed": True,
            "checks": [],
        }

    passed_count = sum(1 for _name, passed in checks if passed)
    earned = points if passed_count == len(checks) else round(points * passed_count / len(checks))

    return {
        "name": name,
        "points": points,
        "earned": earned,
        "passed": earned == points,
        "checks": [
            {"name": check_name, "passed": bool(passed)}
            for check_name, passed in checks
        ],
    }


def quality_coverage_status(
    *,
    required: bool,
    hard_failures: list[str],
    soft_failures: list[str],
    pipeline: dict,
    shape: dict,
    events: list[dict],
    result_text: str,
    task_dir: Path,
    valid_approval_events: list[dict],
    approval_metric_errors: list[str],
    test_checklist: dict,
    finding_register: dict,
    delegation_fidelity: dict,
    human_acceptance: dict,
    evaluation_metrics: dict,
    fake_completion: dict,
    skill_content_audit: dict,
) -> dict:
    threshold = 80
    max_score = 100
    if not required:
        return {
            "required": False,
            "score": max_score,
            "max_score": max_score,
            "threshold": threshold,
            "passed_threshold": True,
            "hard_blockers": [],
            "warnings": [],
            "dimensions": [],
        }

    if pipeline:
        pipeline_shape_checks = [
            ("pipeline_present", True),
            ("implementation_stage", shape["has_implementation_stage"]),
            ("tdd_stage", shape["has_tdd_stage"]),
            ("reviewer_stage", shape["has_reviewer_stage"]),
            ("reviewer_after_implementer", shape["has_reviewer_after_implementer"]),
            ("reviewer_after_each_implementer", shape["has_quality_gate_after_each_implementer"]),
            ("reviewer_after_qa_verify", shape["has_reviewer_after_each_qa_verify"]),
        ]
    else:
        pipeline_shape_checks = [
            ("pipeline_present", False),
            ("implementation_stage", False),
            ("tdd_stage", False),
            ("reviewer_stage", False),
            ("reviewer_after_implementer", False),
            ("reviewer_after_each_implementer", False),
            ("reviewer_after_qa_verify", False),
        ]

    tdd_required = bool(shape["has_tdd_stage"])
    checklist_required = bool(test_checklist.get("required"))
    has_valid_review = bool(valid_approval_events)
    invalid_metric_errors = [
        error for error in approval_metric_errors
        if error.startswith("invalid_") or error in {
            "malformed_quality_metrics_json",
            "quality_metrics_not_object",
            "unexpected_quality_metrics_fields",
            "unreadable_quality_metrics_artifact",
        }
    ]
    dimensions = [
        quality_coverage_dimension("pipeline_shape", 20, pipeline_shape_checks),
        quality_coverage_dimension(
            "pipeline_events",
            20,
            [
                ("progress_events", bool(events)),
                ("implementer_completion", any(event_is_implementer_done(row) for row in events)),
                ("tdd_completion", any(event_is_tdd_done(row) for row in events)),
                ("reviewer_approval", has_valid_review),
            ],
        ),
        quality_coverage_dimension(
            "tdd_evidence",
            20,
            [
                ("test_file_or_exception", (not tdd_required) or has_test_file_evidence(events, result_text) or has_tdd_exception(task_dir)),
                ("red_or_exception", (not tdd_required) or has_tdd_red_or_exception(task_dir)),
                ("refactor_review", (not tdd_required) or has_tdd_refactor_evidence(task_dir)),
                ("test_checklist_workflow", (not checklist_required) or bool(test_checklist.get("valid"))),
            ],
        ),
        quality_coverage_dimension(
            "reviewer_evidence",
            20,
            [
                ("approval_with_quality_metrics", has_valid_review),
                ("quality_metrics_schema_valid", has_valid_review and not invalid_metric_errors),
            ],
        ),
        quality_coverage_dimension(
            "finding_register",
            10,
            [
                ("schema_valid", not finding_register["present"] or finding_register["valid"]),
                ("no_open_findings", not finding_register["open_ids"]),
                ("terminal_findings_have_tests", not finding_register["missing_test_mapping_ids"]),
                ("scope_status_has_owner_or_followup", not finding_register["missing_owner_or_followup_ids"]),
            ],
        ),
        quality_coverage_dimension(
            "optional_gates",
            5,
            [
                (
                    "delegation_fidelity",
                    (not delegation_fidelity["required"])
                    or (delegation_fidelity["has_delegation"] and delegation_fidelity["has_tool_events"]),
                ),
                ("human_acceptance", (not human_acceptance["required"]) or human_acceptance["present"]),
                ("evaluation_metrics", (not evaluation_metrics["required"]) or (evaluation_metrics["present"] and not evaluation_metrics["errors"])),
                ("fake_completion_scan", not fake_completion.get("findings")),
            ],
        ),
        quality_coverage_dimension(
            "skill_content_audit",
            5,
            [
                ("audit_executed", bool(skill_content_audit.get("artifact")) and not any(
                    error in skill_content_audit.get("errors", [])
                    for error in {
                        "missing_skill_content_audit_script",
                        "missing_skill_content_audit_artifact",
                        "invalid_skill_content_audit_artifact",
                        "unreadable_skill_content_audit_artifact",
                    }
                )),
                ("audit_passed", bool(skill_content_audit.get("passed"))),
                ("inventory_present", int(skill_content_audit.get("inventory_count") or 0) > 0),
                ("effective_followups_present", int(skill_content_audit.get("effective_followup_count") or 0) > 0),
            ],
        ),
    ]
    score = min(max_score, sum(dimension["earned"] for dimension in dimensions))

    return {
        "required": True,
        "score": score,
        "max_score": max_score,
        "threshold": threshold,
        "passed_threshold": score >= threshold,
        "hard_blockers": sorted(set(hard_failures)),
        "warnings": sorted(set(soft_failures)),
        "dimensions": dimensions,
    }


def quality_coverage_gaps(coverage: dict) -> list[str]:
    gaps: list[str] = []
    for dimension in coverage.get("dimensions", []):
        dimension_name = str(dimension.get("name") or "unknown")
        for check in dimension.get("checks", []):
            if not check.get("passed"):
                gaps.append(f"{dimension_name}.{check.get('name')}")
    for warning in coverage.get("warnings", []):
        label = f"warning.{warning}"
        if label not in gaps:
            gaps.append(label)
    for blocker in coverage.get("hard_blockers", []):
        label = f"hard_blocker.{blocker}"
        if label not in gaps:
            gaps.append(label)
    return sorted(gaps)


def quality_coverage_decision(coverage: dict, *, strict_gate_required: bool) -> dict:
    required = bool(coverage.get("required"))
    score = int(coverage.get("score") or 0)
    max_score = int(coverage.get("max_score") or 100)
    threshold = int(coverage.get("threshold") or 80)
    passed_threshold = bool(coverage.get("passed_threshold"))
    hard_blockers = list(coverage.get("hard_blockers") or [])
    gaps = quality_coverage_gaps(coverage)

    if not required:
        return {
            "required": False,
            "decision_required": False,
            "score": score,
            "max_score": max_score,
            "threshold": threshold,
            "options": [],
            "recommended": "",
            "gaps": gaps,
        }

    if strict_gate_required or hard_blockers:
        return {
            "required": True,
            "decision_required": False,
            "score": score,
            "max_score": max_score,
            "threshold": threshold,
            "options": ["fix-gaps", "strict-100"],
            "recommended": "fix-gaps",
            "gaps": gaps,
        }

    if passed_threshold and score < max_score and gaps:
        return {
            "required": True,
            "decision_required": True,
            "score": score,
            "max_score": max_score,
            "threshold": threshold,
            "options": ["proceed", "fix-gaps", "strict-100"],
            "recommended": "proceed",
            "gaps": gaps,
        }

    if passed_threshold:
        return {
            "required": True,
            "decision_required": False,
            "score": score,
            "max_score": max_score,
            "threshold": threshold,
            "options": ["proceed"],
            "recommended": "proceed",
            "gaps": gaps,
        }

    return {
        "required": True,
        "decision_required": False,
        "score": score,
        "max_score": max_score,
        "threshold": threshold,
        "options": ["fix-gaps", "strict-100"],
        "recommended": "fix-gaps",
        "gaps": gaps,
    }


def check_quality_loop(
    task_dir: Path,
    *,
    target_status: str | None = None,
    require_rework_cycle: bool = False,
) -> dict:
    task_dir = Path(task_dir)
    register = load_json(task_dir / "register.json")
    pipeline = load_json(task_dir / "pipeline.json")
    result_text = load_text(task_dir / "result.md")
    task = task_description(task_dir, register, pipeline, result_text)
    completed = is_completed(target_status, register, result_text)
    bypassed = bool(QUALITY_BYPASS_RE.search(result_text))
    required = completed and looks_mutating_task(task) and not bypassed

    shape = pipeline_shape(pipeline)
    events = load_jsonl(task_dir / "progress.buffer.jsonl")
    rejection_indexes = [
        idx for idx, row in enumerate(events) if event_is_reviewer_rejected(row)
    ]
    followups = [
        {"event_index": idx, **rejection_followups(events, idx, pipeline)}
        for idx in rejection_indexes
    ]
    approved_events = [
        row for row in events
        if str(row.get("agent", "")) == "reviewer"
        and bool(REVIEW_APPROVED_RE.search(event_text(row)))
    ]
    valid_approval_events = [
        row for row in approved_events
        if event_is_reviewer_approved(row, task_dir)
    ]
    approval_metric_errors = [
        error
        for row in approved_events
        for error in event_quality_metrics_errors(row, task_dir)
    ]
    test_checklist = test_checklist_status(task_dir)
    finding_register = finding_register_status(task_dir)
    delegation_fidelity = delegation_fidelity_status(task_dir)
    human_acceptance = human_acceptance_matrix_status(task_dir)
    evaluation_metrics = evaluation_metrics_status(task_dir)
    fake_completion = fake_completion_status(task_dir, register, events, result_text)
    skill_audit = skill_content_audit_status(task_dir) if required else {
        "required": False,
        "passed": True,
        "artifact": "context/skill-content-audit.json",
        "script": str(skill_content_audit_script()),
        "errors": [],
        "inventory_count": 0,
        "effective_followup_count": 0,
        "shallow_finding_count": 0,
    }
    delegation_required = bool(pipeline.get("requires_delegation_fidelity"))
    human_acceptance_required = bool(pipeline.get("requires_human_acceptance"))
    evaluation_required = bool(pipeline.get("eval_command"))
    delegation_fidelity["required"] = delegation_required
    human_acceptance["required"] = human_acceptance_required
    evaluation_metrics["required"] = evaluation_required
    skill_audit["required"] = required
    test_checklist_required = bool(shape["has_tdd_stage"] and not has_tdd_exception(task_dir))
    test_checklist["required"] = test_checklist_required

    failures: list[str] = []
    if required:
        if not pipeline:
            failures.append("missing_pipeline")
        if not shape["has_implementation_stage"]:
            failures.append("missing_pipeline_implementation_stage")
        if not shape["has_tdd_stage"]:
            failures.append("missing_pipeline_tdd_stage")
        if not shape["has_reviewer_stage"]:
            failures.append("missing_pipeline_reviewer_stage")
        if not shape["has_reviewer_after_implementer"]:
            failures.append("missing_pipeline_reviewer_after_implementer")
        if not shape["has_quality_gate_after_each_implementer"]:
            failures.append("missing_pipeline_reviewer_after_each_implementer")
        if not shape["has_reviewer_after_each_qa_verify"]:
            failures.append("missing_pipeline_reviewer_after_qa_verify")
        if not events:
            failures.append("missing_progress_events")
        if events and not any(event_is_implementer_done(row) for row in events):
            failures.append("missing_pipeline_implementation_completion")
        if events and not any(event_is_tdd_done(row) for row in events):
            failures.append("missing_pipeline_tdd_event")
        if (
            shape["has_tdd_stage"]
            and not has_test_file_evidence(events, result_text)
            and not has_tdd_exception(task_dir)
        ):
            failures.append("missing_tdd_test_file")
        if shape["has_tdd_stage"] and not has_tdd_red_or_exception(task_dir):
            failures.append("missing_tdd_red_phase_evidence")
        if shape["has_tdd_stage"] and not has_tdd_refactor_evidence(task_dir):
            failures.append("missing_tdd_refactor_phase_evidence")
        if test_checklist_required:
            failures.extend(test_checklist["errors"])
        if events and approved_events and not valid_approval_events:
            failures.append("missing_reviewer_quality_metrics_artifact")
        if any(error.startswith("invalid_") or error in {
            "malformed_quality_metrics_json",
            "quality_metrics_not_object",
            "unexpected_quality_metrics_fields",
            "unreadable_quality_metrics_artifact",
        } for error in approval_metric_errors):
            failures.append("invalid_reviewer_quality_metrics_artifact")
        if finding_register["present"] and not finding_register["valid"]:
            failures.append("invalid_finding_register")
        if finding_register["open_ids"]:
            failures.append("unresolved_finding_register_entries")
        if finding_register["missing_test_mapping_ids"]:
            failures.append("missing_finding_test_mapping")
        if finding_register["missing_owner_or_followup_ids"]:
            failures.append("missing_finding_owner_or_followup")
        if delegation_required and not delegation_fidelity["has_delegation"]:
            failures.append("missing_delegation_fidelity_evidence")
        if delegation_required and not delegation_fidelity["has_tool_events"]:
            failures.append("missing_tool_event_fidelity_evidence")
        if human_acceptance_required and not human_acceptance["present"]:
            failures.append("missing_human_acceptance_matrix")
        if evaluation_required and not evaluation_metrics["present"]:
            failures.append("missing_evaluation_metrics")
        if evaluation_required and evaluation_metrics["errors"]:
            failures.extend(evaluation_metrics["errors"])
        if fake_completion.get("findings"):
            failures.append("fake_completion_markers_present")
        if not skill_audit["passed"]:
            failures.extend(skill_audit["errors"] or ["skill_content_audit_failed"])
        if events and not valid_approval_events:
            failures.append("missing_pipeline_reviewer_approval")
        if require_rework_cycle and not rejection_indexes:
            failures.append("missing_rework_cycle")
        if any(not item["ordered"] for item in followups):
            failures.append("missing_rework_after_review_rejection")

    unique_failures = sorted(set(failures))
    risk_level = quality_gate_risk_level(task, result_text)
    strict_gate_required = required and risk_level == "high"
    hard_failures, soft_failures = classify_quality_failures(
        unique_failures,
        strict_gate_required=strict_gate_required,
    )
    quality_coverage = quality_coverage_status(
        required=required,
        hard_failures=hard_failures,
        soft_failures=soft_failures,
        pipeline=pipeline,
        shape=shape,
        events=events,
        result_text=result_text,
        task_dir=task_dir,
        valid_approval_events=valid_approval_events,
        approval_metric_errors=approval_metric_errors,
        test_checklist=test_checklist,
        finding_register=finding_register,
        delegation_fidelity=delegation_fidelity,
        human_acceptance=human_acceptance,
        evaluation_metrics=evaluation_metrics,
        fake_completion=fake_completion,
        skill_content_audit=skill_audit,
    )
    quality_decision = quality_coverage_decision(
        quality_coverage,
        strict_gate_required=strict_gate_required,
    )
    if not required:
        quality_gate_mode = "bypassed" if bypassed else "not_required"
    elif strict_gate_required:
        quality_gate_mode = "strict"
    else:
        quality_gate_mode = "coverage"
    passed = (not required) or (
        not hard_failures and bool(quality_coverage.get("passed_threshold"))
    )

    return {
        "passed": passed,
        "required": required,
        "bypassed": bypassed,
        "risk_level": risk_level,
        "quality_gate_mode": quality_gate_mode,
        "strict_gate_required": strict_gate_required,
        "failures": unique_failures,
        "hard_failures": hard_failures,
        "soft_failures": soft_failures,
        "task": task,
        "quality_coverage": quality_coverage,
        "quality_decision": quality_decision,
        "fake_completion": fake_completion,
        "pipeline_shape": shape,
        "event_count": len(events),
        "rejection_indexes": rejection_indexes,
        "rejection_followups": followups,
        "implementer_event_count": sum(1 for row in events if event_is_implementer_done(row)),
        "tdd_event_count": sum(1 for row in events if event_is_tdd_done(row)),
        "reviewer_approval_count": len(valid_approval_events),
        "reviewer_approved_without_quality_metrics_count": len(approved_events) - len(valid_approval_events),
        "reviewer_quality_metrics_errors": sorted(set(approval_metric_errors)),
        "test_checklist": test_checklist,
        "finding_register": finding_register,
        "delegation_fidelity": delegation_fidelity,
        "human_acceptance": human_acceptance,
        "evaluation_metrics": evaluation_metrics,
        "skill_content_audit": skill_audit,
    }
