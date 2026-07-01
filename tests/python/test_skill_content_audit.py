"""Regression coverage for skill content-depth audit issue #190."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "core" / "agents" / "skills"
EFFECTIVE_JAVA = SKILLS_DIR / "effective-java.md"
REVIEWER_MD = REPO_ROOT / "core" / "agents" / "reviewer.md"
AUDIT_SCRIPT = REPO_ROOT / "core" / "scripts" / "skill-content-audit.py"
CREW_BIN = REPO_ROOT / "core" / "bin" / "crew"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module(AUDIT_SCRIPT, "skill_content_audit_under_test")


def test_effective_java_covers_known_review_gap() -> None:
    text = EFFECTIVE_JAVA.read_text(encoding="utf-8")

    required_terms = [
        "Item 17",
        "Item 50",
        "Item 54",
        "Collections.emptyMap()",
        "Collections.emptyList()",
        "Collections.emptySet()",
        "List.of()",
        "Map.of()",
        "Set.of()",
        "read-only fallback collection",
        "new HashMap<Long, String>()",
    ]

    for term in required_terms:
        assert term in text, f"effective-java.md must cover {term}"


def test_skill_content_audit_reports_inventory_and_effective_followups() -> None:
    assert AUDIT_SCRIPT.is_file(), f"missing audit script: {AUDIT_SCRIPT}"

    result = subprocess.run(
        ["python3", str(AUDIT_SCRIPT), "--format", "json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(result.stdout)
    expected_skill_files = sorted(path.name for path in SKILLS_DIR.glob("*.md"))
    actual_skill_files = sorted(row["file"] for row in payload["inventory"])
    assert actual_skill_files == expected_skill_files

    effective_files = sorted(path.name for path in SKILLS_DIR.glob("effective-*.md"))
    followup_files = sorted(row["file"] for row in payload["effective_followups"])
    assert followup_files == effective_files

    java_contract = payload["content_contracts"]["effective-java.md"]
    assert java_contract["passed"] is True
    assert java_contract["missing"] == []

    assert "shallow_findings" in payload
    for row in payload["inventory"]:
        assert "missing_required_sections" in row


def test_reviewer_requires_applied_language_skill_evidence() -> None:
    text = REVIEWER_MD.read_text(encoding="utf-8")

    assert "language_skill_application_evidence" in text
    assert "not merely loaded" in text
    assert "context/review.md" in text
    assert "skill-content-audit.py" in text
    assert "context/skill-content-audit.json" in text


def test_skill_content_audit_resolves_installed_layouts(tmp_path: Path) -> None:
    agent_crew_home = tmp_path / ".agent-crew"
    system_skills = agent_crew_home / "system" / "agents" / "skills"
    system_skills.mkdir(parents=True)

    system_script = agent_crew_home / "system" / "scripts" / "skill-content-audit.py"
    system_script.parent.mkdir(parents=True)
    compat_script = agent_crew_home / "scripts" / "skill-content-audit.py"
    compat_script.parent.mkdir(parents=True)

    system_layout = audit._resolve_layout(system_script)
    compat_layout = audit._resolve_layout(compat_script)

    assert system_layout.skills_dir == system_skills
    assert compat_layout.skills_dir == system_skills


def test_crew_runtime_autosync_tracks_skill_content_audit_script() -> None:
    text = CREW_BIN.read_text(encoding="utf-8")

    assert "core/scripts/skill-content-audit.py" in text
    assert "${AGENT_CREW_HOME}/scripts/skill-content-audit.py" in text


def test_crew_runtime_autosync_refreshes_agent_skill_assets() -> None:
    text = CREW_BIN.read_text(encoding="utf-8")

    assert "tree_assets_drifted \"${source}/core/agents\"" in text
    assert "tree_assets_drifted \"${source}/core/agents/skills\" \"${AGENT_CREW_HOME}/system/skills\"" in text
    assert "find . -type f -print0" in text
    assert "cmp -s \"${src}/${rel}\" \"${dest}/${rel}\"" in text
    assert "diff -qr" not in text
    assert "copy_tree_assets \"${source}/core/agents\" \"${AGENT_CREW_HOME}/system/agents\"" in text
    assert "copy_tree_assets \"${source}/core/agents/skills\" \"${AGENT_CREW_HOME}/system/skills\"" in text


def test_crew_runtime_tree_sync_removes_destination_only_stale_files(tmp_path: Path) -> None:
    text = CREW_BIN.read_text(encoding="utf-8")
    start = text.index("copy_tree_assets() {")
    end = text.index("\nabsolute_file_path() {", start)
    functions = text[start:end]
    script = tmp_path / "probe-tree-sync.bash"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{functions}\n"
        "src=\"$1/src\"\n"
        "dest=\"$1/dest\"\n"
        "mkdir -p \"${src}\" \"${dest}\"\n"
        "printf 'stale\\n' > \"${dest}/removed-skill.md\"\n"
        "if tree_assets_drifted \"${src}\" \"${dest}\"; then\n"
        "  echo 'drift=1'\n"
        "else\n"
        "  echo 'drift=0'\n"
        "fi\n"
        "copy_tree_assets \"${src}\" \"${dest}\"\n"
        "if [ -e \"${dest}/removed-skill.md\" ]; then\n"
        "  echo 'stale_file=still_present'\n"
        "else\n"
        "  echo 'stale_file=removed'\n"
        "fi\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(script), str(tmp_path)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "drift=1" in result.stdout
    assert "stale_file=removed" in result.stdout
