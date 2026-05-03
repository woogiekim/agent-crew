# /setup — 워크스페이스 초기화

## 상태 경로
```bash
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}"
```

## 실행 순서

1. 현재 디렉토리에서 PROJECT_NAME 결정

2. `{STATE_DIR}` 존재 확인
   - 존재하면: AskUserQuestion 도구로 확인
     - 질문: "'{PROJECT_NAME}' 워크스페이스가 이미 있습니다. 초기화하면 모든 상태가 리셋됩니다."
     - 선택지:
       - "취소 (Recommended)" — setup 종료
       - "초기화" — 모든 상태 리셋 후 진행
     - "취소" 선택 시 종료

3. 디렉토리 초기화
   ```bash
   STATE_DIR="${HOME}/.claude/agent-crew/$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")"
   mkdir -p "${STATE_DIR}/tasks"
   echo "setup_ok"
   ```

4. 완료 메시지 출력

## 완료 메시지 형식
```
✅ agent-crew 워크스페이스 초기화 완료!
   프로젝트: {PROJECT_NAME}
   상태 경로: ~/.claude/agent-crew/{PROJECT_NAME}/

사용 방법:
  /ship "요청 내용"    — 전체 파이프라인 자동 실행
  /status              — 파이프라인 상태 확인
```
