#!/bin/bash
# auto-route.sh - detect natural-language development requests and inject routing context.

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json
import re
import sys

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

try:
    data = json.loads(raw_input)
    prompt = data.get("prompt", "")
except Exception:
    sys.exit(0)

if prompt.startswith("/"):
    sys.exit(0)

if not prompt.strip():
    sys.exit(0)

COMMAND_PAT = r"^\s*(crew:run|ac:crew)(?:\s+(.*))?$"
command_match = re.match(COMMAND_PAT, prompt, re.IGNORECASE | re.DOTALL)
if command_match:
    args = (command_match.group(2) or "").strip()
    args_note = (
        f"Command arguments detected: {args}"
        if args
        else "No command arguments were provided. Follow Step 1 of the command definition and ask for the task description through the host structured input UI."
    )
    directive = f"""[agent-crew] COMMAND — explicit crew:run invocation detected.

The user is invoking the agent-crew workflow command. Do NOT reinterpret this as
a request to run generic project verification, CI, linting, or any host-default task.

Immediate action:
  Execute the workflow defined in ~/.agent-crew/commands/run.md.

{args_note}

Execution rules:
- Treat `crew:run` / `ac:crew` as a command invocation, not natural language.
- Follow the command definition step-by-step, including mandatory requirements collection.
- Delegate execution to task-runner as defined by the command.
- Do NOT replace the workflow with "standard verification" or a direct shell command."""

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": directive,
        }
    }

    print(json.dumps(output, ensure_ascii=True))
    sys.exit(0)

BACKEND_PAT = (
    r"API|backend|server|endpoint|domain|Entity|Repository|Service|Kotlin|"
    r"Spring|DB|database|storage|query|table|controller|Controller|UseCase|"
    r"Command|Event|백엔드|서버|엔드포인트|"
    r"도메인|데이터베이스|저장소|"
    r"쿼리|테이블|컨트롤러"
)
FRONTEND_PAT = (
    r"frontend|UI|screen|component|React|Vue|Next|page|button|form|modal|"
    r"layout|style|CSS|HTML|프론트엔드|화면|"
    r"컴포넌트|페이지|버튼|폼|"
    r"모달|레이아웃|스타일"
)
FULLSTACK_PAT = (
    r"full.?stack|full development|service development|app development|"
    r"system development|풀스택|전체\s*개발|"
    r"서비스\s*개발|앱\s*개발|"
    r"시스템\s*개발"
)
DESIGN_PAT = (
    r"UI design|screen design|UX|design spec|wireframe|"
    r"UI\s*설계|화면\s*설계|"
    r"디자인\s*명세|와이어프레임"
)
ACTION_PAT = (
    r"build|implement|create|add|develop|rename|refactor|update|fix|remove|"
    r"delete|move|change|migrate|modify|replace|extend|integrate|"
    r"만들어|구현해|개발해|"
    r"추가해|수정해|작성해|"
    r"생성해|만들고|구현하고|"
    r"보완|개선|추가|제거|변경|수정|업데이트|"
    r"반영|정리|배포|테스트|리뷰|머지|롤백|시도"
)
QUESTION_PAT = (
    r"why|what|how|explain|describe|"
    r"어떻게|뭐야|무엇|왜|어떤|설명|"
    r"알려|이해"
)
MEMORY_PAT = (
    r"memory|MEMORY\.md|remember|recall|"
    r"기억|피드백|메모리"
)
MEMORY_PATH_PAT = (
    r"~/\.claude/projects/|memory/"
)
# Matches filenames with common code/config extensions
FILE_EXT_PAT = (
    r"\b(?:README|AGENTS|CLAUDE)(?:\.md)?\b|"
    r"\b[\w][\w\-\.]*\.(md|sh|ts|tsx|kt|py|json|yaml|yml|js|jsx)\b"
)
# Matches agent-crew system keywords (Korean and English)
PROJECT_KEYWORD_PAT = (
    r"harness|hook|pipeline|task.?runner|planner|workflow|"
    r"하네스|에이전트|훅|파이프라인|"
    r"플래너|워크플로우"
)
WORKFLOW_ACTION_PAT = (
    r"deploy|deployment|CI|test suite|run tests|merge|rollback|retry|"
    r"배포해?|테스트\s*돌려|리뷰어?\s*붙여|"
    r"병렬로\s*실행|머지해?|롤백|다시\s*시도|요구사항\s*정리"
)


def match(pattern):
    return bool(re.search(pattern, prompt, re.IGNORECASE))


if match(QUESTION_PAT) and not match(ACTION_PAT):
    sys.exit(0)

# Memory/feedback meta-operations: skip routing unless combined with ACTION_PAT
if re.search(MEMORY_PATH_PAT, prompt, re.IGNORECASE):
    if not match(ACTION_PAT):
        sys.exit(0)
if match(MEMORY_PAT) and not match(ACTION_PAT):
    sys.exit(0)

# 저장/기록 without code/file/system target: skip routing
SAVE_PAT = r"저장|기록"
CODE_TARGET_PAT = (
    r"\b(?:README|AGENTS|CLAUDE)(?:\.md)?\b|"
    r"\b[\w][\w\-\.]*\.(md|sh|ts|tsx|kt|py|json|yaml|yml|js|jsx)\b|"
    r"코드|파일|시스템|데이터베이스|DB|서버|API|"
    r"harness|hook|pipeline|task.?runner|planner|workflow|"
    r"하네스|에이전트|훅|파이프라인|플래너|워크플로우"
)
if re.search(SAVE_PAT, prompt, re.IGNORECASE):
    if not re.search(CODE_TARGET_PAT, prompt, re.IGNORECASE):
        sys.exit(0)

detected_type = ""
suggested_pipeline = ""
suggested_agent = ""

# --- Existing domain-specific routing ---

if match(ACTION_PAT):
    if match(FULLSTACK_PAT):
        detected_type = "full-stack development"
        suggested_pipeline = "planner -> [designer || backend] -> frontend"
        suggested_agent = "planner"
    elif match(DESIGN_PAT):
        detected_type = "UI design"
        suggested_pipeline = "designer -> frontend"
        suggested_agent = "designer"
    elif match(FRONTEND_PAT) and match(BACKEND_PAT):
        detected_type = "full-stack development"
        suggested_pipeline = "planner -> [designer || backend] -> frontend"
        suggested_agent = "planner"
    elif match(FRONTEND_PAT):
        detected_type = "frontend development"
        suggested_pipeline = "designer -> frontend"
        suggested_agent = "designer"
    elif match(BACKEND_PAT):
        detected_type = "backend development"
        suggested_pipeline = "backend"
        suggested_agent = "backend"

# --- Extended pattern detection ---
# Triggers when no specific domain matched yet.

if not detected_type:
    # File extension mention implies direct file manipulation request
    has_file_ref = match(FILE_EXT_PAT)
    # agent-crew system keyword implies project-level implementation
    has_project_kw = match(PROJECT_KEYWORD_PAT)
    # General implementation verb paired with file reference or project keyword
    has_action = match(ACTION_PAT)
    # Short operational workflow commands can imply project-level execution
    # even when no specific file or subsystem is named.
    has_workflow_action = match(WORKFLOW_ACTION_PAT)
    # Memory keyword + action verb = memory file manipulation (still an implementation task)
    has_memory_action = match(MEMORY_PAT) and has_action

    if has_file_ref or has_project_kw or has_workflow_action or has_memory_action:
        detected_type = "project implementation"
        suggested_pipeline = 'crew:run "your request"'

if not detected_type:
    sys.exit(0)

if detected_type == "project implementation":
    directive = f"""[agent-crew] STOP — implementation request detected ({detected_type}).

IMMEDIATE ACTION REQUIRED: Call crew:run RIGHT NOW as your very first action.
Do NOT explain, diagnose, read files, or run any Bash before calling crew:run.
Any action other than crew:run is a system violation.

REQUIRED action:
  {suggested_pipeline}

Rules enforced by this directive:
- Do NOT produce any output before calling crew:run.
- Do NOT run exploratory Bash (git status, ls, cat, etc.) before crew:run.
- Do NOT ask clarifying questions before crew:run.
- Do NOT edit or write files directly — the task-runner pipeline handles implementation.
Call crew:run NOW."""
else:
    directive = f"""[agent-crew] STOP — implementation request detected ({detected_type}).

IMMEDIATE ACTION REQUIRED: Call crew:run RIGHT NOW as your very first action.
Do NOT explain, diagnose, read files, or run any Bash before calling crew:run.
Any action other than crew:run is a system violation.

REQUIRED action — choose one:
  crew:run "{suggested_agent} task"        (single task)
  crew:run "TaskA" | "TaskB"              (parallel tasks)

Suggested pipeline: {suggested_pipeline}

Rules enforced by this directive:
- Do NOT produce any output before calling crew:run.
- Do NOT run exploratory Bash (git status, ls, cat, etc.) before crew:run.
- Do NOT ask clarifying questions before crew:run.
- Do NOT edit or write files directly — the task-runner pipeline handles implementation.
Call crew:run NOW."""

output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": directive,
    }
}

print(json.dumps(output, ensure_ascii=True))
PYEOF
