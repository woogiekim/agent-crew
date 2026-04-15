# planner /requirements — PRD 작성 및 파이프라인 결정

## 실행 순서

1. `/start`에서 전달된 요청 또는 사용자 입력 확인

2. 아래 항목을 분석하거나 사용자에게 질문하여 수집
   - 도메인/비즈니스 컨텍스트
   - 핵심 기능 목록
   - 비즈니스 규칙 및 제약
   - UI 포함 여부 (백엔드만 / 풀스택)
   - 완료 기준

3. PRD 작성 → `.claude/state/context/prd.md` 저장

4. 필요 에이전트 결정 (AGENT.md의 파이프라인 결정 기준 참조)

5. `.claude/state/pipeline.json` 갱신
   ```json
   {
     "task": "[요청 원문]",
     "agents": ["planner", ...결정된 에이전트들],
     "currentIndex": 1,
     "status": "IN_PROGRESS"
   }
   ```
   - currentIndex를 1로 갱신 (planner 완료, 다음 에이전트로 이동)

6. `.claude/state/handoff.md` 갱신
   - PRD 요약
   - 다음 에이전트에게 전달할 핵심 컨텍스트

7. git commit: `chore: planner requirements complete`

## 완료 후
자동으로 다음 에이전트(agents[1])의 첫 번째 단계를 실행한다.
