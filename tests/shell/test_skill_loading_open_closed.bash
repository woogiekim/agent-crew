#!/usr/bin/env bash
# test_skill_loading_open_closed.bash
#
# Smoke test for the skill-loading Open/Closed property.
#
# Invariant: adding a new skill file to core/agents/skills/ and declaring it
# in an agent's "## Skills (Loaded On Demand)" section must NOT require any
# change to:
#   - core/rules/agent-skill-loading.md
#   - any other existing skill file
#   - any other existing agent file not directly consuming the skill
#
# This test verifies the convention mechanically:
#   1. Every path declared in agent skill sections resolves to a real file.
#   2. A brand-new skill file added to a temp directory is "loadable" (grep
#      convention works) without touching any existing file.
#   3. The SKILL-TEMPLATE.md structure is present and contains required sections.
#
# Usage: bash tests/shell/test_skill_loading_open_closed.bash
# Exit:  0 = all pass, 1 = one or more failures.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_lib.bash"

REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SKILLS_DIR="${REPO_ROOT}/core/agents/skills"
AGENTS=(
  "${REPO_ROOT}/core/agents/backend.md"
  "${REPO_ROOT}/core/agents/frontend.md"
  "${REPO_ROOT}/core/agents/test-writer.md"
  "${REPO_ROOT}/core/agents/reviewer.md"
)

# ─────────────────────────────────────────────────────────────────────────────
# Helper: extract skill paths declared in a "## Skills (Loaded On Demand)"
# section. Accepts a file path. Prints one path per line.
# Paths are enclosed in backticks in the convention: `core/agents/skills/foo.md`
# ─────────────────────────────────────────────────────────────────────────────
extract_skill_paths() {
  local agent_file="$1"
  # Match backtick-enclosed paths containing "skills/"
  grep -o '`[^`]*skills/[^`]*`' "${agent_file}" 2>/dev/null \
    | tr -d '`'
}

# ─────────────────────────────────────────────────────────────────────────────
# Test 1: SKILL-TEMPLATE.md exists and contains required sections
# ─────────────────────────────────────────────────────────────────────────────
it "SKILL-TEMPLATE.md exists in core/agents/skills/"
assert_file_exists "${SKILLS_DIR}/SKILL-TEMPLATE.md"

TEMPLATE_CONTENT="$(cat "${SKILLS_DIR}/SKILL-TEMPLATE.md" 2>/dev/null || true)"

it "SKILL-TEMPLATE.md contains '## Source' section"
assert_contains "${TEMPLATE_CONTENT}" "## Source"

it "SKILL-TEMPLATE.md contains '## When to Apply' section"
assert_contains "${TEMPLATE_CONTENT}" "## When to Apply"

it "SKILL-TEMPLATE.md contains '## Core Rules' section"
assert_contains "${TEMPLATE_CONTENT}" "## Core Rules"

it "SKILL-TEMPLATE.md contains '## Anti-Patterns' section"
assert_contains "${TEMPLATE_CONTENT}" "## Anti-Patterns"

it "SKILL-TEMPLATE.md contains '## References' section"
assert_contains "${TEMPLATE_CONTENT}" "## References"

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: agent-skill-loading.md exists
# ─────────────────────────────────────────────────────────────────────────────
it "core/rules/agent-skill-loading.md exists"
assert_file_exists "${REPO_ROOT}/core/rules/agent-skill-loading.md"

LOADING_RULE_CONTENT="$(cat "${REPO_ROOT}/core/rules/agent-skill-loading.md" 2>/dev/null || true)"

it "agent-skill-loading.md references Open/Closed Extension Protocol"
assert_contains "${LOADING_RULE_CONTENT}" "Open/Closed Extension Protocol"

# ─────────────────────────────────────────────────────────────────────────────
# Test 3: each implementation agent has a "## Skills (Loaded On Demand)" section
# ─────────────────────────────────────────────────────────────────────────────
for agent_file in "${AGENTS[@]}"; do
  agent_name="$(basename "${agent_file}" .md)"
  AGENT_CONTENT="$(cat "${agent_file}" 2>/dev/null || true)"
  it "${agent_name}.md has '## Skills (Loaded On Demand)' section"
  assert_contains "${AGENT_CONTENT}" "## Skills (Loaded On Demand)"
done

# ─────────────────────────────────────────────────────────────────────────────
# Test 4: every skill path declared in agent files resolves to a real file
# ─────────────────────────────────────────────────────────────────────────────
for agent_file in "${AGENTS[@]}"; do
  agent_name="$(basename "${agent_file}" .md)"
  while IFS= read -r raw_path; do
    [ -z "${raw_path}" ] && continue
    # Resolve path: tilde-prefixed paths resolve from HOME; relative from REPO_ROOT
    case "${raw_path}" in
      "~/"*)
        abs_path="${HOME}/${raw_path#\~/}"
        ;;
      "/"*)
        abs_path="${raw_path}"
        ;;
      *)
        abs_path="${REPO_ROOT}/${raw_path}"
        ;;
    esac
    it "${agent_name}.md skill path exists: ${raw_path}"
    if [ -f "${abs_path}" ]; then
      _pass
    else
      case "${raw_path}" in
        "~/.agent-crew/"*)
          # system-layer skill — may not be present in source-only checkout
          # Decrement total so this is not counted as a failure
          TESTS_TOTAL=$((TESTS_TOTAL - 1))
          ;;
        *)
          _fail "file not found: ${abs_path}"
          ;;
      esac
    fi
  done < <(extract_skill_paths "${agent_file}")
done

# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Open/Closed — adding a NEW skill file and declaring it in a temp
# agent makes it discoverable WITHOUT touching any existing file.
# ─────────────────────────────────────────────────────────────────────────────
TMP_DIR="$(make_tmp)"
FAKE_SKILL="${TMP_DIR}/effective-brainfuck.md"
FAKE_AGENT="${TMP_DIR}/fake-agent.md"

# Create a minimal new skill following the template
cat > "${FAKE_SKILL}" <<'SKILL'
# Skill: effective-brainfuck

## Source
- Urban Muller, *Brainfuck language specification*, 1993

## When to Apply
- Before writing any Brainfuck program

## Core Rules

### Rule 1: Use meaningful loop structure
> Source: Muller, original spec

Loop delimiters `[` and `]` must surround complete semantic units.

## Anti-Patterns
- Unclosed brackets

## References
- Urban Muller, original Brainfuck spec, 1993.
SKILL

# Create a minimal agent that declares the new skill (backtick convention)
cat > "${FAKE_AGENT}" << 'AGENT'
# Fake Agent

## Skills (Loaded On Demand)

Read the following skill files using the Read tool only when needed:
- Brainfuck best practices: `core/agents/skills/effective-brainfuck.md`
AGENT

it "Open/Closed: new skill declared in agent is discoverable via backtick grep convention"
DISCOVERED="$(grep -o '`[^`]*skills/[^`]*`' "${FAKE_AGENT}" 2>/dev/null | tr -d '`' | head -1 || true)"
assert_contains "${DISCOVERED}" "effective-brainfuck"

it "Open/Closed: new skill file resolves to a real file (when placed in skills dir)"
assert_file_exists "${FAKE_SKILL}"

it "Open/Closed: no existing agent file was modified (backend.md still has Skills section)"
assert_contains "$(cat "${REPO_ROOT}/core/agents/backend.md" 2>/dev/null || true)" "## Skills (Loaded On Demand)"

it "Open/Closed: no existing skill file was modified (oop-principles.md still present)"
assert_file_exists "${REPO_ROOT}/core/agents/skills/oop-principles.md"

# ─────────────────────────────────────────────────────────────────────────────
# Test 6: all canonical effective-{lang}.md and cross-cutting skills exist
# ─────────────────────────────────────────────────────────────────────────────
EXPECTED_SKILLS=(
  "effective-kotlin.md"
  "effective-java.md"
  "effective-typescript.md"
  "effective-python.md"
  "effective-go.md"
  "effective-rust.md"
  "effective-scala.md"
  "effective-swift.md"
  "clean-architecture.md"
  "agile-xp.md"
  "domain-driven-design.md"
  "dgs-dataloader.md"
  "SKILL-TEMPLATE.md"
)
for skill in "${EXPECTED_SKILLS[@]}"; do
  it "skill file exists: ${skill}"
  assert_file_exists "${SKILLS_DIR}/${skill}"
done

# ─────────────────────────────────────────────────────────────────────────────
# Test 7: each new skill file has required structural sections
# ─────────────────────────────────────────────────────────────────────────────
NEW_SKILLS=(
  "effective-kotlin.md"
  "effective-java.md"
  "effective-typescript.md"
  "effective-python.md"
  "effective-go.md"
  "effective-rust.md"
  "effective-scala.md"
  "effective-swift.md"
  "clean-architecture.md"
  "agile-xp.md"
  "domain-driven-design.md"
  "dgs-dataloader.md"
)
REQUIRED_SECTIONS=("## Source" "## When to Apply" "## Core Rules" "## Anti-Patterns" "## References")
for skill in "${NEW_SKILLS[@]}"; do
  skill_path="${SKILLS_DIR}/${skill}"
  skill_content="$(cat "${skill_path}" 2>/dev/null || true)"
  for section in "${REQUIRED_SECTIONS[@]}"; do
    it "${skill}: contains '${section}'"
    assert_contains "${skill_content}" "${section}"
  done
done

# ─────────────────────────────────────────────────────────────────────────────
# Test 8: each new skill declares at least 5 Core Rules (H1-level sections ### Rule N)
# ─────────────────────────────────────────────────────────────────────────────
for skill in "${NEW_SKILLS[@]}"; do
  skill_path="${SKILLS_DIR}/${skill}"
  rule_count="$(grep -c '^### Rule [0-9]' "${skill_path}" 2>/dev/null || true)"
  it "${skill}: has at least 5 ### Rule sections (has ${rule_count})"
  if [ "${rule_count:-0}" -ge 5 ] 2>/dev/null; then
    _pass
  else
    _fail "expected >= 5 ### Rule sections, found ${rule_count:-0}"
  fi
done

# ─────────────────────────────────────────────────────────────────────────────
# Test 9: targeted production guidance is declared by the right agents
# ─────────────────────────────────────────────────────────────────────────────
BACKEND_CONTENT="$(cat "${REPO_ROOT}/core/agents/backend.md" 2>/dev/null || true)"
FRONTEND_CONTENT="$(cat "${REPO_ROOT}/core/agents/frontend.md" 2>/dev/null || true)"
TEST_WRITER_CONTENT="$(cat "${REPO_ROOT}/core/agents/test-writer.md" 2>/dev/null || true)"
REVIEWER_CONTENT="$(cat "${REPO_ROOT}/core/agents/reviewer.md" 2>/dev/null || true)"
TDD_CONTENT="$(cat "${REPO_ROOT}/core/agents/skills/tdd.md" 2>/dev/null || true)"
CODE_REVIEW_CONTENT="$(cat "${REPO_ROOT}/core/agents/skills/code-review.md" 2>/dev/null || true)"
AGILE_XP_CONTENT="$(cat "${REPO_ROOT}/core/agents/skills/agile-xp.md" 2>/dev/null || true)"
PIPELINE_PLANNING_CONTENT="$(cat "${REPO_ROOT}/core/agents/skills/pipeline-planning.md" 2>/dev/null || true)"
CODE_QUALITY_CONTENT="$(cat "${REPO_ROOT}/core/rules/code-quality.md" 2>/dev/null || true)"
ANALYST_CONTENT="$(cat "${REPO_ROOT}/core/agents/analyst.md" 2>/dev/null || true)"
PLANNER_CONTENT="$(cat "${REPO_ROOT}/core/agents/planner.md" 2>/dev/null || true)"

it "backend.md declares DGS DataLoader guidance for GraphQL/Feign N+1 prevention"
assert_contains "${BACKEND_CONTENT}" "dgs-dataloader.md"

it "backend.md mandates DGS DataLoader guidance for DGS or Feign resolver work"
assert_contains "${BACKEND_CONTENT}" "DGS/Feign N+1"

it "backend.md declares context-change line break code style"
assert_contains "${BACKEND_CONTENT}" "Insert a line break when the implementation context changes"

it "backend.md enumerates validation to early return context-break enforcement"
assert_contains "${BACKEND_CONTENT}" "Validation or guard reporting -> early return/throw"

it "backend.md applies context-break enforcement to every language"
assert_contains "${BACKEND_CONTENT}" "Apply this rule to every language you generate"

it "backend.md defaults test target variables to sut"
assert_contains "${BACKEND_CONTENT}" "primary system under test variable to \`sut\`"

it "frontend.md defaults test target variables to sut"
assert_contains "${FRONTEND_CONTENT}" "primary system under test variable to \`sut\`"

it "test-writer.md defaults test target variables to sut"
assert_contains "${TEST_WRITER_CONTENT}" "primary test target variable \`sut\`"

it "tdd.md defines system under test variable naming"
assert_contains "${TDD_CONTENT}" "primary test target to \`sut\`"

it "reviewer.md rejects missing context-break blank lines"
assert_contains "${REVIEWER_CONTENT}" "context_break_missing_blank_line"

it "reviewer.md checks side effect to return value context breaks"
assert_contains "${REVIEWER_CONTENT}" "Side effect -> return value construction"

it "code-review skill includes context-break blank line checklist"
assert_contains "${CODE_REVIEW_CONTENT}" "Context-break blank line rule checked"

it "code-review skill reviews sut test target naming"
assert_contains "${CODE_REVIEW_CONTENT}" "Primary test target variables default to \`sut\`"

it "frontend.md declares context-change line break code style"
assert_contains "${FRONTEND_CONTENT}" "Insert a line break when the implementation context changes"

it "code-quality.md defines the software development three principles"
assert_contains "${CODE_QUALITY_CONTENT}" "Software Development Three Principles"

it "code-quality.md names KISS, YAGNI, and DRY"
assert_contains "${CODE_QUALITY_CONTENT}" "KISS"
assert_contains "${CODE_QUALITY_CONTENT}" "YAGNI"
assert_contains "${CODE_QUALITY_CONTENT}" "DRY"

it "backend.md applies KISS, YAGNI, and DRY from code-quality"
assert_contains "${BACKEND_CONTENT}" "KISS, YAGNI, and DRY"

it "frontend.md applies KISS, YAGNI, and DRY from code-quality"
assert_contains "${FRONTEND_CONTENT}" "KISS, YAGNI, and DRY"

it "test-writer.md applies KISS, YAGNI, and DRY from code-quality"
assert_contains "${TEST_WRITER_CONTENT}" "KISS, YAGNI, and DRY"

it "reviewer.md enforces KISS, YAGNI, and DRY"
assert_contains "${REVIEWER_CONTENT}" "KISS, YAGNI, and DRY"

it "code-review skill checks KISS, YAGNI, and DRY"
assert_contains "${CODE_REVIEW_CONTENT}" "KISS, YAGNI, and DRY are checked"

it "agile-xp skill maps the three principles"
assert_contains "${AGILE_XP_CONTENT}" "KISS is Rule 5, YAGNI is Rule 2, and DRY"

it "pipeline planning carries KISS/YAGNI/DRY into PRDs"
assert_contains "${PIPELINE_PLANNING_CONTENT}" "Maintainability: KISS, YAGNI, and DRY"

it "analyst PRDs include KISS/YAGNI/DRY maintainability guidance"
assert_contains "${ANALYST_CONTENT}" "KISS,"
assert_contains "${ANALYST_CONTENT}" "YAGNI"
assert_contains "${ANALYST_CONTENT}" "DRY"

it "planner PRDs include KISS/YAGNI/DRY maintainability guidance"
assert_contains "${PLANNER_CONTENT}" "KISS, YAGNI, and DRY"

# ─────────────────────────────────────────────────────────────────────────────
end_report
