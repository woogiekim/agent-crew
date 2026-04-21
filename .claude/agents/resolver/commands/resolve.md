# resolver /resolve — 병합 충돌 자동 해결

## 상태 경로
```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
TASK_ID=$(cat "${PROJECT_ROOT}/.crew_task_id" 2>/dev/null || echo "")
PROJECT_NAME=$(basename "$PROJECT_ROOT")
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}/tasks/${TASK_ID}"
BRANCH=$(cat "${STATE_DIR}/branch.txt")
WORKTREE=$(cat "${STATE_DIR}/worktree_path.txt")
```

## 실행 순서

1. 충돌 파일 목록 확인 (Bash 도구로 실행)
   ```bash
   git -C "$PROJECT_ROOT" diff --name-only --diff-filter=U
   ```

2. 컨텍스트 파악
   - `{STATE_DIR}/../../../context/prd.md` 읽기 (원래 요구사항)
   - `{STATE_DIR}/context/design-spec.md` 읽기 (task 설계)
   - 충돌 파일 각각 읽기

3. 충돌 해결 전략 결정
   - **양측 모두 유효한 변경**: 두 변경을 합쳐 기능을 통합
   - **한쪽이 구버전**: 최신 로직(task 브랜치) 채택
   - **완전히 다른 부분**: 두 변경 모두 보존, 구조적으로 병합
   - PRD 요구사항을 기준으로 판단

4. 충돌 해결 (Edit 도구로 각 파일의 `<<<<<<<` ~ `>>>>>>>` 제거)
   - 모든 충돌 마커 제거 필수
   - 해결 후 코드가 컴파일/실행 가능한지 확인

5. merge 완료 (Bash 도구로 실행)
   ```bash
   git -C "$PROJECT_ROOT" add -A
   git -C "$PROJECT_ROOT" commit -m "merge: resolve conflicts from ${BRANCH}"
   ```

6. worktree 및 브랜치 정리 (Bash 도구로 실행)
   ```bash
   git -C "$PROJECT_ROOT" worktree remove --force "$WORKTREE"
   git -C "$PROJECT_ROOT" branch -D "$BRANCH"
   ```

7. PHASE_COMPLETE 이벤트 emit (Bash 도구로 실행)
   ```bash
   echo '{"event":"PHASE_COMPLETE","agent":"resolver","phase":"merge-resolve"}' \
     >> "${STATE_DIR}/events.jsonl"
   ```

## 완료 후
`{STATE_DIR}/phase.txt` → `DONE`
`{STATE_DIR}/active_agent.txt` → `resolver`
