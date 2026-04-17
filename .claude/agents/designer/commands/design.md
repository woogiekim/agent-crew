# designer /design — UI/UX 명세 작성

## 상태 경로
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서

1. `{STATE_DIR}/context/prd.md` 읽기
2. `{STATE_DIR}/handoff.md` 읽기

3. 아래 항목으로 UI/UX 명세 작성

### 명세 항목
- **화면 목록**: 필요한 모든 화면/페이지 열거
- **레이아웃**: 각 화면의 구성 요소 배치
- **컴포넌트 정의**: 재사용 컴포넌트, props, 상태
- **인터랙션 흐름**: 사용자 동선, 상태 전환
- **API 연동 포인트**: 백엔드와의 인터페이스 정의

4. `{STATE_DIR}/context/design-spec.md` 저장

5. 완료 이벤트 emit
   ```bash
   echo "{\"ts\":\"$(date -u +%FT%TZ)\",\"agent\":\"designer\",\"event\":\"PHASE_COMPLETE\",\"payload\":{}}" >> {STATE_DIR}/events.jsonl
   ```
   - 데몬 실행 중: 데몬이 `currentIndex` 증가 및 다음 에이전트 신호 발행
   - 데몬 없음 (fallback): `{STATE_DIR}/pipeline.json` currentIndex + 1 직접 갱신

6. `{STATE_DIR}/handoff.md` 갱신
   - 완성된 화면 목록
   - 컴포넌트 구조 요약
   - frontend에게 전달할 구현 우선순위

7. git commit: `docs: designer design-spec complete`

## 완료 후
자동으로 다음 에이전트의 첫 번째 단계를 실행한다.
