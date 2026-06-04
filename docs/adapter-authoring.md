# Adapter Authoring Guide

This guide is for anyone writing a new host adapter for `agent-crew` —
a binding from a specific AI agent host (Claude Code, Codex, Cursor,
Aider, a future host) to the provider-neutral core.

If you can answer "yes" to all of these, you're ready to start:

- You have a target host whose CLI / IDE / agent loop you understand.
- You can write `bash` + a little `python3`.
- You're comfortable reading the existing three adapters
  (`adapters/claude/`, `adapters/codex/`, `adapters/generic/`) as
  reference implementations.

## What an adapter does

`agent-crew` separates **what** the system does (provider-neutral, in
`core/`) from **how** it does it on a specific host (host-specific, in
`adapters/{host}/`). An adapter is responsible for three things:

1. **Detect** that the current environment is the host it claims to
   serve.
2. **Install** host-specific files (slash commands, hook registrations,
   agent configs in the host's preferred format) and **declare** which
   capabilities the host exposes via `capabilities.json`.
3. **Bind** abstract core intents (`askQuestion`, `spawnBackgroundAgent`,
   `interactive_question` UX, etc.) to the host's native tool names or
   conventions.

The core never names a host tool. The adapter is the only place where
host-specific identifiers appear.

## The Three Invariants (read these first)

See `core/rules/host-capabilities.md` for the canonical statement.
Summarized:

1. **Core never calls host-specific tools directly.** Every
   host-specific call sits behind a capability flag with a
   working fallback.
2. **Adding or claiming a capability requires four things:**
   (a) the capability doc under `core/rules/capabilities/{flag}.md`
   already exists, (b) any provider-neutral logic lives in
   `core/scripts/`, (c) your adapter implements the surface OR
   advertises absence, (d) the registry in `core/rules/host-capabilities.md`
   names the flag.
3. **Core markdown never names host tool identifiers.** The mapping
   from abstract intent ("ask the user a structured question") to
   host tool name lives in your adapter's `invocation.md`.

Your adapter exists to satisfy these invariants, not to circumvent them.

## Required directory layout

```
adapters/{your-host}/
├── detect.sh        # required — host self-detection (exit 0 = match)
├── setup.sh         # required — install/sync, writes capabilities.json
└── invocation.md    # required — host-specific behavior rules
```

Optional, depending on host:

```
adapters/{your-host}/
├── skill/           # if host has a skill / extension format
│   └── agent-crew/SKILL.md
└── template/        # if host needs per-host file templates
    └── agents/      # e.g. Codex uses TOML; this dir holds *.toml
```

Naming: lowercase, no spaces, no special characters. Match the host's
canonical short name (e.g., `claude`, `codex`, `cursor`).

## File-by-file contract

### `detect.sh`

A bash script that exits `0` if the current environment is your host,
non-zero otherwise. Keep it side-effect-free — environment-variable
checks only, no network calls, no spawning processes.

```bash
#!/usr/bin/env bash
set -euo pipefail

# Claude example
[ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_SESSION_ID:-}" ]
```

The dispatcher (`core/setup/setup-host.sh`) calls every adapter's
`detect.sh` in turn; the first one that exits 0 wins. Order is not
guaranteed, so make your detection **specific** — match a variable or
file unique to your host.

The `generic` adapter intentionally has `exit 0` as its detection (it
matches everything) and is alphabetically last; treat it as the
universal fallback.

### `setup.sh`

A bash script that:

1. Sources `${AGENT_CREW_HOME}/setup/common.sh` for shared helpers.
2. Honors `AGENT_CREW_MODE` (`install` or `update`) — the only
   difference is logging; the copy operations themselves are idempotent.
3. Copies core directories (`commands`, `hooks`, `rules`, `scripts`,
   `schemas`, `setup`, optionally `agents`) into the host's expected
   paths. `schemas/` was added in Phase F4 — see
   `core/rules/state-files/` for the per-file documentation.
4. Writes `${STATE_DIR}/capabilities.json` declaring which capability
   flags this host supports (see "Declaring capabilities" below).
5. Optionally registers hooks into the host's lifecycle mechanism
   (Claude's `settings.json`, etc.).

Skeleton:

```bash
#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
AGENT_CREW_MODE="${AGENT_CREW_MODE:-install}"

. "${AGENT_CREW_HOME}/setup/common.sh"

if [ "${AGENT_CREW_MODE}" = "update" ]; then
  printf 'MODE: update (host=your-host)\n'
fi

# 1. Copy core assets into your host's expected paths
HOST_DIR="${PROJECT_ROOT}/.your-host"
mkdir -p "${HOST_DIR}"
copy_dir_contents "${AGENT_CREW_HOME}/commands" "${HOST_DIR}/commands"
copy_dir_contents "${AGENT_CREW_HOME}/hooks"    "${HOST_DIR}/hooks"
copy_dir_contents "${AGENT_CREW_HOME}/rules"    "${HOST_DIR}/rules"
copy_dir_contents "${AGENT_CREW_HOME}/scripts"  "${HOST_DIR}/scripts"
copy_dir_contents "${AGENT_CREW_HOME}/schemas"  "${HOST_DIR}/schemas"

# 2. Write capabilities.json
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --ensure \
  --migrate-legacy \
  --format shell)"
cat > "${STATE_DIR}/capabilities.json" <<EOF
{
  "host":                 "your-host",
  "task_tools":           false,
  "agent_background":     false,
  "monitor_tool":         false,
  "cost_tracking":        false,
  "hook_system":          false,
  "interactive_question": false
}
EOF
printf 'CAPABILITIES: %s\n' "${STATE_DIR}/capabilities.json"

# 3. (Optional) register hooks into host's mechanism
# ...
```

### `invocation.md`

A markdown document the host's model reads at session start. It tells
the model:

- The canonical prompt workflow notation (`crew:<intent>`), distinct from the
  native CLI forms (`crew run`, `crew agent`, and other space-separated
  `crew` commands).
- Host-specific aliases or slash-command bindings (if any).
- **The mapping from abstract capability intents to host tool names.**

Example skeleton:

```markdown
# {Your-Host} Invocation Guide

Use the canonical `crew:<intent>` workflow notation in prompts:

\`\`\`text
crew:setup
crew:run "request"
crew:run "TaskA" | "TaskB"
crew:cost
crew:agent-maker
\`\`\`

## Capability mappings

When core emits a logical intent, your host fulfills it as follows:

| Intent (from core) | Host mechanism |
|---|---|
| `askQuestion(prompt, options)` | <your host's structured prompt tool, or "emit markdown options"> |
| `spawnBackgroundAgent(...)` | <your host's bg agent surface, or "inline only"> |
| `createTask(...)` / `updateTask(...)` | <your host's task surface, or "file-based only"> |
```

The mapping section is what enables Invariant 3 — core never names your
tools; `invocation.md` does.

## Declaring capabilities

Six runtime flags are defined in `capabilities.json`, plus one
install-time capability that adapters honor via `setup.sh` only. For
each, decide: does my host expose the required surface (see
`core/rules/capabilities/{flag}.md`)?

| Flag | Kind | If true, host must provide... | If false, fallback... |
|---|---|---|---|
| `task_tools` | runtime | `createTask`/`listTasks`/`getTask`/`updateTask` quartet | `pipeline.json` + 5-second `approval.md` poll |
| `agent_background` | runtime | `spawnBackgroundAgent` + concurrent-safe execution | Inline parallel within one turn |
| `monitor_tool` | runtime | `streamOutput` or `getOutputTail` | `tail -20 progress.log` |
| `cost_tracking` | runtime | Some way to report per-call token totals | No cost data; quality-loop uses retry-count only |
| `hook_system` | runtime | PreToolUse / PostToolUse hook registration | Model-side guidance only |
| `interactive_question` | runtime | `askQuestion(prompt, options) -> chosen` | Structured markdown prompt; model interprets reply |
| `reasoning_tier` | install-time | `setup.sh` materializes the abstract tier (`deep`/`balanced`/`light`) to a concrete host model identifier | Single-model environment — tier hint is advisory only |

**You MUST only declare `true` for capabilities your host genuinely
exposes.** Declaring `true` falsely will break core's gated paths.

The `generic` adapter omits `capabilities.json` entirely; the
absence-contract treats every flag as `false`. That is the floor of
what works.

`reasoning_tier` does NOT appear in `capabilities.json`. It is honored
by your `setup.sh` only — the materializer block writes per-agent
model identifiers into your host's preferred format (e.g., the Claude
adapter rewrites the `model:` frontmatter; the Codex adapter sets a
TOML field). See `core/rules/capabilities/reasoning-tier.md`.

## Wiring core/scripts/

`core/scripts/` holds provider-neutral logic (validators, classifiers,
aggregators) that ANY host can invoke. See `core/scripts/README.md` for
the contract.

How your adapter wires them depends on `hook_system`:

| `hook_system` | Wiring approach |
|---|---|
| `true`  | Your `setup.sh` registers the scripts as PreToolUse / PostToolUse hooks via the host's registration mechanism. Hooks invoke `core/scripts/check-*.py` directly. The Claude adapter's setup.sh is the reference — see its `cost-tracker.sh` and `forbid-plaintext-approval.sh` registration blocks. |
| `false` | Your `invocation.md` (or `skill/SKILL.md`) instructs the model: "before invoking X, run `core/scripts/check-Y.sh` and respect its exit code." Best-effort enforcement. The scripts remain runnable standalone for diagnostic use (`check-plaintext-approval.py --text "..."`). |

Either way, the scripts themselves don't change. Provider-neutrality is
the point.

## Reference implementations

Read these in order — they illustrate three different host integration
shapes:

1. **`adapters/claude/`** — full feature set. As of Phase G6, five of
   the six runtime flags are `true`: `task_tools`, `agent_background`,
   `monitor_tool`, `cost_tracking`, `hook_system`. Only
   `interactive_question` remains `false` (uses the structured-markdown
   fallback). Reasoning-tier is materialized at install time. Read this
   to see what "everything wired" looks like.
2. **`adapters/codex/`** — partial feature set. `task_tools`,
   `agent_background`, `monitor_tool`, `hook_system` are `false`;
   `interactive_question` defaults to the markdown fallback. Uses
   `SKILL.md` for model-side rules instead of OS-level hooks. Read
   this to see how to fall back gracefully on a less-capable host.
3. **`adapters/generic/`** — minimum viable adapter. Omits
   `capabilities.json` entirely (absence-contract treats every flag
   as `false`). Detect script is `exit 0` (last-resort fallback).
   Copies core assets to `.agent-crew/` in the project root. Read this
   to see the smallest possible adapter.

> If your adapter ships custom agent files (e.g., a host-specific
> variant of `supervisor` or `backend`), follow the prompt-cache tier
> convention documented in `docs/cache-tier-convention.md` so the
> agent's prompt benefits from cache-prefix matching across
> invocations.

## Step-by-step: writing a new adapter

1. **Pick a name.** Lowercase, no spaces. Use the host's canonical
   short name.

2. **Create the directory and the three required files.**

   ```
   mkdir adapters/your-host
   cp adapters/generic/detect.sh adapters/your-host/detect.sh
   cp adapters/generic/setup.sh  adapters/your-host/setup.sh
   touch adapters/your-host/invocation.md
   chmod +x adapters/your-host/{detect,setup}.sh
   ```

3. **Edit `detect.sh`** to match your host's signature env var or file.

4. **Edit `setup.sh`** to:
   - Copy core directories to your host's expected layout.
   - Write `capabilities.json` declaring your starting flags (probably
     all `false` initially).
   - (Optional) wire hooks if `hook_system=true`.

5. **Write `invocation.md`** with the canonical command form and the
   capability mappings (even if every flag is currently `false` — the
   mapping for `interactive_question` falls back to "emit markdown
   options" but should be stated explicitly).

6. **Test detection** by setting your host's signature env var and
   running:

   ```
   AGENT_CREW_HOST=auto bash core/setup/setup-host.sh /tmp/test-project
   ```

   Confirm your `setup.sh` ran. Then test forced mode:

   ```
   AGENT_CREW_HOST=your-host bash core/setup/setup-host.sh /tmp/test-project
   ```

7. **Test the absence path.** Set every capability flag to `false`,
   confirm `crew:run "test task"` still completes via fallbacks. This
   is the floor for any adapter.

8. **Incrementally turn flags on** as you implement each capability.
   For each flag flipped to `true`:
   - Re-read `core/rules/capabilities/{flag}.md` and confirm your
     adapter satisfies the Required Adapter Surface.
   - Add a row to the Adapter Examples table in that capability doc.
   - Update your `invocation.md` mapping section to name the
     host-specific tool that fulfills the contract.

9. **Update the host-capabilities registry** at
   `core/rules/host-capabilities.md` if your adapter introduces a flag
   that doesn't exist yet (rare — most new adapters consume existing
   flags). Adding a new flag triggers the four-piece set in
   Invariant 2.

10. **Submit.** A PR adding a new adapter should include:
    - The three required files
    - Adapter Examples row in each affected capability doc
    - An entry under "Reference implementations" in this guide if your
      adapter is a notable third shape (most won't be — claude/codex/
      generic already cover the main shapes)

## Testing checklist before merge

Run these manually before requesting review:

- [ ] `detect.sh` exits 0 only when your host is the active environment.
- [ ] `detect.sh` does not have side effects (no file writes, no
      network).
- [ ] `setup.sh` runs cleanly in both `install` and `update` modes
      (`AGENT_CREW_MODE=update bash adapters/your-host/setup.sh ...`).
- [ ] `setup.sh` is idempotent — running it twice produces the same
      result.
- [ ] `capabilities.json` is written with only flags your host truly
      supports as `true`.
- [ ] `crew:run "simple task"` completes end-to-end with every flag set
      to `false` (the absence-fallback floor).
- [ ] `crew:status` reads task state correctly via fallbacks.
- [ ] For every flag your adapter declares `true`, the Adapter Examples
      table in the corresponding capability doc has a row describing
      your implementation.
- [ ] `invocation.md` includes the capability mapping section.
- [ ] No host-specific tool names appear in any file under `core/`
      (run `grep -rn "{your-tool-name}" core/` to confirm — should
      return zero hits).

## When to deviate from this guide

Don't, in the structure of the three required files. Do, in:

- **Additional optional directories** (`skill/`, `template/`, etc.) —
  fine, host-specific.
- **Wrapping the absence fallback for a flag-false case** — you may
  add a small `setup.sh` helper that writes the markdown fallback for
  `interactive_question=false`, for example.
- **Host-specific hook integration** — Claude uses `settings.json`,
  Codex uses `SKILL.md` — your host may use neither. As long as the
  effect is "validator runs at the right lifecycle moment, exit code
  is respected," the mechanism is yours.

## Getting help

- Read the existing three adapters' source first.
- Each capability has a detailed contract in
  `core/rules/capabilities/{flag}.md`.
- The Three Invariants are non-negotiable; if your design appears to
  require violating one, the design needs revising — not the invariants.
