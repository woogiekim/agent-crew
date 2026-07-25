# crew:interact

Start a natural-language interaction with another AI session.

`interact` is the user-facing command. It keeps relay ids and session refs
internal, lists friendly session candidates, and asks the user to choose by
number or natural-language description before any future send step.

Session candidates come from real AI host session stores, not from agent-crew
task/request state. agent-crew state is only optional enrichment for project,
branch, and recent-work summary fields.

For Codex, `interact` combines the lightweight `session_index.jsonl` list with
recent rollout session headers from the last 3 days so worktree sessions can be
selected by project and branch.

## CLI

```bash
crew interact "방금 relay 변경사항 클로드한테 리뷰 받아줘"
crew interact --to claude "agent-crew main 세션에 이 설계 물어봐줘"
crew interact --select 1 "방금 relay 변경사항 클로드한테 리뷰 받아줘"
```

## Prompt Command

```text
$crew-interact 방금 relay 변경사항 클로드한테 리뷰 받아줘
```

Host prompt adapters should route this to the same `crew:interact` intent.

## Behavior

The command lists candidates like:

```text
전송할 AI 세션 후보를 찾았습니다.

추천:
① Claude · agent-crew · main
   relay 명령 구현 리뷰 · 8분 전

agent-crew
② Codex · docs/rename...
   stager rename/E2E 테스트 · 34분 전

번호나 설명으로 선택하세요.
예: 1, Claude agent-crew, main 브랜치
```

## Contract

- Hide opaque session and relay ids from normal output.
- Put the recommended candidate first.
- Treat user input `1` as choosing the recommended first candidate.
- Group many candidates by project while keeping global numbering.
- Match `--to` as natural tokens across AI type, project, branch, summary, and
  session cwd.
- Keep `relay` as the internal package/state protocol.
