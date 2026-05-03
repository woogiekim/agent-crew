#!/bin/bash
# auto-route.sh — 자연어 개발 요청을 감지해 에이전트 라우팅 힌트를 주입
# UserPromptSubmit 훅: 출력이 Claude의 컨텍스트에 시스템 메시지로 주입됨

INPUT=$(cat)

# 프롬프트 텍스트 추출
PROMPT=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('prompt', ''))
except:
    pass
" 2>/dev/null || echo "")

# 슬래시 명령어는 스킵 (이미 명시적 라우팅)
[[ "$PROMPT" == /* ]] && exit 0

# 빈 프롬프트 스킵
[[ -z "$PROMPT" ]] && exit 0

# 패턴 정의
BACKEND_PAT="API|백엔드|서버|엔드포인트|도메인|Entity|Repository|Service|Kotlin|Spring|DB|데이터베이스|저장소|쿼리|테이블|컨트롤러|Controller|UseCase|Command|Event"
FRONTEND_PAT="프론트엔드|UI|화면|컴포넌트|React|Vue|Next|페이지|버튼|폼|모달|레이아웃|스타일|CSS|HTML"
FULLSTACK_PAT="풀스택|전체 개발|full.?stack|서비스 개발|앱 개발|시스템 개발"
DESIGN_PAT="UI 설계|화면 설계|UX|디자인 명세|와이어프레임|wireframe"
ACTION_PAT="만들어|구현해|개발해|추가해|작성해|생성해|build|implement|create|add|develop|만들고|구현하고"

# 질문/설명 요청은 라우팅 스킵
QUESTION_PAT="어떻게|뭐야|무엇|설명|알려|이해|why|what|how|explain|describe"
if echo "$PROMPT" | grep -qiP "$QUESTION_PAT" && ! echo "$PROMPT" | grep -qiP "$ACTION_PAT"; then
  exit 0
fi

# 라우팅 결정
DETECTED_TYPE=""
SUGGESTED_PIPELINE=""
SUGGESTED_AGENT=""

if echo "$PROMPT" | grep -qiP "$FULLSTACK_PAT"; then
  DETECTED_TYPE="풀스택 개발"
  SUGGESTED_PIPELINE="planner → designer → frontend → backend"
  SUGGESTED_AGENT="planner"
elif echo "$PROMPT" | grep -qiP "$DESIGN_PAT"; then
  DETECTED_TYPE="UI 설계"
  SUGGESTED_PIPELINE="designer (→ frontend)"
  SUGGESTED_AGENT="designer"
elif echo "$PROMPT" | grep -qiP "$FRONTEND_PAT" && echo "$PROMPT" | grep -qiP "$BACKEND_PAT"; then
  DETECTED_TYPE="풀스택 개발"
  SUGGESTED_PIPELINE="planner → designer → frontend → backend"
  SUGGESTED_AGENT="planner"
elif echo "$PROMPT" | grep -qiP "$FRONTEND_PAT"; then
  DETECTED_TYPE="프론트엔드 개발"
  SUGGESTED_PIPELINE="designer → frontend"
  SUGGESTED_AGENT="designer"
elif echo "$PROMPT" | grep -qiP "$BACKEND_PAT"; then
  DETECTED_TYPE="백엔드 개발"
  SUGGESTED_PIPELINE="backend"
  SUGGESTED_AGENT="backend"
fi

# 감지된 경우에만 힌트 주입
if [[ -n "$DETECTED_TYPE" ]] && echo "$PROMPT" | grep -qiP "$ACTION_PAT"; then
  cat <<EOF
<agent-crew-routing>
개발 요청 감지: ${DETECTED_TYPE}
권장 파이프라인: ${SUGGESTED_PIPELINE}

이 요청은 Agent 도구로 서브에이전트를 spawn해서 처리하세요.
- 단순 요청: Agent(subagent_type="${SUGGESTED_AGENT}", prompt=...)로 직접 spawn
- 복잡한 요청: /ship 파이프라인 (planner가 세부 파이프라인 결정)

사용자가 /ship을 입력하지 않았더라도 개발 작업이면 자동으로 에이전트를 spawn하세요.
</agent-crew-routing>
EOF
fi

exit 0
