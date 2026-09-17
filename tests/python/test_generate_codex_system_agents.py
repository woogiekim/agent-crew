"""Tests for Codex system-agent TOML generation."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "generate-codex-system-agents.py"
DEFAULT_POLICY = REPO_ROOT / "adapters" / "codex" / "model-policy.json"


def load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_codex_system_agents", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_frontmatter_returns_empty_for_plain_markdown():
    module = load_generator_module()

    assert module.parse_frontmatter("# Plain Agent\n\nNo frontmatter.\n") == {}


def test_default_policy_inherits_host_models():
    module = load_generator_module()

    assert module.load_model_policy(DEFAULT_POLICY) == {}


def test_generate_codex_system_agents_rejects_missing_source_dir(tmp_path: Path):
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            str(tmp_path / "missing-source"),
            str(tmp_path / "out"),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "source_dir not found" in result.stderr


def test_render_toml_inherits_host_model_by_default(tmp_path: Path):
    module = load_generator_module()
    agent = tmp_path / "analyst.md"
    agent.write_text(
        """---
name: analyst
description: Analyze code.
reasoning_tier: xhigh
model: inherit
---

# Analyst
""",
        encoding="utf-8",
    )

    _, content = module.render_toml(agent)

    assert "model =" not in content
    assert 'model_reasoning_effort = "xhigh"' in content


def test_render_toml_materializes_explicit_policy_override(tmp_path: Path):
    module = load_generator_module()
    policy = tmp_path / "model-policy.json"
    policy.write_text(
        '{"schema_version": 1, "models": {"xhigh": "gpt-frontier"}}\n',
        encoding="utf-8",
    )
    agent = tmp_path / "analyst.md"
    agent.write_text(
        """---
name: analyst
description: Analyze code.
reasoning_tier: xhigh
model: inherit
---

# Analyst
""",
        encoding="utf-8",
    )

    model_policy = module.load_model_policy(policy)
    _, content = module.render_toml(agent, model_policy=model_policy)

    assert 'model = "gpt-frontier"' in content
    assert 'model_reasoning_effort = "xhigh"' in content


def test_load_model_policy_rejects_unknown_tier(tmp_path: Path):
    module = load_generator_module()
    policy = tmp_path / "model-policy.json"
    policy.write_text(
        '{"schema_version": 1, "models": {"turbo": "gpt-frontier"}}\n',
        encoding="utf-8",
    )

    try:
        module.load_model_policy(policy)
    except ValueError as error:
        assert "unknown model policy tier: turbo" in str(error)
    else:
        raise AssertionError("unknown model policy tier must be rejected")
