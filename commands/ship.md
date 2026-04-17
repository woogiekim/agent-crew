# /ship — 전체 파이프라인 자동 실행

## 상태 경로 규칙
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서

1. `/ship "[요청]"` 형태로 입력 받음
   - 인자 없으면: "어떤 작업을 시작할까요?" 질문 후 입력 받기

2. `{STATE_DIR}/phase.txt` 확인
   - 파일 없으면: "워크스페이스가 초기화되지 않았습니다. /setup을 먼저 실행하세요."
   - `DONE` 또는 `REQUIREMENTS`이면: 정상 진행 (새 작업 시작)
   - 그 외 (IN_PROGRESS 상태): `{STATE_DIR}/pipeline.json`의 `status` 확인
     - `status == "DONE"`이면: 정상 진행
     - `status == "IN_PROGRESS"`이면: AskUserQuestion 도구로 확인
       ```
       질문: "진행 중인 작업이 있습니다 (phase: [현재값]). 어떻게 할까요?"
       선택지:
         - "새로 시작" — 현재 작업을 초기화하고 새 작업 시작
         - "취소" — ship 종료
       ```
     - "취소" 선택 시 종료

3. planner 에이전트 활성화
   - `{STATE_DIR}/active_agent.txt` → `planner`
   - `~/.claude/agent-crew/agents/planner/AGENT.md` 읽기

4. planner가 요청 분석 → 필요 에이전트 목록 결정
   - 판단 기준: `~/.claude/agent-crew/agents/planner/AGENT.md` 참조

5. 사용자 확인 (AskUserQuestion 도구 사용)
   - 질문: "다음 순서로 진행합니다: [에이전트 목록]. 시작할까요?"
   - 선택지:
     - "시작 (Recommended)" — 파이프라인 실행
     - "취소" — ship 종료
   - "취소" 선택 시 종료

6. `{STATE_DIR}/pipeline.json` 저장
   ```json
   {
     "task": "[요청 원문]",
     "agents": ["planner", ...],
     "currentIndex": 0,
     "status": "IN_PROGRESS"
   }
   ```

7. 파이프라인 순차 실행 (자동)
   - 현재 에이전트의 담당 단계를 순서대로 실행
   - 각 단계 완료 후 다음 에이전트로 자동 인계 (아래 인계 규칙 참조)

## 에이전트별 담당 단계

| 에이전트 | 실행 단계 |
|---------|---------|
| planner | requirements |
| designer | design |
| frontend | implement → verify |
| backend | design → implement → verify |

## 인계 규칙 (각 에이전트 완료 후 자동 실행)

```
현재 에이전트 완료
  → {STATE_DIR}/handoff.md 갱신
  → pipeline.json currentIndex + 1
  → currentIndex < agents.length:
      active_agent.txt → agents[currentIndex]
      다음 에이전트의 첫 번째 단계 자동 실행
  → currentIndex >= agents.length:
      pipeline.json status → "DONE"
      phase.txt → "DONE"
      "✅ 모든 에이전트 작업 완료" 출력
```
