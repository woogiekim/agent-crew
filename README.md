# AI Agent Workspace

Kotlin + Spring Boot 기반 멀티 에이전트 개발 환경.
Claude Code + Git Worktree + Hooks 기반으로 동작합니다.

## 에이전트 구성

| 에이전트 | 역할 | 상태 |
|---|---|---|
| backend | Kotlin + Spring Boot DDD/TDD 구현 | ✅ 완료 |
| planner | 요구사항 분석, PRD 작성 | 🔜 예정 |
| designer | UI/UX 명세 | 🔜 예정 |
| frontend | UI 구현 | 🔜 예정 |

## 설치

### Copy 방식 (원터치, 기본)
```bash
# 프로젝트 루트에서 실행
curl -s https://raw.githubusercontent.com/woogiekim/ai-agents/main/install.sh | bash
```

### Submodule 방식 (버전 독립 관리)
```bash
curl -s https://raw.githubusercontent.com/woogiekim/ai-agents/main/install.sh | bash -s -- --submodule
```

### 에이전트 업데이트 (Submodule 방식)
```bash
git submodule update --remote .claude-agents
```

---

## 사용 방법

### 단일 에이전트 (백엔드)
```bash
# 프로젝트 루트에서 Claude Code 실행
claude

# 슬래시 커맨드로 워크플로우 진행
/requirements   # 1단계: 요구사항 수집
/design         # 2단계: 설계
/implement      # 3단계: TDD 구현
/verify         # 4단계: 검증
```

### 병렬 에이전트 (Git Worktree)
```bash
# 각 터미널에서 독립 실행
claude --worktree agent/backend
claude --worktree agent/planner
claude --worktree agent/frontend
```

## 워크플로우

```
REQUIREMENTS → DESIGN → IMPLEMENTATION → VERIFICATION
                  ↑______________|  (실패 시 최대 5회)
                  
5회 초과 시 → REQUIREMENTS 재수집
```

## 상태 파일

```
.claude/state/
├── phase.txt          # 현재 페이즈
├── iterations.txt     # 반복 횟수 (0~5)
├── active_agent.txt   # 활성 에이전트
├── handoff.md         # 에이전트 간 인계 문서
└── context/
    ├── requirements.md     # 확정 요구사항
    ├── design.md           # 확정 설계
    ├── tdd_log.md          # TDD 이력
    ├── verify_checklist.md # 검증 체크리스트
    └── session_handoff.md  # 세션 복구용
```

## 컨텍스트 관리

- 컨텍스트 60% 도달 시 즉시 `/compact` 실행
- 세션 종료 전 `session_handoff.md` 갱신 + git commit
- 새 세션 시작 시 Claude가 `state/context/` 자동 로드

## Hooks (자동 실행)

| Hook | 시점 | 역할 |
|---|---|---|
| verify-rules.sh | 파일 저장 후 | else 사용, getter 과다, 테스트 누락 감지 |
| guard-dangerous-commands.sh | bash 실행 전 | 위험 명령어 차단 |
