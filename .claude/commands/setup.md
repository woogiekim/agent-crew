# /setup — 워크스페이스 초기화

## 실행 순서

1. `.claude/state/` 디렉토리 존재 확인
   - 존재하면: "기존 워크스페이스가 감지되었습니다. 초기화하면 모든 상태가 리셋됩니다. 계속할까요? [y/N]" 확인
   - N이면 종료

2. 상태 파일 초기화
   - `.claude/state/phase.txt` → `REQUIREMENTS`
   - `.claude/state/iterations.txt` → `0`
   - `.claude/state/active_agent.txt` → `planner`
   - `.claude/state/pipeline.json` → 초기값 (아래 참조)
   - `.claude/state/handoff.md` → 빈 문서

3. `.claude/state/context/` 디렉토리 초기화
   - `session_handoff.md` → 초기 상태로 작성
   - 나머지 파일 (requirements.md, design.md 등) 있으면 삭제

4. 완료 메시지 출력

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

사용 방법:
  /start "요청 내용"   — 전체 파이프라인 자동 실행
  /requirements        — 요구사항 단계 수동 실행
  /design              — 설계 단계 수동 실행
  /implement           — 구현 단계 수동 실행
  /verify              — 검증 단계 수동 실행
```
