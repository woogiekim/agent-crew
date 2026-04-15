PROJECT_NAME=$(basename $(git rev-parse --show-toplevel 2>/dev/null || pwd))
`~/.claude/agent-crew/{PROJECT_NAME}/pipeline.json`을 읽어 `agents[currentIndex]`를 확인한다.
파일이 없거나 agents가 비어 있으면 `~/.claude/agent-crew/{PROJECT_NAME}/active_agent.txt`를 대신 읽는다.
확인된 에이전트의 `~/.claude/agent-crew/agents/[에이전트]/commands/requirements.md`를 읽고 그 지시에 따라 실행하라.
실행 완료 후 `/start` 명령의 인계 규칙에 따라 다음 단계로 자동 진행하라.
