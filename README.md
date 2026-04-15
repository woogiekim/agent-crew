# agent-crew

Claude Code 글로벌 플러그인 — 모든 프로젝트에서 멀티 에이전트 개발 워크스페이스 제공.

한 번 설치 후 어느 프로젝트에서나 `/start "요청"` 한 줄로 planner → designer → frontend → backend 파이프라인을 자동 실행합니다.

## 설치

```bash
curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash
```

`~/.claude/commands/`와 `~/.claude/agent-crew/` 에 글로벌 설치됩니다.

## 사용 방법

```bash
# 새 프로젝트에서 1회 초기화
/setup

# 전체 파이프라인 자동 실행
/start "요청 내용"

# 단계별 수동 실행
/requirements
/design
/implement
/verify
```

## 워크플로우

```
/start "요청"
  → planner: 요구사항 분석 + 파이프라인 결정
  → (designer: UI/UX 명세)
  → (frontend: UI 구현)
  → backend: DDD 설계 + TDD 구현 + 검증
```

planner가 요청을 분석해 필요한 에이전트만 자동 선택합니다.

| 요청 유형 | 파이프라인 |
|---------|---------|
| 백엔드 API / 도메인 로직 | planner → backend |
| 풀스택 앱 | planner → designer → frontend → backend |
| UI만 | planner → designer → frontend |

## 상태 관리

프로젝트별 상태는 `~/.claude/agent-crew/{PROJECT_NAME}/` 에 저장됩니다. 프로젝트 디렉토리를 오염시키지 않습니다.

## 에이전트

| 에이전트 | 역할 | 상태 |
|---------|------|------|
| planner | 요구사항 분석, PRD 작성, 파이프라인 결정 | ✅ |
| designer | UI/UX 명세 설계 | ✅ |
| frontend | UI 구현 | ✅ |
| backend | Kotlin+Spring Boot DDD/TDD 구현 | ✅ |
