# Instruction Rules Schema

Defines how AI instruction rules are stored in mnemos so that the
`sync-instructions.sh` tool can assemble them deterministically into
host AI guidance files.

## Storage

- **CLI**: `mnemos` (resolved at `/Users/taewookkim/.local/bin/mnemos` or
  whatever the host's `MNEMOS_BIN` env var points to).
- **Layer**: `global` — rules are cross-project, host-spanning policies.
- **ID format**: `rule:<kebab-case-name>` — stable across the project's
  lifetime. Renaming an ID is a breaking change; treat it as a delete
  + recreate with explicit migration.
- **Tag**: every rule item carries the tag `instruction-rule`. The sync
  tool filters by this tag.
- **Path on disk** (managed by mnemos): `~/.mnemos/wiki/global/<id>.md`.

## Item body (rule content)

Rule body is a single markdown document with YAML front matter declaring
the rule's distribution metadata, followed by the rule body itself.

```markdown
---
title: <human-readable rule title>
applies_to:
  - claude
  - codex
  - generic
priority: <integer>           # smaller renders earlier; default 100
section: <section-heading>    # optional H2 grouping label for assembled output
---

<rule body — verbatim markdown, including indented code fences, blockquotes,
and tables. This block is what `sync-instructions.sh` writes between the
host file markers.>
```

### Field semantics

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | Used as the H2 heading in the assembled host file unless `section` overrides. |
| `applies_to` | list[string] | yes | One or more of `claude`, `codex`, `generic`. Use `all` as a shorthand for all three. |
| `priority` | int | no | Sort key inside a section. Lower runs first. Defaults to `100`. |
| `section` | string | no | Section grouping. Rules with the same `section` appear together. Defaults to the rule's title (one rule per section). |

### Host identifiers (`applies_to` values)

| Host | Identifier | Target file |
|---|---|---|
| Claude Code | `claude` | `~/.claude/CLAUDE.md` |
| Codex | `codex` | `~/.codex/AGENTS.md` |
| Generic | `generic` | `~/.agent-crew/AGENTS.md` |
| Repository fallback | (always written) | `<repo>/core/global-agents.md` |

The repository fallback is **always written** regardless of `applies_to` —
it serves as a rendered backup that `install.sh` can ship to hosts that
have not yet adopted the sync tool. It includes the union of all rules.

## Assembly contract

`sync-instructions.sh` performs these steps per host:

1. Query: `mnemos list --layer global --limit 9999` then filter items whose
   `tags` contain `instruction-rule`. (mnemos has no built-in tag query;
   the sync tool does this client-side.)
2. Read each item's content via `mnemos read <id>`.
3. Parse YAML front matter from each rule body.
4. Filter to rules whose `applies_to` contains the host identifier (or `all`).
5. Sort by `section` then `priority` then `id`.
6. Render markdown block:
   ```text
   <!-- agent-crew-start -->
   <!-- MANAGED BLOCK — DO NOT EDIT HERE.
        Edit rules via `mnemos capture --layer global --id <id> --content "<body>"`
        and re-run `crew:sync-instructions`. Manual edits will be overwritten. -->
   <!-- Assembled: <ISO-8601 UTC timestamp> from <N> mnemos rules -->

   # agent-crew — Global Rules

   ## <section or title>

   <rule body>

   ## ...
   <!-- agent-crew-end -->
   ```
7. Atomically rewrite the target file: read existing content, replace the
   marker block (or append + wrap if no markers), write to a sibling
   tempfile, `os.rename` over the target.

## Idempotency

A second invocation against an unchanged mnemos store produces a
byte-identical file *except* for the `Assembled:` timestamp line. The
sync tool detects this case by stripping the timestamp comment before
comparing — if the rest matches, the file is left untouched and no
write occurs. This guarantees `git diff` is empty on no-op runs.

## Backwards compatibility

- First-time sync on a file with no markers: the tool prepends the marker
  block before the existing content (content is preserved verbatim under
  the markers, never deleted).
- The `~/AGENTS.md` mnemos manifest is **explicitly excluded** from the
  host list — it is a separate concern (mnemos's own internal registry).
- Existing `merge_agent_crew_section()` in `core/setup/common.sh`
  continues to function — it now reads from `core/global-agents.md`
  which the sync tool keeps current.
