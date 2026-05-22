# crew:update - Refresh installed agent-crew assets from source repo

## Purpose

`crew:update` re-runs the host adapter installation against the current
source repository to refresh installed agents, hooks, rules, policies, commands,
skills, and adapter scripts under `~/.agent-crew/` and the host-specific
location (e.g. `~/.claude/agent-crew/` for the Claude adapter).

It complements `crew:setup`:

| Command       | Purpose                                          | State reset prompt |
|---------------|--------------------------------------------------|--------------------|
| `crew:setup`  | First-time install or fresh project init         | Yes (if state exists) |
| `crew:update` | Refresh installed assets from a newer source repo| No (always preserves state) |

Unlike `crew:setup`, this command:

- Never prompts to reset per-project state under `~/.agent-crew/state/`.
- Never deletes extraneous files at the install destination.
- Uses `cp -f` (Bash) for all file content updates, guaranteeing byte-for-byte
  replacement of installed files with source content.
- Is idempotent: re-running with no source changes produces identical installed
  files — `cp -f` always overwrites destination with source, so a second run
  leaves files byte-for-byte identical to their source counterparts.
- Does not alter `~/.claude/settings.json` hook configuration beyond what
  the original `install.sh` already does (it reuses the same marker-merge
  logic).

## Arguments

| Argument | Default | Description |
|---|---|---|
| none | — | `crew:update` always refreshes from the remote source repository. |

## State Paths

```bash
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
```

## Source Acquisition

`crew:update` always starts from a fresh remote checkout. It does not depend on
an existing local source clone.

```bash
REPO_URL="https://github.com/woogiekim/agent-crew"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

git clone --depth 1 "${REPO_URL}" "${WORK_DIR}"
SOURCE_ROOT="${WORK_DIR}"
SOURCE_DIR="${SOURCE_ROOT}/core"
ADAPTERS_DIR="${SOURCE_ROOT}/adapters"
```

## Execution

1. For each file category below, use Bash `cp -f` (or `cp -rf`) to copy all
   source files to the destination. This guarantees byte-for-byte replacement
   regardless of what was previously installed — the destination always matches
   the source exactly after the copy.

   Bash is used for all file operations:
   - `mkdir -p` (create destination directories)
   - `cp -f` / `cp -rf` (copy files — overwrites destination unconditionally)
   - `chmod +x` (make shell scripts executable)
   - `settings.json` hook registration (python3 merge helpers from `install.sh`)

   **File categories and their source → destination mappings:**

   | Category | Source | Destination (primary) | Destination (compat alias) |
   |---|---|---|---|
   | commands | `${SOURCE_DIR}/commands/` | `${AGENT_CREW_HOME}/system/commands/` | `${AGENT_CREW_HOME}/commands/` |
   | rules | `${SOURCE_DIR}/rules/` | `${AGENT_CREW_HOME}/system/rules/` | `${AGENT_CREW_HOME}/rules/` |
   | hooks | `${SOURCE_DIR}/hooks/` | `${AGENT_CREW_HOME}/system/hooks/` | `${AGENT_CREW_HOME}/hooks/` |
   | scripts | `${SOURCE_DIR}/scripts/` | `${AGENT_CREW_HOME}/system/scripts/` | `${AGENT_CREW_HOME}/scripts/` |
   | schemas | `${SOURCE_DIR}/schemas/` | `${AGENT_CREW_HOME}/system/schemas/` | `${AGENT_CREW_HOME}/schemas/` |
   | policies | `${SOURCE_DIR}/policies/` | `${AGENT_CREW_HOME}/system/policies/` | `${AGENT_CREW_HOME}/policies/` |
   | setup | `${SOURCE_DIR}/setup/` | `${AGENT_CREW_HOME}/system/setup/` | `${AGENT_CREW_HOME}/setup/` |
   | adapters | `${ADAPTERS_DIR}/` | `${AGENT_CREW_HOME}/system/adapters/` | `${AGENT_CREW_HOME}/adapters/` |
   | agents | `${SOURCE_DIR}/agents/` | `${AGENT_CREW_HOME}/system/agents/` | (via sync_system_agents) |
   | skills | `${SOURCE_DIR}/agents/skills/` | `${AGENT_CREW_HOME}/system/skills/` | `${AGENT_CREW_HOME}/skills/` |

   **Subdirectory categories:** `rules/` contains a `capabilities/`
   subdirectory (per-flag detail docs); `scripts/` and `policies/` may be flat
   or contain subdirectories. Use `cp -rf src/. dest/` for these categories so all
   subdirectories and their contents are copied recursively and destination
   paths preserve the relative structure from the source root.
   | claude hooks | `${AGENT_CREW_HOME}/hooks/` | `${CLAUDE_DIR}/agent-crew/hooks/` | — |
   | claude rules | `${AGENT_CREW_HOME}/rules/` | `${CLAUDE_DIR}/agent-crew/rules/` | — |
   | claude setup | `${AGENT_CREW_HOME}/setup/` | `${CLAUDE_DIR}/agent-crew/setup/` | — |
   | claude commands | `${AGENT_CREW_HOME}/commands/` | `${CLAUDE_DIR}/commands/` | — |
   | claude agents | `${AGENT_CREW_HOME}/system/agents/` | `${CLAUDE_DIR}/agent-crew/agents/` | — |
   | claude skills | `${AGENT_CREW_HOME}/skills/` | `${CLAUDE_DIR}/agent-crew/skills/` | — |

   For each category, use Bash:

   ```bash
   # Flat categories (commands, hooks, schemas, setup, adapters, skills):
   mkdir -p "${DEST_DIR}"
   cp -f "${SRC_DIR}/"* "${DEST_DIR}/"

   # Recursive categories (rules, scripts, agents):
   mkdir -p "${DEST_DIR}"
   cp -rf "${SRC_DIR}/." "${DEST_DIR}/"

   # After copying scripts and hooks:
   chmod +x "${DEST_DIR}/"*.sh 2>/dev/null || true
   ```

   Do NOT use the Read/Write/Edit tools for file copying. Those tools perform
   diff-based or content-augmenting operations that can preserve or add
   destination content not present in the source, breaking idempotency.
   `cp -f` / `cp -rf` unconditionally replaces the destination with the source
   byte-for-byte.

   **Agent layer enforcement** (use Bash, not Read/Write):

   After writing agents, run `sync_system_agents` to prune stale agents that
   were removed from the source repo:

   ```bash
   . "${SOURCE_DIR}/setup/common.sh"
   sync_system_agents \
     "${SOURCE_DIR}/agents" \
     "${AGENT_CREW_HOME}/system/agents" \
     "mcp-manager.md"
   ```

   Then merge system + user agents into the discovery destination:

   ```bash
   merge_agents_to_discovery \
     "${AGENT_CREW_HOME}/system/agents" \
     "${AGENT_CREW_HOME}/user/agents" \
     "${CLAUDE_DIR}/agents"
   ```

   **Skill layer enforcement** (use Bash, not Read/Write):

   After syncing agents, run `sync_system_skills` to install skills from the
   source repo into the system skill layer and prune stale skills that were
   removed from the source repo:

   ```bash
   . "${SOURCE_DIR}/setup/common.sh"
   sync_system_skills \
     "${SOURCE_DIR}/agents/skills" \
     "${AGENT_CREW_HOME}/system/skills"
   ```

   Then merge system + user skills into the unified discovery destination.
   User skills take precedence — a user skill with the same filename as a
   system skill overwrites the system copy in the discovery path:

   ```bash
   merge_skills_to_discovery \
     "${AGENT_CREW_HOME}/system/skills" \
     "${AGENT_CREW_HOME}/user/skills" \
     "${AGENT_CREW_HOME}/skills"
   ```

   Finally, copy the unified skill discovery to the Claude mirror path:

   ```bash
   copy_dir_contents \
     "${AGENT_CREW_HOME}/skills" \
     "${CLAUDE_DIR}/agent-crew/skills"
   ```

3.5. **Phase C3.0 Migration — Remove Stale `task-runner` Files**

   The `task-runner` agent was renamed to `supervisor` in Phase C3.0.
   `sync_system_agents` and `merge_agents_to_discovery` auto-prune two of the
   four installation paths; the other two are copied via `cp -R src/. dest/`
   which overwrites but does not delete. Defensively remove all four
   locations so the host never sees both the old and the new agent.

   Uses the standard migration helper (see § Migration Conventions
   below). The block is idempotent — `rm -f` is silent on missing files.
   After the first successful `crew:update` post-C3.0 it becomes a no-op.

   ```bash
   PROJECT_ROOT_LOCAL="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
   bash "${AGENT_CREW_HOME}/scripts/migrate-rm-stale.sh" \
     "Phase C3.0 task-runner" \
     "${AGENT_CREW_HOME}/system/agents/task-runner.md" \
     "${CLAUDE_DIR}/agents/task-runner.md" \
     "${CLAUDE_DIR}/agent-crew/agents/task-runner.md" \
     "${CODEX_HOME:-${HOME}/.codex}/agents/task-runner.toml" \
     "${PROJECT_ROOT_LOCAL}/.codex/agents/task-runner.toml"
   ```

   > **Note:** the literal token `task-runner` survives intentionally inside
   > this migration block — it is the name of the OLD file being removed.
   > Verification greps must allow these occurrences in `update.md`.

3.6. **Phase C2 Note — Supervisor sub-modules**

   Phase C2 split `supervisor.md` into an index plus three sibling content
   modules (`supervisor-bootstrap.md`, `supervisor-stages.md`,
   `supervisor-retry.md`). `sync_system_agents` and
   `merge_agents_to_discovery` handle these automatically because they sit
   at the top level of `core/agents/` (the same flat-glob copy that already
   moves `supervisor.md`). No migration code is required — the three new
   files arrive on the next `crew:update` and the host registers only
   `supervisor.md` as an agent (the others have no `name:` frontmatter).

3.7. **Phase 3.1 Migration — Remove Stale `scribe` Agent and Outline Hook**

   The `scribe` agent was a user-specific Outline / Plane / connect-docs
   integration that should never have been classified as a system agent.
   It is removed from the system layer in Phase 3.1; users who wrote
   custom scribe workflows must copy their version to
   `~/.agent-crew/user/agents/scribe.md` BEFORE running `crew:update`
   (this migration only removes the system copies). The paired
   `outline-posttooluse.sh` hook is also removed — it was passive (never
   wired into `settings.json`), so no hook unregistration is required.

   `sync_system_agents` and `merge_agents_to_discovery` auto-prune stale
   generated agents when no matching user-owned agent exists. If
   `~/.agent-crew/user/agents/scribe.md` exists, the generated host
   discovery files are user-owned outputs and MUST NOT be removed by this
   migration; otherwise every `crew:update` re-creates them from user/
   and then deletes them again. Hooks are copied via `cp -R` at three
   paths, so the stale hook is still removed defensively.

   The block is idempotent — `rm -f` is silent on missing files. After
   the first successful `crew:update` post-3.1 it becomes a no-op. The
   literal tokens `scribe` and `outline-posttooluse` survive inside this
   migration block intentionally; verification greps must allow these
   occurrences in `update.md` (same convention as the C3.0 `task-runner`
   block above).

   ```bash
   # Pre-removal warning if scribe is in system/ but absent from user/
   # (user-data preservation prompt — specific to this migration; not
   # extracted to migrate-rm-stale.sh).
   if [ -f "${AGENT_CREW_HOME}/system/agents/scribe.md" ] \
      && [ ! -f "${AGENT_CREW_HOME}/user/agents/scribe.md" ]; then
     printf '[crew:update] WARNING: scribe.md is being removed from system/ but no user/ copy exists.\n'
     printf '             If you use scribe, run BEFORE re-running crew:update:\n'
     printf '               cp "%s" "%s"\n' \
       "${AGENT_CREW_HOME}/system/agents/scribe.md" \
       "${AGENT_CREW_HOME}/user/agents/scribe.md"
     printf '             Continuing in 3s (Ctrl-C to abort)...\n'
     sleep 3
   fi

   # Stale scribe system copy. Generated host discovery files are removed
   # only when no user-owned scribe agent exists.
   bash "${AGENT_CREW_HOME}/scripts/migrate-rm-stale.sh" \
     "Phase 3.1 scribe" \
     "${AGENT_CREW_HOME}/system/agents/scribe.md"

   if [ ! -f "${AGENT_CREW_HOME}/user/agents/scribe.md" ]; then
     PROJECT_ROOT_LOCAL="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
     bash "${AGENT_CREW_HOME}/scripts/migrate-rm-stale.sh" \
       "Phase 3.1 scribe discovery" \
       "${CLAUDE_DIR}/agents/scribe.md" \
       "${CLAUDE_DIR}/agent-crew/agents/scribe.md" \
       "${PROJECT_ROOT_LOCAL}/.codex/agents/scribe.toml"
   fi

   # Stale outline-posttooluse hook — three installation paths
   bash "${AGENT_CREW_HOME}/scripts/migrate-rm-stale.sh" \
     "Phase 3.1 outline-posttooluse" \
     "${AGENT_CREW_HOME}/system/hooks/outline-posttooluse.sh" \
     "${AGENT_CREW_HOME}/hooks/outline-posttooluse.sh" \
     "${CLAUDE_DIR}/agent-crew/hooks/outline-posttooluse.sh"
   ```

   > **User-data preservation:** if a user has placed their own
   > customized `scribe.md` at `~/.agent-crew/user/agents/scribe.md`, it
   > is preserved — the migration removes only `system/agents/scribe.md`
   > while that user copy exists. The user copy continues to be merged
   > into `~/.claude/agents/scribe.md` by `merge_agents_to_discovery` and
   > into Codex project agents by the Codex adapter on subsequent updates.

   > **Hook registration:** `outline-posttooluse.sh` was never registered
   > as a `PostToolUse` hook in either `install.sh` or
   > `adapters/claude/setup.sh` (verified during Phase 3.1 audit). No
   > `settings.json` rewrite is needed — removing the script alone is
   > sufficient.

3.8. **Issue #26 — Rebuild mnemos FTS index after mnemos update**

   `mnemos search` was returning raw YAML frontmatter blocks and `MEMORY.md`
   index entries as search hits (Issue #26).  The fix shipped in mnemos
   (`core/fts.py` — strip frontmatter before FTS indexing; `agents/scanner.py`
   — exclude `MEMORY.md` from `discover_memory_files`).

   Because the FTS database (`~/.mnemos/.agent/state/fts.db`) was populated
   before the fix, existing entries still contain the stale frontmatter-polluted
   content.  The database is rebuilt correctly on the next `mnemos ingest-claude-md`
   run — this step triggers that rebuild automatically as part of `crew:update`.

   The block is idempotent and safe to re-run: `ingest-claude-md` uses
   content-hash deduplication so repeated runs are no-ops on unchanged files.

   ```bash
   if [ -x "${MNEMOS_BIN:-${HOME}/.local/bin/mnemos}" ]; then
     printf '[crew:update] Rebuilding mnemos FTS index (issue #26 fix)...\n'
     "${MNEMOS_BIN:-${HOME}/.local/bin/mnemos}" ingest-claude-md --quiet 2>/dev/null || true
     printf '[crew:update] mnemos FTS index rebuilt.\n'
   fi
   ```

   `|| true` ensures a mnemos failure never blocks the broader update.
   `--quiet` suppresses per-item capture notices that would clutter the
   update log.

   > **One-time action:** After the first `crew:update` post-Issue-#26 the FTS
   > database is clean and future runs of `ingest-claude-md` are content-hash
   > no-ops for unchanged memory files.

2. Refresh adapter paths in two phases (P5 split):

   Before adapter-specific paths are refreshed, `update-global-adapters.sh`
   also copies `core/hooks/*.sh` into both `${AGENT_CREW_HOME}/system/hooks/`
   and `${AGENT_CREW_HOME}/hooks/`. Hook payloads are live runtime behavior;
   stale `auto-route.sh` copies must not keep emitting old STOP/ROUTE guidance
   after source fixes have landed.

   **(a) Global-scope update** — runs all installed global-scope adapters
   (Claude `~/.claude/agent-crew/`, Codex `~/.codex/skills/agent-crew/` and
   the internal agent-crew guide mirror at `~/.codex/agent-crew/skills/`)
   without requiring PROJECT_ROOT context. The mirror is not the native Codex
   skill directory; native Codex skills live under `~/.codex/skills/`.
   Only adapters whose installation directory already exists on this machine
   are updated (installation-presence guard):

   ```bash
   AGENT_CREW_MODE=update SOURCE_ROOT="${SOURCE_ROOT}" \
     bash "${AGENT_CREW_HOME}/scripts/update-global-adapters.sh"
   ```

3. Update settings.json hook registrations (idempotent):

   ```bash
   AGENT_CREW_MODE=update \
   AGENT_CREW_INSTALL_CLAUDE_COMPAT=0 \
   AGENT_CREW_SOURCE_DIR="${SOURCE_ROOT}" \
     bash "${SOURCE_ROOT}/install.sh"
   ```

   This re-runs the marker-merge helpers so any newly added global hooks are
   registered without duplicating existing entries. `AGENT_CREW_SOURCE_DIR`
   MUST point to the repository root (the directory containing `core/` and
   `adapters/`), not to `${SOURCE_DIR}`. `AGENT_CREW_INSTALL_CLAUDE_COMPAT=0`
   prevents this global hook-registration pass from re-running a project-local
   Claude adapter and overwriting the current project's active-host
   `capabilities.json`.

4. **Project-local update** — re-runs the detected host adapter for the
   current project so project-local files are also refreshed. This step runs
   after the global `install.sh` pass so the final
   `${STATE_DIR}/capabilities.json` belongs to the active project host, not to
   the Claude compatibility layer. The fan-out loop in `setup-host.sh` runs all
   detected+installed adapters in sequence instead of stopping at the first
   match (P1 fix):

   ```bash
   PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   AGENT_CREW_MODE=update \
     bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "${PROJECT_ROOT}"
   ```

5. **Sync host AI instruction files from mnemos (Phase L17).** After the
   asset refresh and adapter re-run, materialize the canonical instruction
   rules stored in mnemos into the host AI md files. This is the
   companion to `crew:sync-instructions` and keeps Claude / Codex /
   Generic guidance coherent with any rule edits since the last update.

   The seed script is run first (idempotent — no-ops when the rule items
   already exist with identical content), then the sync tool applies any
   pending diffs:

   ```bash
   if [ -x "${MNEMOS_BIN:-${HOME}/.local/bin/mnemos}" ]; then
     bash "${SOURCE_DIR}/scripts/seed-instruction-rules.sh" --apply || true
     bash "${SOURCE_DIR}/scripts/sync-instructions.sh"     --apply || true
   else
     printf '[crew:update] mnemos CLI not found at %s — skipping instruction sync.\n' \
       "${MNEMOS_BIN:-${HOME}/.local/bin/mnemos}"
     printf '              Host AI files remain in their current state.\n'
   fi
   ```

   `|| true` ensures a mnemos hiccup never fails the broader update.
   The dedicated `crew:sync-instructions` command remains available for
   manual re-runs and dry-run inspection. See
   `core/commands/sync-instructions.md` and `core/docs/ssot-design.md`
   for the architecture.

## Safety Guarantees

- `${AGENT_CREW_HOME}/state/` is NEVER touched. The `cp -f` approach
  targets only the categories listed above, which never overlap with state.
- The state directory marker file `${STATE_DIR}/tasks/active` (if present
  from an in-flight crew task) is preserved.
- `cp -f` guarantees byte-for-byte replacement: a second `crew:update` run
  with no source changes produces installed files that are always identical
  to source. Unlike Read/Write/Edit tools (which perform diff-based or
  content-augmenting operations), `cp -f` unconditionally overwrites the
  destination — installed files can never be larger than source.
- Any locally-created custom agents at `~/.agent-crew/user/agents/` are
  preserved — `sync_system_agents` and `merge_agents_to_discovery` only
  operate on the `system/agents/` layer.
- Any locally-created custom skills at `~/.agent-crew/user/skills/` are
  preserved — `sync_system_skills` only operates on the `system/skills/`
  layer. `merge_skills_to_discovery` copies user skills after system skills
  so user skills take precedence in the unified `~/.agent-crew/skills/` view.
  User skill files are NEVER deleted or overwritten by `crew:update`.
- Every local/remote update writes a preservation manifest under
  `${AGENT_CREW_HOME}/state/${PROJECT_NAME}/update-preservation/`. The manifest
  records before/after counts and hashes for user agents, user skills, and
  relevant host settings. If a user-owned agent or skill disappears during the
  update, the update fails instead of silently reporting success.

## Migration Notes

### Migration Conventions

Each phase that removes or relocates files installed by an earlier version
of agent-crew SHOULD add a migration block to this file. The block is
executed during `crew:update` on existing installations to clean up the
two-of-four installation paths that the existing sync helpers
(`sync_system_agents`, `merge_agents_to_discovery`) do NOT auto-prune:

- `${CLAUDE_DIR}/agent-crew/agents/` (Claude mirror — `cp -R` copy, no prune)
- `${PROJECT_ROOT}/.codex/agents/` (Codex per-project — `cp -R` copy, no prune)
- `${CLAUDE_DIR}/agent-crew/hooks/` (Claude hook mirror — `cp -R` copy)
- `${AGENT_CREW_HOME}/hooks/` (compat alias under user home)

#### Standard pattern

Use the provider-neutral helper `core/scripts/migrate-rm-stale.sh`. It
takes a label string + one or more candidate paths and idempotently
removes any that exist. Re-running it after a successful migration is a
no-op with a single "already migrated" log line.

```bash
bash "${AGENT_CREW_HOME}/scripts/migrate-rm-stale.sh" \
  "Phase X.Y short-tag" \
  "${AGENT_CREW_HOME}/system/agents/old-name.md" \
  "${CLAUDE_DIR}/agents/old-name.md" \
  "${CLAUDE_DIR}/agent-crew/agents/old-name.md" \
  "${PROJECT_ROOT_LOCAL}/.codex/agents/old-name.toml"
```

#### Where to put new migration blocks

| Migration type | Location |
|---|---|
| **File removal / rename** (executable bash) | Numbered substep in § Execution (e.g. 3.8, 3.9) **AND** an informational entry in § Migration Notes below. |
| **Schema/contract change with user-visible impact** (documentation only) | Subsection in § Migration Notes only. |
| **No-op note** (sync helpers handle it; future readers should know why) | Subsection in § Migration Notes only. |

#### Rules

1. Migration code MUST be idempotent. `migrate-rm-stale.sh` and the
   user-data preservation guard (see Phase 3.1 example) both satisfy
   this; future patterns must too.
2. Literal old filenames inside a migration block are intentional —
   they are the names of the files being removed. Verification greps
   that count `old-name` references must allow these occurrences in
   `update.md`.
3. User-data preservation: if removing a file from `system/` could
   strand user customization, the migration block MUST include a
   pre-removal `WARNING` prompt + `sleep 3` grace period (see Phase
   3.1 scribe example).
4. Hooks that were registered in `~/.claude/settings.json` need
   explicit `settings.json` cleanup separate from file removal; verify
   the registration status before writing a hook-removal block (the
   audit in Phase 3.1 found `outline-posttooluse.sh` was never
   registered, so no `settings.json` rewrite was needed).

### Phase 3.2 — `reasoning_tier` materialization

System agents now declare a `reasoning_tier` (`deep` / `balanced` /
`light`) in their frontmatter. On `crew:update`, the Claude adapter
rewrites the `model:` line of each installed agent at
`~/.claude/agents/*.md` to a concrete model identifier based on the
declared tier (see `core/rules/capabilities/reasoning-tier.md`).

Source files under `core/agents/` keep `model: inherit` and are not
changed. User agents under `~/.agent-crew/user/agents/` are left
untouched — user-owned files retain whatever `model:` value they
have. Agents without YAML frontmatter (e.g. `korean-normalizer.md`)
are silently skipped.

If you previously hand-edited `~/.claude/agents/*.md` to set a custom
`model:` for a system agent, your edit will be overwritten on the
next update. Move the agent to `~/.agent-crew/user/agents/` (and
rename it to avoid the system filename collision) to preserve a
manual model choice.

The Codex adapter does NOT auto-map `reasoning_tier` to a concrete
model. Codex custom-agent TOML supports official per-agent keys such as
`model`, `model_reasoning_effort`, and `sandbox_mode`; when users put
those keys in `~/.agent-crew/user/agents/*.md` frontmatter, the Codex
adapter preserves them in generated `.codex/agents/*.toml`. The abstract
`reasoning_tier` remains advisory unless the user supplies concrete
Codex model settings.

### Phase 3.3 — `cost_tracking` capability + cost circuit breaker

The Claude adapter now advertises `cost_tracking: true` in
`capabilities.json` and registers `cost-tracker.sh` as a `PostToolUse`
hook in `~/.claude/settings.json`. On the next `crew:update`:

- `adapters/claude/setup.sh` re-writes `capabilities.json` with the
  new flag set to `true`. Existing files without the field default
  to `false` per the Absence Contract, so until update runs, the
  supervisor treats cost tracking as disabled — old installations
  continue to work unchanged.
- The `PostToolUse` registration for `cost-tracker.sh` is idempotent
  (mirrors the existing `agent-diff-post.sh` pattern). Re-running
  `crew:update` is safe.
- `core/scripts/cost-aggregate.py` is a new file — copied alongside
  other scripts under `${AGENT_CREW_HOME}/scripts/`.
- The legacy `~/.agent-crew/metrics/costs.jsonl` file (written by the
  pre-3.3 `cost-tracker.sh`) is **NOT** automatically migrated. The
  new hook writes to per-task files under
  `${STATE_DIR}/cost/<TASK_ID>.jsonl` instead. Users who want to keep
  the historical session-scoped data can leave `metrics/costs.jsonl`
  in place; the new `crew:cost` does not read it but does not delete
  it either.
- No manual intervention is needed: a fresh `crew:update` flips all
  the relevant pieces atomically.

User-facing config:

- `AGENT_CREW_BUDGET_DEEP`, `AGENT_CREW_BUDGET_BALANCED`,
  `AGENT_CREW_BUDGET_LIGHT` env vars override per-tier budgets.
  Defaults: 200,000 / 150,000 / 100,000 tokens. See
  `core/rules/quality-loop.md` § Cost Circuit Breaker.

Codex and generic adapters: no change. `cost_tracking` remains
`false` (implicit via absence from their `capabilities.json` or
absence of the file entirely). `crew:cost` prints a one-paragraph
fallback note on those adapters.

### Phase 3.5 — Auto handoff page-out (opt-in)

The supervisor can now compact `{TASK_DIR}/handoff.md` between stages
when it grows beyond a configurable threshold. The compacted handoff
replaces the original at `{TASK_DIR}/handoff.md`; the original is
preserved at `{TASK_DIR}/archive/handoff-{N}.md`.

**The feature is OFF by default.** Existing installations are
unaffected by `crew:update` until the user explicitly opts in:

```bash
export AGENT_CREW_HANDOFF_AUTO_PAGEOUT=1
# Optional: override default threshold (8000 chars ≈ 2000 tokens for
# English-heavy text, ~2700 tokens for mixed Korean). Lower values
# trigger page-outs more aggressively; higher values let handoff.md
# grow.
export AGENT_CREW_HANDOFF_PAGEOUT_THRESHOLD=8000
```

When enabled, the supervisor measures `handoff.md` after each stage
completion (via `wc -m`). If the size exceeds the threshold, the
supervisor invokes the documenter agent in `MODE=page-out` — a single
additional **light-tier** LLM call that produces a one-paragraph-per-
stage digest plus the last 2–3 verbatim stage outputs. The original
handoff is moved (not copied) to `{TASK_DIR}/archive/handoff-{N}.md`
where `N` is monotonically increasing, derived statelessly from
`ls archive/handoff-*.md | wc -l + 1`.

**Cost impact when enabled.** One extra light-tier call per page-out
event. The conservative default threshold (8000 chars) means most
short pipelines never trigger a page-out. Long pipelines (10+ stages
or stages that append verbose handoff content) may see 1–3 page-outs
per task. The page-out call counts toward the cost circuit breaker
total (see Phase 3.3).

**Failure mode.** If the page-out itself fails (documenter returns
`STATUS: BLOCKED` or crashes), the supervisor logs
`HANDOFF_PAGEOUT_FAILED` and continues with the un-paged handoff.
The pipeline is never failed because of a page-out failure. See
`core/rules/quality-loop.md` § Page-Out As Hygiene Operation.

**Cost breaker interaction.** If the cost circuit breaker has already
reached `exceeded` when a page-out would otherwise fire, the
supervisor SKIPS the page-out (logs `HANDOFF_PAGEOUT_SKIPPED |
reason=cost_exceeded`) and continues. Page-out never fires when the
budget is already gone.

**No migration code required.** This is a pure opt-in feature with no
state-file schema change and no installed-file removal. The new
documenter `MODE=page-out` branch arrives via the standard agent-file
sync (`merge_agents_to_discovery`).

### Phase F5 — Structured progress event buffer

The supervisor now writes every progress event to a structured JSONL
buffer at `${STATE_DIR}/tasks/${TASK_ID}/progress.buffer.jsonl` in
addition to the existing `progress.log` and stderr mirror. Schema:
`core/rules/state-files/progress-buffer-jsonl.md`.

**No migration code required.** Pure additive:

- New per-task file `progress.buffer.jsonl` appears alongside the
  existing `progress.log` for every task started after upgrading.
  Older task directories without the JSONL file continue to render
  via the legacy `tail -20 progress.log` fallback in `crew:status` —
  no retroactive write.
- No env var or feature toggle: the dual-write is always on. Both
  files are written from a single `log_progress` invocation in
  `supervisor-bootstrap.md` Phase 0.
- No `settings.json` changes.
- No new capability flag. The existing `monitor_tool` flag continues
  to gate host-streamed event consumption; F5 refines only the
  file-based fallback path.

**Storage impact.** The JSONL buffer is roughly the same size as
`progress.log` per task (one structured line per event; ~250 bytes
per row vs ~80 bytes for the legacy line). A typical short pipeline
emits 20–40 events; a long pipeline with retries and page-outs may
reach 200. Total per-task storage stays well below 100 KB even in
the worst case.

**Trace correlation.** Each row carries a `trace_id` of the form
`{SESSION_ID}.{TASK_ID}.{STAGE_INDEX}.{RETRY_ATTEMPT}` so events
from the same attempt correlate, and events from different retries
of the same stage are distinguishable. See the schema doc for the
full field catalog.

**Consumer rollout.** `crew:status` Step 5 automatically prefers the
JSONL buffer when present. No user action required.

**Orchestrator-side change.** `crew:run` now passes `SESSION_ID` to
the supervisor via the input block (previously absent for single-task
runs). The supervisor falls back to deriving `SESSION_ID` from
`TASK_ID` if the orchestrator omits it — old-style spawn paths remain
functional.

### Phase F4 — State-file schema validation + register.json

The supervisor now writes a per-task `register.json` pointer file
alongside `pipeline.json`, and a stdlib Python validator at
`${AGENT_CREW_HOME}/scripts/validate-state-schema.py` runs at every
supervisor Phase 0 to catch malformed state before serious work. Schemas
live under `${AGENT_CREW_HOME}/schemas/*.schema.json` (and the compat
mirror at `${AGENT_CREW_HOME}/system/schemas/`).

**No migration code required.** Pure additive:

- New per-task file `register.json` appears alongside the existing
  `pipeline.json` for every task started after upgrading. Pre-F4 task
  directories without `register.json` continue to work — the validator
  silently warns on absence and the supervisor's resume path tolerates
  it. The next phase boundary update will create register.json
  retroactively on resumed tasks.
- No env var or feature toggle: the validator is always invoked.
- No new capability flag. Schema validation is host-agnostic.
- No `settings.json` changes.

**Validator severity classes (mixed mode).**

- Hard halts (exit 2): own-task files (`register.json`,
  `pipeline.json`, `progress.buffer.jsonl`) with type errors or missing
  required fields. The supervisor writes BLOCKED with
  `BLOCKER: state_schema_invalid` and returns to the orchestrator.
- Soft warns (exit 1): cross-task files (`session.json`,
  `capabilities.json`); forward-compat (`schema_version > 1`); pre-F4
  absent files. The supervisor logs `STATE_WARN` and continues.

**Forward compatibility.** Every schema includes a `schema_version`
field. The current schema is v1. Future versions bump the field and the
validator tolerates higher versions with a warning (forward-compat).

**Storage impact.** `register.json` is ~600 bytes per task. The 5
schema JSON files total ~6 KB and sit under `${AGENT_CREW_HOME}/schemas/`
once per install, not per task.

**Update steps.** The standard category sync in § Execution copies
`core/schemas/` into both `system/schemas/` and the `schemas/` compat
alias. No special migration block — `crew:update` picks the schemas up
on the next refresh.

**Cross-references updated.**

- `core/rules/disambiguation.md` § Approval Workflow drops the
  "(once introduced)" qualifier on register.json caching.
- `core/rules/task-injection.md` § `task_hash` field drops the
  "register.json does not exist yet" note (it now exists, but the
  field placement decision stays — task_hash lives in session.json
  only, not register.json, because session.json is the dedup source).
- `core/rules/state-files/progress-buffer-jsonl.md` § Related Files
  drops the "Planned (Phase F4)" tag on `register.json.md`.
- `core/scripts/README.md` § Planned scripts removes the
  `validate-state-schema.py` row (the script now exists).

**Consumer rollout.** `crew:status` Step 2.5 (new in F4) prefers
register.json for `current_phase`, `approval_status`, and
`verification_status` when present; falls back to the existing
`result.md` grep + `pipeline.json` parsing for pre-F4 task
directories. No user action required.

### Phase G6 — Forbid plain-text approval (hook_system implemented)

A new `PostToolUse[Agent]` hook blocks free-text yes/no approval
prompts ("Shall I merge?" / "...진행할까요?") with an exit-2 stderr
message fed back to the model. Implements refactor item 6 and flips
the Claude adapter's `hook_system` capability flag from `false` to
`true`.

**No migration code required.** Pure additive:

- New file `core/scripts/check-plaintext-approval.py` — provider-neutral
  validator. Accepts hook-payload JSON on stdin or `--text "..."` for
  diagnostic invocation. Exit 0 = clean, exit 2 = violation. Patterns
  cover the common English modal phrasings (Shall I / Should I / Do
  you want me to / Would you like me to / May I / Can I) and Korean
  equivalents (할까요? / 해드릴까요? / 진행할까요? / 해도 될까요? /
  해도 되나요?). The "Can I help" greeting-style is excluded as a
  guarded false-positive.
- New file `core/hooks/forbid-plaintext-approval.sh` — claude-style
  shell wrapper that forwards hook input to the validator. Resolves
  the validator from `${AGENT_CREW_HOME}/scripts/` first, then
  `${AGENT_CREW_HOME}/system/scripts/` (compat alias). Silent no-op
  when the validator is absent.
- `adapters/claude/setup.sh` registers the hook via the same
  `settings.json` merge pattern as `cost-tracker.sh`. Matcher:
  `"Agent"`. Timeout: 5s.
- `adapters/claude/setup.sh` capabilities.json now advertises
  `"hook_system": true`.

**Validator semantics.**

- Hook fires on every `Agent` (Task) tool completion.
- Exit 2 + stderr → claude surfaces the message to the assistant on
  the next turn. The model receives clear feedback about which phrase
  violated and which rule it broke (`core/rules/disambiguation.md`).
- Non-Agent tool calls are filtered out (`--tool Agent` default).
- Empty payloads and unknown tool_response shapes silently exit 0.

**Storage impact.** None — the hook adds ~1 KB to settings.json (one
hook entry).

**False-positive risk.** The patterns deliberately require both
modal-verb prefix AND a literal question mark, so prose that merely
references the rule (e.g., a doc explaining "Shall I merge?-style
prompts are forbidden") matches the regex but is an accepted false
positive at PostToolUse — the hook fires after agent completion, so
flagging the agent for quoting the rule in its response is a
reasonable nudge.

**Adapters without `hook_system=true`.** codex and generic adapters
continue to rely on model-side guidance documented in their
`SKILL.md` / `invocation.md`. The validator script remains usable
standalone for diagnostic checks (`check-plaintext-approval.py --text
"..."`).

**Update steps.** The standard category sync in § Execution copies
`core/scripts/` and `core/hooks/` into both `system/` and the compat
alias. After updating, run `crew:setup` (or `adapters/claude/setup.sh`
directly) so the new hook gets registered in
`~/.claude/settings.json`.

### Phase J13 — Pipeline telemetry aggregator

A read-only aggregator surfaces per-task wall-clock duration, stage
and retry counts, and token totals across recent runs. Exposed as
`crew:telemetry`. Provider-neutral — no capability flag gates the
command.

**No migration code required.** Pure additive:

- New file `core/scripts/telemetry-aggregate.py` — walks
  `${STATE_DIR}/tasks/*/register.json`,
  `${STATE_DIR}/tasks/*/progress.buffer.jsonl`, and
  `${STATE_DIR}/cost/*.jsonl`. Computes per-task metrics +
  aggregate summary. `--format text|json`. Selectors: `--task-id`,
  `--session-id`, `--recent N`, `--since/--until YYYY-MM-DD`.
- New file `core/commands/telemetry.md` — thin slash-command wrapper
  that picks the right invocation.

**Read-only.** The aggregator never mutates state. It reads existing
JSONL buffers and JSON snapshots written by the supervisor; the
report is computed on every invocation.

**Absence tolerance.** Three independent data sources per task:

- `register.json` — Phase F4. Missing → status/phase/blockers shown
  as `—`.
- `progress.buffer.jsonl` — Phase F5. Missing → duration/stage/retry
  shown as `—`.
- `${STATE_DIR}/cost/${TASK_ID}.jsonl` — Phase 3.3 + Claude host.
  Missing → tokens shown as `—`.

Pre-F4/F5 task directories render partial data gracefully. The
script never errors on absence.

**Storage impact.** None — the aggregator is a script, not a state
file. No new directories under `${STATE_DIR}`.

**Update steps.** The standard category sync in § Execution copies
`core/scripts/` and `core/commands/` into both `system/` and the
compat alias. The new `crew:telemetry` slash command is discoverable
immediately after the next refresh.

### Phase I11 — Per-stage wall-clock timeout (opt-in)

The supervisor's Stage Retry Rule now consults a per-stage wall-clock
budget read from `AGENT_CREW_STAGE_TIMEOUT_SECONDS`. When the env var
is unset or `0` (the default), behavior is identical to pre-I11. When
set to a positive integer, the supervisor halts with
`STATUS: blocked` + `BLOCKER: stage_timeout` if any single stage
(including all its retries) exceeds the budget.

**No migration code required.** Pure additive:

- `supervisor-bootstrap.md` Phase 0 resolves `STAGE_TIMEOUT_SECONDS`
  from the env var; `0` is the absence-tolerant default.
- `supervisor-stages.md` Phase 2 stage loop records
  `STAGE_START_EPOCH` once per stage (not per parallel agent — the
  budget applies to the slowest agent in the stage).
- `supervisor-retry.md` Stage Retry Rule runs a timeout check before
  every invoke-agent call, mirroring the Cost Circuit Breaker
  pattern. Hard stop skips BLOCKED Recovery for the same reason cost
  overruns do (escalation, not retry, is the correct response).
- `supervisor.md` Event catalog gains `STAGE_TIMEOUT` so
  `progress.buffer.jsonl` and `crew:status` surface the event.
- `register.json.blocked_by` records `["stage_timeout"]` for
  programmatic detection without parsing `result.md`.

**No new capability flag.** Stage timeout is host-agnostic. Adapters
do nothing.

**No `settings.json` changes.** No hook is added.

**Recommended values.**

- `AGENT_CREW_STAGE_TIMEOUT_SECONDS=1800` (30 min): conservative
  default for most projects; catches genuinely hung stages without
  false-positives on long legitimate work.
- `AGENT_CREW_STAGE_TIMEOUT_SECONDS=3600` (60 min): for projects
  with heavy analysis or large refactors.
- Unset or `0`: disabled — recommended for one-off / exploratory
  runs where the operator is watching live.

**Interaction with the cost circuit breaker.** Both run at the same
checkpoint (before every invoke-agent call). If both budgets are
exceeded in the same iteration, the cost breaker fires first and
`blocked_by` records `["cost_budget_exceeded"]`. To record both,
extend the env vars and let the natural order play out.

**Update steps.** No category changes — all edits land in existing
files. After `crew:update` picks up the new supervisor sub-modules,
set the env var to opt in.

### Phase J14 — Autonomous task injection (inject-intent detection)

`crew:run` Step 1.5 now classifies the user's input for unambiguous
inject-intent phrasing and auto-routes to the injection path when a
phrase matches AND a session is live. Skips the structured
user-choice prompt when the intent is clear.

**No migration code required.** Pure additive:

- New file `core/scripts/detect-inject-intent.sh` — bash classifier
  (POSIX grep, no Python). Reads user input on stdin, returns exit 0
  + the matched phrase when a Korean or English inject-intent pattern
  matches; exit 1 otherwise.
- `core/commands/run.md` Step 1.5 gains an "inject-intent detection"
  sub-step that runs the classifier when `IS_LIVE_SESSION == 1` and
  short-circuits to the injection path when `INJECT_INTENT` is
  non-empty. An `[crew] INJECT_AUTO | matched=... | session=...`
  notice is emitted so operators can see why the prompt was skipped.

**Patterns covered.**

| Lang | Phrases |
|---|---|
| Korean | `추가로 해줘` / `이것도 부탁해` / `더해줘` / `이어서 해줘` / `추가로 작업해줘` / `이것까지` / `추가로 처리해줘` / `이것도 해줘` / `추가로 부탁` |
| English | `Also do ...` / `And also` / `Additionally` / `One more thing` / `While you're at it` / `Plus do` |

The classifier is **conservative by design** — incomplete connectors
like `also implement X` or `추가 feature` do NOT match. False
negatives fall through to the existing structured user-choice
prompt; false positives would silently route a fresh task into a
live session, which is harder to recover from.

**No new capability flag.** Inject-intent detection runs inline in
`crew:run`; works on every adapter regardless of `hook_system`.

**No `settings.json` changes.** No hook is registered.

**Interaction with the existing routing matrix.**

| Live session | `--inject` flag | `INJECT_INTENT` | Behavior |
|---|---|---|---|
| 0 (no) | any | any | Proceed to Step 2 (fresh run) |
| 1 (yes) | set | any | Inject (explicit flag wins) |
| 1 (yes) | unset | non-empty | Inject (auto-detected, no prompt) — Phase J14 |
| 1 (yes) | unset | empty | Structured prompt (existing behavior) |

**Update steps.** The standard category sync in § Execution copies
`core/scripts/` so the classifier is installed automatically. After
the next `crew:update`, supported inject-intent phrases route
autonomously without any operator action.

### Issue 21 — `cp -f` replaces Read/Write/Edit for idempotent file sync

**Problem.** Step 3 previously instructed the AI to use the Read/Write/Edit tools
for copying source files to install destinations. Unlike `cp -f`, the Edit tool
performs diff-based updates that can preserve or augment destination content not
present in the source. This broke idempotency: a second `crew:update` run could
produce installed agent files larger than the source (observed: `supervisor-retry.md`
and `supervisor-stages.md` contained fan-out prerequisite content added by a prior
Edit-based update run).

**Fix.** Step 3 now instructs the AI to use `cp -f` / `cp -rf` (Bash) for all file
categories. `cp -f` unconditionally replaces the destination with the source byte-for-byte,
so every `crew:update` run leaves installed files identical to their source counterparts.
The Read/Write/Edit tools are explicitly forbidden for file-copying operations.

**Safety Guarantees updated.** The idempotency guarantee in § Safety Guarantees is now
stated precisely: a second run always produces files byte-for-byte identical to source.

**No migration code required.** This is a fix to the update procedure itself, not a
schema or file-structure change. Existing installations that ran the old Edit-based step
may have over-sized agent files; running `crew:update` after this fix corrects them on
the next run.

### Phase L15 — Output language rule

Adds the explicit counterpart to the long-standing Korean Input
Normalization rule (`core/rules/korean-input.md`). User-facing output
now has a documented contract: it should match the user's input
language (Claude does this naturally), while structured status tokens
remain English as a parser invariant.

**No migration code required.** Pure documentation:

- New file `core/rules/output-language.md` codifies the input/output
  language split, lists the English-only status invariant
  (`STATUS: completed`, `REVIEW: APPROVED`, `PLAN:`, `BLOCKER:`, etc.),
  and notes the specialist-agent exception (e.g., `learning-mentor`).
- `core/global-agents.md` gains an Output Language section that
  pairs the two rules.
- `core/agents/supervisor.md` Absolute Rules adds the English-only
  status keyword invariant — explicit so localized status tokens
  don't silently misparse into the crash-retry path.
- `core/hooks/agent-diff-post.sh` header comment translated to
  English for parity with peer hooks.
- `README.md` Key Features gains a "Bilingual input + localized
  output" bullet.

**No new capability flag.** Output language is host-agnostic and
follows the AI's natural response language.

**No `settings.json` changes.** No hook is registered.

**Why an invariant on status keywords?** The supervisor's
stage-result parser uses regex against literal English tokens. If an
agent localizes the keyword (`상태: 완료` instead of
`STATUS: completed`), the parser classifies the response as a crash
and burns the Stage Retry Rule budget. The fix is to document the
expectation, not to teach the parser every language's keyword
variants.

**Update steps.** The standard category sync in § Execution copies
`core/rules/` so the new file installs automatically. No `crew:setup`
re-run required.

### Phase L16 — System/user skill layer classification

Skills now have a formal system/user layer structure mirroring the agent
layer. The source-of-truth location `core/agents/skills/` is unchanged;
the new infrastructure adds install destinations and a discovery merge path.

**Directory layout after this phase:**

| Path | Purpose |
|---|---|
| `core/agents/skills/*.md` | Source repo — system skill definitions |
| `~/.agent-crew/system/skills/` | System skill install destination (synced from source; always replaced) |
| `~/.agent-crew/user/skills/` | User skill layer (custom / override skills; never overwritten by crew:update) |
| `~/.agent-crew/skills/` | Unified discovery path (system + user merged; user wins on name conflict) |
| `~/.claude/agent-crew/skills/` | Claude mirror of the unified discovery path |

**Precedence:** when the same filename exists in both `system/skills/` and
`user/skills/`, the user copy wins in the merged `~/.agent-crew/skills/`
view. Unlike the agent layer (which warns on conflict), the skill layer
treats user-overriding-system as a first-class workflow — useful for
tailoring skill guidance without forking the repo.

**No breaking changes.** Existing agent references to skills via relative
paths inside agent `.md` files are unaffected. The skill files themselves
are unchanged; only the install machinery is new.

**crew:update steps.** Two new functions in `core/setup/common.sh`:
- `sync_system_skills` — prunes stale system skills and copies new/updated
  ones from source; never touches `user/skills/`.
- `merge_skills_to_discovery` — merges system + user skills with user-wins
  precedence into `~/.agent-crew/skills/` (the unified discovery path).

**crew:setup / adapters/claude/setup.sh changes.** On install and update:
- Creates `~/.agent-crew/system/skills/`, `~/.agent-crew/user/skills/`,
  `~/.agent-crew/skills/`, and `~/.claude/agent-crew/skills/`.
- Writes a `~/.agent-crew/user/skills/README.md` placeholder (if absent).
- Runs `sync_system_skills` + `merge_skills_to_discovery` + mirror copy.

**No migration code required.** Pure additive — no files are removed from
existing installations. The new directories are created with `mkdir -p`
(idempotent). Existing skill references in agent prompts continue to work
as before.

### Phase L17 — Instruction SSOT via mnemos

Adds the canonical AI-instruction store and a marker-based sync tool.
Host AI md files (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`,
`~/.agent-crew/AGENTS.md`, plus the in-repo `core/global-agents.md`
rendered fallback) are now assembled from mnemos global-layer items
tagged `instruction-rule`. Edits flow through `mnemos capture --layer
global --id <id>` instead of N-way manual file edits.

**No migration code required.** Pure additive:

- New files `core/scripts/seed-instruction-rules.sh` and
  `core/scripts/sync-instructions.sh` arrive through the standard
  `core/scripts/` category sync.
- New `core/commands/sync-instructions.md` registers the
  `crew:sync-instructions` slash command for manual / dry-run use.
- The existing `<!-- agent-crew-start -->` / `<!-- agent-crew-end -->`
  markers are reused — no host-file marker rewrite is required on
  upgrade.
- `core/global-agents.md` is now overwritten by the sync tool on every
  `--apply` run. The repo-tracked version is the rendered output of
  the seed-script-defined rule bodies, so any drift between the
  bodies inside `seed-instruction-rules.sh` and the file is corrected
  automatically when `crew:update` runs.
- See `core/docs/ssot-design.md` for architecture and
  `core/rules/instruction-rules-schema.md` for the rule schema.

**No new capability flag.** The sync tool detects mnemos's presence
at runtime and short-circuits gracefully when absent (logs a one-line
notice and leaves host files untouched).

**Failure tolerance.** Step 7 of § Execution wraps both calls in
`|| true` so a mnemos hiccup never fails the broader update flow.
Host files in their pre-update state remain valid (the marker block
content from the prior sync remains correct guidance).

### Issue 26 — mnemos search: strip frontmatter + exclude MEMORY.md index

**Problem.** `mnemos search` surfaced raw YAML frontmatter blocks (the
`---\nname: ...\n---` source-file metadata) and `MEMORY.md` auto-generated
link-list index entries as search hits, hiding the actual captured insight
bodies.  The noise-to-signal ratio was high enough that meaningful content was
routinely missed.

**Root cause (two independent issues).**

1. `core/fts.py` — `FTSIndex.index_item()` stored the full raw content of a
   memory file including the YAML frontmatter block.  FTS snippets shown by
   `mnemos search` therefore started with `---\nkey: val\n---` instead of the
   insight body.

2. `agents/scanner.py` — `ClaudeMdScanner.discover_memory_files()` included
   every `*.md` file under `~/.claude/projects/*/memory/`, including the
   auto-generated `MEMORY.md` index file.  That file is a link list, not a
   content document; it polluted every search that touched ingested memories.

**Fix (in mnemos companion package).**

- `core/fts.py`: Added `_strip_frontmatter()` (regex-based, zero new
  dependencies) and called it in `index_item()` before storing content in the
  FTS database.
- `agents/scanner.py`: `discover_memory_files()` now skips any file whose
  name (case-insensitively) equals `MEMORY.MD`.

**agent-crew migration action (Step 3.8 of § Execution).**

Because the FTS database was populated before the fix, existing entries
contain stale frontmatter-polluted content.  Step 3.8 runs `mnemos
ingest-claude-md --quiet` to rebuild the FTS index with clean data.  This is
idempotent — unchanged files are skipped after the first rebuild.

**Tests.**

`tests/shell/test_mnemos_search_filter.bash` covers the expected behaviour with
a mock mnemos stub (no real installation required):
- MEMORY.md (upper- and lowercase) is excluded from ingest.
- Inner frontmatter is stripped before storage.
- Search returns the meaningful insight body, not YAML key-value lines.
- Search for MEMORY.md-sourced content returns zero results.

**No capability flag.** The fix is entirely in mnemos and the FTS rebuild step;
no `capabilities.json` change is required.

**No `settings.json` changes.** No new hook is registered.

## Completion Message

```text
agent-crew updated.
Source : {SOURCE_DIR}
Install: ~/.agent-crew  (and ~/.claude/agent-crew when claude adapter active)

Usage:
  crew:run "request"    # business as usual
```
