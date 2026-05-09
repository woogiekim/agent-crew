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

BACKEND_PAT = (
    r"API|backend|server|endpoint|domain|Entity|Repository|Service|Kotlin|"
    r"Spring|DB|database|storage|query|table|controller|Controller|UseCase|"
    r"Command|Event|\ubc31\uc5d4\ub4dc|\uc11c\ubc84|\uc5d4\ub4dc\ud3ec\uc778\ud2b8|"
    r"\ub3c4\uba54\uc778|\ub370\uc774\ud130\ubca0\uc774\uc2a4|\uc800\uc7a5\uc18c|"
    r"\ucffc\ub9ac|\ud14c\uc774\ube14|\ucee8\ud2b8\ub864\ub7ec"
)
FRONTEND_PAT = (
    r"frontend|UI|screen|component|React|Vue|Next|page|button|form|modal|"
    r"layout|style|CSS|HTML|\ud504\ub860\ud2b8\uc5d4\ub4dc|\ud654\uba74|"
    r"\ucef4\ud3ec\ub10c\ud2b8|\ud398\uc774\uc9c0|\ubc84\ud2bc|\ud3fc|"
    r"\ubaa8\ub2ec|\ub808\uc774\uc544\uc6c3|\uc2a4\ud0c0\uc77c"
)
FULLSTACK_PAT = (
    r"full.?stack|full development|service development|app development|"
    r"system development|\ud480\uc2a4\ud0dd|\uc804\uccb4\s*\uac1c\ubc1c|"
    r"\uc11c\ube44\uc2a4\s*\uac1c\ubc1c|\uc571\s*\uac1c\ubc1c|"
    r"\uc2dc\uc2a4\ud15c\s*\uac1c\ubc1c"
)
DESIGN_PAT = (
    r"UI design|screen design|UX|design spec|wireframe|"
    r"UI\s*\uc124\uacc4|\ud654\uba74\s*\uc124\uacc4|"
    r"\ub514\uc790\uc778\s*\uba85\uc138|\uc640\uc774\uc5b4\ud504\ub808\uc784"
)
ACTION_PAT = (
    r"build|implement|create|add|develop|rename|refactor|update|fix|remove|"
    r"delete|move|change|migrate|modify|replace|extend|integrate|"
    r"\ub9cc\ub4e4\uc5b4|\uad6c\ud604\ud574|\uac1c\ubc1c\ud574|"
    r"\ucd94\uac00\ud574|\uc218\uc815\ud574|\uc791\uc131\ud574|"
    r"\uc0dd\uc131\ud574|\ub9cc\ub4e4\uace0|\uad6c\ud604\ud558\uace0"
)
QUESTION_PAT = (
    r"why|what|how|explain|describe|"
    r"\uc5b4\ub5bb\uac8c|\ubb50\uc57c|\ubb34\uc5c7|\uc124\uba85|"
    r"\uc54c\ub824|\uc774\ud574"
)


def match(pattern):
    return bool(re.search(pattern, prompt, re.IGNORECASE))


if match(QUESTION_PAT) and not match(ACTION_PAT):
    sys.exit(0)

if not match(ACTION_PAT):
    sys.exit(0)

detected_type = ""
suggested_pipeline = ""
suggested_agent = ""

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

if not detected_type:
    sys.exit(0)

directive = f"""[agent-crew] Development request detected: {detected_type}
Suggested pipeline: {suggested_pipeline}

Direct implementation is prohibited before the required agent or skill step.
Choose one of the following first:
  Single focused task -> host AI delegation target="{suggested_agent}"
  Workflow run -> crew:run "request"
  Multiple independent tasks -> crew:run "TaskA" | "TaskB"

Use provider-neutral `crew:<intent>` syntax by default."""

output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": directive,
    }
}

print(json.dumps(output, ensure_ascii=True))
PYEOF
