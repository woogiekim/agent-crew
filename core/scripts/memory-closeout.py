#!/usr/bin/env python3
"""Index one explicitly verified, source-backed project lesson."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from project_memory_source import project_evidence_tag


HEADING = re.compile(r"^#{1,6}\s+\S")
FIELD = re.compile(r"^- (Condition|Decision|Evidence):\s*(.*)$")


def project_file(root: Path, path: Path) -> Path:
    resolved = (root / path).resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file():
        raise ValueError(f"프로젝트 파일이 아닙니다. {path}")
    return resolved


def validate_lesson(root: Path, lesson: Path) -> str:
    if lesson.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("교훈을 Markdown 파일에 작성해야 합니다.")

    lines = lesson.read_text(encoding="utf-8").strip("\r\n").splitlines()
    headings = [i for i, line in enumerate(lines) if HEADING.match(line)]
    if headings != [0]:
        raise ValueError("교훈 문서는 제목으로 시작하고 섹션 하나만 포함해야 합니다.")

    fields = {}
    for line in lines[1:]:
        field = FIELD.match(line)
        if field is None:
            continue
        key, value = field.groups()
        if key in fields or not value.strip():
            raise ValueError(f"교훈 필드가 중복되거나 비어 있습니다. {key}")
        fields[key] = value.strip()

    if fields.keys() != {"Condition", "Decision", "Evidence"}:
        raise ValueError("Condition, Decision, Evidence 필드를 각각 하나씩 작성해야 합니다.")

    return project_evidence_tag(root, lesson, fields["Evidence"])


def capture(memory: str, root: Path, lesson: Path, evidence_tag: str) -> dict:
    result = subprocess.run(
        [memory, "project-context", "capture", str(lesson), "--project-id", root.name,
         "--project-root", str(root), "--tag", evidence_tag, "--json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    if result.returncode != 0:
        raise ValueError(f"memory provider가 교훈 저장에 실패했습니다. 종료 코드 {result.returncode}")
    try:
        reply = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError("memory provider가 교훈 저장 결과를 반환하지 않았습니다.") from exc
    if not isinstance(reply, dict) or reply.get("status") != "ok" or reply.get("section_count") != 1:
        raise ValueError("memory provider에서 교훈 한 건의 저장을 확인하지 못했습니다.")
    entries = [reply.get(key, []) for key in ("created", "updated", "skipped")]
    if not all(isinstance(items, list) for items in entries):
        raise ValueError("memory provider가 유효한 교훈 ID를 반환하지 않았습니다.")
    ids = [item for items in entries for item in items]
    if len(ids) != 1 or not isinstance(ids[0], str) or not ids[0].strip():
        raise ValueError("memory provider가 교훈 한 건의 ID를 반환하지 않았습니다.")
    return reply


def main() -> int:
    memory = sys.argv[1]
    parser = argparse.ArgumentParser(prog="memory closeout", allow_abbrev=False)
    parser.add_argument("lesson", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--verified", action="store_true", required=True,
                        help="교훈이 현재 원본과 검증 결과에 부합함을 확인합니다.")
    args = parser.parse_args(sys.argv[2:])

    try:
        root = args.project_root.resolve(strict=True)
        if not root.is_dir() or not root.name:
            raise ValueError("프로젝트 루트는 실제 프로젝트 디렉터리여야 합니다.")
        lesson = project_file(root, args.lesson)
        evidence_tag = validate_lesson(root, lesson)
        reply = capture(memory, root, lesson, evidence_tag)
    except (OSError, RuntimeError, ValueError, OverflowError, subprocess.TimeoutExpired) as error:
        parser.exit(2, f"[memory closeout] {error}\n")
    print(json.dumps(reply, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
