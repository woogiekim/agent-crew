# Instruction SSOT Design — mnemos + Sync Tool

## Problem

agent-crew guidance is duplicated across at least four AI instruction files:

| File | Lines | Owner | Drift today |
|---|---|---|---|
| `~/.claude/CLAUDE.md` | ~321 | Claude Code global | Has updated routing rules, mnemos block |
| `~/.codex/AGENTS.md` | ~37 | Codex global | Korean conversational rules (host-specific), no agent-crew rules |
| `~/.agent-crew/AGENTS.md` | ~275 | agent-crew mid-tier | Rebuilt by install.sh from `core/global-agents.md` |
| `<repo>/AGENTS.md` | ~241 | repo-local | Stale terminology (`task-runner` vs `supervisor`); missing recent updates |

The existing `merge_agent_crew_section()` in `core/setup/common.sh` already
performs marker-based injection between `<!-- agent-crew-start -->` /
`<!-- agent-crew-end -->`, but only fires at `crew:setup` and offers no
per-host filter or post-setup refresh path. Edits to `core/global-agents.md`
do not propagate to host files until a manual per-host setup is re-run.

## Architecture choice — Option C: mnemos canonical + sync tool

### Considered alternatives

| Option | Description | Verdict |
|---|---|---|
| **A. Pure mnemos templating** | Each host file is a thin stub like `{{< mnemos search rule: --layer global >}}` evaluated at AI-host load time. | Rejected. No AI host evaluates such directives at load time. Would require a host hook on every read. |
| **B. Pure file build tool** | Source under `core/instructions/<rule>.md`, sync tool concatenates. | Rejected for this brief. Loses mnemos's queryability, layered storage, and the user's explicit "leverage mnemos" directive. |
| **C. Hybrid (chosen)** | mnemos holds canonical rules in global layer; sync tool reads them and rewrites host files between existing markers. | Accepted. mnemos is the mutation API (`mnemos capture`, `mnemos edit`); the sync tool is the materializer. |
| **D. Symlinks** | Symlink each host file to one canonical file. | Rejected. Breaks across Codex (does not follow symlinks reliably), invisible in git clones, no per-host filter possible. User explicitly flagged this as a fallback only. |

### Why mnemos over a flat file source

- **Queryable**: `mnemos search rule: --layers global` lets agents (or
  future tooling) find rules by topic without grep.
- **Per-rule audit trail**: mnemos tracks `created_at`, `access_count`,
  `quality_score` per item — useful for "which rules are stale" reporting.
- **Layered evolution**: a rule can graduate from `session` (one user's
  experiment) → `project` (proven for one repo) → `global` (canonical)
  via mnemos's promotion flow, then become an instruction rule via the
  seed script.
- **Already wired**: agent-crew already invokes mnemos via hooks; this
  centralization keeps the toolchain coherent.

## Components delivered

| Path | Purpose |
|---|---|
| `core/rules/instruction-rules-schema.md` | Defines rule body format, IDs, applies_to filter. |
| `core/scripts/seed-instruction-rules.sh` | Reconciles the repository-owned runtime command rules; an explicit `bootstrap-missing` profile creates absent baseline items without replacing canonical mnemos content. |
| `core/scripts/sync-instructions.sh` | Daily-use sync: queries mnemos, assembles per-host content, atomically rewrites between markers. |
| `core/commands/sync-instructions.md` | Explicit `crew:sync-instructions` command for manual reassembly. |
| `core/docs/ssot-rule-inventory.md` | Initial decomposition of current rules into rule IDs. |

## User workflow

### Adding a rule

```bash
mnemos capture --layer global \
  --id rule:new-policy-name \
  --tag instruction-rule \
  --content "$(cat <<'EOF'
---
title: New Policy Name
applies_to: [all]
priority: 100
---

Policy body in markdown.
EOF
)"

crew:sync-instructions    # propagate to all hosts
```

### Editing a rule

```bash
mnemos edit rule:input-language --content "$(cat new-body.md)"
crew:sync-instructions
```

### Removing a rule

```bash
mnemos archive rule:obsolete-policy
mnemos forget  rule:obsolete-policy   # optional hard delete
crew:sync-instructions
```

### Listing all instruction rules

```bash
mnemos list --layer global | grep instruction-rule
# or, more precisely, via the sync tool's dry-run:
crew:sync-instructions --dry-run
```

## Migration path

1. **Inspect**: `bash core/scripts/seed-instruction-rules.sh --dry-run --profile bootstrap-missing`
   — reports which baseline rule IDs would be created and which existing
   canonical rules would be preserved.
2. **Seed**: `bash core/scripts/seed-instruction-rules.sh --apply --profile bootstrap-missing`
   — creates only missing baseline rules in the mnemos global layer. It never
   updates existing mnemos content.
3. **Dry-run sync**: `bash core/scripts/sync-instructions.sh` (default
   is dry-run) — prints unified diffs of every host file change without
   writing.
4. **Apply sync**: `bash core/scripts/sync-instructions.sh --apply` —
   actually rewrites host files.
5. **Subsequent edits** use `mnemos capture/edit` + `crew:sync-instructions`.
   Running the seeder without a profile is reserved for the maintained
   `runtime-command-surface` compatibility repair and does not reconcile
   unrelated global policy.

## Failure modes

| Failure | Behavior |
|---|---|
| mnemos CLI missing | Sync exits non-zero with `ERROR: mnemos not found at $MNEMOS_BIN`. Host files untouched. |
| Rule body has invalid YAML front matter | Sync prints `WARN: skipping rule:<id> (invalid front matter)` and excludes it from the assembled output. Other rules still apply. |
| Host file missing | Sync skips the host file with a `WARN: <path> does not exist (skipping)` notice. Other hosts still update. |
| Host file has no markers | Sync wraps existing content under the markers (existing content preserved verbatim above an inserted marker block). |
| User manually edited inside marker block | Overwritten on next sync. The marker comment warns about this loudly. |
| `core/global-agents.md` becomes the only target (mnemos absent) | Install.sh continues to read it as the source; the rendered fallback ensures hosts that pull a release tarball still get the latest rules. |

## Idempotency guarantee

Two consecutive `sync-instructions.sh --apply` runs against an unchanged
mnemos store produce zero file changes on the second run. The tool
strips the `Assembled:` timestamp before computing equality so that
timestamp-only deltas do not trigger writes.

## Out of scope

- Editing `~/AGENTS.md` — that is the mnemos manifest, a separate concern.
- Migrating Codex's Korean conversational rules into mnemos — they are
  host-specific and live outside the marker block (preserved verbatim).
- A graphical rule editor — `mnemos capture` is the supported API.
