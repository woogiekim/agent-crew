# crew:relay

Package a local prompt handoff for another AI session.

Use this when the current session needs to prepare context for Claude, Codex,
Gemini, or another AI host without automatically executing that host.

## CLI

```bash
crew relay --to claude "Investigate hook latency"
crew relay --to codex --from-task 20260725-043606-0
crew relay --to gemini --mode review --paths core/hooks/auto-route.sh "Review this path"
crew relay --to claude --copy "Continue this analysis"
```

## Behavior

`crew relay` creates a relay package under:

```text
~/.agent-crew/state/{PROJECT_STATE_KEY}/relays/{RELAY_ID}/
```

The package contains:

- `manifest.json`: relay metadata, target host, source host, mode, and file paths.
- `context.json`: project root, branch, git status, referenced paths, and optional task context.
- `prompt.md`: the rendered target-session prompt.
- `copy.txt`: the same prompt text, suitable for clipboard transfer.

## Options

- `--to <host>`: target AI host name. Required.
- `--mode <ask|run|review|debug>`: prompt intent. Defaults to `ask`.
- `--from-task <task-id>`: include existing task `handoff.md` and `result.md` snippets.
- `--paths <path>`: include a referenced path. Repeat for multiple paths.
- `--copy`: copy the rendered prompt with `pbcopy` when available.

## Safety

This command is local-only. It does not start another AI session, call a host
bridge, push, deploy, merge, or mutate external systems.
