#!/bin/bash
# auto-route.sh - detect natural-language development requests and inject routing context.

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json
import re
import shlex
import sys
import os
import shutil

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

def _env_flag(name):
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


if _env_flag("AGENT_CREW_AUTO_ROUTE_DISABLED") or _env_flag("AGENT_CREW_HOST_BRIDGE_ACTIVE"):
    sys.exit(0)


def _bridge_status():
    raw = os.environ.get("AGENT_CREW_HOST_BRIDGE_COMMAND", "").strip()
    if not raw:
        return (False, "AGENT_CREW_HOST_BRIDGE_COMMAND is not set.")
    try:
        argv = shlex.split(raw)
    except ValueError as error:
        return (False, f"AGENT_BRIDGE command is not parseable ({error}).")
    if not argv:
        return (False, "AGENT_CREW_HOST_BRIDGE_COMMAND is empty.")

    executable = argv[0]
    if os.path.isabs(executable) or "/" in executable:
        if os.path.isfile(executable) and os.access(executable, os.X_OK):
            return (True, "bridge executable is available.")
        return (False, f"bridge executable is not runnable: {executable}")

    if shutil.which(executable):
        return (True, "bridge executable is available.")
    return (False, f"bridge executable is not in PATH: {executable}")


HOST_BRIDGE_READY, HOST_BRIDGE_REASON = _bridge_status()

try:
    data = json.loads(raw_input)
    prompt = data.get("prompt", "")
except Exception:
    sys.exit(0)

if prompt.startswith("/"):
    sys.exit(0)

if not prompt.strip():
    sys.exit(0)

COMMAND_PAT = r"^\s*((?:crew|ac):(setup|run|crew|task|status|cost|agent-maker|agent|sync-instructions|telemetry|update))(?:\s+(.*))?$"
command_match = re.match(COMMAND_PAT, prompt, re.IGNORECASE | re.DOTALL)
if command_match:
    command = command_match.group(1).lower()
    intent = command_match.group(2).lower()
    args = (command_match.group(3) or "").strip()

    command_file_by_intent = {
        "setup": "setup.md",
        "run": "run.md",
        "crew": "run.md",
        "task": "run.md",
        "status": "status.md",
        "cost": "cost.md",
        "agent-maker": "agent-maker.md",
        "agent": "agent.md",
        "sync-instructions": "sync-instructions.md",
        "telemetry": "telemetry.md",
        "update": "update.md",
    }
    command_file = command_file_by_intent.get(intent, "run.md")

    if intent in ("run", "crew", "task"):
        args_note = (
            f"Command arguments detected: {args}"
            if args
            else "No command arguments were provided. Follow Step 1 of the command definition and ask for the task description through the host structured input UI."
        )
        intent_rules = """- Follow the command definition step-by-step, including mandatory requirements collection.
- Delegate execution to supervisor as defined by the command.
- Do NOT replace the workflow with "standard verification", CI, linting, or a direct shell command."""
    elif intent == "setup":
        args_note = "No task description is needed. Initialize the current project exactly as the setup command defines."
        intent_rules = """- Follow the setup command definition step-by-step.
- Do NOT inspect repository build files, Gradle/Kotlin configuration, package manifests, or CI files before executing setup.
- Run the host adapter setup flow and initialize agent-crew state as defined by the command."""
    else:
        args_note = (
            f"Command arguments detected: {args}"
            if args
            else "No command arguments were provided."
        )
        intent_rules = """- Follow the referenced command definition step-by-step.
- Do NOT substitute a host-default action or generic project inspection."""

    directive = f"""[agent-crew] COMMAND — explicit {command} invocation detected.

The user is invoking the agent-crew workflow command. Do NOT reinterpret this as
a request to inspect the repository, run generic verification, CI, linting, or
any host-default task.

Immediate action:
  Execute the workflow defined in ~/.agent-crew/commands/{command_file}.

{args_note}

Execution rules:
- Treat `{command}` as a command invocation, not natural language.
{intent_rules}"""

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
    r"why|what|how|explain|describe|tell me|show me|list|which|"
    r"어떻게|뭐야|무엇|왜|어떤|설명|"
    r"알려|이해|뭔지|뭔가|뭐가|뭘|어디|누가|언제|"
    r"있나요|합니까|인가요|할까요|됩니까|인지요|했나요|"
    r"활용|사용하고|쓰고|동작|작동|비교|평가|체크|쓸만|쓸\s*만|솔직"
)
# Truly atomic facts that need no agent — a bare yes/no, a bare file path,
# or a bare single number. These stay inline even when QUESTION_PAT fires.
# Must be very tight: multi-word or explanatory responses never qualify.
TRIVIAL_ATOMIC_PAT = (
    r"^\s*(yes|no|true|false|예|아니오|맞아|아니야)\s*[.!?]?\s*$|"  # bare yes/no
    r"^\s*~?/[\w./\-]+\s*$|"                                          # bare file path
    r"^\s*\d+(\.\d+)?\s*[a-zA-Z%]?\s*$"                               # bare number/metric
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
# Artifact-mutation pattern — catches natural-language requests to modify,
# save, publish, refine, or update repo/worktree/state artifacts (markdown,
# docs, issue drafts, etc.) without requiring a file extension in the prompt.
# Korean verbs: 정리, 저장, 발행, 반영, 수정, 고쳐, 업데이트, 작성, 수정해줘
# Artifact nouns: 파일, 문서, 이슈, 초안, 마크다운, 내용, 클로드가 저장
# Combined: the pattern must fire ONLY when both a mutation verb AND an
# artifact noun appear in the same prompt, to avoid false positives on
# pure read/explain requests that mention artifacts.
ARTIFACT_VERB_PAT = (
    r"정리\s*해|정리해줘|정리해서|저장해|저장된|발행해|발행했|반영해|반영했|"
    r"수정해|수정했|수정해줘|고쳐줘|고쳐서|업데이트해|업데이트했|"
    r"작성해줘|작성해서|써줘|써서|넣어줘|넣어서|바꿔줘|바꿔서|"
    r"publish|save\s+(?:this\s+)?to|write\s+(?:this\s+)?to|"
    r"update\s+(?:the\s+)?(?:doc|file|issue|draft|markdown|md)|"
    r"update\s+(?:the\s+)?saved|put\s+this\s+in|add\s+this\s+to"
)
ARTIFACT_NOUN_PAT = (
    r"파일|문서|이슈|초안|마크다운|내용|클로드가\s*저장|저장했던\s*파일|"
    r"저장한\s*파일|작성한\s*파일|작성된\s*파일|"
    r"issue\s*draft|work\s*item|plane\s*issue|github\s*issue|"
    r"saved\s+file|the\s+(?:file|doc|issue|draft)|"
    r"\.md\b|\.txt\b|docs?/"
)
ISSUE_PUBLICATION_PAT = (
    r"publish\s+(?:(?:the|these|those)\s+)?issues?|create\s+(?:(?:the|these|those)\s+)?(?:work\s+items?|issues?)|"
    r"update\s+(?:(?:the|these|those)\s+)?(?:work\s+items?|issues?)|rename\s+(?:(?:the|these|those)\s+)?(?:work\s+items?|issues?)|"
    r"change\s+(?:the\s+)?(?:work\s+item|issue)\s+title|"
    r"bulk\s+create\s+(?:work\s+items?|issues?)|import\s+(?:issues?|task\s+list)|"
    r"seed\s+(?:the\s+)?project|upload\s+(?:the\s+)?task\s+list|"
    r"issue\s+publication|work\s+item\s+creation|"
    r"이슈\s*(?:발행|생성|등록|업로드|수정|변경)|작업\s*항목\s*(?:생성|등록|수정|변경)|"
    r"업무\s*항목\s*(?:생성|등록|수정|변경)|제목\s*변경|태스크\s*목록\s*(?:가져오기|업로드)"
)
DIRECT_TRACKER_TOOL_PAT = (
    r"mcp__plane__(?:create|update|delete)_work_item|"
    r"mcp__gitlab__(?:create|update|delete)_issue|"
    r"gh\s+issue\s+create|"
    r"curl\s+.*(?:/issues|/work-items|/work_items)"
)
READONLY_REVIEW_PAT = (
    r"review|evaluate|assess|compare|honest\s+review|check|diagnos(?:e|is)|"
    r"inspect|determine|identify\s+(?:gaps|issues|problems|fixes)|"
    r"리뷰|검토|평가|비교|솔직|쓸만|쓸\s*만|"
    r"괜찮|문제점|개선점|부족|체크|고쳐야\s*하|뭘\s*고쳐|확인할\s*기준"
)
REVIEW_MUTATION_PAT = (
    r"fix\s+it|apply\s+the\s+fix|make\s+the\s+change|implement|"
    r"수정해|수정해줘|수정\s*(?:→|->|후|하고|및|,)|고쳐줘|반영해|반영해줘|구현해|"
    r"바꿔줘|넣어줘|업데이트해|업데이트해줘"
)
CONDITIONAL_REVIEW_FIX_PAT = (
    r"if\s+(?:needed|necessary|there\s+are\s+gaps)|if\s+.*(?:fix|improve)|"
    r"부족하면|필요하면|문제가\s*있으면|갭이\s*있으면"
)
FOLLOWUP_EXECUTION_PAT = (
    r"test\s*→|commit|push|crew-update|crew:update|"
    r"테스트\s*(?:→|->|후|하고|및|,)|커밋|푸시|push|업데이트까지|"
    r"수정\s*(?:→|->|후|하고|및|,)"
)


def match(pattern):
    return bool(re.search(pattern, prompt, re.IGNORECASE))


def emit_question_route(target_agent: str, route_reason: str):
    question_directive = (
        f"[agent-crew] ROUTE — question detected, routing to {target_agent} ({route_reason}).\n\n"
        f"Do NOT answer this question inline. In Codex, let any explicitly invoked "
        f"or domain-specific Codex skill load first, then invoke the crew-agent "
        f"skill wrapper with the question.\n\n"
        f"REQUIRED action:\n"
        f"  crew:agent \"{target_agent}\" \"{{user's question}}\"\n\n"
        f"Invoke Skill(\"crew-agent\") with the user's question and agent={target_agent}; "
        f"preserve any loaded Codex skill context as direct-agent input.\n"
        f"Direct inline responses for questions are forbidden — even short ones.\n"
        f"The ONLY permitted inline response is a bare atomic fact: "
        f"literal yes/no, a bare file path, or a bare single number with no explanation."
    )
    if not HOST_BRIDGE_READY:
        question_directive += (
            "\n\nHost bridge is unavailable ("
            f"{HOST_BRIDGE_REASON}). Crew routing still proceeds."
            "\nThe runtime will record a resumable internal handoff when no "
            "external bridge command is configured."
        )
    question_output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": question_directive,
        }
    }
    print(json.dumps(question_output, ensure_ascii=True))
    sys.exit(0)


def emit_no_bridge_inline_fallback(reason: str):
    """Compatibility shim for callsites that previously short-circuited inline."""
    return not HOST_BRIDGE_READY


if (
    match(QUESTION_PAT)
    and match(READONLY_REVIEW_PAT)
    and not match(ACTION_PAT)
    and not (match(CONDITIONAL_REVIEW_FIX_PAT) and match(FOLLOWUP_EXECUTION_PAT))
):
    if emit_no_bridge_inline_fallback("read-only review request"):
        pass

    emit_question_route("analyst", "read-only review/evaluation Q")


if match(READONLY_REVIEW_PAT) and re.search(
    r"do\s+not\s+edit|read[- ]only|no\s+files?\s+edited|수정하지\s*마|읽기\s*전용",
    prompt,
    re.IGNORECASE,
):
    if emit_no_bridge_inline_fallback("read-only explicit request"):
        pass

    emit_question_route("analyst", "read-only review/evaluation Q")

if match(QUESTION_PAT) and not match(ACTION_PAT):
    # Questions and explanations must go through crew:agent — not inline.
    # Exception: truly atomic facts (bare yes/no, bare path, bare number)
    # that need no explanation are allowed inline.
    if emit_no_bridge_inline_fallback("question"):
        pass

    if re.search(TRIVIAL_ATOMIC_PAT, prompt.strip(), re.IGNORECASE):
        sys.exit(0)  # bare atomic fact — inline is fine

    # Determine the best agent via the routing rules in agent-routing.md.
    # Default: analyst for codebase Q; historian for session/git/project state Q.
    HISTORIAN_PAT = (
        r"어떤\s*에이전트|방금|what just|what did|what ran|what agent|"
        r"this session|this branch|session history|spawned|이번\s*세션|"
        r"recent activity|currently running|어떤\s*commit|무슨\s*commit|"
        r"what('s|s)?\s+running|git log|git history|progress\.log"
    )
    if re.search(HISTORIAN_PAT, prompt, re.IGNORECASE):
        target_agent = "historian"
        route_reason = "session/git/project-state Q"
    else:
        target_agent = "analyst"
        route_reason = "codebase/explanation Q"

    emit_question_route(target_agent, route_reason)

# --- Trivial-intent fast-path (Change A) ---
# Detect short operational git intents that map to a known command template.
# These are handled directly by the model without a full crew:run waterfall.
# MUST NOT emit "STOP" or "crew:run" to avoid triggering the full pipeline.

TRIVIAL_INTENT_PAT = {
    # English intents — with "git" prefix
    r"\b(git\s+)?status\b":               ("git status",                    "status"),
    r"\bgit\s+push\b":                    ("git push",                      "push"),
    r"\bgit\s+merge\b":                   ("git merge <branch>",            "merge"),
    r"\bgit\s+tag\b":                     ("git tag <name>",                "tag"),
    r"\b(rollback|revert)\b":             ("git revert HEAD",               "rollback/revert"),
    r"\bgit\s+commit\b":                  ("git commit -m '...'",           "commit"),
    # English bare compound git operations (no "git" prefix required)
    r"\bmerge\s+and\s+push\b":            ("git merge <branch> && git push", "merge+push"),
    r"\bpush\s+and\s+merge\b":            ("git push && git merge <branch>", "push+merge"),
    r"^\s*push\s*$":                      ("git push",                      "push"),
    r"^\s*merge\s*$":                     ("git merge <branch>",            "merge"),
    r"^\s*commit\s*$":                    ("git commit -m '...'",           "commit"),
    # Korean equivalents
    r"머지|병합":                          ("git merge <branch>",            "merge"),
    r"푸시":                               ("git push",                      "push"),
    r"상태(\s*확인)?":                     ("git status",                    "status"),
    r"태그":                               ("git tag <name>",                "tag"),
    r"롤백|되돌리기":                      ("git revert HEAD",               "rollback/revert"),
    r"커밋":                               ("git commit -m '...'",           "commit"),
    r"머지\s*(하고|하고\s*나서)?\s*푸시":  ("git merge <branch> && git push", "merge+push"),
    r"푸시\s*(하고|하고\s*나서)?\s*머지":  ("git push && git merge <branch>", "push+merge"),
}

DESTRUCTIVE_INTENTS = {"push", "merge", "deploy", "tag", "rollback/revert", "merge+push", "push+merge"}

fast_path_candidate = len(prompt.strip()) <= 120 and "\n" not in prompt
if fast_path_candidate:
    for pat, (cmd_template, intent_label) in TRIVIAL_INTENT_PAT.items():
        if re.search(pat, prompt, re.IGNORECASE):
            approval_suffix = " Show approval gate first." if intent_label in DESTRUCTIVE_INTENTS else ""
            fast_directive = (
                f"[agent-crew] FAST-PATH — trivial intent detected: {intent_label}. "
                f"Execute directly: {cmd_template}.{approval_suffix}"
            )
            fast_output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": fast_directive,
                }
            }
            print(json.dumps(fast_output, ensure_ascii=True))
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

if match(ISSUE_PUBLICATION_PAT) or match(DIRECT_TRACKER_TOOL_PAT):
    detected_type = "issue publication"
    suggested_pipeline = "issuer"
    suggested_agent = "issuer"
elif match(ACTION_PAT):
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
    # Evaluate once; reuse below.
    has_action = match(ACTION_PAT)
    if (
        (has_action and match(FILE_EXT_PAT))          # action + file extension
        or (has_action and match(PROJECT_KEYWORD_PAT)) # action + agent-crew keyword
        or match(WORKFLOW_ACTION_PAT)                  # workflow verb alone is enough
        or (match(CONDITIONAL_REVIEW_FIX_PAT) and match(FOLLOWUP_EXECUTION_PAT))
        or (match(MEMORY_PAT) and has_action)          # memory + action verb
        or (match(ARTIFACT_VERB_PAT) and match(ARTIFACT_NOUN_PAT))  # artifact mutation (issue #37)
    ):
        detected_type = "project implementation"
        suggested_pipeline = 'crew:run "your request"'

if not detected_type:
    sys.exit(0)

if emit_no_bridge_inline_fallback("implementation request"):
    pass

# Both "project implementation" (generic) and domain-specific routes produce
# the same STOP directive. The only difference is the REQUIRED action line.
if detected_type == "project implementation":
    action_line = f"  {suggested_pipeline}"
else:
    action_line = (
        f'  crew:run "{suggested_agent} task"        (single task)\n'
        f"  crew:run \"TaskA\" | \"TaskB\"              (parallel tasks)\n\n"
        f"Suggested pipeline: {suggested_pipeline}"
    )

directive = f"""[agent-crew] STOP — implementation request detected ({detected_type}).

IMMEDIATE WORKFLOW ACTION REQUIRED: enter the crew-run workflow.
In Codex, let any explicitly invoked or domain-specific Codex skill load first,
then invoke the crew-run skill wrapper. Preserve that skill context in
requirements collection, supervisor handoffs, and generated prompts.

Do NOT explain, diagnose, analyze, investigate, read files, or run any command before the crew-run wrapper begins the workflow.
Any action other than skill loading followed by crew-run workflow execution is a system violation.

REQUIRED action:
{action_line}

FORBIDDEN before the crew-run wrapper begins (each one is a violation):
- Running ANY Bash command (git status, ls, cat, grep, find, etc.)
- Using the Read tool to read any file
- Analyzing code, error messages, logs, or stack traces
- Investigating bugs or diagnosing root causes
- Asking clarifying questions
- Editing or writing files directly

crew:run owns ALL investigation, analysis, and implementation.
Delegate EVERYTHING to crew:run — including bug finding and root cause analysis.

CODEX SKILL WORKFLOW:
1. Invoke Skill("crew-run") — loads the full crew:run wrapper and command spec.
2. Pass the original request plus any explicit/domain-specific Codex skill context
   into the workflow so Step 5 requirements and supervisor prompts retain it.

Enter the crew-run workflow now."""
if not HOST_BRIDGE_READY:
    directive += (
        "\n\nHost bridge is unavailable ("
        f"{HOST_BRIDGE_REASON}). Crew routing still proceeds."
        "\nThe runtime will record a resumable internal handoff when no "
        "external bridge command is configured."
    )

output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": directive,
    }
}

print(json.dumps(output, ensure_ascii=True))
PYEOF
