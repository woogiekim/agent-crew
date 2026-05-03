# agent-crew — Global Claude Code Instructions

## 자동 에이전트 라우팅 (핵심 규칙)

사용자가 **코딩/구현/개발 작업**을 자연어로 요청하면 `/ship`을 명시하지 않아도 에이전트를 자동 spawn한다.

### 라우팅 판단 기준

| 요청 유형 | 첫 번째 spawn |
|---------|------------|
| 백엔드 API, 도메인 로직, DB | `backend` 에이전트 직접 |
| UI/화면 구현 | `designer` → `frontend` 순서 |
| 풀스택 / 범위 불명확 | `planner` 먼저 (파이프라인 결정) |
| 요구사항 분석, 기획 | `planner` 에이전트 |

### 자동 실행 vs 직접 응답 구분

**에이전트 spawn:** "만들어줘", "구현해줘", "개발해줘", "추가해줘", "수정해줘" + 개발 관련 내용
**직접 응답:** "어떻게", "설명해", "왜", "무엇" → 질문이면 에이전트 없이 직접 답변

### 실행 방법
```
# 단순 요청 — 바로 spawn
Agent(subagent_type="backend", prompt="TASK_DIR: ... \n요청 내용...")

# 복잡하거나 범위 불명확 — planner 먼저
Agent(subagent_type="planner", prompt="REQUEST: ... \nTASK_DIR: ...")
→ pipeline.json 읽어 다음 에이전트 결정
```

STATE_DIR 없으면 `~/.claude/agent-crew/{PROJECT_NAME}/tasks/{TASK_ID}` 형식으로 자동 생성.

## AskUserQuestion 사용 규칙

- 선택지에 "직접 입력", "기타 입력", "텍스트로 입력" 등의 자유 입력 옵션을 추가하지 않는다.
- AskUserQuestion은 항상 "Other" 자유 입력 필드를 자동 제공하므로 중복이다.
