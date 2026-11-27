"""Validate the current source location of a project-context memory."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any


SWIFT_DECLARATION = re.compile(
    r'^\s*\((?:func|class|struct|enum|actor|protocol|type_alias|var)_decl\b'
    r'[^\n]*?\brange=\[[^\n]*?\]\s+"([^"\n]+)"', re.MULTILINE,
)
EVIDENCE_TAG_PREFIX = "evidence-sha256:"
EVIDENCE_FIELD = re.compile(r"^- Evidence:[ \t]*(.+)$", re.MULTILINE)
STRUCTURED_LESSON_FIELDS = re.compile(r"^- (Condition|Decision|Evidence):", re.MULTILINE)


def evidence_tags(tags: Any) -> list[str]:
    return [tag for tag in tags if isinstance(tag, str) and tag.startswith(EVIDENCE_TAG_PREFIX)] if isinstance(tags, list) else []


def project_evidence_tag(root: Path, note: Path, locator: str) -> str:
    filename, separator, line_number = locator.rpartition(":")
    if not separator or not filename or Path(filename).is_absolute() or not line_number.isdecimal():
        raise ValueError("Evidence는 프로젝트 상대 경로와 줄 번호로 작성해야 합니다.")
    number = int(line_number)
    if number < 1:
        raise ValueError("Evidence의 줄 번호는 1 이상이어야 합니다.")

    source = (root / filename).resolve(strict=True)
    source.relative_to(root)
    if source == note or not source.is_file():
        raise ValueError("Evidence는 교훈 문서와 별개인 프로젝트 원본 파일을 가리켜야 합니다.")

    digest = hashlib.sha256(locator.encode("utf-8") + b"\0")
    anchor_found = False
    with source.open("rb") as stream:
        for index, line in enumerate(stream, start=1):
            digest.update(line)
            if index == number:
                anchor_found = bool(line.decode("utf-8").strip())
    if not anchor_found:
        raise ValueError("Evidence가 가리키는 원본 줄이 없거나 비어 있습니다.")
    return EVIDENCE_TAG_PREFIX + digest.hexdigest()


def can_review_candidate(row: dict[str, Any], scope: dict[str, Any]) -> bool:
    for candidate_scope in (scope, scope.get("project_context")):
        if not isinstance(candidate_scope, dict):
            continue
        if (
            candidate_scope.get("project_root_hash")
            and candidate_scope["project_root_hash"] == row.get("project_root_hash")
            and candidate_scope.get("project_id")
            and candidate_scope["project_id"] == row.get("project_id")
        ):
            return bool(
                row.get("layer") == "project"
                and row.get("record_type") == "project_context_section"
                and row.get("source_content_hash")
                and row.get("semantic_status") == "active"
                and not row.get("superseded_by")
            )
    return False


def reviewed_source_binding(question: str, row: dict[str, Any]) -> str | None:
    if row.get("record_type") != "project_context_section" or row.get("layer") != "project":
        return None
    values = [question, row.get("memory_id") or row.get("id")]
    values.extend(row.get(key) for key in ("project_id", "project_root_hash", "source_path", "source_section", "source_content_hash"))
    values.extend(sorted(evidence_tags(row.get("tags"))))
    if not all(isinstance(value, str) and value and "\0" not in value for value in values):
        return None
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()


def project_markdown_section(text: str, section: str) -> str:
    """Use the ATX boundaries and whitespace normalization of Mnemos project-context capture."""
    lines = text.splitlines()
    headings = [(index, match.group(1).strip()) for index, line in enumerate(lines)
                if (match := re.match(r"^#{1,6}\s+(.+?)\s*$", line))]
    if not headings:
        return "\n".join(lines).strip() if section == "(document)" else ""
    end = len(lines)
    # Capture uses the same ID for repeated headings, so the last section wins.
    for start, title in reversed(headings):
        if title == section:
            return "\n".join(lines[start:end]).strip()
        end = start
    if section == "(preamble)":
        return "\n".join(lines[:headings[0][0]]).strip()
    return ""


def swift_source_issue(source: Path, section: str) -> str | None:
    try:
        parsed = subprocess.run(
            ["swiftc", "-frontend", "-dump-parse", str(source)],
            capture_output=True, encoding="utf-8", errors="replace", timeout=8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "project_source_section_unverified"
    if parsed.returncode or not parsed.stdout.lstrip().startswith("(source_file "):
        return "project_source_section_unverified"

    declarations = SWIFT_DECLARATION.findall(parsed.stdout)
    matches = sum(section in (name, name.partition("(")[0]) for name in declarations)
    if not matches:
        return "project_source_section_missing"
    if matches > 1:
        return "project_source_section_ambiguous"
    return None


def project_source_issue(project_root: Any, row: dict[str, Any], *, excerpt: str | None = None) -> str | None:
    source_path = row.get("source_path")
    section = row.get("source_section")
    unavailable = "project_source_unavailable"
    if not all(isinstance(value, str) and value.strip() for value in (project_root, source_path, section)):
        return unavailable
    root = Path(project_root)
    relative = Path(source_path)
    if not root.is_absolute() or relative.is_absolute():
        return unavailable

    try:
        root = root.resolve(strict=True)
        source = (root / relative).resolve(strict=True)
        source.relative_to(root)
        if not source.is_file():
            return unavailable
        suffix = relative.suffix.lower()
        if excerpt is not None and suffix not in {".md", ".markdown"}:
            return "project_source_excerpt_unverified"
        if suffix == ".swift" and section != "(document)":
            if source.stat().st_size > 512_000:
                return "project_source_section_unverified"
            return swift_source_issue(source, section)
        if suffix not in {".md", ".markdown"}:
            with source.open("rb") as stream:
                stream.read(1)
            return None
        if source.stat().st_size > 512_000:
            return unavailable
        text = source.read_text(encoding="utf-8", errors="ignore")
    except (OSError, RuntimeError, ValueError):
        return unavailable

    current = project_markdown_section(text, section)
    if not current:
        return "project_source_section_missing"
    expected_hash = row.get("source_content_hash")
    if expected_hash and hashlib.sha256(current.encode("utf-8")).hexdigest() != expected_hash:
        return "project_source_changed"
    if expected_hash and str(row.get("content") or "").strip() != current:
        return "project_recalled_body_mismatch"
    pinned = evidence_tags(row.get("tags"))
    if not pinned and set(STRUCTURED_LESSON_FIELDS.findall(current)) == {"Condition", "Decision", "Evidence"}:
        return "project_evidence_unverified"
    if pinned:
        locators = EVIDENCE_FIELD.findall(current)
        if len(locators) != 1:
            return "project_evidence_unavailable"
        try:
            actual_tag = project_evidence_tag(root, source, locators[0].strip())
        except (OSError, RuntimeError, ValueError):
            return "project_evidence_unavailable"
        if pinned != [actual_tag]:
            return "project_evidence_changed"
    if excerpt is not None:
        body = current.partition("\n")[2] if re.match(r"^#{1,6}[ \t]+", current) else current
        if f"\n{excerpt}\n" not in f"\n{body}\n":
            return "project_source_excerpt_missing"
    return None
