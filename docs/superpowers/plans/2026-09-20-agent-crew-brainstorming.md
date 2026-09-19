# Agent Crew Brainstorming Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resumable Brainstorm Phase to `crew:run` that visibly classifies work as `Spike`, `Bounded`, or `Architectural`, adapts the interview depth, and binds design decisions into the existing approval lifecycle.

**Architecture:** A deterministic classifier establishes a minimum classification while a read-only Brainstorm Agent may raise it using repository evidence. The Supervisor owns all questions, state transitions, design and combined approvals; the analyst consumes only an accepted or approved design. Canonical JSON artifacts and hashes make resume and invalidation deterministic without changing `crew:agent` or weakening external-action approvals.

**Tech Stack:** Python 3 standard library, JSON Schema files consumed by the repository's lightweight validator, Markdown agent/command contracts, Bash integration tests, pytest.

**Spec:** `docs/superpowers/specs/2026-09-19-agent-crew-brainstorming-design.md`

## Global Constraints

- Apply this feature only to `crew:run`; do not change the direct execution contract of `crew:agent`.
- Preserve the user's task text as the immutable Root Input Snapshot.
- Classification order is `Spike < Bounded < Architectural`; a semantic result may raise but never lower the deterministic minimum.
- Run preliminary classification before requirements and final classification after requirements.
- Show every classification and its evidence to the user.
- `Bounded` uses one combined design-and-execution-plan approval; `Architectural` uses separate design and execution-plan approvals.
- User downgrade changes only brainstorming ceremony and never weakens external-write, destructive-action, deployment, credential, permission, or security approvals.
- Newly discovered architectural impact invalidates a downgrade and every dependent approval.
- Questions and approvals remain owned by the Supervisor or orchestrator, never by the Brainstorm Agent.
- Use canonical structured fields for approval hashes; do not add a model-based semantic-diff mechanism.
- Do not add an LLM call to technical lifecycle hooks.
- Follow Red → Green → Refactor for every production-code task.
- Keep all verification offline.

---

## File Structure

### New files

- `core/scripts/brainstorm-classification.py` — deterministic minimum classification, result resolution, canonical field hashing, and CLI output.
- `core/schemas/brainstorm-classification.schema.json` — preliminary/final rule and semantic classification artifact contract.
- `core/schemas/brainstorm-dialogue.schema.json` — ordered questions, responses, section acknowledgements, and idempotency keys.
- `core/schemas/brainstorm-approval.schema.json` — downgrade, architectural design approval, and bounded combined approval records.
- `core/agents/brainstorm.md` — read-only semantic classification, adaptive-question, approach-comparison, and design-drafting agent contract.
- `adapters/codex/template/agents/brainstorm.toml` — Codex bootstrap that loads the provider-neutral agent definition.
- `tests/python/test_brainstorm_classification.py` — deterministic classification and canonical-hash unit tests.
- `tests/python/test_brainstorm_state_schema.py` — artifact schema and validator coverage.
- `tests/python/test_brainstorm_agent_contract.py` — agent authority, output, and adapter mirror contract tests.
- `tests/python/test_brainstorm_supervisor_contract.py` — static supervisor lifecycle and approval-boundary contract tests.
- `tests/integration/test_brainstorm_workflow.bash` — fresh/resume/promotion/downgrade workflow scenarios.

### Modified files

- `core/scripts/validate-state-schema.py` — validate optional Brainstorm JSON artifacts when present.
- `core/schemas/register.schema.json` — add Brainstorm phases, pointers, classification, and design approval status.
- `core/agents/supervisor-bootstrap.md` — run preliminary/final classification, Brainstorm Agent dialogue, design validation, approvals, resume, and invalidation before analyst planning.
- `core/agents/supervisor.md` — document the new phase ordering and completion invariants.
- `core/agents/analyst.md` — consume the accepted design hash and stop on missing or mismatched Brainstorm input.
- `core/policies/agent-capabilities.json` — register Brainstorm Agent as read-only without approval or workflow-state authority.
- `core/commands/run.md` — orchestrator handling for Brainstorm interactions across one or many tasks.
- `core/commands/status.md` — render Brainstorm phase, classification, and pending interaction.
- `core/commands/smm.md` — include Brainstorm pointers in the read-only single view.
- `README.md` — document the new lifecycle and user-visible behavior.
- `tests/python/test_validate_state_schema.py` — validator cases for optional Brainstorm artifacts.
- `tests/python/test_readme_runtime_alignment.py` — documentation/runtime alignment assertions.

---

### Task 1: Deterministic Classification and Canonical Hashing

**Files:**
- Create: `core/scripts/brainstorm-classification.py`
- Create: `tests/python/test_brainstorm_classification.py`

**Interfaces:**
- Consumes: raw task text, optional requirements text, optional semantic classification JSON, and deterministic evidence flags.
- Produces: `classify_minimum(task: str, requirements: str = "", evidence: dict | None = None) -> dict`, `resolve_classification(rule_result: dict, semantic_result: dict | None) -> dict`, `canonical_hash(fields: dict) -> str`, and a CLI supporting `--stage preliminary|final`, `--requirements-file`, `--semantic-file`, `--evidence-file`, and `--format json|text`.

- [ ] **Step 1: Write failing tests for ordering, hard rules, resolution, and hashing**

```python
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "core/scripts/brainstorm-classification.py"
spec = importlib.util.spec_from_file_location("brainstorm_classification", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_incompatible_public_contract_forces_architectural():
    result = module.classify_minimum(
        "Remove the legacy response field from the public API",
        evidence={"backward_incompatible_public_contract": True},
    )
    assert result["classification"] == "Architectural"
    assert result["matched_rules"] == ["backward_incompatible_public_contract"]


def test_semantic_result_can_raise_but_not_lower_rule_minimum():
    rule = {"classification": "Architectural", "matched_rules": ["security_boundary_change"]}
    lowered = module.resolve_classification(rule, {"classification": "Bounded", "evidence": []})
    raised = module.resolve_classification(
        {"classification": "Bounded", "matched_rules": []},
        {"classification": "Architectural", "evidence": ["ownership boundary moves"]},
    )
    assert lowered["classification"] == "Architectural"
    assert lowered["resolution"] == "rule_minimum_preserved"
    assert raised["classification"] == "Architectural"
    assert raised["resolution"] == "semantic_raise"


def test_file_count_and_api_keyword_do_not_force_architectural():
    result = module.classify_minimum("Add a backward-compatible API field in five files")
    assert result["classification"] == "Bounded"


def test_canonical_hash_ignores_display_copy_but_changes_bound_fields():
    base = {"classification": "Bounded", "goals": ["add field"], "display_summary": "first"}
    assert module.canonical_hash(base) == module.canonical_hash({**base, "display_summary": "second"})
    assert module.canonical_hash(base) != module.canonical_hash({**base, "goals": ["remove field"]})
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m pytest tests/python/test_brainstorm_classification.py -q`

Expected: collection fails because `core/scripts/brainstorm-classification.py` does not exist.

- [ ] **Step 3: Implement classification constants, hard-rule evaluation, and conservative fallback**

```python
ORDER = {"Spike": 0, "Bounded": 1, "Architectural": 2}
HARD_RULES = {
    "new_subsystem": "Architectural",
    "backward_incompatible_public_contract": "Architectural",
    "persistent_data_migration": "Architectural",
    "security_boundary_change": "Architectural",
    "multi_repository_contract": "Architectural",
    "workflow_governance_change": "Architectural",
    "destructive_or_hard_to_reverse": "Architectural",
    "post_approval_scope_expansion": "Architectural",
}


def classify_minimum(task: str, requirements: str = "", evidence: dict | None = None) -> dict:
    evidence = evidence or {}
    matched = [rule for rule in HARD_RULES if evidence.get(rule) is True]
    analysis_only = evidence.get("analysis_only") is True
    classification = "Architectural" if matched else ("Spike" if analysis_only else "Bounded")
    return {
        "classification": classification,
        "matched_rules": matched,
        "rule_version": 1,
        "evidence": evidence,
    }
```

Implement `resolve_classification` by comparing `ORDER`; malformed or unknown semantic output must return the rule minimum with `semantic_status: "degraded"`. Do not infer hard-rule evidence from file count or isolated keywords.

- [ ] **Step 4: Implement canonical hashing and the CLI**

```python
BOUND_FIELDS = (
    "classification", "downgrade", "goals", "non_goals", "interfaces",
    "responsibility_boundaries", "data_model", "repositories", "modules",
    "security_risks", "operational_risks", "pipeline",
)


def canonical_hash(fields: dict) -> str:
    bound = {key: fields.get(key) for key in BOUND_FIELDS if key in fields}
    payload = json.dumps(bound, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

The JSON CLI result must include `schema_version`, `stage`, `rule_result`, `semantic_result`, `final_classification`, `resolution`, and `classifier_version`. On unreadable semantic/evidence input, exit nonzero and print a structured error to stderr instead of silently returning `Bounded`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python3 -m pytest tests/python/test_brainstorm_classification.py -q`

Expected: all tests pass.

- [ ] **Step 6: Refactor and re-run the focused tests**

Keep rule evaluation, resolution, serialization, and CLI parsing in separate functions. Confirm no single helper mixes user-facing copy with classification policy.

Run: `python3 -m pytest tests/python/test_brainstorm_classification.py -q`

Expected: all tests pass after the no-op or focused refactor.

- [ ] **Step 7: Commit the classifier**

```bash
git add core/scripts/brainstorm-classification.py tests/python/test_brainstorm_classification.py
git commit -m "feat: add deterministic brainstorm classification"
```

---

### Task 2: Brainstorm Artifact Schemas and Register Pointers

**Files:**
- Create: `core/schemas/brainstorm-classification.schema.json`
- Create: `core/schemas/brainstorm-dialogue.schema.json`
- Create: `core/schemas/brainstorm-approval.schema.json`
- Create: `tests/python/test_brainstorm_state_schema.py`
- Modify: `core/scripts/validate-state-schema.py`
- Modify: `core/schemas/register.schema.json`
- Modify: `tests/python/test_validate_state_schema.py`

**Interfaces:**
- Consumes: Brainstorm JSON artifacts under `{TASK_DIR}/context/`.
- Produces: hard schema validation when artifacts exist; register phases `phase_1b_brainstorm`, `phase_1c_plan`, and pointers `brainstorm_classification_path`, `brainstorm_dialogue_path`, `brainstorm_design_path`, `brainstorm_approval_path`.

- [ ] **Step 1: Write failing schema tests for valid artifacts and rejected invalid state**

```python
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / "core/scripts/validate-state-schema.py"


def make_valid_task(tmp_path: Path) -> Path:
    task_dir = tmp_path / "tasks/20260920-120000-0"
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "register.json").write_text(json.dumps(valid_register()), encoding="utf-8")
    return task_dir


def run_validator(task_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(VALIDATOR), "--state-dir", str(task_dir.parent.parent),
         "--task-dir", str(task_dir), "--format", "json"],
        text=True, capture_output=True,
    )


def write_classification(task_dir: Path, preliminary: str) -> None:
    payload = classification_fixture(preliminary=preliminary)
    (task_dir / "context/brainstorm-classification.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def write_dialogue(task_dir: Path, **overrides) -> None:
    payload = dialogue_fixture()
    payload.update(overrides)
    (task_dir / "context/brainstorm-dialogue.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_brainstorm_optional_artifacts_validate(tmp_path):
    task_dir = make_valid_task(tmp_path)
    write_classification(task_dir, preliminary="Architectural")
    write_dialogue(task_dir, status="waiting_for_input", active_question_id="q-1")
    result = run_validator(task_dir)
    assert result.returncode == 0, result.stdout


def test_dialogue_rejects_plural_active_question_field(tmp_path):
    task_dir = make_valid_task(tmp_path)
    write_dialogue(task_dir, active_question_ids=["q-1", "q-2"])
    result = run_validator(task_dir)
    assert result.returncode == 2
    assert "active_question_ids" in result.stdout


def test_register_accepts_brainstorm_phase_and_pointers(tmp_path):
    register = valid_register(current_phase="phase_1b_brainstorm")
    register["brainstorm_classification_path"] = "/tmp/task/context/brainstorm-classification.json"
    assert validate_register(register) == []
```

Define `valid_register`, `classification_fixture`, and `dialogue_fixture` in the same test file with every required field copied literally from the three new schemas. Do not import private fixtures from another test module.

- [ ] **Step 2: Run schema tests and verify RED**

Run: `python3 -m pytest tests/python/test_brainstorm_state_schema.py tests/python/test_validate_state_schema.py -q`

Expected: failures report missing Brainstorm schemas/mappings and unknown register fields/phases.

- [ ] **Step 3: Define classification, dialogue, and approval schemas**

Use `additionalProperties: false` for all three top-level objects. Require these fields:

```json
{
  "classification": [
    "schema_version", "task_id", "raw_input_hash", "preliminary",
    "classifier_version", "status"
  ],
  "dialogue": [
    "schema_version", "task_id", "classification", "status",
    "questions", "section_acknowledgements"
  ],
  "approval": [
    "schema_version", "task_id", "decisions"
  ]
}
```

`final` is optional until requirements collection completes. Dialogue has one optional singular `active_question_id`; an array or plural active-question field is rejected by `additionalProperties: false`. Classification enums are `Spike`, `Bounded`, and `Architectural`. Dialogue status enums are `not_started`, `waiting_for_input`, `design_review`, `ready_for_approval`, `accepted`, and `blocked`. Each approval decision requires `decision_id`, `approval_kind`, `status`, `design_hash`, `bound_fields`, and `created_at`; `decision_at` is required only after the decision leaves `pending`. Approval kinds are `architectural_design`, `bounded_combined`, and `user_downgrade`; approval status is `pending`, `approved`, `cancelled`, or `invalidated`.

- [ ] **Step 4: Register optional artifacts with the state validator and extend register schema**

Add to `OPTIONAL_TASK_FILES`:

```python
("context/brainstorm-classification.json", "brainstorm-classification.schema.json", "error", False),
("context/brainstorm-dialogue.json", "brainstorm-dialogue.schema.json", "error", False),
("context/brainstorm-approval.json", "brainstorm-approval.schema.json", "error", False),
```

Add the new Brainstorm phase values and path properties to `register.schema.json`. Keep legacy `phase_1bc` valid for pre-feature task directories and resume compatibility.

- [ ] **Step 5: Run focused schema tests and verify GREEN**

Run: `python3 -m pytest tests/python/test_brainstorm_state_schema.py tests/python/test_validate_state_schema.py -q`

Expected: all tests pass.

- [ ] **Step 6: Validate the repository schemas and refactor repeated test fixtures**

Run: `python3 core/scripts/validate-state-schema.py --state-dir /tmp --format json`

Expected: exit 0 with zero schema parse errors. Consolidate fixture builders only when it reduces duplicated literal JSON without hiding required fields.

- [ ] **Step 7: Commit artifact contracts**

```bash
git add core/schemas/brainstorm-classification.schema.json core/schemas/brainstorm-dialogue.schema.json core/schemas/brainstorm-approval.schema.json core/schemas/register.schema.json core/scripts/validate-state-schema.py tests/python/test_brainstorm_state_schema.py tests/python/test_validate_state_schema.py
git commit -m "feat: define brainstorm workflow state"
```

---

### Task 3: Read-only Brainstorm Agent and Host Bootstrap

**Files:**
- Create: `core/agents/brainstorm.md`
- Create: `adapters/codex/template/agents/brainstorm.toml`
- Create: `tests/python/test_brainstorm_agent_contract.py`
- Modify: `core/policies/agent-capabilities.json`
- Modify: `adapters/claude/setup.sh`

**Interfaces:**
- Consumes: `TASK`, `TASK_DIR`, `PROJECT_ROOT`, `MODE=classify|next_question|compare|design`, requirements path, classification path, and dialogue path.
- Produces: structured `BRAINSTORM` response blocks and `brainstorm-design.md`; never writes approval, register, pipeline, PRD, or external state.

- [ ] **Step 1: Write failing contract tests**

```python
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT = REPO_ROOT / "core/agents/brainstorm.md"
MANIFEST = REPO_ROOT / "core/policies/agent-capabilities.json"


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


def test_capability_manifest_denies_workflow_mutation_and_delegation():
    profile = manifest()["agents"]["brainstorm"]
    assert profile["may_delegate"] is False
    assert profile["may_mutate_workflow_state"] is False
    assert "approval_gate" in profile["denied_capabilities"]
```

- [ ] **Step 2: Run focused agent tests and verify RED**

Run: `python3 -m pytest tests/python/test_brainstorm_agent_contract.py tests/python/test_agent_capability_check.py -q`

Expected: failures report the missing agent, adapter bootstrap, and capability profile.

- [ ] **Step 3: Implement the provider-neutral Brainstorm Agent contract**

The agent frontmatter must use `reasoning_tier: xhigh`, `model: inherit`, and inspection tools plus `Write` for the single task artifact `TASK_DIR/context/brainstorm-design.md`. Define exact output for every mode:

```text
BRAINSTORM:
  mode: classify
  classification: Architectural
  evidence:
    - source: file:line or task-artifact path
      finding: responsibility boundary moves
  unresolved: []
  readiness: READY
```

`next_question` returns exactly one question with `question_id`, `header`, `prompt`, two or three mutually exclusive options, and `why_it_matters`. `compare` returns one to three materially distinct approaches with a recommendation. `design` writes `brainstorm-design.md`, returns its path and canonical fields, and rejects unfinished markers, contradictions, scope overflow, or implementation-blocking unknowns.

The agent may inspect the repository and write only `TASK_DIR/context/brainstorm-design.md`. It must not call the host question UI, write approvals, update register state, create pipeline/PRD files, modify project source, implement code, delegate agents, or perform external writes.

- [ ] **Step 4: Add capability manifest and adapter bootstrap entries**

Add a `brainstorm` manifest entry with role `readonly`, model/reasoning tier `xhigh`, allowed capabilities `read_file`, `task_artifact_write`, `requirements_analysis`, and `structured_output`; deny `approval_gate`, `delegate_agents`, `destructive_command`, `edit_project_file`, and `pipeline_state_write`.

Add `brainstorm.md` to Claude's built-in-name collision list. Add the Codex TOML bootstrap using the same four-step pattern as `requirements.toml`, pointing to `${AGENT_CREW_HOME}/system/agents/brainstorm.md`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python3 -m pytest tests/python/test_brainstorm_agent_contract.py tests/python/test_agent_capability_check.py tests/python/test_generate_codex_system_agents.py -q`

Expected: all tests pass.

- [ ] **Step 6: Generate a temporary Codex mirror and inspect it**

Run: `tmp_dir=$(mktemp -d) && python3 core/scripts/generate-codex-system-agents.py core/agents "$tmp_dir" && test -f "$tmp_dir/brainstorm.toml" && rg -n "system/agents/brainstorm.md|model_reasoning_effort" "$tmp_dir/brainstorm.toml"`

Expected: `brainstorm.toml` exists, points to the provider-neutral definition, and carries the intended reasoning tier. Remove the temporary directory after inspection.

- [ ] **Step 7: Commit the Brainstorm Agent**

```bash
git add core/agents/brainstorm.md adapters/codex/template/agents/brainstorm.toml core/policies/agent-capabilities.json adapters/claude/setup.sh tests/python/test_brainstorm_agent_contract.py
git commit -m "feat: add read-only brainstorm agent"
```

---

### Task 4: Supervisor Classification, Dialogue, and Design State Machine

**Files:**
- Create: `tests/python/test_brainstorm_supervisor_contract.py`
- Modify: `core/agents/supervisor-bootstrap.md`
- Modify: `core/agents/supervisor.md`

**Interfaces:**
- Consumes: classifier CLI, requirements artifact, Brainstorm Agent responses, structured user answers.
- Produces: Phase 1a preliminary classification, Phase 1b final classification/dialogue/design, progress events, and register phase updates; does not yet implement approval decisions, which Task 5 adds.

- [ ] **Step 1: Write failing lifecycle contract tests**

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "core/agents/supervisor-bootstrap.md"


def test_preliminary_classification_runs_before_requirements_and_final_after():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert text.index("--stage preliminary") < text.index("Phase 1a: Requirement Collection Gate")
    assert text.index("Phase 1a: Requirement Collection Gate") < text.index("--stage final")


def test_architectural_questions_are_single_active_question():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "active_question_id" in text
    assert "one active question per task" in text
    assert "MODE=next_question" in text


def test_bounded_path_groups_high_impact_questions():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "Bounded" in text
    assert "grouped structured interaction" in text
```

- [ ] **Step 2: Run supervisor contract tests and verify RED**

Run: `python3 -m pytest tests/python/test_brainstorm_supervisor_contract.py -q`

Expected: assertions fail because the Brainstorm Phase is not present.

- [ ] **Step 3: Add preliminary classification before requirements collection**

Document and execute:

```bash
python3 "${AGENT_CREW_HOME}/scripts/brainstorm-classification.py" \
  --stage preliminary \
  --task "${TASK}" \
  --evidence-file "${TASK_DIR}/context/brainstorm-preliminary-evidence.json" \
  --format json \
  > "${TASK_DIR}/context/brainstorm-classification.json"
```

Render `BRAINSTORM_CLASSIFICATION`, `REASON`, and `PROCESS`. Use preliminary `Architectural` to select the one-question deep interview and preliminary `Bounded` to select grouped high-impact requirements. Preliminary state must never set approval status.

- [ ] **Step 4: Add final classification and user-visible resolution after requirements**

Delegate `MODE=classify` to Brainstorm Agent, store its response without rewriting, and run the classifier with `--stage final --requirements-file ... --semantic-file ...`. On deterministic classifier failure, emit `DEGRADED` and stop or take the heavier defensible path; never silently default to `Bounded`.

- [ ] **Step 5: Add adaptive dialogue and design generation**

For `Spike`, present the probe contract and terminate after findings. For `Bounded`, collect unresolved high-impact questions in one structured interaction and ask the Brainstorm Agent for a short design. For `Architectural`, repeat `MODE=next_question` with one `active_question_id` until readiness, then call `MODE=compare` and `MODE=design`.

Persist each response using a new idempotency key before asking the next question. Record section acknowledgements separately from final approval. Validate the generated design for unfinished markers, contradictions, scope overflow, and blocking unknowns before advancing.

- [ ] **Step 6: Run focused lifecycle tests and verify GREEN**

Run: `python3 -m pytest tests/python/test_brainstorm_supervisor_contract.py -q`

Expected: all tests pass.

- [ ] **Step 7: Refactor the prompt contract and re-run tests**

Keep classification, question rendering, artifact persistence, and design validation in separate titled subsections. Ensure phase prose contains no duplicate approval implementation that belongs to Task 5.

Run: `python3 -m pytest tests/python/test_brainstorm_supervisor_contract.py tests/python/test_brainstorm_agent_contract.py -q`

Expected: all tests pass.

- [ ] **Step 8: Commit the Brainstorm state machine**

```bash
git add core/agents/supervisor-bootstrap.md core/agents/supervisor.md tests/python/test_brainstorm_supervisor_contract.py
git commit -m "feat: add brainstorm phase to supervisor"
```

---

### Task 5: Design Approval, Downgrade, Hash Binding, and Resume

**Files:**
- Modify: `core/agents/supervisor-bootstrap.md`
- Modify: `core/agents/supervisor.md`
- Modify: `tests/python/test_brainstorm_supervisor_contract.py`
- Create: `tests/integration/test_brainstorm_workflow.bash`

**Interfaces:**
- Consumes: final classification, canonical design fields/hash, user design decision or downgrade decision, existing `approval.md` execution gate.
- Produces: `brainstorm-approval.json`, bounded combined approval binding, invalidation events, and exact resume position.

- [ ] **Step 1: Add failing approval and resume contract tests**

```python
def test_architectural_plan_cannot_start_before_design_approval():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    design_gate = text.index("approval_kind: architectural_design")
    analyst_phase = text.index("Phase 1c: Analyst")
    assert design_gate < analyst_phase
    assert "approved design_hash" in text[design_gate:analyst_phase]


def test_bounded_approval_binds_design_and_plan_hashes_once():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "approval_kind: bounded_combined" in text
    assert "design_hash" in text
    assert "execution_plan_hash" in text
    assert "separate bounded design approval" not in text


def test_downgrade_does_not_change_external_action_gates():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "downgrade changes brainstorming ceremony only" in text
    assert "Phase 2.5 remains required" in text
```

Add Bash scenarios for question resume, final design approval resume, downgrade, changed design hash, and `Bounded` to `Architectural` promotion.

- [ ] **Step 2: Run focused contract and integration tests and verify RED**

Run: `python3 -m pytest tests/python/test_brainstorm_supervisor_contract.py -q && bash tests/integration/test_brainstorm_workflow.bash`

Expected: new approval assertions/scenarios fail.

- [ ] **Step 3: Implement Architectural design approval**

After self-review, display the complete design and write a pending `architectural_design` record. Only Supervisor/orchestrator renders the structured approval. On approval, store `design_hash`, canonical `bound_fields`, `decision_at`, and idempotency key. On changes or cancellation, return to design refinement or terminate without creating PRD/pipeline.

- [ ] **Step 4: Implement informed downgrade**

Before offering downgrade, display automatic classification, evidence, skipped design steps, expected risks, and affected boundaries. Store both automatic results and the user decision. The resulting path is `Bounded`, but retain the original `Architectural` classification and `override: Bounded` rather than rewriting history.

- [ ] **Step 5: Bind Bounded design and execution plan into Phase 1d**

Extend the existing Phase 1d record so one structured interaction binds:

```json
{
  "approval_kind": "bounded_combined",
  "design_hash": "<sha256>",
  "execution_plan_hash": "<sha256>",
  "classification_hash": "<sha256>",
  "status": "approved"
}
```

Do not create a separate bounded design approval or add another user interaction.

- [ ] **Step 6: Implement invalidation and precise resume**

Recompute canonical hashes at every phase boundary. A changed goal, non-goal, interface, responsibility boundary, data model, repository/module set, risk, pipeline, classification, or downgrade status invalidates dependent approvals. Display-copy changes do not. Resume by dialogue/design/approval status; never treat a placeholder file as approval.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run: `python3 -m pytest tests/python/test_brainstorm_supervisor_contract.py -q && bash tests/integration/test_brainstorm_workflow.bash`

Expected: all Python assertions and Bash scenarios pass.

- [ ] **Step 8: Run state-schema validation and refactor duplicated hash checks**

Run: `python3 -m pytest tests/python/test_brainstorm_state_schema.py tests/python/test_validate_state_schema.py -q`

Expected: all tests pass. Consolidate repeated canonical-hash verification into the classifier CLI instead of copying JSON normalization snippets across approval subsections.

- [ ] **Step 9: Commit approval and resume behavior**

```bash
git add core/agents/supervisor-bootstrap.md core/agents/supervisor.md tests/python/test_brainstorm_supervisor_contract.py tests/integration/test_brainstorm_workflow.bash
git commit -m "feat: bind brainstorm design approvals"
```

---

### Task 6: Analyst Boundary and Multi-task Orchestrator Integration

**Files:**
- Modify: `core/agents/analyst.md`
- Modify: `core/commands/run.md`
- Modify: `tests/python/test_brainstorm_supervisor_contract.py`
- Modify: `tests/integration/test_brainstorm_workflow.bash`

**Interfaces:**
- Consumes: accepted/approved `brainstorm-design.md`, design hash, and classification artifact.
- Produces: analyst artifacts linked to the design hash; orchestrator-controlled per-task Brainstorm interactions without cross-task dialogue mixing.

- [ ] **Step 1: Write failing analyst and orchestrator tests**

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYST = REPO_ROOT / "core/agents/analyst.md"
RUN_MD = REPO_ROOT / "core/commands/run.md"


def test_analyst_requires_matching_brainstorm_design_hash():
    text = ANALYST.read_text(encoding="utf-8")
    assert "BRAINSTORM_DESIGN_PATH" in text
    assert "BRAINSTORM_DESIGN_HASH" in text
    assert "brainstorm_design_hash_mismatch" in text
    assert "Never expand the accepted design" in text


def test_run_orchestrator_keeps_dialogue_order_per_task():
    text = RUN_MD.read_text(encoding="utf-8")
    assert "one active Brainstorm question per task" in text
    assert "task_id" in text
    assert "preserve per-task question order" in text
```

Extend the integration fixture to start two tasks, answer one task, and assert that the other task's `active_question_id` and dialogue history are unchanged.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python3 -m pytest tests/python/test_brainstorm_supervisor_contract.py -q && bash tests/integration/test_brainstorm_workflow.bash`

Expected: analyst hash and multi-task isolation assertions fail.

- [ ] **Step 3: Move merged analyst planning to Phase 1c and bind its inputs**

Update agent trigger documentation from Phase 1b+1c to Phase 1c. Add inputs:

```text
BRAINSTORM_CLASSIFICATION_PATH: {TASK_DIR}/context/brainstorm-classification.json
BRAINSTORM_DESIGN_PATH: {TASK_DIR}/context/brainstorm-design.md
BRAINSTORM_DESIGN_HASH: {approved or accepted canonical hash}
```

Before writing analysis/PRD/pipeline, verify the artifact hash and design status. Return `STATUS: BLOCKED` with `BLOCKER: brainstorm_design_hash_mismatch` or `brainstorm_design_not_accepted` when invalid. Copy `brainstorm_design_hash` into `analysis.md`, `prd.md`, and `pipeline.json`. State explicitly that the analyst may identify a needed scope expansion but must return it to Phase 1b instead of silently expanding the design.

- [ ] **Step 4: Update `crew:run` orchestration for Brainstorm interactions**

Single task: route structured questions and design approval to its Supervisor. Multiple tasks: each task keeps one active question and ordered dialogue; the orchestrator may present task-labeled interactions together only when doing so does not violate an architectural task's dependency on its previous answer. Keep candidate selection, design approval, execution approval, and external-action approval as distinct recorded decisions.

- [ ] **Step 5: Preserve legacy resume compatibility**

When an older task has a valid `phase_1bc` pipeline and no Brainstorm artifacts, resume under the legacy approved-plan contract. Do not fabricate retrospective Brainstorm approval. New tasks always use `phase_1b_brainstorm` then `phase_1c_plan`.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run: `python3 -m pytest tests/python/test_brainstorm_supervisor_contract.py -q && bash tests/integration/test_brainstorm_workflow.bash`

Expected: all tests pass, including the two-task isolation scenario.

- [ ] **Step 7: Run analyst and pipeline regression tests**

Run: `python3 -m pytest tests/python/test_acceptance_criteria_contract.py tests/python/test_pipeline_capability_check.py tests/python/test_quality_loop_gate.py -q && bash tests/integration/test_pipeline_schema_validity.bash`

Expected: all tests pass.

- [ ] **Step 8: Perform the refactor review and rerun the focused tests**

Remove duplicated Brainstorm input descriptions between `analyst.md` and `run.md` by keeping the authoritative field contract in the agent definition and linking to it from the command. Do not extract wording whose duplication is required for host handoff safety.

Run: `python3 -m pytest tests/python/test_brainstorm_supervisor_contract.py -q && bash tests/integration/test_brainstorm_workflow.bash`

Expected: all tests still pass.

- [ ] **Step 9: Commit analyst and orchestrator integration**

```bash
git add core/agents/analyst.md core/commands/run.md tests/python/test_brainstorm_supervisor_contract.py tests/integration/test_brainstorm_workflow.bash
git commit -m "feat: connect brainstorm design to crew planning"
```

---

### Task 7: Operator Surfaces, Documentation, and Full Regression

**Files:**
- Modify: `core/commands/status.md`
- Modify: `core/commands/smm.md`
- Modify: `README.md`
- Modify: `tests/python/test_readme_runtime_alignment.py`
- Modify: `tests/integration/test_crew_status_render.bash`
- Modify: `tests/integration/test_brainstorm_workflow.bash`

**Interfaces:**
- Consumes: register Brainstorm fields and durable artifacts.
- Produces: concise operator-visible classification, pending interaction, design approval state, documentation, and full-suite evidence.

- [ ] **Step 1: Write failing status and documentation alignment tests**

```python
def test_readme_documents_brainstorm_phase_and_approval_split():
    text = readme_text()
    assert "Spike / Bounded / Architectural" in text
    assert "Brainstorm Phase" in text
    assert "Bounded" in text and "combined design and plan approval" in text
    assert "Architectural" in text and "separate design approval" in text
    assert "crew:agent" in text and "unchanged" in text
```

Add status fixtures asserting:

```text
Phase      : phase_1b_brainstorm
Brainstorm : Architectural / waiting_for_input
Question   : q-2
Design     : pending
```

- [ ] **Step 2: Run documentation and status tests and verify RED**

Run: `python3 -m pytest tests/python/test_readme_runtime_alignment.py -q && bash tests/integration/test_crew_status_render.bash`

Expected: assertions fail because the new operator surface is undocumented and unrendered.

- [ ] **Step 3: Update status and SMM rendering**

Prefer register pointers; read Brainstorm artifacts only when present. Show classification, dialogue status, active question ID, design approval status, and downgrade marker. For legacy tasks, omit the Brainstorm block rather than displaying false defaults. Keep output concise and read-only.

- [ ] **Step 4: Update README lifecycle and artifact documentation**

Replace the old `requirements → analyst+planner → approval` diagrams and tables with the new Phase 1a/1b/1c/1d flow. Document preliminary versus final classification, interaction differences, downgrade limits, combined versus separate approval, artifact layout, resume behavior, and unchanged `crew:agent`/external-action boundaries.

- [ ] **Step 5: Run focused operator/documentation tests and verify GREEN**

Run: `python3 -m pytest tests/python/test_readme_runtime_alignment.py -q && bash tests/integration/test_crew_status_render.bash`

Expected: all tests pass.

- [ ] **Step 6: Run every Brainstorm-focused test together**

Run: `python3 -m pytest tests/python/test_brainstorm_classification.py tests/python/test_brainstorm_state_schema.py tests/python/test_brainstorm_agent_contract.py tests/python/test_brainstorm_supervisor_contract.py tests/python/test_validate_state_schema.py -q && bash tests/integration/test_brainstorm_workflow.bash`

Expected: all tests pass with zero failures.

- [ ] **Step 7: Run the complete offline repository suite**

Run: `bash tests/run-all.sh`

Expected: Python, shell, and integration suites all report `PASS` with zero failures.

- [ ] **Step 8: Review the final diff for scope and generated/mirror consistency**

Run: `git diff --check && git status --short && git diff --stat`

Expected: no whitespace errors; only files named in this plan plus mechanically generated adapter mirrors required by existing setup tests are changed. Confirm no `crew:agent`, external-write, push, deployment, or dangerous-command approval behavior was weakened.

- [ ] **Step 9: Commit operator surfaces and documentation**

```bash
git add core/commands/status.md core/commands/smm.md README.md tests/python/test_readme_runtime_alignment.py tests/integration/test_crew_status_render.bash tests/integration/test_brainstorm_workflow.bash
git commit -m "docs: document crew brainstorm workflow"
```

---

## Final Verification Checklist

- [ ] `python3 -m pytest tests/python/test_brainstorm_classification.py tests/python/test_brainstorm_state_schema.py tests/python/test_brainstorm_agent_contract.py tests/python/test_brainstorm_supervisor_contract.py tests/python/test_validate_state_schema.py -q`
- [ ] `bash tests/integration/test_brainstorm_workflow.bash`
- [ ] `bash tests/run-all.sh`
- [ ] `python3 core/scripts/agent-capability-check.py --format json`
- [ ] `git diff --check`
- [ ] Confirm `crew:run` shows classification and evidence before implementation.
- [ ] Confirm bounded work uses one combined approval interaction.
- [ ] Confirm architectural planning is impossible before design approval.
- [ ] Confirm user downgrade does not alter external-action approvals.
- [ ] Confirm resume returns to the exact pending question or approval boundary.
- [ ] Confirm legacy approved `phase_1bc` tasks resume without fabricated Brainstorm state.
- [ ] Confirm `crew:agent` behavior is unchanged.
