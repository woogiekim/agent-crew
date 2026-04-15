# 설계 명세

## 도메인 모델

| 개념 | 역할 | DDD 매핑 |
|------|------|---------|
| Plugin | 설치/초기화 단위 | Aggregate Root |
| Pipeline | 에이전트 실행 순서 + 현재 위치 | Aggregate Root |
| Agent | 역할별 전문가 (planner/designer/frontend/backend) | Entity |
| Phase | 단계 enum (REQUIREMENTS/DESIGN/IMPLEMENTATION/VERIFICATION/DONE) | Value Object |
| Handoff | 에이전트 간 인계 문서 | Value Object |

---

## 파일 구조

```
.claude/
├── plugin.json                       # Claude Code 플러그인 매니페스트
├── CLAUDE.md
├── commands/
│   ├── setup.md                      # 워크스페이스 초기화
│   ├── start.md                      # 파이프라인 자동 실행 진입점
│   ├── requirements.md               # 라우터 → active_agent의 requirements
│   ├── design.md                     # 라우터 → active_agent의 design
│   ├── implement.md                  # 라우터 → active_agent의 implement
│   └── verify.md                     # 라우터 → active_agent의 verify
├── agents/
│   ├── planner/
│   │   ├── AGENT.md
│   │   ├── commands/requirements.md  # PRD 작성 + 파이프라인 결정
│   │   └── skills/
│   ├── designer/
│   │   ├── AGENT.md
│   │   ├── commands/design.md        # UI/UX 명세 작성
│   │   └── skills/
│   ├── frontend/
│   │   ├── AGENT.md
│   │   ├── commands/implement.md
│   │   ├── commands/verify.md
│   │   └── skills/
│   └── backend/
│       ├── AGENT.md                  # 기존 유지
│       ├── commands/
│       └── skills/
├── hooks/
│   ├── verify-rules.sh
│   └── guard-dangerous-commands.sh
└── state/
    ├── phase.txt
    ├── active_agent.txt
    ├── iterations.txt
    ├── pipeline.json                 # NEW: 파이프라인 정의
    ├── handoff.md
    └── context/
        ├── session_handoff.md
        ├── prd.md                    # planner 산출물
        ├── design-spec.md            # designer 산출물
        ├── requirements.md
        ├── design.md
        ├── tdd_log.md
        └── verify_checklist.md
```

---

## pipeline.json 스키마

```json
{
  "task": "사용자 요청 원문",
  "agents": ["planner", "designer", "backend"],
  "currentIndex": 0,
  "status": "IN_PROGRESS"
}
```

- `status`: `PENDING` | `IN_PROGRESS` | `DONE`
- `currentIndex`: 현재 실행 중인 에이전트 인덱스 (0부터 시작)

---

## plugin.json 스키마

```json
{
  "name": "agent-crew",
  "version": "1.0.0",
  "description": "Multi-agent development workspace for Claude Code",
  "commands": ["setup", "start", "requirements", "design", "implement", "verify"]
}
```

---

## 오케스트레이션 흐름

### /start "요청"
1. planner가 요청 분석 → 필요 에이전트 목록 결정
2. pipeline.json 저장
3. 사용자 확인: "planner → designer → backend 순으로 진행합니다. 계속할까요? [Y/n]"
4. 확인 후 currentIndex=0 에이전트부터 자동 순차 실행
5. 각 에이전트 완료 → handoff.md 갱신 → currentIndex+1 → 다음 에이전트 자동 실행

### 명령어 라우팅 (/requirements, /design, /implement, /verify)
1. pipeline.json에서 agents[currentIndex] 확인 → active_agent 결정
2. 해당 에이전트의 commands/[phase].md 실행

### /setup
1. 기존 .claude/state/ 있으면 덮어쓰기 확인
2. 모든 에이전트 동시 활성화 (선택 없음)
3. state/ 초기화 (phase=REQUIREMENTS, iterations=0, active_agent=planner)
4. 완료 메시지 출력

---

## 에이전트별 실행 단계

| 에이전트 | 담당 단계 | 산출물 |
|---------|---------|-------|
| planner | requirements | prd.md |
| designer | design | design-spec.md |
| frontend | implement → verify | 프론트엔드 소스 코드 |
| backend | design → implement → verify | 백엔드 소스 코드 |

---

## 트레이드오프

| 선택 | 장점 | 단점 |
|------|------|------|
| pipeline.json (JSON 형식) | 구조적, 파싱 용이 | 텍스트보다 직접 편집 번거로움 |
| planner가 파이프라인 결정 | 유연, 태스크 최적화 | 판단 오류 → 사용자 확인으로 보정 |
| 모든 에이전트 동시 활성화 | 설치 단순, 선택 불필요 | AGENT.md 전체 로드로 컨텍스트 증가 |
| 상태 파일 기반 오케스트레이션 | 단순, 디버깅 용이, 세션 복원 가능 | 파일 손상 시 수동 복구 필요 |
