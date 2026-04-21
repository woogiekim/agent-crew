# /setup — 워크스페이스 초기화

## 프로젝트명 결정
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROJECT_ROOT = $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR    = ~/.claude/agent-crew/{PROJECT_NAME}
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

3. 디렉토리 및 파일 초기화 (Bash 도구로 실행)
   ```bash
   STATE_DIR="${HOME}/.claude/agent-crew/$(basename $(git rev-parse --show-toplevel 2>/dev/null || pwd))"
   mkdir -p "${STATE_DIR}/tasks"

   # config.json — 동시 실행 제한
   cat > "${STATE_DIR}/config.json" <<'EOF'
   {
     "maxConcurrentTasks": 2
   }
   EOF

   echo "setup_ok"
   ```

4. `feature/main` 브랜치 확인 및 생성 (Bash 도구로 실행)
   ```bash
   git show-ref --verify --quiet refs/heads/feature/main \
     || git checkout -b feature/main
   git checkout -  2>/dev/null || true
   echo "branch_ok"
   ```

5. 완료 메시지 출력

## 완료 메시지 형식
```
✅ agent-crew 워크스페이스 초기화 완료!
   프로젝트: {PROJECT_NAME}
   상태 경로: ~/.claude/agent-crew/{PROJECT_NAME}/
   동시 실행 제한: 2 (config.json에서 변경 가능)

사용 방법:
  /ship "요청 내용"    — 전체 파이프라인 자동 실행 (병렬 지원)
  /status              — 파이프라인 및 데몬 상태 패널 출력

실시간 모니터링 (별도 터미널):
  crew-status --live
```
