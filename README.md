# agent-crew

> Claude Code 글로벌 플러그인 — 모든 프로젝트에서 멀티 에이전트 개발 파이프라인을 `/ship` 한 줄로 실행

![License](https://img.shields.io/github/license/woogiekim/agent-crew)
![Platform](https://img.shields.io/badge/platform-Claude%20Code-blue)

## 📌 목차

- [프로젝트 소개](#-프로젝트-소개)
- [핵심 기능](#-핵심-기능)
- [설치 방법](#-설치-방법)
- [사용법](#-사용법)
- [워크플로우](#-워크플로우)
- [에이전트](#-에이전트)
- [상태 모니터링](#-상태-모니터링)
- [기여 방법](#-기여-방법)
- [라이선스](#-라이선스)

---

## 💡 프로젝트 소개

- **문제 인식:** Claude Code로 개발할 때 요구사항 분석 → 설계 → 구현 → 검증을 매번 수동으로 지시해야 하며, 여러 에이전트 역할을 일관되게 조율하기 어렵습니다.
- **해결 방안:** agent-crew는 Claude Code 글로벌 플러그인으로 설치되어 어느 프로젝트에서나 `/ship "요청"` 한 줄로 planner → designer → frontend → backend 파이프라인을 자동 실행합니다.
- **핵심 목적:** 개발자가 "무엇을 만들지"에만 집중할 수 있도록, 에이전트 간 인계·상태 관리·파이프라인 실행을 완전 자동화합니다.

## ✨ 핵심 기능

- **자동 파이프라인:** 요청 유형에 따라 필요한 에이전트만 자동 선택·순차 실행
- **이벤트 기반 상태 관리:** `events.jsonl` append + `crew-daemon`이 `pipeline.json`을 원자적으로 갱신 (레이스 컨디션 방지)
- **실시간 상태 패널:** `crew-status --live`로 모든 프로젝트의 파이프라인 진행 상황 모니터링
- **프로젝트 격리:** 상태는 `~/.claude/agent-crew/{PROJECT_NAME}/`에만 저장, 프로젝트 디렉토리 오염 없음
- **글로벌 설치:** 한 번 설치로 모든 프로젝트에서 동일한 명령어 사용

## 🛠️ 설치 방법

```bash
curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash
```

명령어(`/setup`, `/ship` 등), 에이전트, 훅, 상태 도구가 `~/.claude/`에 자동 설치됩니다.

**설치 후 PATH 반영:**
```bash
source ~/.zshrc   # zsh
# 또는
source ~/.bashrc  # bash
```

## 🚀 사용법

```bash
# 1. 새 프로젝트에서 1회 초기화
/setup

# 2. 전체 파이프라인 자동 실행
/ship "요청 내용"

# 단계별 수동 실행
/requirements
/design
/implement
/verify

# 상태 확인
/status
crew-status --live   # 실시간 모니터링 (별도 터미널)
```

## 🔄 워크플로우

```
/ship "요청"
  → planner  : 요구사항 분석 + PRD 작성 + 파이프라인 결정
  → designer : UI/UX 명세 (필요 시)
  → frontend : UI 구현 + 검증 (필요 시)
  → backend  : DDD 설계 + TDD 구현 + 검증
```

planner가 요청을 분석해 필요한 에이전트만 자동 선택합니다:

| 요청 유형 | 파이프라인 |
|---|---|
| 백엔드 API / 도메인 로직 | planner → backend |
| 풀스택 앱 | planner → designer → frontend → backend |
| UI만 | planner → designer → frontend |

각 단계 완료 시 에이전트가 `events.jsonl`에 이벤트를 기록하면 `crew-daemon`이 자동으로 다음 에이전트를 활성화합니다.

## 🤖 에이전트

| 에이전트 | 역할 |
|---|---|
| planner | 요구사항 분석, PRD 작성, 파이프라인 결정 |
| designer | UI/UX 명세 설계 |
| frontend | UI 구현 및 검증 |
| backend | Kotlin + Spring Boot DDD/TDD 구현 |

## 📊 상태 모니터링

```bash
crew-status             # 전체 프로젝트 상태 1회 출력
crew-status --live      # 2초마다 실시간 갱신
crew-status --live 5    # 5초마다 갱신
crew-daemon status      # 오케스트레이터 데몬 상태 확인
crew-daemon stop        # 데몬 수동 종료
```

패널 예시:
```
╔════════════════════════════════════════════════════════╗
║ agent-crew  projects: 2                                ║
╠════════════════════════════════════════════════════════╣
║ ▶ my-project                                           ║
║   Task   주문 도메인 API 구현                           ║
║   Status IN_PROGRESS  phase: IMPLEMENTATION            ║
║   Agent  backend                                       ║
║   ✓planner → ▶backend                                  ║
║   Daemon ● RUNNING  pid:12345  events:3                ║
╚════════════════════════════════════════════════════════╝
```

## 🤝 기여 방법

1. 이 저장소를 Fork합니다
2. 새 브랜치를 생성합니다 (`git checkout -b feat/새기능`)
3. 변경사항을 커밋합니다 (`git commit -m 'feat: 새기능 추가'`)
4. 브랜치에 Push합니다 (`git push origin feat/새기능`)
5. Pull Request를 생성합니다

## 📄 라이선스

MIT License — [LICENSE](LICENSE) 파일을 참조하세요.
