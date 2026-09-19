import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT = REPO_ROOT / "core/agents/brainstorm.md"
MANIFEST = REPO_ROOT / "core/policies/agent-capabilities.json"
CODEX_BOOTSTRAP = REPO_ROOT / "adapters/codex/template/agents/brainstorm.toml"
CLAUDE_SETUP = REPO_ROOT / "adapters/claude/setup.sh"


def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    result = {}
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_brainstorm_agent_is_read_only_and_cannot_approve():
    text = AGENT.read_text(encoding="utf-8")
    assert "allowed-tools: Read, Write, Grep, Glob, Bash" in text
    assert "AskUserQuestion" not in frontmatter(text)["allowed-tools"]
    assert "Never write brainstorm-approval.json" in text
    assert "Never write pipeline.json" in text
    assert "Write only TASK_DIR/context/brainstorm-design.md" in text


def test_brainstorm_agent_declares_all_four_modes():
    text = AGENT.read_text(encoding="utf-8")
    for mode in ("classify", "next_question", "compare", "design"):
        assert f"MODE={mode}" in text


def test_brainstorm_agent_declares_read_only_input_artifacts():
    text = AGENT.read_text(encoding="utf-8")
    for name in ("REQUIREMENTS_PATH", "CLASSIFICATION_PATH", "DIALOGUE_PATH"):
        assert name in text


def test_host_bootstraps_reference_the_brainstorm_definition():
    bootstrap = CODEX_BOOTSTRAP.read_text(encoding="utf-8")
    assert "${AGENT_CREW_HOME}/system/agents/brainstorm.md" in bootstrap
    assert 'model_reasoning_effort = "xhigh"' in bootstrap
    assert "brainstorm.md" in CLAUDE_SETUP.read_text(encoding="utf-8")


def test_capability_manifest_denies_workflow_mutation_and_delegation():
    profile = manifest()["agents"]["brainstorm"]
    assert profile["may_delegate"] is False
    assert profile["may_mutate_workflow_state"] is False
    assert "approval_gate" in profile["denied_capabilities"]
