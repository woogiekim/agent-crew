"""Variants 단계에서 공유하는 원자적 상태 I/O와 Git 조회."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import re
import os
from pathlib import Path
import subprocess
import tempfile


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    value = load_json(path)
    if not value:
        raise ValueError(f"손상된 상태 파일: {path}")
    return value


def write_bytes(path: Path, data: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path: Path, value: dict) -> None:
    write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


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


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                            text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git 검증 실패")
    return result.stdout.strip()
def variants_artifacts_dir(state_dir: Path, session: dict | None = None) -> Path:
    session = load_json(state_dir / "session.json") if session is None else session
    if not session.get("variants_dir"):
        return state_dir
    session_id = str(session.get("session_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        raise ValueError("invalid variants session id")
    expected = state_dir.resolve() / "variants" / session_id
    actual = Path(session["variants_dir"]).resolve()
    if actual != expected or not actual.is_relative_to(state_dir.resolve()):
        raise ValueError("variants artifact directory must be session scoped")
    return actual
