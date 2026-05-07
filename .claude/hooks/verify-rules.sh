#!/bin/bash
# verify-rules.sh
# PostToolUse(Edit/Write) 시 자동 실행 — 규칙 위반 감지

CHANGED_FILE="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"
VIOLATIONS=()

# ── Kotlin 규칙 ─────────────────────────────────────────────
if [[ "$CHANGED_FILE" == *.kt ]]; then
  IS_TEST=false
  [[ "$CHANGED_FILE" == *Test.kt || "$CHANGED_FILE" == *Spec.kt ]] && IS_TEST=true

  # 1. else 키워드 (테스트 제외)
  if [[ "$IS_TEST" == false ]]; then
    ELSE_COUNT=$(grep -c '} else' "$CHANGED_FILE" 2>/dev/null || echo 0)
    if [[ "$ELSE_COUNT" -gt 0 ]]; then
      VIOLATIONS+=("[생활체조 #2] else 키워드 사용 감지 (${ELSE_COUNT}곳) — Early return 으로 변경하세요")
    fi
  fi

  # 2. getter 패턴 (Tell Don't Ask)
  GETTER_COUNT=$(grep -cE '\.get[A-Z]|\.is[A-Z]' "$CHANGED_FILE" 2>/dev/null || echo 0)
  if [[ "$GETTER_COUNT" -gt 3 ]]; then
    VIOLATIONS+=("[Tell Don't Ask] getter 과다 사용 감지 (${GETTER_COUNT}곳) — 객체에게 행동을 위임하세요")
  fi

  # 3. 소스 파일에 대응하는 테스트 파일 존재 여부
  if [[ "$IS_TEST" == false && "$CHANGED_FILE" == */main/* ]]; then
    TEST_FILE="${CHANGED_FILE/\/main\//\/test\/}"
    TEST_FILE="${TEST_FILE%.kt}Test.kt"
    if [[ ! -f "$TEST_FILE" ]]; then
      VIOLATIONS+=("[TDD] 테스트 파일 없음 — ${TEST_FILE} 을 먼저 작성하세요")
    fi
  fi
fi

# ── TypeScript / JavaScript 규칙 ────────────────────────────
if [[ "$CHANGED_FILE" == *.ts || "$CHANGED_FILE" == *.tsx ]]; then
  IS_TEST=false
  [[ "$CHANGED_FILE" == *.test.ts || "$CHANGED_FILE" == *.spec.ts \
  || "$CHANGED_FILE" == *.test.tsx || "$CHANGED_FILE" == *.spec.tsx ]] && IS_TEST=true

  # 1. any 타입 사용
  ANY_COUNT=$(grep -cE ':\s*any\b|as\s+any\b|<any>' "$CHANGED_FILE" 2>/dev/null || echo 0)
  if [[ "$ANY_COUNT" -gt 0 ]]; then
    VIOLATIONS+=("[TypeScript] any 타입 사용 감지 (${ANY_COUNT}곳) — 구체적인 타입으로 대체하세요")
  fi

  # 2. console.log 잔류 (테스트 제외)
  if [[ "$IS_TEST" == false ]]; then
    LOG_COUNT=$(grep -cE 'console\.(log|warn|error|debug)' "$CHANGED_FILE" 2>/dev/null || echo 0)
    if [[ "$LOG_COUNT" -gt 0 ]]; then
      VIOLATIONS+=("[코드 품질] console 문 감지 (${LOG_COUNT}곳) — 제거하거나 logger로 교체하세요")
    fi
  fi

  # 3. 소스 파일에 대응하는 테스트 파일 존재 여부 (src/ 하위만)
  if [[ "$IS_TEST" == false && "$CHANGED_FILE" == */src/* ]]; then
    BASE="${CHANGED_FILE%.*}"
    EXT="${CHANGED_FILE##*.}"
    TEST_FILE="${BASE}.test.${EXT}"
    if [[ ! -f "$TEST_FILE" ]]; then
      VIOLATIONS+=("[TDD] 테스트 파일 없음 — ${TEST_FILE} 을 먼저 작성하세요")
    fi
  fi
fi

if [[ "$CHANGED_FILE" == *.js || "$CHANGED_FILE" == *.jsx ]]; then
  IS_TEST=false
  [[ "$CHANGED_FILE" == *.test.js || "$CHANGED_FILE" == *.spec.js \
  || "$CHANGED_FILE" == *.test.jsx || "$CHANGED_FILE" == *.spec.jsx ]] && IS_TEST=true

  if [[ "$IS_TEST" == false ]]; then
    LOG_COUNT=$(grep -cE 'console\.(log|warn|error|debug)' "$CHANGED_FILE" 2>/dev/null || echo 0)
    if [[ "$LOG_COUNT" -gt 0 ]]; then
      VIOLATIONS+=("[코드 품질] console 문 감지 (${LOG_COUNT}곳) — 제거하거나 logger로 교체하세요")
    fi
  fi
fi

# ── 결과 출력 ────────────────────────────────────────────────
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
