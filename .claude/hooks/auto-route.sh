#!/bin/bash
# auto-route.sh — 자연어 개발 요청 감지 → 스킬 강제 실행 directive 주입
# UserPromptSubmit 훅: JSON additionalContext 형식으로 출력해야 system context에 확실하게 주입됨

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import sys, json, re, os

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

try:
    data = json.loads(raw_input)
    prompt = data.get("prompt", "")
except Exception:
    sys.exit(0)

# 슬래시 명령어 스킵
if prompt.startswith("/"):
    sys.exit(0)

if not prompt.strip():
    sys.exit(0)

# 패턴 정의
BACKEND_PAT   = r"API|백엔드|서버|엔드포인트|도메인|Entity|Repository|Service|Kotlin|Spring|DB|데이터베이스|저장소|쿼리|테이블|컨트롤러|Controller|UseCase|Command|Event"
FRONTEND_PAT  = r"프론트엔드|UI|화면|컴포넌트|React|Vue|Next|페이지|버튼|폼|모달|레이아웃|스타일|CSS|HTML"
FULLSTACK_PAT = r"풀스택|전체 개발|full.?stack|서비스 개발|앱 개발|시스템 개발"
DESIGN_PAT    = r"UI 설계|화면 설계|UX|디자인 명세|와이어프레임|wireframe"
ACTION_PAT    = r"만들어|구현해|개발해|추가해|작성해|생성해|build|implement|create|add|develop|만들고|구현하고"
QUESTION_PAT  = r"어떻게|뭐야|무엇|설명|알려|이해|why|what|how|explain|describe"

def match(pat):
    return bool(re.search(pat, prompt, re.IGNORECASE))

# 질문/설명 요청은 라우팅 스킵
if match(QUESTION_PAT) and not match(ACTION_PAT):
    sys.exit(0)

# 액션 동사 없으면 스킵
if not match(ACTION_PAT):
    sys.exit(0)

# 라우팅 결정
detected_type     = ""
suggested_pipeline = ""
suggested_agent   = ""

if match(FULLSTACK_PAT):
    detected_type      = "풀스택 개발"
    suggested_pipeline = "planner → [designer ‖ backend] → frontend"
    suggested_agent    = "planner"
elif match(DESIGN_PAT):
    detected_type      = "UI 설계"
    suggested_pipeline = "designer → frontend"
    suggested_agent    = "designer"
elif match(FRONTEND_PAT) and match(BACKEND_PAT):
    detected_type      = "풀스택 개발"
    suggested_pipeline = "planner → [designer ‖ backend] → frontend"
    suggested_agent    = "planner"
elif match(FRONTEND_PAT):
    detected_type      = "프론트엔드 개발"
    suggested_pipeline = "designer → frontend"
    suggested_agent    = "designer"
elif match(BACKEND_PAT):
    detected_type      = "백엔드 개발"
    suggested_pipeline = "backend"
    suggested_agent    = "backend"

if not detected_type:
    sys.exit(0)

# JSON additionalContext 형식으로 출력 (plain text보다 system context에 확실하게 주입됨)
directive = f"""[agent-crew] 개발 요청 감지: {detected_type}
권장 파이프라인: {suggested_pipeline}

⛔ 직접 구현 금지 — Edit/Write/Bash 도구로 코드를 직접 작성하지 말 것.
✅ 반드시 아래 중 하나를 먼저 실행할 것:
   단일 태스크 → Agent 도구: subagent_type="{suggested_agent}"
   복잡한 태스크 → /ship 스킬
   다중 병렬 태스크 → /crew 스킬

스킬/에이전트 실행 없이 Edit·Write·코드 생성을 시작하는 것은 이 규칙 위반이다."""

output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": directive
    }
}

print(json.dumps(output, ensure_ascii=False))
PYEOF
