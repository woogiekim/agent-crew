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
import hashlib
from pathlib import Path

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

def _env_flag(name):
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


if _env_flag("AGENT_CREW_AUTO_ROUTE_DISABLED") or _env_flag("AGENT_CREW_HOST_BRIDGE_ACTIVE"):
    sys.exit(0)


def _bridge_status():
    raw = os.environ.get("AGENT_CREW_HOST_BRIDGE_COMMAND", "").strip()
    if not raw:
        raw = _default_bridge_command()
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


def _default_bridge_command():
    if _env_flag("AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT") or _env_flag("AGENT_CREW_DISABLE_DEFAULT_HOST_BRIDGE"):
        return ""

    home = Path(os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))).expanduser()
    project_root = Path(os.environ.get("PROJECT_ROOT", os.getcwd())).resolve()
    host = os.environ.get("AGENT_CREW_HOST", "").strip().lower()
    if not host:
        try:
            slug = re.sub(r"[^A-Za-z0-9._-]+", "-", project_root.name.strip()).strip(".-").lower() or "project"
            digest = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:10]
            keyed = home / "state" / f"{slug}-{digest}"
            legacy = home / "state" / project_root.name
            state_dir = keyed if keyed.exists() else legacy
            capabilities = json.loads((state_dir / "capabilities.json").read_text(encoding="utf-8"))
            host = str(capabilities.get("host") or capabilities.get("adapter") or "").strip().lower()
        except Exception:
            host = ""

    bridge_name = {
        "codex": "codex-host-bridge",
        "claude": "claude-host-bridge",
    }.get(host)
    if not bridge_name:
        return ""

    candidate = home / "adapters" / host / "bin" / bridge_name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return ""


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

COMMAND_PAT = (
    r"^\s*(?:(?P<colon>(?:crew|ac):(?P<colon_intent>"
    r"setup|run|crew|task|status|cost|agent-maker|agent|smm|sync-instructions|telemetry|update"
    r"))|\$(?P<wrapper>crew-(?P<wrapper_intent>"
    r"setup|run|status|cost|agent-maker|agent|smm|update"
    r")))(?:\s+(?P<args>.*))?$"
)
command_match = re.match(COMMAND_PAT, prompt, re.IGNORECASE | re.DOTALL)
if command_match:
    command = (command_match.group("colon") or f"${command_match.group('wrapper')}").lower()
    intent = (command_match.group("colon_intent") or command_match.group("wrapper_intent")).lower()
    args = (command_match.group("args") or "").strip()

    command_file_by_intent = {
        "setup": "setup.md",
        "run": "run.md",
        "crew": "run.md",
        "task": "run.md",
        "status": "status.md",
        "cost": "cost.md",
        "agent-maker": "agent-maker.md",
        "agent": "agent.md",
        "smm": "smm.md",
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

    wrapper_note = ""
    if command.startswith("$crew-"):
        wrapper_note = f"""
Codex wrapper invocation:
  Load Skill("{command[1:]}") before executing the mapped workflow intent.
  Treat text after {command} as command arguments, not as a request to review the wrapper itself.
"""

    directive = f"""[agent-crew] COMMAND — explicit {command} invocation detected.

The user is invoking the agent-crew workflow command. Do NOT reinterpret this as
a request to inspect the repository, run generic verification, CI, linting, or
any host-default task.

Immediate action:
  Execute the workflow defined in ~/.agent-crew/commands/{command_file}.
{wrapper_note}

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
    r"되나요|되죠|되잖아요|"
    r"활용|사용하고|쓰고|동작|작동|비교|평가|체크|쓸만|쓸\s*만|솔직"
)
# Machine-control replies are not substantive answers. They are allowed through
# so numbered structured-choice fallbacks can resolve without being hijacked by
# a catch-all route.
CONTROL_REPLY_PAT = (
    r"^\s*(?:[0-9]+|[A-Da-d])\s*$|"
    r"^\s*(?:approve|cancel|hold|승인|취소|보류)\s*$"
)
FOLLOWUP_CONTINUATION_PAT = (
    r"^\s*(?:go|yes|ok|okay|continue|proceed|do\s+it|please\s+proceed|"
    r"네|네\s*(?:진행(?:해(?:주세요)?)?|계속(?:해(?:주세요)?)?|"
    r"그렇게\s*(?:가시죠|해주세요|해줘)?|해주세요|해줘)|"
    r"예|좋아요|진행|진행해|진행해주세요|계속|계속해|계속해주세요|"
    r"가시죠|그렇게\s*가시죠|해주세요|해줘)\s*[.!?。]*\s*$"
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
    r"bulk\s+create\s+(?:work\s+items?|issues?)|import\s+(?:issues?|task\s+list)|"
    r"seed\s+(?:the\s+)?project|upload\s+(?:the\s+)?task\s+list|"
    r"issue\s+publication|work\s+item\s+creation|"
    r"이슈\s*(?:발행|생성|등록|업로드)|작업\s*항목\s*(?:생성|등록)|"
    r"업무\s*항목\s*(?:생성|등록)|태스크\s*목록\s*(?:가져오기|업로드)"
)
DIRECT_TRACKER_TOOL_PAT = (
    r"mcp__plane__(?:create|update|delete)_work_item|"
    r"mcp__gitlab__(?:create|update|delete)_issue|"
    r"gh\s+issue\s+create|"
    r"curl\s+.*(?:/issues|/work-items|/work_items)"
)
DIRECT_TRACKER_LIFECYCLE_PAT = (
    r"mcp__plane__update_work_item|"
    r"mcp__gitlab__update_issue|"
    r"gh\s+issue\s+(?:edit|close|reopen)"
)
ISSUE_REF_PAT = (
    r"\b[A-Z][A-Z0-9]+-\d+\b"
    r"(?:\s*(?:~|-|to|through|,)\s*(?:[A-Z][A-Z0-9]+-)?\d+\b|"
    r"\s*,\s*\b[A-Z][A-Z0-9]+-\d+\b)*"
)
ISSUE_STATE_TRANSITION_PAT = (
    r"완료\s*처리|완료|시작|진행\s*중(?:으로)?|진행|"
    r"상태\s*(?:변경|전환)|"
    r"status\s+(?:to|as|=)|state\s+(?:to|as|=)|"
    r"done|start(?:ed)?|in\s*progress|cancel(?:led)?|"
    r"보류|hold|blocked|QA|배포|deploy(?:ed)?|"
    r"reopen(?:ed)?|close(?:d)?|취소"
)
ISSUE_FIELD_UPDATE_PAT = (
    r"라벨\s*(?:추가|변경|삭제|제거)|우선순위\s*(?:변경|수정|설정)|"
    r"담당자\s*(?:변경|추가|지정|삭제)|제목\s*변경|"
    r"labels?\s*(?:add|remove|update|change|set)|"
    r"priority\s*(?:change|update|set)|"
    r"assignees?\s*(?:change|update|add|set|remove)|"
    r"title\s*(?:change|update|rename)|"
    r"(?:update|rename|change)\s+(?:the\s+)?(?:work\s+item|issue)\s+title|"
    r"field\s+update"
)
ISSUE_LIFECYCLE_PAT = (
    rf"(?:{ISSUE_REF_PAT}).{{0,120}}(?:{ISSUE_STATE_TRANSITION_PAT}|{ISSUE_FIELD_UPDATE_PAT})|"
    rf"(?:{ISSUE_STATE_TRANSITION_PAT}|{ISSUE_FIELD_UPDATE_PAT}).{{0,120}}(?:{ISSUE_REF_PAT})"
)
READONLY_REVIEW_PAT = (
    r"review|evaluate|assess|compare|honest\s+review|check|diagnos(?:e|is)|"
    r"inspect|determine|identify\s+(?:gaps|issues|problems|fixes)|"
    r"리뷰|검토|평가|비교|솔직|쓸만|쓸\s*만|"
    r"괜찮|문제점|개선점|부족|체크|고쳐야\s*하|뭘\s*고쳐|확인할\s*기준"
)
READONLY_COMPLAINT_PAT = (
    r"안\s*쓰|안쓰|안\s*되|안되|못\s*하|못하|"
    r"자꾸|계속\s*(?:문제|실패|무시|빠지)"
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
        f"ROUTE_LOCK: crew-agent\n"
        f"TARGET_AGENT: {target_agent}\n"
        f"FIRST_ACTION_ONLY:\n"
        f"  crew:agent \"{target_agent}\" \"{{user's question}}\"\n\n"
        f"In Codex: let explicitly invoked Codex skill context pass through, "
        f"then Invoke Skill(\"crew-agent\"). Do not auto-load non-agent-crew "
        f"or third-party host/plugin skills by description match; preserve only "
        f"explicitly invoked Codex skill context.\n\n"
        f"INLINE_ANSWER: FORBIDDEN\n"
        f"NO_PRELUDE: do not explain, summarize, inspect files, run Bash, or answer before crew-agent starts.\n"
        f"COMPLIANCE: route-directive-guard checks Agent responses for this lock."
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


def emit_stop_route(detected_type: str, action_line: str):
    directive = f"""[agent-crew] STOP — implementation request detected ({detected_type}).

ROUTE_LOCK: crew-run
FIRST_ACTION_ONLY:
{action_line}

In Codex: let explicitly invoked Codex skill context pass through, then load
Skill("crew-run"), preserve explicit skill context in requirements collection,
then execute the workflow intent. Do not auto-load non-agent-crew or third-party
host/plugin skills by description match. Preserve explicitly invoked skill
context in requirements collection, supervisor handoffs, and generated prompts.

INLINE_IMPLEMENTATION_OR_ANSWER: FORBIDDEN
NO_PRELUDE: do not explain, diagnose, inspect files, run Bash, ask questions,
or edit files before crew-run starts.
COMPLIANCE: route-directive-guard checks Agent responses for this lock.

CODEX SKILL WORKFLOW:
1. Invoke Skill("crew-run") — loads the full crew:run wrapper and command spec.
2. Pass the original request plus any explicitly invoked Codex skill context
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
    sys.exit(0)


def emit_no_bridge_inline_fallback(reason: str):
    """Compatibility shim for callsites that previously short-circuited inline."""
    return not HOST_BRIDGE_READY


if re.search(CONTROL_REPLY_PAT, prompt, re.IGNORECASE):
    sys.exit(0)

if re.search(FOLLOWUP_CONTINUATION_PAT, prompt, re.IGNORECASE):
    emit_stop_route(
        "follow-up continuation",
        '  crew:run "continue the prior agent-crew task or request"',
    )

if match(READONLY_COMPLAINT_PAT) and not match(REVIEW_MUTATION_PAT):
    emit_question_route("analyst", "behavior complaint/diagnostic request")


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
    if emit_no_bridge_inline_fallback("question"):
        pass

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

# --- Operational intent routing ---
# Short git/status intents are still classified quickly, but they no longer
# authorize inline execution. Read-only status routes to historian; mutating
# git operations route through crew:run so the agent-crew workflow remains the
# mandatory response path.

TRIVIAL_INTENT_PAT = {
    # English intents — with "git" prefix
    r"^\s*(?:git\s+)?status(?:\s+[-\w]+)?\s*$": ("git status",              "status"),
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
    r"^\s*상태(?:\s*확인)?\s*$":           ("git status",                    "status"),
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
            if intent_label == "status":
                emit_question_route("historian", "read-only git/project status request")

            emit_stop_route(
                f"operational {intent_label} request",
                f'  crew:run "{prompt.strip()}"',
            )

# Memory/feedback meta-operations route through historian for read-only lookup.
if re.search(MEMORY_PATH_PAT, prompt, re.IGNORECASE):
    if not match(ACTION_PAT):
        emit_question_route("historian", "memory/support-path lookup")
if match(MEMORY_PAT) and not match(ACTION_PAT):
    emit_question_route("historian", "memory/session request")

# 저장/기록 without code/file/system target still routes as state/memory mutation.
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
        emit_stop_route("state or memory mutation", '  crew:run "your request"')

detected_type = ""
suggested_pipeline = ""
suggested_agent = ""

# --- Existing domain-specific routing ---

if match(ISSUE_LIFECYCLE_PAT) or match(DIRECT_TRACKER_LIFECYCLE_PAT):
    detected_type = "issue lifecycle"
    suggested_pipeline = "issuer"
    suggested_agent = "issuer"
elif match(ISSUE_PUBLICATION_PAT) or match(DIRECT_TRACKER_TOOL_PAT):
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

# Issue #127 — mutating-verb-without-read-only-signal fallback.
#
# Before this guard, any ACTION_PAT match that did NOT also match a domain or
# supplementary heuristic fell through to `emit_question_route("analyst",
# "general user request")` below — routing clearly mutating requests like
# "fix the bug", "add a test", "commit the changes", "rename a variable",
# "refactor this function", "remove the legacy alias", "change the default
# value", or "버그를 수정해주세요" to crew:agent instead of crew:run.
#
# Acceptance criterion #3 of issue #127 requires that mutating requests
# always route through crew:run (STOP) with the existing approval and review
# gates. This guard tightens the fallback so a bare mutating verb is treated
# as a project implementation request unless a read-only signal is present.
#
# Read-only signals that override the mutating verb (preserve ROUTE):
#   - QUESTION_PAT (the prompt is shaped as a question)
#   - READONLY_REVIEW_PAT (review / evaluate / inspect / diagnose / 검토)
#   - READONLY_COMPLAINT_PAT (안 쓰 / 안 되 / 자꾸 ...)
#   - Explicit "do not edit / read-only / 수정하지 마 / 읽기 전용"
#
# This guard never relaxes STOP for any verb; it only converts ambiguous
# "ACTION_PAT + no domain + no read-only signal" prompts from ROUTE to STOP.
if not detected_type and match(ACTION_PAT):
    has_readonly_signal = (
        match(QUESTION_PAT)
        or match(READONLY_REVIEW_PAT)
        or match(READONLY_COMPLAINT_PAT)
        or bool(re.search(
            r"do\s+not\s+edit|read[- ]only|no\s+files?\s+edited|"
            r"수정하지\s*마|읽기\s*전용",
            prompt,
            re.IGNORECASE,
        ))
    )
    if not has_readonly_signal:
        detected_type = "project implementation"
        suggested_pipeline = 'crew:run "your request"'

if not detected_type:
    emit_question_route("analyst", "general user request")

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

emit_stop_route(detected_type, action_line)
PYEOF
