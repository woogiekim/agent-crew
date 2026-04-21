# planner /requirements — 요구사항 수집 및 PRD 작성

## 상태 경로
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서

### 0단계 — 데몬 시작 (반드시 실행)
아래 명령을 Bash 도구로 실행한다. 이미 실행 중이면 "이미 실행 중" 메시지가 출력되고 무시된다.
```bash
bash ~/.claude/agent-crew/crew-daemon.sh status | grep -q RUNNING \
  || nohup bash ~/.claude/agent-crew/crew-daemon.sh start \
       >> "${HOME}/.claude/agent-crew/$(basename $(git rev-parse --show-toplevel 2>/dev/null || pwd))/daemon.log" 2>&1 &
```

### 1단계 — 요청 분석 (내부)
사용자 요청을 읽고 다음 항목을 초안으로 추출한다 (아직 사용자에게 보여주지 않음):
- 도메인/비즈니스 컨텍스트
- 핵심 기능 후보 목록
- 구현 범위 예상 (백엔드 / 풀스택 / UI만)
- 비즈니스 규칙/제약 후보

---

### 2단계 — 요구사항 수집 대화 (AskUserQuestion 필수)

아래 4개의 질문을 순서대로 모두 실행한다. 하나라도 건너뛰지 않는다.

#### 질문 A — 구현 범위
AskUserQuestion 도구 사용:
- 질문: "구현 범위를 선택해주세요."
- 선택지:
  - "백엔드 API / 도메인 로직만 (Recommended)" — REST API, 비즈니스 로직, DB
  - "풀스택 — UI + 백엔드" — 화면 포함 전체 구현
  - "UI만 (프론트엔드)" — 화면/컴포넌트만
  - "분석/설계만" — 코드 없이 문서만

#### 질문 B — 핵심 기능 확인
1단계에서 추출한 핵심 기능 목록을 나열한 뒤 AskUserQuestion 도구 사용:
- 질문: "다음 기능으로 구현할까요?\n[추출한 기능 목록을 번호로 나열]"
- 선택지:
  - "맞습니다 — 진행 (Recommended)"
  - "기능을 추가/수정하겠습니다" → 선택 시: 수정 내용을 텍스트로 입력해달라고 요청 후 응답 대기
  - "기능 목록을 처음부터 다시 작성하겠습니다" → 선택 시: 기능 목록을 텍스트로 입력해달라고 요청 후 응답 대기

#### 질문 C — 비즈니스 규칙 & 제약
AskUserQuestion 도구 사용:
- 질문: "특별히 적용해야 할 규칙이나 제약이 있나요?"
- 선택지:
  - "없음 — 표준 구현으로 진행 (Recommended)"
  - "성능 요구사항 있음 (처리량, 응답시간 등)" → 선택 시: 구체적인 수치/조건 텍스트 입력 요청
  - "보안/인증 요구사항 있음" → 선택 시: 어떤 보안 요건인지 텍스트 입력 요청
  - "기존 시스템 연동 필요" → 선택 시: 연동 대상 및 방식 텍스트 입력 요청
  - "기타 제약 있음" → 선택 시: 제약 내용 텍스트 입력 요청

#### 질문 D — 완료 기준 확인
수집된 정보로 완료 기준을 자동 생성한 뒤 AskUserQuestion 도구 사용:
- 질문: "완료 기준을 확인해주세요:\n[자동 생성한 완료 기준 목록]"
- 선택지:
  - "맞습니다 — PRD 작성 시작 (Recommended)"
  - "완료 기준을 수정하겠습니다" → 선택 시: 수정 내용 텍스트 입력 요청

---

### 3단계 — PRD 작성
수집된 요구사항을 바탕으로 `{STATE_DIR}/context/prd.md` 작성:

```markdown
# PRD: [기능명]

## 배경
[비즈니스 컨텍스트]

## 핵심 기능
[확정된 기능 목록]

## 비즈니스 규칙
[수집된 규칙/제약]

## 완료 기준
[확정된 완료 기준]

## 구현 범위
[선택된 범위]
```

---

### 4단계 — 파이프라인 결정 및 저장

필요 에이전트 결정 (`~/.claude/agent-crew/agents/planner/AGENT.md`의 파이프라인 결정 기준 참조)

`{STATE_DIR}/pipeline.json` 갱신:
```json
{
  "task": "[요청 원문]",
  "agents": ["planner", ...결정된 에이전트들],
  "currentIndex": 0,
  "status": "IN_PROGRESS"
}
```

`{STATE_DIR}/handoff.md` 갱신:
- PRD 요약
- 다음 에이전트에게 전달할 핵심 컨텍스트

---

### 5단계 — 완료 처리

```bash
echo "{\"ts\":\"$(date -u +%FT%TZ)\",\"agent\":\"planner\",\"event\":\"PHASE_COMPLETE\",\"payload\":{}}" >> {STATE_DIR}/events.jsonl
```
- 데몬 실행 중: 데몬이 `currentIndex` 증가 및 다음 에이전트 신호 발행
- 데몬 없음 (fallback): `pipeline.json` currentIndex → 1, `active_agent.txt` → agents[1] 직접 갱신

git commit: `chore: planner requirements complete`

## 완료 후
자동으로 다음 에이전트(agents[1])의 첫 번째 단계를 실행한다.
