"""README alignment checks for runtime behavior that has drifted before."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
README = REPO_ROOT / "README.md"


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_documents_merged_analyst_planner_flow():
    text = readme_text()
    assert "analyst+planner" in text
    assert "Phase 1b+1c" in text
    assert "requirements → analyst → planner" not in text
    assert "Phase 1b: analyst" not in text
    assert "Phase 1c: planner" not in text


def test_readme_documents_sufficiency_gated_requirements():
    text = readme_text()
    assert "Requirements sufficiency gate" in text
    assert "Sufficiency-Gated Architecture" in text
    assert "delegate to requirements agent only when ambiguous" in text


def test_readme_documents_codex_capability_fallbacks():
    text = readme_text()
    assert "Host Capability Caveat" in text
    assert "Codex currently runs in guided prompt mode" in text
    assert "`agent_background`, `task_tools`" in text
    assert "inline execution and markdown/file" in text
    assert "fallbacks instead of claiming native background sessions" in text
    assert "advisory prompt-workflow guardrails" in text
    assert "not as enforced `hook_system=true` guarantees" in text


def test_readme_documents_native_cli_boundary():
    text = readme_text()
    assert "`crew` is the native shell entrypoint" in text
    assert "`crew setup`, `crew status`,\n`crew trace`, `crew cost`, `crew doctor`, `crew config`, `crew debug`, `crew resume`,\n`crew update --local`, and the initial `crew run` / `crew agent` state\ntransitions are deterministic CLI paths" in text
    assert "`crew run` writes task state and a\nsupervisor handoff" in text
    assert "until the host AI prompt runtime completes that handoff" in text
    assert "`crew agent` validates a\nread-only direct-agent request" in text
    assert "the host prompt\nruntime still performs the analysis" in text


def test_docs_distinguish_workflow_notation_from_native_cli_forms():
    global_agents = (REPO_ROOT / "core" / "global-agents.md").read_text(encoding="utf-8")
    seed_rules = (REPO_ROOT / "core" / "scripts" / "seed-instruction-rules.sh").read_text(
        encoding="utf-8"
    )
    docs = [
        README.read_text(encoding="utf-8"),
        (REPO_ROOT / "adapters" / "codex" / "invocation.md").read_text(encoding="utf-8"),
        global_agents,
    ]
    combined = "\n".join(docs)
    compact = " ".join(combined.split())
    assert "`crew:<intent>` workflow notation" in combined
    assert "native shell CLI uses space-separated commands such as `crew run` and `crew agent`" in compact
    assert "Slash-style commands are host-specific aliases" in combined
    assert "this adapter does not create adapter-owned slash aliases" in compact
    for wrapper in ("$crew-setup", "$crew-cost", "$crew-agent-maker"):
        assert f"| `{wrapper}` |" in global_agents
        assert f"| `{wrapper}` |" in seed_rules


def test_codex_guide_mirror_is_not_native_skill_directory():
    text = (REPO_ROOT / "core" / "commands" / "update.md").read_text(encoding="utf-8")
    script = (REPO_ROOT / "core" / "scripts" / "update-global-adapters.sh").read_text(encoding="utf-8")
    combined = text + "\n" + script
    compact = " ".join(combined.split())
    assert "internal agent-crew guide mirror at `~/.codex/agent-crew/skills/`" in combined
    assert "not the native Codex skill directory" in compact
    assert "native Codex skills live under `~/.codex/skills/`" in combined


def test_readme_documents_agent_crew_skill_dispatch_layers():
    text = readme_text()

    assert "Agent-first skill dispatch" in text
    assert "`~/.agent-crew/system/skills/`" in text
    assert "`~/.agent-crew/user/skills/`" in text
    assert "`~/.agent-crew/skills/`" in text
    assert "`~/.codex/agent-crew/skills/`" in text
    assert "native Codex skills remain under `~/.codex/skills/`" in text
    assert "`decision_context`" in text
    assert "does not create `skill-use.json` proof artifacts" in text
    assert "advisory gaps rather than\ncompletion blockers" in text
    assert "`~/.agent-crew/agents/skills/`" not in text


def test_readme_defines_prompt_internal_control_layer():
    text = readme_text()
    compact = " ".join(text.split())
    assert "orchestration layer that runs inside\nhost AI prompt workflows" in text
    assert "It is not a replacement for Codex, Claude, Copilot" in text
    assert "The host AI remains the execution plane" in text
    assert "agent-crew\nprovides the local control plane" in text
    assert "Comparisons to autonomous harnesses should be read at this layer only" in compact
    assert "does not try to replace the host AI, own OS-level execution, or operate as an independent commercial harness" in compact
    assert "agent-crew complements productized harnesses and broad skill catalogs" in compact


def test_readme_documents_one_shot_dangerous_command_approval():
    text = readme_text()
    assert "workflow-integrity check, not an OS\nsandbox" in text
    assert "one-shot JSON approval" in text
    assert "exact `kind`,\n`command`, and a short-lived `expires_at` timestamp" in text
    assert "short-lived `expires_at` timestamp" in text


def test_readme_explains_requirements_question_skip_and_wait_contract():
    text = readme_text()
    assert "A missing question can therefore\nbe intentional" in text
    assert "`SUFFICIENT` tasks synthesize a `REQUIREMENTS` block inline" in text
    assert "`AMBIGUOUS` tasks must ask and wait" in text


def test_readme_does_not_overstate_native_runtime_execution():
    text = readme_text()
    assert "The native `crew`\nCLI remains the deterministic control plane" in text
    assert "waits for the host prompt workflow to complete the execution\ncontract" in text
    assert "No daemon processes, no file polling, no signal files" not in text


def test_readme_preserves_validation_conclusion():
    text = readme_text()
    assert "prompt handling has improved" in text
    assert "Native control-plane commands are now fast enough for routine use" in text
    assert "remaining performance risk is host prompt-runtime latency" in text
    assert "continue to be\nmeasured during commercialization validation" in text


def test_active_work_docs_require_concise_operator_messages():
    docs = [
        (REPO_ROOT / "core" / "commands" / "run.md").read_text(encoding="utf-8"),
        (REPO_ROOT / "core" / "commands" / "status.md").read_text(encoding="utf-8"),
        (REPO_ROOT / "core" / "rules" / "task-injection.md").read_text(encoding="utf-8"),
    ]
    combined = "\n".join(docs)
    assert "Operator-facing brevity" in combined
    assert "Active-work messages are concise by default" in combined
    assert "session id, task id" in combined
    assert "long policy narration" in combined


def test_readme_documents_automatic_issue_reporting():
    text = readme_text()
    assert "Native issue reporting" in text
    assert "crew report auto" in text
    assert "unexpected supervisor infrastructure blockers" in text
    assert "core/hooks/auto-issue-report.sh" in text
    assert "core/rules/auto-issue-reporting.md" in text


def test_readme_documents_trace_resume_and_config_improvements():
    text = readme_text()
    assert "`tool-events.jsonl` records native tool calls keyed by `trace_id`" in text
    assert "`delegation.jsonl` records provider-neutral span lineage" in text
    assert "`crew config dump --effective`" in text
    assert "`crew doctor` | Native shell command: split operational checks" in text
    assert "records RESUME_REQUESTED" in text
