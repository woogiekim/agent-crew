# crew:sync-instructions — Re-assemble Host AI Instruction Files

Materializes the canonical instruction rules stored in **mnemos** (global
layer, tagged `instruction-rule`) into the host AI instruction files
(`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.agent-crew/AGENTS.md`,
and the repo's `core/global-agents.md`).

This command is the **manual companion** of the automatic sync that
`crew:update` performs at the end of every update. Use it when:

- You edited a rule via `mnemos capture --layer global --id <id> ...`
  and want the change to land in host files immediately.
- You added a new rule and want to inspect the diff before applying.
- A host file has drifted from mnemos (manual edit) and you want to
  reset it from the canonical store.

## Default behavior — dry-run

```text
crew:sync-instructions
```

Runs `core/scripts/sync-instructions.sh` with no arguments, which defaults
to **dry-run mode**: prints a unified diff for every host file that would
change, mutates nothing. Exit code 3 indicates pending diffs (use `--apply`
to write); exit 0 means already in sync.

## Apply mode

```text
crew:sync-instructions --apply
```

Atomically rewrites every host file's marker block. Idempotent: a second
`--apply` run against an unchanged mnemos store performs zero writes.

## Per-host filter

```text
crew:sync-instructions --hosts claude --apply
crew:sync-instructions --hosts claude,codex
```

Limits the operation to a subset of hosts. Valid host identifiers:
`claude`, `codex`, `generic`, `repo`.

## 명시적인 단일 목적지

기본 경로 밖의 기존 지침은 `--hosts codex --target-file /absolute/AGENTS.md`로
미리 확인하고 `--apply`로 적용한다. 호스트는 `claude`, `codex`, `generic` 중
하나만 지정한다. `repo`는 전체 파일 교체 정책이므로 허용하지 않는다.
절대 경로, 존재하는 부모 디렉터리, 심볼릭 링크가 아닌 일반 파일만 허용한다
(새 파일 생성은 허용). 기본 호스트 대상과 필터링 동작은 바뀌지 않는다.
관리 블록 밖의 내용은 그대로 보존하므로 중복 사용자 규칙 정리는 별도 작업이다.

## How rules flow

```text
mnemos global layer (canonical)
    │   ── ~/.mnemos/wiki/global/rule:*.md
    ▼
core/scripts/sync-instructions.sh
    ├── ~/.claude/CLAUDE.md            (filtered by applies_to)
    ├── ~/.codex/AGENTS.md             (filtered by applies_to)
    ├── ~/.agent-crew/AGENTS.md        (filtered by applies_to)
    └── core/global-agents.md          (union — rendered fallback)
```

Content outside the `<!-- agent-crew-start --> ... <!-- agent-crew-end -->`
marker pair is **preserved verbatim**. This is how Codex's host-specific
Korean conversational rules continue to live alongside the agent-crew
managed block.

## Adding a new rule

```bash
mnemos capture --layer global --id rule:new-policy \
  --tag instruction-rule \
  --content "$(cat <<'EOF'
---
title: New Policy
applies_to: [all]
priority: 100
---

Rule body in markdown.
EOF
)"
crew:sync-instructions --apply
```

## Editing a rule

```bash
mnemos edit rule:input-language --content "$(cat new-body.md)"
crew:sync-instructions          # inspect diff
crew:sync-instructions --apply  # land it
```

## Initial seeding

Before this command can produce useful output, the mnemos global layer
must contain the rule items. On a new store, create the repository baseline
rules with the explicit non-destructive bootstrap profile:

```bash
bash core/scripts/seed-instruction-rules.sh --dry-run --profile bootstrap-missing
bash core/scripts/seed-instruction-rules.sh --apply --profile bootstrap-missing
```

`bootstrap-missing` creates absent rules only. It never replaces an existing
mnemos rule; subsequent policy edits use `mnemos edit` because mnemos remains
the canonical source. Without a profile, the seeder reconciles only the
repository-owned `runtime-command-surface` rules.

See `core/docs/ssot-design.md` for the architecture rationale and
`core/rules/instruction-rules-schema.md` for the rule item format.
