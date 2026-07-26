# crew:interact

Start a natural-language interaction with another AI session.

`interact` is the user-facing command. It keeps relay ids and session refs
internal, lists friendly session candidates, and asks the user to choose by
number or natural-language description. Once a target is selected, delivery is
attempted by default. Use `--no-send` for selection-only behavior.

Session candidates come from real AI host session stores, not from agent-crew
task/request state. agent-crew state is only optional enrichment for project,
branch, and recent-work summary fields.

When Agent of Empires (`aoe`) is installed, `interact` also discovers
AoE-registered Claude/Codex/OpenCode sessions from `aoe list` and selected AoE
sessions are delivered through `aoe send` without requiring per-shell delivery
environment variables. Set `AGENT_CREW_INTERACT_AOE_ENABLED=0` to disable this
integration.

For Codex, `interact` combines the lightweight `session_index.jsonl` list with
recent rollout session headers from the last 3 days so worktree sessions can be
selected by project and branch.

## CLI

```bash
crew interact "방금 relay 변경사항 클로드한테 리뷰 받아줘"
crew interact --to claude "agent-crew main 세션에 이 설계 물어봐줘"
crew interact --select 1 "방금 relay 변경사항 클로드한테 리뷰 받아줘"
crew interact --to contents-systsem --select 1 "hello"
crew interact --to contents-systsem --select 1 --no-send "hello"
crew interact --to contents-systsem --select 1 --send --copy "hello"
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
- `--select` attempts delivery by default and only a host adapter that returns
  explicit success may print `STATUS: sent`.
- `--no-send` only selects the target and prints `STATUS: selected`.
- `--send` is retained as an explicit, backward-compatible way to request the
  default delivery behavior.
- Unsupported host/session delivery creates a relay package and prints
  `STATUS: packaged`; it must not pretend the prompt was sent.
- Clipboard fallback is available only when `--copy` is explicit. Normal
  natural-language delivery must not copy by default.
- Real execution is enabled by an explicit delivery command, either
  `AGENT_CREW_INTERACT_DELIVERY_COMMAND_<HOST>` or
  `AGENT_CREW_INTERACT_DELIVERY_COMMAND`. Supported placeholders are
  `{prompt_file}`, `{copy_file}`, `{context_file}`, `{manifest_file}`,
  `{relay_dir}`, `{output_file}`, `{project_root}`, `{cwd}`, and
  `{target_host}`.
- AoE candidates do not require these environment variables. When the selected
  candidate came from `aoe list`, `interact` calls `aoe send <title> <prompt>`
  directly and records the result in `delivery.json`.
- A configured delivery command must exit with status 0 before `interact`
  reports `STATUS: sent`. Its stdout, stderr, return code, command, cwd, and
  output file path are recorded in `delivery.json` under the relay directory.
- If a configured delivery command fails or times out, `interact` reports
  `STATUS: failed` and still prints the relay prompt path for recovery.
