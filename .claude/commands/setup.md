# /setup — 워크스페이스 초기화

## 프로젝트명 결정
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서

1. 현재 디렉토리에서 프로젝트명 결정 (위 규칙 적용)

2. `{STATE_DIR}` 존재 확인
   - 존재하면: AskUserQuestion 도구로 확인
     - 질문: "'{PROJECT_NAME}' 워크스페이스가 이미 있습니다. 초기화하면 모든 상태가 리셋됩니다."
     - 선택지:
       - "취소 (Recommended)" — setup 종료
       - "초기화" — 모든 상태 리셋 후 진행
     - "취소" 선택 시 종료

3. `{STATE_DIR}/context/` 및 `{STATE_DIR}/agent_signal/` 디렉토리 생성

4. 상태 파일 초기화
   - `{STATE_DIR}/phase.txt` → `REQUIREMENTS`
   - `{STATE_DIR}/iterations.txt` → `0`
   - `{STATE_DIR}/active_agent.txt` → `planner`
   - `{STATE_DIR}/pipeline.json` → 초기값
   - `{STATE_DIR}/handoff.md` → 빈 문서
   - `{STATE_DIR}/context/session_handoff.md` → 초기 상태
   - `{STATE_DIR}/events.jsonl` → 빈 파일 생성

5. crew-daemon 시작
   ```bash
   bash ~/.claude/agent-crew/crew-daemon.sh start &
   ```
   - PID는 `{STATE_DIR}/orchestrator.pid`에 자동 기록됨
   - 파이프라인 DONE/FAILED 시 자동 종료
   - 30분 이벤트 없으면 유휴 타임아웃으로 자동 종료
   - 수동 종료: `bash ~/.claude/agent-crew/crew-daemon.sh stop`

6. 완료 메시지 출력

## pipeline.json 초기값
```json
{
  "task": "",
  "agents": [],
  "currentIndex": 0,
  "status": "PENDING"
}
```

## 완료 메시지 형식
```
✅ agent-crew 워크스페이스 초기화 완료!
   프로젝트: {PROJECT_NAME}
   상태 경로: ~/.claude/agent-crew/{PROJECT_NAME}/

사용 방법:
  /ship "요청 내용"    — 전체 파이프라인 자동 실행
  /status              — 파이프라인 및 데몬 상태 패널 출력
  /requirements        — 요구사항 단계 수동 실행
  /design              — 설계 단계 수동 실행
  /implement           — 구현 단계 수동 실행
  /verify              — 검증 단계 수동 실행

실시간 모니터링 (별도 터미널):
  watch -n 2 bash ~/.claude/agent-crew/crew-status.sh
```
