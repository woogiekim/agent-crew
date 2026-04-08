#!/bin/bash
# verify-rules.sh
# PostToolUse(Edit/Write) 시 자동 실행 — 규칙 위반 감지

CHANGED_FILE="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"

# Kotlin 소스 파일만 검사
if [[ "$CHANGED_FILE" != *.kt ]]; then
  exit 0
fi

# 테스트 파일인지 확인
IS_TEST=false
if [[ "$CHANGED_FILE" == *Test.kt ]] || [[ "$CHANGED_FILE" == *Spec.kt ]]; then
  IS_TEST=true
fi

VIOLATIONS=()

# 1. else 키워드 사용 감지 (테스트 파일 제외)
if [[ "$IS_TEST" == false ]]; then
  ELSE_COUNT=$(grep -c '} else' "$CHANGED_FILE" 2>/dev/null || echo 0)
  if [[ "$ELSE_COUNT" -gt 0 ]]; then
    VIOLATIONS+=("[생활체조 #2] else 키워드 사용 감지 (${ELSE_COUNT}곳) — Early return 으로 변경하세요")
  fi
fi

# 2. getter 패턴 감지 (Tell Don't Ask 위반)
GETTER_COUNT=$(grep -cE '\.get[A-Z]|\.is[A-Z]' "$CHANGED_FILE" 2>/dev/null || echo 0)
if [[ "$GETTER_COUNT" -gt 3 ]]; then
  VIOLATIONS+=("[Tell Don't Ask] getter 과다 사용 감지 (${GETTER_COUNT}곳) — 객체에게 행동을 위임하세요")
fi

# 3. 소스 파일에 대응하는 테스트 파일 존재 여부 확인
if [[ "$IS_TEST" == false ]] && [[ "$CHANGED_FILE" == */main/* ]]; then
  TEST_FILE="${CHANGED_FILE/\/main\//\/test\/}"
  TEST_FILE="${TEST_FILE%.kt}Test.kt"
  if [[ ! -f "$TEST_FILE" ]]; then
    VIOLATIONS+=("[TDD] 테스트 파일 없음 — ${TEST_FILE} 을 먼저 작성하세요")
  fi
fi

# 결과 출력
if [[ ${#VIOLATIONS[@]} -gt 0 ]]; then
  echo "⚠️  규칙 위반 감지: $CHANGED_FILE"
  for v in "${VIOLATIONS[@]}"; do
    echo "  - $v"
  done
  echo ""
  echo "위 항목을 수정한 후 진행하세요."
  exit 1
fi

exit 0
