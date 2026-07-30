# crew:run - Unified Task Orchestration

Run one or more tasks through the same execution engine.
Every task is executed by a `supervisor`. A single request spawns one
`supervisor`; multiple requests spawn multiple `supervisor` agents.

`crew:run` is the canonical workflow entry point.

```text
[orchestrator] crew:run "Task A" | "Task B" | "Task C"
      |
      v
normalize the input into one or more task entries
      |
      v
classify trivial intent (Step 1.7) ──► trivial?
      |                                   |
      | no                                | yes
      v                                   v
prepare one execution context per task   inline dispatch
      |                                  (status / commit /
      v                                   merge / push / deploy /
delegate one supervisor per task         tag / rollback) with
      |                                   interactive-question approval gate
      v                                   for destructive ops
collect results and provide merge guidance
```

## Core Principle

The orchestration engine should not run planner, designer, backend, or frontend
stages directly. It should always delegate a full task to `supervisor`.

This gives single-task and multi-task execution the same engine:

- Single request -> one `supervisor`
- Multiple requests -> multiple `supervisor` agents

## Lean Workflow Contract

Apply `core/rules/lean-workflow-methodology.md` as the shared lightweight
methodology for this command. In particular:

- Keep this command as a thin harness: route, normalize, prepare state, and
  delegate.
- Follow the public phase vocabulary `Align -> Plan -> Execute/TDD -> Review`
  without duplicating the full methodology here.
- Enforce Workflow Origin vs Target Scope: a workflow command token is the origin, not the target artifact, unless the user explicitly names the command,
  wrapper, file, or `SKILL.md` as the review target.
- Pass large artifacts by path and surface concrete gaps rather than asking
  agents to manufacture proof artifacts.

## Parallel-First Rule

**Always prefer parallel fan-out over sequential execution.**

File overlap between parallel tasks is not a reason to serialize. If parallel
supervisors modify the same file, merge conflicts are resolved by the
**resolver agent** after all runners complete — that is its explicit purpose.

Sequential execution (`N == 1`) is only correct when tasks have a true
dependency (Task B cannot start until Task A's output exists).

```
# Correct — parallel even if tasks touch the same files
crew:run "Fix bug A" | "Fix bug B"

# Wrong — serializing to avoid a conflict the resolver handles
crew:run "Fix bug A"   # then wait...
crew:run "Fix bug B"
```

## Execution Steps

### 0. Auto-sync Installed Commands

> **This step runs before all other steps and is silent on success.** It ensures
> the installed commands under `~/.agent-crew/commands/` and `~/.claude/commands/`
> are always in sync with the source repository. This prevents stale command
> definitions (the root cause of injection detection failures when source commands
> are updated but installed copies are not refreshed).

Resolve the source repository once:

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"

# Resolve the local source checkout only when this repo is already present.
# crew:update no longer records a persistent source path, so this step now
# skips by default in installed environments.
SOURCE_ROOT=""
_TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
if [ -d "${_TOPLEVEL}/core" ] && [ -d "${_TOPLEVEL}/adapters" ]; then
  SOURCE_ROOT="${_TOPLEVEL}"
fi
```

If `SOURCE_ROOT` resolves and `${SOURCE_ROOT}/core/commands/` exists, sync system
command files to the installed system and discovery locations. User command
seeds from `${SOURCE_ROOT}/core/user/commands/` sync only to the user/discovery
command locations, never to `system/commands`.

```bash
if [ -n "${SOURCE_ROOT}" ] && [ -d "${SOURCE_ROOT}/core/commands" ]; then
  # Sync commands: source → system layer (canonical installed copy)
  cp "${SOURCE_ROOT}/core/commands/"*.md "${AGENT_CREW_HOME}/system/commands/" 2>/dev/null || true
  # Sync commands: source → compat alias (backward-compatible path)
  cp "${SOURCE_ROOT}/core/commands/"*.md "${AGENT_CREW_HOME}/commands/" 2>/dev/null || true
  # Sync user command seeds: source → user/discovery paths only.
  mkdir -p "${AGENT_CREW_HOME}/user/commands"
  for _cmd in "${SOURCE_ROOT}/core/user/commands/"*.md; do
    [ -f "${_cmd}" ] || continue
    [ -f "${AGENT_CREW_HOME}/user/commands/$(basename "${_cmd}")" ] \
      || cp "${_cmd}" "${AGENT_CREW_HOME}/user/commands/" 2>/dev/null || true
    cp "${_cmd}" "${AGENT_CREW_HOME}/commands/" 2>/dev/null || true
  done
  # Sync commands: source → Claude namespaced slash-command path (/crew:<intent>)
  mkdir -p "${CLAUDE_DIR}/commands/crew"
  rm -f \
    "${CLAUDE_DIR}/commands/agent-maker.md" \
    "${CLAUDE_DIR}/commands/agent.md" \
    "${CLAUDE_DIR}/commands/cost.md" \
    "${CLAUDE_DIR}/commands/evolve.md" \
    "${CLAUDE_DIR}/commands/interact.md" \
    "${CLAUDE_DIR}/commands/relay.md" \
    "${CLAUDE_DIR}/commands/run.md" \
    "${CLAUDE_DIR}/commands/sessions.md" \
    "${CLAUDE_DIR}/commands/setup.md" \
    "${CLAUDE_DIR}/commands/smm.md" \
    "${CLAUDE_DIR}/commands/status.md" \
    "${CLAUDE_DIR}/commands/sync-instructions.md" \
    "${CLAUDE_DIR}/commands/task.md" \
    "${CLAUDE_DIR}/commands/telemetry.md" \
    "${CLAUDE_DIR}/commands/update.md" \
    "${CLAUDE_DIR}/commands/workflow.md" \
    2>/dev/null || true
  cp "${SOURCE_ROOT}/core/commands/"*.md "${CLAUDE_DIR}/commands/crew/" 2>/dev/null || true
  cp "${SOURCE_ROOT}/core/user/commands/"*.md "${CLAUDE_DIR}/commands/" 2>/dev/null || true
fi

# Also sync rules (session protocol references core/rules/task-injection.md).
# Stale rules do not break execution but may cause agent confusion.
if [ -n "${SOURCE_ROOT}" ] && [ -d "${SOURCE_ROOT}/core/rules" ]; then
  cp "${SOURCE_ROOT}/core/rules/"*.md "${AGENT_CREW_HOME}/system/rules/" 2>/dev/null || true
  cp "${SOURCE_ROOT}/core/rules/"*.md "${AGENT_CREW_HOME}/rules/" 2>/dev/null || true
fi

# Sync helper scripts used by command definitions. Commands must not point at
# stale or missing helpers after Step 0 refreshes the prompt definition.
if [ -n "${SOURCE_ROOT}" ] && [ -d "${SOURCE_ROOT}/core/scripts" ]; then
  mkdir -p "${AGENT_CREW_HOME}/system/scripts" "${AGENT_CREW_HOME}/scripts"
  cp "${SOURCE_ROOT}/core/scripts/"*.py "${AGENT_CREW_HOME}/system/scripts/" 2>/dev/null || true
  cp "${SOURCE_ROOT}/core/scripts/"*.py "${AGENT_CREW_HOME}/scripts/" 2>/dev/null || true
  cp "${SOURCE_ROOT}/core/scripts/"*.sh "${AGENT_CREW_HOME}/system/scripts/" 2>/dev/null || true
  cp "${SOURCE_ROOT}/core/scripts/"*.sh "${AGENT_CREW_HOME}/scripts/" 2>/dev/null || true
  chmod +x "${AGENT_CREW_HOME}/system/scripts/"*.py "${AGENT_CREW_HOME}/scripts/"*.py \
    "${AGENT_CREW_HOME}/system/scripts/"*.sh "${AGENT_CREW_HOME}/scripts/"*.sh \
    2>/dev/null || true
fi

# Sync hooks as runtime behavior, not just install-time templates. Stale
# auto-route hooks can keep injecting old STOP/ROUTE directives after source
# fixes land.
if [ -n "${SOURCE_ROOT}" ] && [ -d "${SOURCE_ROOT}/core/hooks" ]; then
  mkdir -p "${AGENT_CREW_HOME}/system/hooks" "${AGENT_CREW_HOME}/hooks"
  cp "${SOURCE_ROOT}/core/hooks/"*.sh "${AGENT_CREW_HOME}/system/hooks/" 2>/dev/null || true
  cp "${SOURCE_ROOT}/core/hooks/"*.sh "${AGENT_CREW_HOME}/hooks/" 2>/dev/null || true
  chmod +x "${AGENT_CREW_HOME}/system/hooks/"*.sh "${AGENT_CREW_HOME}/hooks/"*.sh \
    2>/dev/null || true
fi
```

**Silent on success**: this step emits nothing when the sync completes normally.
If `SOURCE_ROOT` cannot be resolved (e.g., the agent-crew source repo is not
present on this machine), skip this step entirely and proceed to Step 1. The
absence of a source root is not an error — the installed commands may already
be current from the last `crew:update` run.

> **Note**: This step updates command, rule, script, and hook payload files. It
> does NOT re-run hook registration, agent discovery merge, or any other install side-effect.
> For a full refresh of all assets, run `crew:update` explicitly.

### 0b. Warn on Project-Local Update Drift

Before creating task state, check whether global installed assets are newer
than the current project's local adapter files. This warning is advisory and
must not block task creation.

```bash
python3 "${AGENT_CREW_HOME}/scripts/update-project-registry.py" \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  check-stale \
  --project-root "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" \
  --format text || true
```

If stale, print the compact warning and continue. The operator can run
`crew update` in the current project or `crew update --all-projects` to refresh
registered project-local adapter files.

---

### 1. Collect Tasks

Use provided arguments as task descriptions. If none are provided, ask through
the host AI tool's structured input UI.

Accept:

- One task: `crew:run "implement order API"`
- Multiple tasks: `crew:run "Order API" | "Product API" | "User API"`
- Injecting into a live run: `crew:run --inject "new task"` (see Step 1.5)

Preserve each input task verbatim with cardinality `N >= 1`. Do not translate
Korean or other non-English task text to English before planning, handoff, or
agent execution. The exact user text is the canonical downstream task text.

#### Issue Comment Ingestion

If the task references a GitHub issue, read the issue body and all
non-minimized comments before planning or implementation. Treat later comments
as potential requirement updates. If comments contradict the body, surface the
contradiction before implementation.

Record ingestion evidence in task context before planning:

```text
comments_ingested: true
comment_count: {N}
latest_comment_at: {timestamp}
comment_derived_requirements: [...]
```

The native helper is:

```bash
crew issue-ingest ISSUE_NUMBER --task-id TASK_ID --repo OWNER/REPO
```

### 1.5. Injection Detection

> **This step runs after Step 1 input normalization and before Step 2 state
> initialization.** It detects whether a live parallel session is already
> running for this project, and if so, routes the new task as an injection
> into that session instead of starting a fresh run.

#### What is task injection?

Task injection allows a user to submit new tasks while an existing `crew:run`
parallel fan-out is still in progress. Injected tasks join the live session:
they get their own TASK_ID, TASK_DIR, git worktree, and supervisor, and they
participate in the final result collection, resolver, and approval gates
alongside the original tasks.

The canonical reference for the injection protocol is
`core/rules/task-injection.md`.

#### Operator-facing brevity

When Step 1.5 or Step 1.6 detects active work, keep default output short:
include the session id, task id, current status/phase, and one next command
when available. Reserve policy detail, duplicate rationale, stale-session
diagnostics, and full workflow narration for explicit verbose or
troubleshooting requests.

#### Live session detection

Check whether an active parallel session exists by looking for a `session.json`
file in the project's state directory:

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --prefer-existing-legacy \
  --format shell)"
SESSION_FILE="${STATE_DIR}/session.json"
```

**Setup guard (pre-injection)**: Before reading `session.json`, verify that the
project has been initialized. If either `STATE_DIR` does not exist or
`capabilities.json` is absent inside it, stop immediately and display this error
(no silent failure — host adapter implementations MUST surface both lines verbatim):

```text
Error: Project '{PROJECT_NAME}' is not initialized.
Run crew:setup first to initialize the workspace.
```

The `{PROJECT_NAME}` placeholder resolves to display metadata from the bash
block above. `STATE_DIR` resolves through `PROJECT_STATE_KEY` so duplicate
project basenames do not collide. The guard is expressed as:

```bash
CAPABILITIES_FILE="${STATE_DIR}/capabilities.json"
if [ ! -d "${STATE_DIR}" ] || [ ! -f "${CAPABILITIES_FILE}" ]; then
  printf 'Error: Project '\''%s'\'' is not initialized.\nRun crew:setup first to initialize the workspace.\n' \
    "${PROJECT_NAME}"
  return 1 2>/dev/null || exit 1
fi
```

A **live session** is one where `session.json` exists AND its `status` field
is `"running"`:

```bash
IS_LIVE_SESSION=$(python3 -c "
import json, sys
try:
    s = json.load(open('${SESSION_FILE}'))
    print('1' if s.get('status') == 'running' else '0')
except Exception:
    print('0')
" 2>/dev/null)
```

#### Inject-intent detection (Phase J14)

Before the prompt-based fallback below fires, classify the user's
input for autonomous inject-intent. Patterns like "추가로 해줘",
"이것도 부탁해", "더해줘", "Also do ...", "While you're at it ..."
are unambiguous signals that the user wants to ADD to the live
session, not start a fresh one. When detected, skip the user
prompt entirely and proceed straight to the injection execution
path.

```bash
INJECT_INTENT=""
if [ "${IS_LIVE_SESSION}" = "1" ]; then
  INJECT_INTENT=$(printf '%s' "${USER_INPUT}" \
    | bash "${AGENT_CREW_HOME}/scripts/detect-inject-intent.sh" 2>/dev/null) \
    || INJECT_INTENT=""
fi
```

When `INJECT_INTENT` is non-empty, the system treats it as an
implicit `--inject` flag. The routing matrix below short-circuits to
the injection path without prompting the user.

The detector is intentionally conservative — phrases like "also
implement X" or "추가 feature" (incomplete connectors) do NOT match,
so a user describing a fresh task is not auto-routed into the live
session. When in doubt, the routing falls through to the structured
user-choice prompt below.

#### Injection routing

**If `IS_LIVE_SESSION == 0`:** No live session. Proceed normally to Step 2.

**If `IS_LIVE_SESSION == 1` AND (the `--inject` flag was passed OR
`INJECT_INTENT` is non-empty):** A live session exists and the user
either explicitly requested injection or used unambiguous inject-intent
phrasing (Phase J14). Route the new task(s) as injections (see
injection execution path below). When auto-detected via
`INJECT_INTENT`, emit a notice so the operator can see why the prompt
was skipped:

```bash
if [ -z "${INJECT_FLAG:-}" ] && [ -n "${INJECT_INTENT}" ]; then
  printf '[crew] INJECT_AUTO | matched=%q | session=%s\n' \
    "${INJECT_INTENT}" "${SESSION_ID}" >&2
fi
```

**If `IS_LIVE_SESSION == 1` AND N == 1 AND neither `--inject` nor
`INJECT_INTENT` is set:** A live session exists but the user did not
explicitly request injection and the phrasing is ambiguous. Ask via
the host's interactive question mechanism (see
`core/rules/capabilities/interactive-question.md`) before deciding:

```text
# Structured user-choice intent (host-bound — see
# core/rules/capabilities/interactive-question.md):
ask_question:
  header: "Live Session"
  question: "A background session ({SESSION_ID}) is running. Join it or start independently?"
  options:
    - label: "Inject into session"
      description: "Add this task to the running pipeline (spawns background runner, returns immediately)"
    - label: "Run independently"
      description: "Start a fresh run in this session (inline, not background)"
```

- **Inject into session**: follow the injection execution path below.
- **Run independently**: proceed normally to Step 2 as a fresh N=1 run
  (inline mode — supervisor runs in the current turn, not as a background agent).

**If `IS_LIVE_SESSION == 1` AND N > 1 AND neither `--inject` nor
`INJECT_INTENT` is set:** A live session exists, but the user submitted
multiple tasks without an explicit inject flag and the phrasing is
ambiguous. Ask the user to clarify:

```text
# Structured user-choice intent (host-bound — see
# core/rules/capabilities/interactive-question.md):
ask_question:
  header: "Live Session Detected"
  question: "A parallel crew:run session (ID: {SESSION_ID}) is already running.
             Do you want to inject these {N} new tasks into the live session,
             or start a completely separate new run?"
  options:
    - label: "Inject into live session"
      description: "Add these tasks to the running pipeline"
    - label: "Start new separate run"
      description: "Begin an independent parallel run (creates a new session)"
```

- **Inject**: follow the injection execution path below.
- **New run**: proceed normally to Step 2 with a new `SESSION_ID`.

#### Injection execution path

When injection is chosen (regardless of whether triggered by `--inject`, the N==1
prompt, or the N>1 prompt):

1. Read the live `SESSION_ID` from `session.json`:

   ```bash
   SESSION_ID=$(python3 -c "
   import json
   s = json.load(open('${SESSION_FILE}'))
   print(s['session_id'])
   " 2>/dev/null)
   ```

2. Emit an injection notice:

   ```
   [crew] INJECT | session={SESSION_ID} | {N} new task(s) joining live run
   ```

3. For each new task, generate a new `TASK_ID`, `TASK_DIR`, `BRANCH`, and
   worktree — identical to Step 4. Skip Step 2 and Step 3 (no resume
   detection for injected tasks). Proceed directly to Step 5 (requirements)
   and then Step 6 (supervisor spawn as background agent).

4. After spawning the injected supervisor(s), register each into
   `session.json` by appending to its `tasks` array:

   ```bash
   python3 -c "
   import json, re
   def _task_hash(t):
       h = re.sub(r'\s+', ' ', t).strip().lower()
       h = re.sub(r'[.,;:!?]+\$', '', h)
       return h
   s = json.load(open('${SESSION_FILE}'))
   s['tasks'].append({
       'task_id': '${TASK_ID}',
       'task_dir': '${TASK_DIR}',
       'branch': '${BRANCH}',
       'task': '${TASK}',
       'task_hash': _task_hash('${TASK}'),
       'status': 'running',
       'injected': True
   })
   json.dump(s, open('${SESSION_FILE}', 'w'), ensure_ascii=False, indent=2)
   "
   ```

5. Print the injection summary and **RETURN immediately** (end the turn).
   Do NOT enter any poll loop. The background supervisor(s) will run
   autonomously; use `crew:status` to monitor progress or
   `crew:status --collect` to wait for results.

   ```
   [crew] INJECT | session={SESSION_ID} | {N} task(s) spawned as background agent(s)
   Task(s) registered: {TASK_ID_1}, {TASK_ID_2}, ...
   Monitor with: crew:status
   Collect when done: crew:status --collect
   ```

6. **Do not start a new orchestrator.** The injected tasks run as independent
   background agents and are collected by `crew:status --collect`.

#### Injection guard

The injection path MUST NOT be entered when:
- The detected session's `status` is `"completed"` or `"blocked"` (stale file).
- The `SESSION_FILE` is older than 24 hours (likely abandoned).
- The project has no `STATE_DIR` (setup not run).

Stale-session check:

```bash
python3 -c "
import json, os, time, sys
try:
    path = '${SESSION_FILE}'
    s = json.load(open(path))
    age = time.time() - os.path.getmtime(path)
    if s.get('status') != 'running' or age > 86400:
        print('stale')
    else:
        print('live')
except Exception:
    print('absent')
" 2>/dev/null
```

If `stale` or `absent`: treat `IS_LIVE_SESSION == 0` and proceed to Step 1.6.

### 1.6. Duplicate Task Detection

> **This step runs after Step 1.5 (Injection Detection) and before Step
> 1.7 (Fast-Path Intent Classification). It only runs when
> `IS_LIVE_SESSION == 1`. If Step 1.5 already routed into the injection
> path or determined the session is stale/absent, skip this step
> entirely.**
>
> **Goal**: detect when the user is re-issuing a task that is already in
> flight in the live session, and route the decision to the user via the
> host's interactive question mechanism instead of silently spawning a
> duplicate.

#### When this step runs

The duplicate check runs only when **all** of the following are true:

1. Step 1.5 detected a live session (`IS_LIVE_SESSION == 1`).
2. Step 1.5 did NOT route to the injection path (the user chose "Run
   independently" or "Start new separate run", or `--inject` was not
   used and the user is being prompted for routing).
3. The normalized session's `tasks[]` array contains at least one entry
   whose `status` is `"running"` AND whose `task_hash` matches the
   normalized form of the new task.

The normalization algorithm matches `core/rules/task-injection.md` (see
the `task_hash` field documentation):

```bash
NEW_HASH=$(python3 -c "
import re, sys
t = sys.argv[1]
h = re.sub(r'\s+', ' ', t).strip().lower()
h = re.sub(r'[.,;:!?]+$', '', h)
print(h)
" "${TASK}")
```

#### Detect a duplicate

```bash
DUPLICATE_TASK_ID=$(python3 -c "
import json, sys
try:
    s = json.load(open('${SESSION_FILE}'))
    target = '${NEW_HASH}'
    for t in s.get('tasks', []):
        if t.get('status') != 'running':
            continue
        if not t.get('task_hash'):
            # Pre-B0 entry with no task_hash — cannot compare, treat as unique.
            continue
        if t['task_hash'] == target:
            print(t['task_id'])
            break
except Exception:
    pass
" 2>/dev/null)
```

**If `DUPLICATE_TASK_ID` is empty**, no duplicate. Proceed to Step 1.7.

#### Route through interactive question (per disambiguation rule)

When a duplicate is detected, route via the host's interactive question
mechanism (see `core/rules/capabilities/interactive-question.md`) per
the disambiguation rule (see `core/rules/disambiguation.md`). Heuristic
auto-decision is forbidden — the user must choose.

```text
# Structured user-choice intent (host-bound — see
# core/rules/capabilities/interactive-question.md):
ask_question:
  header: "Duplicate Task"
  question: "A task with the same description is already running in session
             {SESSION_ID} (task id {DUPLICATE_TASK_ID}). What would you like
             to do?"
  options:
    - label: "Show in-flight status"
      description: "Display the running task's current phase / stage progress;
                    do not spawn a new task."
    - label: "Start as a new task anyway"
      description: "Spawn a new supervisor for this description; the two
                    will run in parallel under the same session."
    - label: "Cancel"
      description: "Abort this crew:run invocation; the running task
                    continues untouched."
```

#### Resolution

- **Show in-flight status**: tail the duplicate task's `progress.log`
  inline (`tail -20 "${SESSION_TASK_DIR}/progress.log"` where
  `${SESSION_TASK_DIR}` is the duplicate entry's `task_dir`), then **STOP
  — end the turn**. Do NOT proceed to Step 2.

- **Start as a new task anyway**: cache the decision (write a sentinel
  file `${STATE_DIR}/dedup-override.txt` containing the new task's hash
  and the current timestamp), then proceed normally to Step 1.7. If the
  user re-runs the exact same `crew:run` within 60 seconds, Step 1.6
  reads the sentinel and skips the prompt — the decision is sticky to
  avoid double-prompting on retry. The sentinel is purged after first
  read.

- **Cancel**: print `Cancelled — no task spawned.` and **STOP**. The
  in-flight task continues running untouched.

#### Backward compatibility

When the live `session.json` was created by a pre-B0 run, none of its
`tasks[]` entries have a `task_hash` field. In that case the detector
loop above finds zero matches (each missing field is skipped) and
execution proceeds to Step 1.7 — the user is never prompted spuriously.
This is intentional: dedup is best-effort, and a pre-B0 session simply
lacks the metadata to support it.

### 1.7. Fast-Path Intent Classification

> **This step runs after Step 1.5 (Injection Detection) and before Step 2 (State
> Init). It detects trivial operational intents — merge, push, deploy, tag,
> rollback, status, commit-only — and dispatches them through the
> orchestrator turn, bypassing requirements / analyst / planner / supervisor /
> stage agents / reviewer entirely.**
>
> **Goal**: reduce a "merge and push" run from 2–5 minutes to under 30 seconds.

#### When the fast path runs

The fast path runs only when **all** of the following are true:

1. `N == 1` (exactly one task — the fast path does not apply to parallel runs).
2. The Step 1.5 injection detector returned `IS_LIVE_SESSION == 0`. If a live
   parallel session is running, the user's intent is to inject — that takes
   precedence over local fast-path dispatch.
3. The normalized TASK string matches one of the trivial-intent patterns below
   AND none of the exclusion phrases are present (see "Negative-match
   disambiguation").
4. The host advertises `interactive_question = true` in capabilities.json OR
   the active adapter has a conditional native mapping available in the current
   session (for example Codex Plan mode `request_user_input`). This is required
   for destructive intents — see
   `core/rules/capabilities/interactive-question.md`. When the flag is false,
   no conditional surface is available, or the capability is absent,
   destructive fast-path intents fall through to the regular pipeline; the
   read-only `status` and non-destructive `commit_only` paths still run inline.

If any of the above is false, **skip this step entirely and proceed to Step 2
unchanged.** The fast path is purely additive — it never breaks the existing
pipeline contract.

> **Step 5 Exception (explicit).** The framework's standing "NEVER-SKIP" rule
> on Step 5 (Collect Requirements) does not apply when the Step 1.7 classifier
> matches a trivial intent. The whole point of the fast path is to skip
> requirements collection, the analyst, the planner, the supervisor spawn, and
> the reviewer for operational requests that have no requirements to collect.
> Step 5 remains mandatory for every request that falls through to Step 2.

#### Trivial-intent patterns

The classifier inspects the normalized TASK string (lowercased, trimmed). It
uses simple shell regex — no Python, no ML, no parsing — so it adds at most a
few milliseconds of overhead even on the fall-through path.

```bash
classify_trivial_intent() {
  # $1 = normalized TASK string
  local task_lc
  task_lc=$(printf "%s" "$1" | tr '[:upper:]' '[:lower:]' | tr -s ' ')

  # --- Unambiguous operational prefixes (checked first, override negative-match) ---
  # These start with "git ..." or other explicit operational phrasing that no
  # implementation request would ever use. They short-circuit before the
  # negative-match keyword filter below.
  case "$task_lc" in
    "git status"|"git push"|"git push "*|"git commit"|"git commit "*|\
    "git add"|"git add "*|"git tag"|"git tag "*|"git merge"|"git merge "*|\
    "git revert"|"git revert "*)
      # Fall through to the per-intent dispatch below — we just want to bypass
      # the negative-match for these explicit git commands.
      ;;
    "create tag"|"create tag "*)
      printf "tag\n"; return
      ;;
    "push to origin"|"push to remote"|*" push to origin"*|*" push to remote"*)
      printf "push\n"; return
      ;;
  esac

  # --- Negative-match disambiguation ---
  # The classifier must distinguish three compound cases when an
  # implementation keyword is present:
  #
  #   (a) impl keyword + NO trivial verb anywhere   → 'none'
  #       Example: "refactor authentication module" → 'none'
  #
  #   (b) impl keyword + trivial verb in the SAME phrase → 'ambiguous'
  #       Example: "push and refactor auth"          → 'ambiguous'
  #       Example: "commit and merge feature X"      → 'ambiguous'
  #       Example: "merge two designs"               → 'ambiguous'
  #
  #   (c) impl keyword + zero compound coordinator   → 'none'
  #       (same as (a); the impl keyword wins.)
  #
  # The 'ambiguous' return is consumed by Step 1.7.5 below, which routes
  # the user through a structured user-choice intent (see
  # `core/rules/disambiguation.md`).

  local has_impl=0
  local has_trivial_verb=0

  case "$task_lc" in
    *" add "*|"add "*|*" implement "*|"implement "*|\
    *" create "*|"create "*|*" build "*|"build "*|\
    *" fix "*|"fix "*|*" refactor "*|"refactor "*|\
    *" remove "*|"remove "*|*" update "*|"update "*|\
    *" change "*|"change "*|*" migrate "*|"migrate "*|\
    *" extend "*|"extend "*|*" integrate "*|"integrate "*|\
    *" replace "*|"replace "*|*" move "*|"move "*)
      has_impl=1
      ;;
  esac

  case "$task_lc" in
    *"merge"*|*"push"*|*"deploy"*|*"release"*|\
    *"tag"*|*"rollback"*|*"revert"*|*"commit"*|*"stage"*)
      has_trivial_verb=1
      ;;
  esac

  if [ "$has_impl" = "1" ] && [ "$has_trivial_verb" = "1" ]; then
    # Compound input — trivial verb mixed with implementation keyword.
    # Cannot decide unilaterally; defer to user choice.
    printf "ambiguous\n"; return
  fi

  if [ "$has_impl" = "1" ]; then
    # Plain implementation request — full pipeline.
    printf "none\n"; return
  fi

  # --- Per-intent classification (only reached after negative-match passes) ---

  # status — "status", "show status", "what changed", "what's changed", "git status"
  case "$task_lc" in
    "status"|"show status"|"what changed"|"whats changed"|"what's changed"|\
    "show me status"|"git status")
      printf "status\n"; return
      ;;
  esac

  # commit-only — bare commit verb with optional message. "stage changes" /
  # "stage" alone also matches. Implementation phrasing was filtered above.
  case "$task_lc" in
    "commit"|"commit "*|"stage"|"stage changes"|"stage "*|\
    "git commit"|"git commit "*|"git add"|"git add "*)
      printf "commit_only\n"; return
      ;;
  esac

  # rollback — "rollback", "revert", "revert last commit", "git revert ..."
  case "$task_lc" in
    "rollback"|"rollback "*|"revert"|"revert "*|*" rollback"|*" revert"|\
    "git revert"|"git revert "*)
      printf "rollback\n"; return
      ;;
  esac

  # tag — "tag", "tag v1.0.0", "git tag ..." (the "create tag" prefix was
  # already handled in the operational-prefix block above).
  case "$task_lc" in
    "tag"|"tag "*|"git tag"|"git tag "*)
      printf "tag\n"; return
      ;;
  esac

  # push — "push", "push <branch>", "git push ..." (the "push to origin"
  # phrase was already handled in the operational-prefix block above).
  case "$task_lc" in
    "push"|"push "*|"git push"|"git push "*)
      printf "push\n"; return
      ;;
  esac

  # deploy — "deploy", "release", "deploy to {env}", "release v1.0"
  case "$task_lc" in
    "deploy"|"deploy "*|"release"|"release "*|*" deploy "*|*" release "*)
      printf "deploy\n"; return
      ;;
  esac

  # merge — requires branch context to disambiguate from "merge two refactors"
  # or "merge data structures". Must contain "branch", "into main", "into
  # master", a literal feat/fix/docs/refactor/test/chore/* branch pattern, or
  # be the explicit "git merge ..." form.
  case "$task_lc" in
    "merge"|"merge "*|"git merge"|"git merge "*)
      case "$task_lc" in
        *"branch"*|*"into main"*|*"into master"*|\
        *"feat/"*|*"fix/"*|*"docs/"*|*"refactor/"*|*"test/"*|*"chore/"*|\
        "git merge "*)
          printf "merge\n"; return
          ;;
      esac
      ;;
  esac

  printf "none\n"
}

INTENT=$(classify_trivial_intent "${TASK}")
```

The function returns one of:

| Returned token | Meaning |
|---|---|
| `merge`        | Merge a feature branch into main (destructive — needs approval) |
| `push`         | Push current branch / main to origin (destructive — needs approval) |
| `deploy`       | Run deployment script / release flow (destructive — needs approval) |
| `tag`          | Create or push a git tag (destructive — needs approval) |
| `rollback`     | Revert the last commit or roll back a deploy (destructive — needs approval) |
| `status`       | Show repo state inline (read-only — no approval) |
| `commit_only`  | Commit current diff through `git-committer`; never direct shell commit |
| `ambiguous`    | Compound input mixes a trivial verb with implementation phrasing — route to a structured user-choice intent (see Step 1.7.5) |
| `none`         | Not a trivial intent — fall through to Step 2 |

#### Dispatch table

When `INTENT != "none"`, dispatch inline. **No supervisor is spawned. No
`TASK_DIR` is created. No `pipeline.json`, `progress.log`, `result.md`,
worktree, or branch is created** (the destructive intents operate on the
current branch / HEAD only).

##### `status` — inline read-only summary

```bash
echo "### 🔍 Repo Status"
echo
echo "\`\`\`"
echo "Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
echo
echo "Working tree:"
git status --short 2>/dev/null | head -20 | sed 's/^/  /'
echo
echo "Recent commits:"
git log --oneline -5 2>/dev/null | sed 's/^/  /'
echo "\`\`\`"
```

Then **STOP — end the turn**. Do not proceed to Step 2.

##### `commit_only` — git-committer mediated commit

Commit-only requests are local git mutations. They are not allowed to run a
raw shell commit path from `crew:run`, even when the request appears trivial.
If the `git-committer` user agent is installed and its trigger matches, the
orchestrator must select it before any commit or amend command mutates history.

Required dispatch record before mutation:

```text
{TASK_DIR}/context/specialist-dispatch.md
selected_agent: supervisor
selected_handler: vcs.commit.message.compose=git-committer
selected_handler: vcs.history.local_mutation=git-committer
selection_reason: commit request / commit checkpoint
execution_mode: fast-path commit intent
```

Commit flow:

1. Resolve commit mode: `apply-new` for commit/stage requests, `apply-amend`
   for amend/reword requests, or `recommend` for message-only requests.
2. Pass branch context, issue refs, staged/unstaged diff summary, and the raw
   user intent to `git-committer`.
3. Display the proposed message and apply it only through the orchestrator-owned
   structured approval/mutation path used by `crew:commit`.
4. Record final audit fields in task context when available: selected commit
   agent, candidate message source, final commit subject, convention match
   result, and completed capability handler results. The completion record is
   provider-agnostic coverage, not the sole proof of execution; for example:

   ```json
   {
     "handler_results": [
       {
         "capability": "vcs.commit.message.compose",
         "handler": "git-committer",
         "state": "completed",
         "artifact": "context/git-committer-result.md"
       },
       {
         "capability": "vcs.history.local_mutation",
         "handler": "git-committer",
         "state": "completed",
         "artifact": "context/git-committer-result.md"
       }
     ]
   }
   ```

   Store that payload at `{TASK_DIR}/context/handler-results.json` or one JSON
   file per capability under `{TASK_DIR}/context/capabilities/` when the handler
   produces it.

If no task context exists yet, create one before continuing. If no commit
message capability provider is installed, fall through to the regular
supervisor workflow instead of inventing an ad hoc commit message.
Completion/repair for a current-session fallback reports missing commit
capability selection or completion as advisory coverage gaps instead of forcing
separate proof-artifact files. Selected handler fields are audit metadata; they
are not proof that the selected handler ran to completion.

Then **STOP — end the turn** after the commit agent workflow completes or the
request is explicitly cancelled.

##### Destructive intents (`merge` / `push` / `deploy` / `tag` / `rollback`)

For destructive intents, the orchestrator owns the approval gate per CLAUDE.md
Approval Rule. The flow is:

1. **Compose a PLAN summary** describing the exact git command that will run.
   The PLAN is shown inline as text — there is no `action-plan.md` file
   because no stage agent is waiting on `approval.md`. Example:

   ```text
   ### 🎯 Fast-Path Action Plan

   \`\`\`
   Intent     : push
   Command    : git push origin {BRANCH}
   Risk       : medium
   Reversible : no (remote receives commits)

   Current branch : {BRANCH}
   Commits        :
     {git log --oneline @{u}..HEAD 2>/dev/null || git log --oneline -3}
   \`\`\`
   ```

2. **Emit a structured user-choice intent** (per
   `core/rules/capabilities/interactive-question.md`) — the single, structured
   approval gate. Plain-text approval is forbidden per CLAUDE.md.

   - header: short intent label ("Push", "Merge", "Deploy", "Tag", "Rollback")
   - question: "Review the fast-path action plan above. Approve to run the
     command now, or cancel to hold."
   - options:
     - label: "Approve" — description: "Run the command now"
     - label: "Cancel"  — description: "Hold, do not run anything"

3. **On Approve**: execute the git command inline (see per-intent commands
   below). Print the result. Then **STOP — end the turn**.

4. **On Cancel**: print "Cancelled — no action taken." Then **STOP**.

Per-intent commands (executed inline only after Approve):

| Intent | Command |
|---|---|
| `merge`    | `git checkout main && git merge --no-ff "${SOURCE_BRANCH}" -m "merge: ${SOURCE_BRANCH} into main"` where `${SOURCE_BRANCH}` is the branch token extracted from TASK (the first `feat/...` / `fix/...` / etc. pattern, or the branch named after "branch" / "into main"). When no branch is identified, prompt via the host's interactive question mechanism (see `core/rules/capabilities/interactive-question.md`) for the branch name before composing the PLAN. |
| `push`     | `git push origin "$(git rev-parse --abbrev-ref HEAD)"` for a feature branch, or `git push origin main` when the current branch is `main`. The PLAN line names the exact branch. |
| `deploy`   | Defer to the project's deploy script when one is recorded. When none is recorded, fall through to the regular pipeline — the fast path does not invent deploy commands. |
| `tag`      | `git tag "${TAG_NAME}" && git push origin "${TAG_NAME}"` where `${TAG_NAME}` is extracted from TASK (e.g. `tag v1.0.0` → `v1.0.0`). When the tag name is missing, prompt via the host's interactive question mechanism (see `core/rules/capabilities/interactive-question.md`) before composing the PLAN. |
| `rollback` | `git revert --no-edit HEAD` for "rollback" / "revert last commit". For broader rollback intents (revert deploy, reset to tag), fall through to the regular pipeline. |

#### What the fast path bypasses

- Step 2 (state init) — no `STATE_DIR` / `TASK_DIR` / branch / worktree created
- Step 3 (resume detection) — no resume state to track for stateless ops
- Step 4 (task context) — no per-task setup
- Step 5 (requirements collection) — see Step 5 Exception above
- Step 6 (supervisor spawn) — no subagent spawned at all
- Inside the supervisor: analyst, planner, stage agents (designer, backend,
  frontend, devops, reviewer), Phase 1d plan approval, Phase 2.5 stage action
  gate — none of these run because no supervisor is spawned

#### What the fast path still honors

- Korean Input Normalization (Step 1)
- Injection Detection (Step 1.5) — runs first, so trivial intents submitted
  during a live parallel session inject correctly instead of fast-pathing
- Centralized Approval Gate (CLAUDE.md Approval Rule) — destructive intents
  pass through the host's interactive question mechanism (see
  `core/rules/capabilities/interactive-question.md`) exactly as the framework
  requires
- "supervisor never pushes" rule — the fast path is the orchestrator, not the
  supervisor, so it is allowed to push after approval (per Steps 10–11)

#### Fall-through

When `INTENT == "none"`, this step is silent. Proceed to Step 1.7.5 (which
is also a no-op for `none`) and then Step 2 with no behavioral change. The
classifier overhead is a single shell function call with a handful of
`case` branches, so the fall-through cost is negligible.

### 1.7.5. Ambiguous Intent Dispatch

> **This step runs only when `INTENT == "ambiguous"` from Step 1.7.** It
> routes the user through a structured user-choice intent (see
> `core/rules/disambiguation.md` and
> `core/rules/capabilities/interactive-question.md`) to resolve compound
> phrasings such as `push and refactor auth` or `commit and merge` where
> a trivial verb is mixed with implementation phrasing.

#### Cache check (avoid re-prompting on retry)

The dispatcher caches the user's choice keyed by the TASK string's
`task_hash` (same normalization as Step 1.6) under
`${STATE_DIR}/ambiguous-cache.json`. Each entry maps a hash to the
chosen interpretation (`"trivial:{intent}"`, `"full"`, or `"cancel"`)
with a 60-minute TTL.

```bash
mkdir -p "${STATE_DIR}"
CACHE_FILE="${STATE_DIR}/ambiguous-cache.json"
NEW_HASH=$(python3 -c "
import re, sys
t = sys.argv[1]
h = re.sub(r'\s+', ' ', t).strip().lower()
h = re.sub(r'[.,;:!?]+$', '', h)
print(h)
" "${TASK}")

CACHED=$(python3 -c "
import json, os, time
try:
    c = json.load(open('${CACHE_FILE}'))
    e = c.get('${NEW_HASH}')
    if e and (time.time() - e.get('ts', 0)) < 3600:
        print(e['choice'])
except Exception:
    pass
" 2>/dev/null)
```

If `CACHED` is non-empty, skip the prompt and apply the cached choice.

#### Compose the question

Inspect the matched verbs to populate the option labels. The trivial
candidate is the *strongest* match (the verb whose unambiguous form is
closest in the input).

```text
# Structured user-choice intent (host-bound — see
# core/rules/capabilities/interactive-question.md):
ask_question:
  header: "Ambiguous Intent"
  question: "Your request mixes a trivial git operation ({trivial_candidate})
             with implementation phrasing. How should I interpret it?"
  options:
    - label: "Treat as trivial: {trivial_candidate}"
      description: "Dispatch as a fast-path {trivial_candidate} (status,
                    commit, push, etc.); do not spawn a supervisor."
    - label: "Treat as a full development task"
      description: "Run the regular pipeline (analyst → planner → stages →
                    reviewer)."
    - label: "Cancel and rephrase"
      description: "Abort; let me re-issue crew:run with clearer phrasing."
```

#### Resolution

- **Treat as trivial**: cache `"trivial:{intent}"` and re-enter the Step
  1.7 dispatch table with `INTENT = {trivial_candidate}`. The
  destructive-intent approval gate still runs.
- **Treat as a full development task**: cache `"full"` and proceed to
  Step 2 with `INTENT = "none"`.
- **Cancel and rephrase**: cache `"cancel"`, print `Cancelled — please
  re-issue with clearer phrasing.`, and **STOP — end the turn**.

#### Cache write

After the user resolves the question, persist the decision:

```bash
python3 -c "
import json, os, time
try:
    c = json.load(open('${CACHE_FILE}'))
except Exception:
    c = {}
c['${NEW_HASH}'] = {'choice': '${CHOICE}', 'ts': time.time()}
json.dump(c, open('${CACHE_FILE}', 'w'), ensure_ascii=False, indent=2)
"
```

The cache TTL is intentionally short (60 minutes) — a phrasing the user
re-issues hours later may have a different intent.

#### Fall-through

When `INTENT == "none"`, this step is a no-op. Proceed to Step 2.

### 2. Initialize State Paths

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --ensure \
  --migrate-legacy \
  --format shell)"
```

If `STATE_DIR` does not exist **or** `${STATE_DIR}/capabilities.json` does not
exist, stop immediately and display this error to the user (no silent failure —
host adapter implementations MUST surface both lines verbatim):

```text
Error: Project '{PROJECT_NAME}' is not initialized.
Run crew:setup first to initialize the workspace.
```

The `{PROJECT_NAME}` placeholder resolves to display metadata from the bash
block above; `STATE_DIR` uses `PROJECT_STATE_KEY`.

The check covers two distinct failure modes:

- `STATE_DIR` absent — `crew:setup` was never run for this project.
- `STATE_DIR` present but `capabilities.json` absent — `crew:setup` was interrupted
  or only partially completed (e.g., `mkdir` ran but the adapter install did not).

Both conditions indicate an unconfigured project and must produce the same error.
A `capabilities.json` that exists but is empty or unparseable is treated as
configured (the supervisor falls back to all-false flags — this is expected
behaviour for minimal setups, not an error).

If `capabilities.json` declares a different host than the active adapter, the
runtime MUST refresh the active host adapter before continuing. This prevents a
shared workspace initialized under Claude from being reused by Codex with stale
Claude capability flags.

Current host resolution:

```bash
CURRENT_HOST="${AGENT_CREW_HOST:-auto}"
if [ "${CURRENT_HOST}" = "auto" ]; then
  if [ -n "${CODEX:-}${CODEX_CI:-}${CODEX_THREAD_ID:-}${CODEX_MANAGED_BY_NPM:-}" ]; then
    CURRENT_HOST="codex"
  else
    CURRENT_HOST=""
  fi
fi
```

Host mismatch guard:

```bash
CAPABILITIES_HOST=$(python3 -c "
import json, sys
try:
    print(json.load(open('${CAPABILITIES_FILE}')).get('host', ''))
except Exception:
    print('')
" 2>/dev/null)

if [ -n "${CURRENT_HOST}" ] && [ -n "${CAPABILITIES_HOST}" ] \
   && [ "${CAPABILITIES_HOST}" != "${CURRENT_HOST}" ]; then
  if [ -x "${AGENT_CREW_HOME}/adapters/${CURRENT_HOST}/setup.sh" ]; then
    AGENT_CREW_HOST="${CURRENT_HOST}" AGENT_CREW_MODE=update \
      bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "${PROJECT_ROOT}"
  else
    printf 'Error: Project '\''%s'\'' capabilities were generated for host '\''%s'\'' but current host is '\''%s'\''.\n' \
      "${PROJECT_NAME}" "${CAPABILITIES_HOST}" "${CURRENT_HOST}"
    printf 'Run crew:setup under the current host to refresh capabilities.json.\n'
    return 1 2>/dev/null || exit 1
  fi
fi
```

The guard is expressed as:

```bash
CAPABILITIES_FILE="${STATE_DIR}/capabilities.json"
if [ ! -d "${STATE_DIR}" ] || [ ! -f "${CAPABILITIES_FILE}" ]; then
  printf 'Error: Project '\''%s'\'' is not initialized.\nRun crew:setup first to initialize the workspace.\n' \
    "${PROJECT_NAME}"
  return 1 2>/dev/null || exit 1
fi
```

Before spawning any supervisor agents, capture the current HEAD:

```bash
PRE_RUN_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")
```

### 3. Resume Detection

If `N > 1`, skip this step entirely — always start a new fan-out run and
proceed directly to Step 4.

If `N == 1`, check for the newest incomplete task under `STATE_DIR/tasks`.
An incomplete task is one that has a `pipeline.json` file but no `result.md`
with `STATUS: completed`.

```bash
# Fast check: find the most recent task directory without a completed result.
# The grep accepts both plain-text ("STATUS: completed") and Markdown-bold
# ("**Status:** completed") for backward compatibility (issue #31).
RESUME_CANDIDATE=$(find "${STATE_DIR}/tasks" -maxdepth 1 -mindepth 1 -type d \
  -exec sh -c '[ -f "$1/pipeline.json" ] && ! grep -qiE "^(\*\*)?status:\*{0,2}\s+\**completed\**" "$1/result.md" 2>/dev/null && echo "$1"' _ {} \; \
  | sort | tail -1)
```

If `RESUME_CANDIDATE` is non-empty, ask whether to resume it or start a new run.

If resuming:

- reuse the existing `TASK_ID`
- reuse the existing `TASK_DIR`
- reuse the recorded branch or worktree metadata if present
- continue through the same `supervisor`

### 4. Prepare Each Task Context

For each task index `i`:

```bash
TASK_ID="$(date +%Y%m%d-%H%M%S)-${i}"
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"

branch_prefix_for_task() {
  python3 - "$1" <<'PYEOF'
import re
import sys

text = sys.argv[1].lower()
words = set(re.findall(r"[a-z0-9]+", text))

rules = [
    ("fix", {"fix", "fixes", "fixed", "bug", "bugs", "repair", "repairs", "broken", "error", "errors", "failing", "failure", "failures", "regression", "regressions"}, ()),
    ("docs", {"doc", "docs", "documentation", "readme", "guide", "guides", "instruction", "instructions", "manual"}, ()),
    ("refactor", {"refactor", "refactors", "refactoring", "restructure", "cleanup", "simplify", "reorganize"}, ("clean up",)),
    ("test", {"test", "tests", "testing", "spec", "specs", "coverage", "qa"}, ()),
    ("chore", {"chore", "chores", "build", "dependency", "dependencies", "deps", "config", "configuration", "setup", "tooling", "maintenance"}, ("continuous integration",)),
]

for prefix, tokens, phrases in rules:
    if words & tokens or any(phrase in text for phrase in phrases):
        print(prefix)
        break
else:
    print("feature")
PYEOF
}

task_slug_for_branch() {
  python3 - "$1" <<'PYEOF'
import re
import sys

text = sys.argv[1].lower()
words = re.findall(r"[a-z0-9]+", text)
stopwords = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "so", "that", "the",
    "to", "with", "instead", "only", "than", "rather"
}
slug_words = [word for word in words if word not in stopwords]
slug = "-".join(slug_words)[:48].strip("-")
print(slug or "task")
PYEOF
}

TASK_SLUG="$(task_slug_for_branch "${TASK}")"
BRANCH_PREFIX="$(branch_prefix_for_task "${TASK}")"
BRANCH="${BRANCH_PREFIX}/${TASK_SLUG}"
```

Branch prefixes must describe the work type rather than defaulting to
`feature/`. Use `fix/` for bug fixes, `docs/` for documentation, `refactor/`
for restructuring without behavior changes, `test/` for test-only work,
`chore/` for maintenance, build, dependency, setup, CI, and tooling work, and
`feat/` for new or improved product behavior. The task slug is derived from the
task description and provides sufficient uniqueness — no TASK_ID suffix is
appended. See `core/rules/branch-naming.md` for the full naming spec.

Execution context depends on cardinality:

- If `N == 1`, **do not create a worktree**. Use the current project worktree
  directly. Create the branch with a regular `git checkout -b ${BRANCH}` only
  (no `git worktree add`). This avoids `git worktree add` latency entirely for
  single-task runs.
- If `N > 1`, create one isolated git worktree per task. **Pre-create all
  worktrees before starting requirements collection** so that I/O-bound worktree
  setup overlaps with the user-facing requirement interview.

Before invoking `git worktree add`, evaluate the worktree lifecycle guards.
These guards keep the harness AI-agnostic (bash + git only) and prevent
nested-worktree, submodule, and untracked-isolation-directory regressions.
The primitives the block uses are:

- `git rev-parse --git-dir` and `git rev-parse --git-common-dir` (Guard 1
  comparison probes — when they differ the caller is in a linked worktree).
- `git rev-parse --show-superproject-working-tree` (Guard 2 submodule probe).
- `git check-ignore -q .crew-worktrees` (Guard 3 ignore verification).

```bash
# Guard 2: Submodule guard
# A submodule context must NOT be classified as "already in a linked worktree"
# in Guard 1. Detect it first so Guard 1 can fall through correctly.
CREW_SUPERPROJECT="$(git -C "${PROJECT_ROOT}" rev-parse --show-superproject-working-tree 2>/dev/null || true)"

# Guard 1: Detect existing isolation (linked-worktree reuse)
# If GIT_DIR and GIT_COMMON_DIR differ AND we are NOT inside a submodule, the
# caller is already in a linked worktree — reuse it and SKIP `git worktree add`.
CREW_GIT_DIR_RAW="$(git -C "${PROJECT_ROOT}" rev-parse --git-dir 2>/dev/null || true)"
CREW_GIT_COMMON_RAW="$(git -C "${PROJECT_ROOT}" rev-parse --git-common-dir 2>/dev/null || true)"
# Normalize relative paths via realpath; fall back to `cd && pwd -P` if realpath
# is unavailable on the host.
crew_realpath() {
  if command -v realpath >/dev/null 2>&1; then
    realpath "$1" 2>/dev/null
  else
    ( cd "$1" 2>/dev/null && pwd -P ) || printf '%s' "$1"
  fi
}
CREW_GIT_DIR="$(crew_realpath "${CREW_GIT_DIR_RAW}")"
CREW_GIT_COMMON="$(crew_realpath "${CREW_GIT_COMMON_RAW}")"

WORKTREE_PATH="${PROJECT_ROOT}/.crew-worktrees/${TASK_ID}"
SKIP_WORKTREE_ADD=0
if [ -z "${CREW_SUPERPROJECT}" ] \
   && [ -n "${CREW_GIT_DIR}" ] \
   && [ -n "${CREW_GIT_COMMON}" ] \
   && [ "${CREW_GIT_DIR}" != "${CREW_GIT_COMMON}" ]; then
  SKIP_WORKTREE_ADD=1
  WORKTREE_PATH="${PROJECT_ROOT}"
  printf '[crew] worktree-guard 1: already in linked worktree (git-dir=%s common=%s) — reusing %s\n' \
    "${CREW_GIT_DIR}" "${CREW_GIT_COMMON}" "${WORKTREE_PATH}"
fi

# Guard 3: Ignore verification
# `.crew-worktrees/` MUST be git-ignored before any `git worktree add`, so the
# harness's per-task isolation directory never bleeds into commits.
if [ "${SKIP_WORKTREE_ADD}" -eq 0 ]; then
  if ! git -C "${PROJECT_ROOT}" check-ignore -q .crew-worktrees 2>/dev/null; then
    GITIGNORE_PATH="${PROJECT_ROOT}/.gitignore"
    if ! grep -Fxq '.crew-worktrees/' "${GITIGNORE_PATH}" 2>/dev/null; then
      printf '%s\n' '.crew-worktrees/' >> "${GITIGNORE_PATH}"
    fi
    git -C "${PROJECT_ROOT}" add .gitignore
    git -C "${PROJECT_ROOT}" commit -m "chore(repo): ignore .crew-worktrees harness directory"
    if ! git -C "${PROJECT_ROOT}" check-ignore -q .crew-worktrees 2>/dev/null; then
      printf '[crew] worktree-guard 3: .crew-worktrees still not ignored after .gitignore update — halting\n' >&2
      exit 1
    fi
  fi
fi

mkdir -p "${TASK_DIR}/context"
if [ "${SKIP_WORKTREE_ADD}" -eq 0 ]; then
  git -C "${PROJECT_ROOT}" worktree add -b "${BRANCH}" "${WORKTREE_PATH}" HEAD
fi
```

The orchestrator owns context preparation only. The execution engine remains the
same in both modes.

After creating the branch/worktree and before requirements collection, write
minimal task metadata plus an initial progress line. This makes `crew:status`
useful even if the host stalls before the supervisor reaches Phase 0:

```bash
mkdir -p "${TASK_DIR}/context"
printf '%s\n' "${TASK}" > "${TASK_DIR}/task.txt"
printf '%s\n' "${BRANCH}" > "${TASK_DIR}/branch.txt"
printf '%s\n' "${PRE_RUN_HEAD}" > "${TASK_DIR}/pre-run-head.txt"
printf '%s\n' "${PROJECT_ROOT_FOR_TASK:-${PROJECT_ROOT}}" > "${TASK_DIR}/project-root.txt"
printf '%s | ORCHESTRATOR_HANDOFF | task context prepared; requirements pending\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${TASK_DIR}/progress.log"
```

When Codex routed the request through a skill wrapper after another explicitly
invoked Codex skill loaded, preserve that context as task metadata. Do not strip
explicit `$skill` mentions or app-provided context from `TASK`; additionally,
when the wrapper provides a `CODEX_SKILL_CONTEXT` string, write it before
requirements collection. Domain-match alone is not approval to auto-load a
non-agent-crew or third-party host/plugin skill:

```bash
if [ -n "${CODEX_SKILL_CONTEXT:-}" ]; then
  printf '%s\n' "${CODEX_SKILL_CONTEXT}" > "${TASK_DIR}/context/codex-skill-context.md"
fi
```

Every later prompt that receives `TASK_DIR` must treat this file, when present,
as part of the user request context.

#### Session Registry Initialization (N > 1 only)

For parallel runs, after all task contexts are prepared, create (or overwrite)
`session.json` in `STATE_DIR`. This file is the canonical registry for all
tasks in the current execution session — including any tasks injected later
via Step 1.5.

```bash
SESSION_ID="$(date +%Y%m%d-%H%M%S)"
SESSION_FILE="${STATE_DIR}/session.json"

python3 -c "
import json, re, sys

def _task_hash(t):
    h = re.sub(r'\s+', ' ', t).strip().lower()
    h = re.sub(r'[.,;:!?]+$', '', h)
    return h

tasks = []
# task_list is a list of dicts with task_id, task_dir, branch, task
for entry in ${TASK_LIST_JSON}:
    tasks.append({
        'task_id': entry['task_id'],
        'task_dir': entry['task_dir'],
        'branch': entry['branch'],
        'task': entry['task'],
        'task_hash': _task_hash(entry['task']),
        'status': 'running',
        'injected': False
    })

session = {
    'session_id': '${SESSION_ID}',
    'status': 'running',
    'pre_run_head': '${PRE_RUN_HEAD}',
    'tasks': tasks
}
json.dump(session, open('${SESSION_FILE}', 'w'), ensure_ascii=False, indent=2)
"
```

Where `${TASK_LIST_JSON}` is a JSON array of `{task_id, task_dir, branch, task}`
built from the task contexts created in this step.

The session file is written atomically before any supervisor is spawned, so
that a concurrent `crew:run --inject` arriving immediately after Step 4 will
see a valid `session.json` with `status: running`.

For single-task runs (`N == 1`), no session file is written — injection requires
a live parallel session and is not meaningful for single-task execution.

### 5.pre — Requirements Sufficiency Check

> **NEVER-SKIP-WITHOUT-SUFFICIENCY-CHECK**: REQUIREMENTS must always be produced
> before Step 6 — but the *agent invocation* itself is now optional. The gate is
> the sufficiency check below, not the agent call. The check returns either
> `SUFFICIENT` (synthesize REQUIREMENTS inline, skip the agent entirely) or
> `AMBIGUOUS` (fall through to Step 5 with a single-round agent invocation).
>
> Step 5 is mandatory for every `crew:run` invocation that reaches it, unless
> (a) Step 1.7 (Fast-Path Intent Classification) classified this as a trivial
> operational intent — in which case the orchestrator has already returned and
> Step 5 is not reached at all — or (b) Step 5.pre's sufficiency check
> synthesized REQUIREMENTS inline, in which case Step 5's agent invocation is
> bypassed but REQUIREMENTS still exists on disk before Step 6.
>
> The principle "REQUIREMENTS must exist before any stage runs" is preserved.
> What changed: well-specified prompts no longer pay the 22 s agent round-trip
> when the TASK string already carries scope + target + constraints with high
> confidence, and trivial operational intents (merge/push/etc.) bypass the
> pipeline entirely via Step 1.7.

Run the sufficiency check once per task, before Step 5. Use the deterministic
helper script instead of inlining scoring code into this command prompt:

```text
${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py
```

Read `core/rules/requirements-sufficiency.md` only if the helper contract is
unclear; do not preload that rule during command startup, fast-path
classification, injection detection, or trivial operational dispatch.

Run the check and branch:

```bash
SUFFICIENCY=$(python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --status "${TASK}")
POLICY=$(python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --policy \
  --intensity "${AGENT_CREW_INTERACTION_INTENSITY:-balanced}" \
  "${TASK}")
```

**If `SUFFICIENCY == "SUFFICIENT"`:** Synthesize the REQUIREMENTS block inline
from the matched signals — do NOT spawn the requirements agent. Write the
synthesized block to `{TASK_DIR}/context/requirements.md` (same path the agent
would have used) and proceed directly to Step 6.

Synthesize with the same helper and do not ask the requirements agent:

```bash
python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --write "${TASK_DIR}/context/requirements.md" "${TASK}"
```

The written block must remain compatible with the requirements agent's
`REQUIREMENTS: |` output. If
`{TASK_DIR}/context/codex-skill-context.md` exists, append a `skill_context:`
field to the synthesized block that points at that file; do not inline large
skill output into requirements.

**If `SUFFICIENCY == "AMBIGUOUS"`:** Proceed to Step 5 (collect via agent) with
the mode selected by `POLICY`:

- `single_round` — run the existing single structured-choice requirements
  interview.
- `deep_interview` — run `MODE: deep_interview` and keep implementation blocked
  until `ambiguity <= ${AGENT_CREW_AMBIGUITY_THRESHOLD:-0.20}`.
- `direct_answer` — valid only for question-shaped read-only work under
  `light`; implementation/mutation requests must not use it to bypass
  requirements.

For parallel runs (`N > 1`), run the sufficiency check for each task
independently. Tasks whose check returns `SUFFICIENT` skip Step 5 entirely;
tasks whose check returns `AMBIGUOUS` spawn the requirements agent in
the selected requirements mode in parallel with the others.

### 5. Collect Requirements Per Task (AMBIGUOUS path only)

> **NEVER-SKIP-WITHOUT-SUFFICIENCY-CHECK**: Step 5 runs only when Step 5.pre
> returned `AMBIGUOUS` for this task. REQUIREMENTS is still mandatory before
> Step 6 — but if the sufficiency check already synthesized it inline, do not
> re-collect. The task argument is a description, not requirements; the
> sufficiency check decides whether the description carries enough signal.
>
> Step 5 is also not reached when Step 1.7 (Fast-Path Intent Classification)
> already short-circuited the pipeline for a trivial operational intent. Every
> request that *does* reach Step 5 is on the regular slow-path pipeline and
> has just been told by Step 5.pre that its TASK string is too ambiguous to
> synthesize from.

**When `N == 1`:** Delegate to the requirements agent (blocking):

```text
TASK: {task description}
TASK_INDEX: 0
TASK_DIR: {TASK_DIR}
MODE: {single_round|deep_interview from POLICY}
CODEX_SKILL_CONTEXT_PATH: {TASK_DIR}/context/codex-skill-context.md
  (include only when the file exists)

Run the selected structured user-choice interview (per
`core/rules/capabilities/interactive-question.md`), validate scope, detect
ambiguities, write {TASK_DIR}/context/requirements.md, preserve
CODEX_SKILL_CONTEXT_PATH in the requirements file when present, and return the
REQUIREMENTS block. In `MODE: deep_interview`, ask targeted follow-up questions
until the ambiguity threshold is satisfied or report BLOCKED before
implementation.
```

Wait for the agent to return. Extract the `REQUIREMENTS` block and record it.

> **`MODE: two_round` is a compatibility fallback.** `MODE: deep_interview` is
> the preferred deeper path for high-ambiguity `deep` / `strict` policy work.
> `two_round` remains available for legacy callers, but the orchestrator should
> prefer the policy-selected mode.

**When `N > 1`:** Spawn all requirements agents for `AMBIGUOUS` tasks
**simultaneously in a single response** (one Agent tool call per ambiguous task,
all issued together). Do NOT send them one at a time — parallel spawn is
mandatory for N > 1. Tasks whose Step 5.pre returned `SUFFICIENT` are NOT
spawned here (their REQUIREMENTS was already synthesized inline):

```text
# Issue all Agent calls for AMBIGUOUS tasks in the same response (parallel fan-out):
For each AMBIGUOUS task i:
  TASK: {task i description}
  TASK_INDEX: i
  TASK_DIR: {TASK_DIR_i}
  MODE: single_round
  Run a single-round structured user-choice interview (per `core/rules/capabilities/interactive-question.md`), write requirements.md, return REQUIREMENTS block.
```

Wait for **all** spawned requirements agents to complete before proceeding to
Step 6. Extract each task's `REQUIREMENTS` block from its agent's response and
record it. Do not run supervisors while requirements collection is still in
progress for any AMBIGUOUS task.

### 6. Run Supervisors

> **MANDATORY DELEGATION RULE — non-negotiable.** The orchestrator (the Claude
> instance loaded with this `run.md`) MUST spawn a `supervisor` subagent for
> every task via the host's Agent/Task tool. The orchestrator MUST NOT run
> planner, designer, backend, frontend, devops, or any other stage agent
> directly, and MUST NOT execute pipeline phases (Phase 0 through Phase 3)
> inline as itself. Doing so is what this section calls **inline execution**,
> and it is a workflow violation.
>
> Required behavior:
> - Call the host's Agent tool **once per task** with `subagent_type: supervisor`
>   (or the host's equivalent) and the input block defined below.
> - Wait for each `supervisor` to return its STATUS report. The orchestrator's
>   job is dispatch, health check (Supervisor Health Check below), and result
>   collection — not implementation.
>
> Forbidden behaviors (each one is a bug):
> - Reading `supervisor.md` and "playing the role" of supervisor inline.
> - Invoking the planner agent directly from this orchestrator step.
> - Performing `touch ${STATE_DIR}/tasks/active`
>   from the orchestrator — that marker is created by `supervisor` Phase 1c,
>   and creating it elsewhere masks the underlying delegation failure.
> - Editing project source files from the orchestrator. The orchestrator only
>   writes to `${TASK_DIR}` (state files) and to remotes during Step 11.
>
> Why this matters: `supervisor.md` Phase 1b+1c is the only place that creates
> the active task marker the `direct-edit-guard` PreToolUse hook checks for. If
> the orchestrator skips delegation, Phase 1b+1c never executes, the marker is
> never created, and every subsequent Edit/Write to project source is blocked by
> the hook. Every observed "hook blocked my edit" symptom in this repo traces back
> to a missing delegation here.

> **Plan Approval Gate (N == 1):** For single-task runs, the plan approval gate is
> handled **inside** the supervisor at Phase 1d. The supervisor reads `pipeline.json`
> and `analysis.md` after the merged analyst spawn, displays the full implementation
> plan, and emits a structured user-choice intent (see
> `core/rules/capabilities/interactive-question.md`) before any stage agent
> executes. Do NOT add a separate plan approval gate here in the orchestrator
> for N == 1.
>
> **Plan Approval Gate (N > 1):** For parallel runs, each supervisor independently
> handles Phase 1d for its own pipeline. After all supervisors have finished Phase
> 1b+1c (merged analysis+planning), each will pause at Phase 1d awaiting user
> approval. The orchestrator does not consolidate these approvals — each
> supervisor's Phase 1d is independent.

Delegate one `supervisor` per task. The orchestrator chooses between two
delegation surfaces based on the `agent_background` capability flag.

Read both `agent_background` and `task_tools` in a single Python process so
the file is opened only once and both Step 6 and Step 7.5 reuse the cached
values without a second process startup:

```bash
# Single read — both flags cached here and reused in Steps 6 and 7.5.
read -r HAS_AGENT_BACKGROUND HAS_TASK_TOOLS < <(python3 -c "
import json
try:
    c = json.load(open('${CAPABILITIES_PATH}'))
    print(
        '1' if c.get('agent_background') else '0',
        '1' if c.get('task_tools') else '0',
    )
except Exception:
    print('0 0')
" 2>/dev/null)
```

Before spawning any supervisor, write the boot sentinel and append a progress
event. This applies to both the background P4 path and the legacy inline path;
without it, a host-side stall before supervisor Phase 0 looks like a silent
hang.

```bash
SPAWNED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'spawned_at=%s\nsession_id=%s\n' "${SPAWNED_AT}" "${SESSION_ID:-single}" \
  > "${TASK_DIR}/supervisor-pending.txt"
printf '%s | SUPERVISOR_HANDOFF | waiting for supervisor Phase 0\n' \
  "${SPAWNED_AT}" >> "${TASK_DIR}/progress.log"
```

**P4 — Background fan-out (preferred when `HAS_AGENT_BACKGROUND == 1`).**
Spawn each supervisor as a host background agent, print a "Background Session
Started" summary, and **RETURN immediately** (end the turn). Do NOT enter any
poll loop.

This branch runs for **every** nontrivial task — including single-task runs
(`N == 1`) — when the capability flag is true. The previous `N == 1` carve-out
to the inline path is gone: unifying single and parallel under the background
surface is what makes mid-session task injection work for ordinary one-shot
`crew:run` invocations as well as for parallel fan-outs. Trivial intents
(Step 1.7) still dispatch inline because they never spawn a supervisor.

The orchestrator does **not** call `TaskCreate` before spawning. Each
supervisor creates its own host task entry at Phase 0 startup (when
`HAS_TASK_TOOLS == 1`). This removes the dual-path coupling where the
orchestrator needed to know whether to pre-create or skip. The `HAS_TASK_TOOLS`
flag is used only by `crew:status` (Step 7.5) to choose its polling method —
it does not affect the P4 spawn path.

```text
for each task i:
    # Write the supervisor-pending sentinel/progress event shown above.

    # Spawn the supervisor as a background agent. The supervisor handles
    # its own TaskCreate in Phase 0 when task_tools capability is present.
    spawn supervisor as background agent with:
        TASK, TASK_ID, TASK_DIR, PROJECT_ROOT, BRANCH,
        MODE: supervisor,
        EXECUTION_MODE=parallel,
        REQUIREMENTS=$REQUIREMENTS
```

After all N background supervisors are spawned, print the following summary
and **STOP — end the turn**:

```
## 🏁 Background Session Started

\`\`\`
Session : {SESSION_ID}
Tasks   : {N} supervisor(s) spawned as background agents

  Task 1 : {TASK_1 description truncated to 60 chars}
           branch={BRANCH_1}  id={TASK_ID_1}
  Task 2 : {TASK_2 description truncated to 60 chars}
           branch={BRANCH_2}  id={TASK_ID_2}
  ...
\`\`\`

> Background agents are running.
> - Check pipeline state: `crew:status`
> - Inject another task: `crew:run "new task"`
> - Collect final results: `crew:status --collect`

Next step suggestion: run `crew:status` shortly to see the live phase /
stage progression. The orchestrator turn has ended; this terminal is
free for additional `crew:run` or `crew:status` invocations.
```

**Do NOT proceed to Steps 7–11 on the P4 path.** Those steps (result
collection, merge, summary, deploy) are delegated to `crew:status --collect`,
which the user invokes at any time after the background session finishes.
Returning early here is what enables true mid-run task injection: because the
orchestrator's turn has ended, the user can immediately run
`crew:run "new task"` to inject into the live session.

Under this path, **each supervisor owns a per-task `direct-edit-guard`
marker** (`tasks/active.<TASK_ID>`) so concurrent teardown by one runner does
not strand another runner's edits. The hook accepts either layout — see
`core/hooks/direct-edit-guard.sh` and
`core/rules/capabilities/agent-background.md`.

**Legacy inline fan-out** is used only when `HAS_AGENT_BACKGROUND == 0`
(Codex, generic, and any other host that has not advertised
`agent_background = true` in `capabilities.json`). It is the best-effort
fallback for hosts without a background-agent surface; the orchestrator's
turn stays alive until every supervisor returns, and task injection is
effectively unavailable.

- If `N == 1`, invoke one `supervisor` via the host's Agent/Task tool. Do not
  execute the pipeline inline.
- If `N > 1`, invoke all `supervisor` agents concurrently in a single
  response containing N parallel Agent tool calls.
- Codex adapter constraint: when invoking the supervisor through Codex
  `spawn_agent` / Agent tooling, do not request a full-history fork together
  with explicit agent/model/reasoning options. Use a prompt-only handoff with
  the `supervisor` agent selection, or set `fork_context=false`. The supervisor
  receives all required state through the prompt fields below and must read any
  needed context from `TASK_DIR`, `PROJECT_ROOT`, and installed agent-crew
  files.

Hosts that advertise `agent_background = true` do not reach this branch —
they always take the P4 path above, regardless of `N`.

Both paths use the same supervisor agent definition. The supervisor's Phase 0
behavior is identical in both cases: when `HAS_TASK_TOOLS == 1`, it calls
`TaskCreate` itself at startup. No `HOST_TASK_ID` is pre-passed by the
orchestrator on either path.

Each supervisor receives:

```text
TASK: {task description}
TASK_ID: {TASK_ID}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {execution root for this task}
BRANCH: {BRANCH}
MODE: supervisor
EXECUTION_MODE: single or parallel
SESSION_ID: {SESSION_ID}
CODEX_SKILL_CONTEXT_PATH: {TASK_DIR}/context/codex-skill-context.md
  (include only when the file exists)
REQUIREMENTS: |
  scope: {scope answer}
  target: {target answer}
  constraints: {constraints answer(s)}
  skill_context: {TASK_DIR}/context/codex-skill-context.md, if present
  followup:
    {field_name}: {Round 2 answer A, if collected}
    {field_name}: {Round 2 answer B, if collected}

Complete this task autonomously through the full pipeline.
Write the completion report to {TASK_DIR}/result.md.
```

#### Supervisor Health Check (Persistent Execution — inline path only)

> **P4 path skip**: When `HAS_AGENT_BACKGROUND == 1`, the orchestrator has
> already returned at the end of the spawn block above. This health check
> and the result collection loop below apply only to the **inline path**
> (`HAS_AGENT_BACKGROUND == 0`). Background-path crash classification and
> retries are performed by `crew:status --collect`.

After each supervisor returns (inline path), the orchestrator must verify its output:

- If the supervisor returns **without a STATUS field** (crash, token limit,
  or interrupt):
  - Treat as a crash. Do **not** mark the task as failed.
  - Re-invoke the same supervisor with identical parameters.
  - The supervisor will resume from `pipeline.json` (Phase 0 resume check).
  - Retry up to **3 times** before marking the task as blocked.

**P7 — capability-gated crash classification (when `HAS_TASK_TOOLS == 1`).**
When the parent host task id is available at `${TASK_DIR}/host-task-id.txt`,
the orchestrator should consult `TaskGet(parent_taskId).status` to classify
the "no STATUS field" outcome before retrying:

```text
HOST_STATUS=$(TaskGet(taskId=$(cat "${TASK_DIR}/host-task-id.txt")).status)
```

| `TaskGet` status | Classification | Orchestrator action |
|---|---|---|
| `error` | True crash | Re-invoke (counts against 3-retry budget) |
| `completed` | Token-truncation tail | Re-invoke with resume hint pointing at `${TASK_DIR}/progress.log` and `pipeline.json`; this resume does **not** count against the 3-retry budget (one free token-truncation resume per task) |
| `blocked` | Task-runner reached BLOCKED but failed to write STATUS | Read `${TASK_DIR}/result.md`; if STATUS present treat as blocked, else re-invoke as crash |
| `in_progress` / `pending` | Host did not yet observe completion — likely runtime interrupt | Re-invoke (counts as crash) |
| `cancelled` | User cancelled at gate | Mark task blocked with reason "Cancelled by approval gate" — do not retry |

When `HAS_TASK_TOOLS == 0` or the parent host task id is absent: skip the
classification entirely and apply the legacy "every no-STATUS outcome is a
crash, retry up to 3 times" rule. Behavior is identical to pre-P7.

This "끈질기게 실행" (persistent execution) rule means the orchestrator never
gives up on a supervisor until it explicitly returns `STATUS: blocked` with a
real, substantive blocker.

Wait for all supervisors to finish (including any crash-retry cycles).

#### Session-Aware Result Collection (inline path only — N > 1 with injection support)

> **P4 path skip**: On the background fan-out path (`HAS_AGENT_BACKGROUND == 1`),
> the orchestrator has already returned early after spawning. This collection
> loop is only used by the **inline path** (`HAS_AGENT_BACKGROUND == 0`).
> For the P4 path, result collection is performed by `crew:status --collect`.

When a session file exists, the orchestrator's result collection loop MUST
monitor `session.json` continuously rather than operating on a fixed task list.
New tasks injected after Step 6 via Step 1.5 appear as additional entries in
the `tasks` array; they must be picked up without restarting the collection
loop.

```bash
# Dynamic collection loop — runs until session is done
COLLECTED=()
PENDING_TASK_IDS=()  # Start with original tasks

while true:
    # Re-read session.json to pick up any injected tasks
    ALL_TASK_IDS=$(python3 -c "
    import json
    s = json.load(open('${SESSION_FILE}'))
    for t in s['tasks']:
        if t['status'] not in ('completed', 'blocked'):
            print(t['task_id'])
    " 2>/dev/null)

    # Check for newly-injected tasks not yet in our monitoring pool
    for TASK_ID in $ALL_TASK_IDS; do
        if [[ ! " ${PENDING_TASK_IDS[@]} " =~ " ${TASK_ID} " ]]; then
            PENDING_TASK_IDS+=("${TASK_ID}")
            log_progress "INJECT_DETECTED" "task_id=${TASK_ID} added to collection pool"
        fi
    done

    # Check which pending tasks have completed
    for TASK_ID in "${PENDING_TASK_IDS[@]}"; do
        TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
        if grep -qiE "^(\*\*)?status:\*{0,2}\s+\**(completed|blocked|BLOCKED)\**" "${TASK_DIR}/result.md" 2>/dev/null; then
            COLLECTED+=("${TASK_ID}")
            PENDING_TASK_IDS=("${PENDING_TASK_IDS[@]/$TASK_ID}")  # remove from pending
            # Update session.json status for this task
            python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
for t in s['tasks']:
    if t['task_id'] == '${TASK_ID}':
        t['status'] = 'completed'
        break
json.dump(s, open('${SESSION_FILE}', 'w'), ensure_ascii=False, indent=2)
"
        fi
    done

    # Check if all tasks (original + injected) are done
    REMAINING=$(python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
print(sum(1 for t in s['tasks'] if t['status'] not in ('completed', 'blocked')))
" 2>/dev/null)

    if [ "${REMAINING}" = "0" ]; then
        break  # All tasks have reached terminal state
    fi

    sleep 2  # Poll interval; TaskGet-based wake-up is preferred when HAS_TASK_TOOLS=1
done
```

When `HAS_TASK_TOOLS == 1` and background task IDs are tracked, use
`TaskList` + `TaskGet` for the wakeup signal instead of polling `result.md`
directly — the file remains the canonical source.

After all tasks complete, mark `session.json` as done so future `crew:run`
invocations do not treat it as a live session.

> **MANDATORY (Codex / generic inline path — `HAS_AGENT_BACKGROUND == 0`):**
> After all inline supervisors return (and after any crash-retry cycles),
> call `finalize-session.sh` unconditionally. This is the authoritative
> finalization step for the inline path. Skipping it leaves `session.json`
> with `status: running`, causing future `crew:run` invocations to detect a
> false live session and offer the injection prompt incorrectly.
>
> The script is idempotent: calling it on an already-completed session is safe.
> The P4 background path must NOT call this script — its finalization is
> handled by `crew:status --collect` (Step 4S).

```bash
# MANDATORY inline-path finalization — run unconditionally after all supervisors finish.
# This call is the canonical session-close step for HAS_AGENT_BACKGROUND=0, N>1 runs.
bash "${AGENT_CREW_HOME}/scripts/finalize-session.sh" "${SESSION_FILE}" "${STATE_DIR}"
FINALIZE_RC=$?
if [ "${FINALIZE_RC}" -eq 2 ]; then
  # Exit code 2 = partial success: some tasks had no result.md (likely crashed).
  # The script already updated what it could. Log a warning and continue —
  # the stale-session timeout will clean up any residual 'running' entries.
  echo "[crew] WARN | finalize-session: one or more tasks missing result.md (rc=2)" >&2
elif [ "${FINALIZE_RC}" -ne 0 ]; then
  # Exit codes 1+ (other than 2) are hard errors. Log but do not abort —
  # Step 7 result collection will still read result.md directly.
  echo "[crew] WARN | finalize-session: unexpected exit code ${FINALIZE_RC}" >&2
fi
```

### 7.5. Parallel Action Gate (inline path, N > 1 only)

> **P4 path skip**: When `HAS_AGENT_BACKGROUND == 1`, the orchestrator
> already returned early at the end of Step 6. This step is **not executed
> on the P4 path**. On the P4 path, the action gate for each supervisor is
> handled by the supervisor's own Phase 2.5 Stage Action Gate (using
> per-task `approval.md`). The consolidated gate here is only for the inline
> parallel path (`HAS_AGENT_BACKGROUND == 0`, `N > 1`).

> **Skip this step entirely when N == 1.** For single-task runs, the supervisor
> itself acts as the local orchestrator for its own stage agents and issues the
> consolidated structured user-choice intent (per
> `core/rules/capabilities/interactive-question.md`) via its Phase 2.5 Stage
> Action Gate. Proceed directly to Step 7 (Collect Results).

When `N > 1`, all supervisors execute concurrently. Before any stage agent
executes a deploy, merge, push, or other destructive action, the orchestrator
must consolidate their plans and issue a **single** approval gate.

#### Protocol

**Phase A — Plan collection (supervisors block, waiting for approval.md)**

Each stage agent (devops, etc.) that would previously ask for approval must instead:
1. Write its planned actions to `{TASK_DIR}/context/action-plan.md`
2. Return a `PLAN:` block to its parent supervisor — do not execute yet
3. The supervisor writes `PLAN_READY` to `{TASK_DIR}/context/approval.md`
4. The supervisor polls `{TASK_DIR}/context/approval.md` for `APPROVED` or
   `CANCELLED` (up to 60s, 5s interval) before releasing execution

**Phase B — Centralized approval (orchestrator)**

After all supervisors have written `PLAN_READY` to their `approval.md`, the
orchestrator:

1. Reads `action-plan.md` from every `TASK_DIR`
2. Composes a consolidated approval summary:

   ```text
   ### 📝 Consolidated Action Plan

   \`\`\`
   Task 1 [{BRANCH_1}]:
     deploy : push to staging via docker-compose up -d
     merge  : git merge --no-ff {BRANCH_1} into main

   Task 2 [{BRANCH_2}]:
     deploy : run npm run build && rsync dist/ to server
     merge  : git merge --no-ff {BRANCH_2} into main
   \`\`\`
   ```

3. Emits a **single** structured user-choice intent (per
   `core/rules/capabilities/interactive-question.md`):
   - header: "Approve All Actions"
   - question: "Review the consolidated action plan above. Approve to release all tasks, or cancel to hold."
   - options:
     - label: "Approve all"
       description: "Release all task pipelines to execute"
     - label: "Cancel all"
       description: "Hold all tasks, no actions taken"

4. On **Approve all**: write `APPROVED` to `{TASK_DIR}/context/approval.md` for each task
5. On **Cancel all**: write `CANCELLED` to `{TASK_DIR}/context/approval.md` for each task, then stop

#### P2 — TaskList-based PLAN_READY detector (capability-gated)

The orchestrator reads
`${STATE_DIR}/capabilities.json` once and caches
`HAS_TASK_TOOLS`. When `HAS_TASK_TOOLS == 1` the preferred fan-in path is a
single `TaskList()` round-trip filtered by `metadata.stage == "plan_ready"`
matching the run's task IDs. The file write is still the contract — the
`TaskList` call is only the fast convergence signal:

```text
# HAS_TASK_TOOLS already set in Step 6 combined-read above — no re-read needed.

if [ "${HAS_TASK_TOOLS}" = "1" ]; then
  # Preferred path: deterministic readiness check, one round-trip (no sleep).
  # P1 wrote TaskUpdate(status="blocked", metadata.stage="plan_ready") on each
  # supervisor's parent host task. We poll TaskList every 1s (long-poll if the
  # host supports wake-on-change) until every expected task is present.
  EXPECTED_TASK_IDS="{comma-separated list of TASK_IDs from this run}"
  ELAPSED=0
  while [ $ELAPSED -lt 120 ]; do
    READY=$(TaskList()
      | jq -r '.[] | select(.metadata.stage=="plan_ready") | .metadata.task_id'
      | sort -u)
    MISSING=$(comm -23 <(echo "$EXPECTED_TASK_IDS" | tr ',' '\n' | sort -u) \
                       <(echo "$READY"))
    if [ -z "$MISSING" ]; then
      break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
  done
fi

# File-based fallback (always runs when HAS_TASK_TOOLS == 0, and as a safety
# backstop after the TaskList path when capability is enabled — the file is the
# source of truth, the host call is only the convergence signal).
for TASK_DIR in {all task dirs}; do
  until grep -q "PLAN_READY\|APPROVED\|CANCELLED" "${TASK_DIR}/context/approval.md" 2>/dev/null; do
    sleep 5
  done
done

# Read and consolidate all action plans
for TASK_DIR in {all task dirs}; do
  cat "${TASK_DIR}/context/action-plan.md"
done

# After the structured user-choice decision, write result to each task. When the
# capability is enabled, ALSO transition each supervisor's parent host task —
# the TaskGet waiters inside P1 will wake on the next event without paying the
# 5-second file-poll cadence.
RESULT="APPROVED"  # or CANCELLED
for TASK_DIR in {all task dirs}; do
  echo "${RESULT}" > "${TASK_DIR}/context/approval.md"
  if [ "${HAS_TASK_TOOLS}" = "1" ]; then
    HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt" 2>/dev/null)
    if [ -n "$HOST_TASK_ID" ]; then
      # APPROVED → in_progress, CANCELLED → cancelled
      if [ "$RESULT" = "APPROVED" ]; then
        TaskUpdate(taskId=$HOST_TASK_ID, status="in_progress")
      else
        TaskUpdate(taskId=$HOST_TASK_ID, status="cancelled")
      fi
    fi
  fi
done
```

When `HAS_TASK_TOOLS == 0` the orchestrator runs only the legacy file-poll
loop above — identical behavior to pre-P2. The capability flag opts into a
faster wakeup; it never removes the file contract.

> **Orchestrator rule**: The orchestrator MUST NOT proceed to Step 7 until all
> supervisors have received their approval signal and resumed (or halted on
> CANCELLED). Task-runners that received CANCELLED must report STATUS: blocked
> with reason "Cancelled by consolidated approval gate."

---

### 7. Collect Results & Show Per-Task Summary

> **P4 path skip**: When `HAS_AGENT_BACKGROUND == 1`, the orchestrator
> already returned early at the end of Step 6. Steps 7–11 are **not
> executed on the P4 path** — they are performed by `crew:status --collect`
> when the user is ready to finalize the session. Steps 7–11 below apply
> only to the **inline path** (`HAS_AGENT_BACKGROUND == 0`).

#### Session-Aware Task List

When `session.json` exists (all `N > 1` runs), the orchestrator derives its
task list dynamically from the session file rather than from a static list
built at Step 4. This ensures that injected tasks (added via Step 1.5 after
Step 6 runs) are included in result collection, the merger, and the final
summary without any orchestrator restart.

```bash
# Read the current task list from the session file
TASK_ENTRIES=$(python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
for t in s['tasks']:
    print(t['task_id'], t['task_dir'], t['branch'], sep='|')
" 2>/dev/null)
```

At every poll iteration, re-read `session.json` to detect newly-registered
injected tasks before checking their completion status (see the collection loop
in Step 6's Session-Aware Result Collection section).

#### P4 — Background fan-out result collection

When supervisors were spawned as background host agents (Step 6 background
path, `HAS_AGENT_BACKGROUND == 1`), the orchestrator does NOT block on inline
Agent return values. Instead it polls each task's parent host task for
terminal status:

```text
# For every TASK_DIR in the run (from session.json, updated dynamically):
HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt")

# Wait for terminal status. TaskGet returns instantly on state change;
# the 2-second guard sleep bounds the busy-wait if the host returns
# synchronously. The total timeout matches the runner's worst-case
# pipeline duration (the orchestrator has no separate budget).
while true:
    STATUS = TaskGet(HOST_TASK_ID).status
    if STATUS in ("completed", "blocked", "cancelled"):
        break
    sleep 2
```

After all supervisors reach a terminal status, the orchestrator reads each
runner's `${TASK_DIR}/result.md` (canonical artifact) AND `TaskOutput` (live
event stream, when `HAS_MONITOR_TOOL == 1`) to assemble the Run Summary. When
both sources are available, `result.md` takes precedence — the host stream is
diagnostic only.

The crash-retry rule below applies identically: a runner whose
`TaskGet().status == "error"` (or whose `result.md` is missing after status
reached `completed`) is treated as a crash and re-spawned, up to 3 attempts.

When `HAS_AGENT_BACKGROUND == 0`: the orchestrator simply waits for the inline
Agent calls from Step 6 to return, as before. Behavior is identical to pre-P4.

Injected tasks that arrived via the background fan-out path also have their
`HOST_TASK_ID` registered in `session.json` at injection time; the collection
loop picks them up on the next `session.json` re-read.

#### Live Progress

Task-runners emit `[crew]`-prefixed lines throughout execution to surface
real-time lifecycle events. These lines appear inline as each phase and stage
boundary is crossed — the orchestrator does NOT suppress them. Example output
visible during a pipeline run:

```
[crew] 20260510-140000-0 | STARTED | implement order API
[crew] 20260510-140000-0 | PHASE | 1a — Requirement collection
[crew] 20260510-140000-0 | PHASE | 1b — Analysis
[crew] 20260510-140000-0 | PHASE | 1c — Planning
[crew] 20260510-140000-0 | PHASE | 1d — Plan approval
[crew] 20260510-140000-0 | STAGE | 1/2 — backend
[crew] 20260510-140000-0 | STAGE_DONE | backend — N/A
[crew] 20260510-140000-0 | STAGE | 2/2 — reviewer
[crew] 20260510-140000-0 | STAGE_DONE | reviewer — APPROVED
[crew] 20260510-140000-0 | COMPLETED | branch=feat/implement-order-api commits=3
```

In parallel runs (N > 1), each supervisor's TASK_ID prefix makes interleaved
lines from concurrent runners easy to distinguish.

**File-based progress log:** In addition to inline `[crew]` lines, every progress
event is written to `{TASK_DIR}/progress.log` as a timestamped line. Because
sub-agent inline output may be buffered until the agent completes, the progress
log provides a reliable source of truth for current pipeline state at any point
during execution. Run `crew:status` at any time to see the current pipeline state
read from this log. For N > 1, `crew:status` shows the most recently active task.

After all supervisors finish, the orchestrator prints the full Run Summary below.

**MANDATORY: Output the Run Summary block below to the user before proceeding to any next step. This cannot be skipped.**

For each task, read the result file to extract status and branch, and collect commits:

```bash
RESULT=$(cat "${TASK_DIR}/result.md" 2>/dev/null || echo "")
COMMITS=$(git -C "${PROJECT_ROOT_FOR_TASK}" log --oneline HEAD ^main 2>/dev/null || echo "N/A")
```

#### Missing or Incomplete Result Handling

If `result.md` is missing or the STATUS field is absent:

- Do **not** report "No result report found."
- Treat as a supervisor crash. Re-invoke the supervisor for that task.
- Pass the same `TASK_DIR` so the supervisor resumes from `pipeline.json`.
- Retry up to **3 times** per task.
- Only after all retries are exhausted: report the task as `blocked` with the
  reason "supervisor did not produce a result after 3 restart attempts."

In parallel runs (`N > 1`), apply this retry logic independently per task —
a crashed supervisor must not block result collection for other tasks.

Display a summary for every task. Do not proceed to Step 8 until the Run Summary has been printed to the user.

For each task, collect the diff relative to the pre-run HEAD:

```bash
# Show changed files with stats
git -C "${PROJECT_ROOT_FOR_TASK}" diff --stat ${PRE_RUN_HEAD}..HEAD

# Show diff preview (cap at 200 lines)
DIFF_OUTPUT=$(git -C "${PROJECT_ROOT_FOR_TASK}" diff ${PRE_RUN_HEAD}..HEAD 2>/dev/null)
DIFF_LINES=$(echo "$DIFF_OUTPUT" | wc -l | tr -d ' ')
if [ "$DIFF_LINES" -le 200 ]; then
  echo "$DIFF_OUTPUT"
else
  echo "$DIFF_OUTPUT" | head -200
  echo "… $((DIFF_LINES - 200)) more lines. Run: git diff ${PRE_RUN_HEAD}..HEAD"
fi
```

If `${TASK_DIR}/context/evolution-report.md` exists, include a compact
Learning Summary after the commits block. Use the sidecar report as read-only
evidence; do not infer generated assets from it. The summary must surface
operator-visible status instead of only printing artifact paths: `captured`,
`captured_events`, `repeated_pattern`, `proposal`, `evidence`, `reason`, and
`next_action`. If the file is absent, omit this section entirely.

If `${TASK_DIR}/context/evolution-proposals-summary.txt` exists, include a
compact Self-Evolution Proposals block immediately after the Learning Report.
This block is advisory only: it surfaces pending approval-gated proposals and
does not mean any asset was created or applied.

```text
**📦 Run Summary**

\`\`\`
Task 1 : {description}  [injected]    ← "(injected)" tag when task.injected == true
Status : ✅ completed | 🚫 blocked
Branch : {branch}

Changes:
  {git diff --stat {PRE_RUN_HEAD}..HEAD output}

Diff:
  {git diff {PRE_RUN_HEAD}..HEAD | head -200 output}
  (If over 200 lines: "… {N} more lines. Run: git diff {PRE_RUN_HEAD}..HEAD")

Commits ({N}):
  {git log --oneline, up to 5 lines}

Learning Summary:
  captured: yes|no
  captured_events: {N}
  repeated_pattern: yes|no
  proposal: none|approval_required|approved|applied
  evidence: {context/evolution-report.md and learning/events.jsonl when present}
  reason: {why a proposal exists or why it does not}
  next_action: {approval or more evidence}

Self-Evolution Proposals:
  {context/evolution-proposals-summary.txt lines, when present}
\`\`\`

\`\`\`
Task 2 : {description}
...
\`\`\`
```

The `[injected]` tag appears next to any task whose `session.json` entry has
`"injected": true`. This gives operators a clear visual distinction between
original and dynamically-added tasks in the run summary.

If any task has `STATUS: blocked`, do not proceed to deployment.
Report the blocker and stop.

---

### 8. Merge Branches (inline path, N > 1 only)

> **P4 path skip**: On the background fan-out path, this step is performed by
> `crew:status --collect`, not here. See Step 7 header.

> **Skip this step entirely when N == 1.** For single-task runs, proceed directly
> to Step 9. The feature branch will be pushed as-is in Step 10.

When `N > 1`, merge all task feature branches into `main` locally before
showing the deployment plan. The branch list is read from `session.json` so
that injected tasks (which joined the session after Step 6) are included:

```bash
ALL_BRANCHES=$(python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
for t in s['tasks']:
    if t['status'] == 'completed':
        print(t['branch'])
" 2>/dev/null)

git checkout main
for BRANCH in ${ALL_BRANCHES}; do
  git merge --no-ff "${BRANCH}" -m "merge: ${BRANCH} into main"
done
```

If a merge conflict occurs during any merge, invoke the conflict resolver before
continuing:

```text
crew:run "resolve merge conflicts"
```

Do not proceed to Step 9 until all merges complete cleanly.

After all merges succeed, collect the combined commit log for the deployment plan:

```bash
git log --oneline HEAD ^origin/main | head -10
```

---

### 9. Implementation Summary

> **Inline path only.** On the P4 background fan-out path, this step is performed
> by `crew:status --collect`. See Step 7 header.

Always display the implementation summary for every completed run, regardless of
whether a devops stage was included in the pipeline:

**When N > 1 (after merge):**

```text
**🛠️ Implementation Summary**

\`\`\`
Merged branches into main (local):
  {BRANCH_1}  ({N} commits)
  {BRANCH_2}  ({N} commits)

Commits ready for push (origin/main..HEAD):
  {git log --oneline origin/main..HEAD, up to 10 lines}
\`\`\`

> No remote push has occurred yet.
```

**When N == 1:**

```text
**🛠️ Implementation Summary**

\`\`\`
Branch  : {BRANCH}  ({N} commits)
Commits :
  {git log --oneline HEAD ^main, up to 5 lines}
\`\`\`

> No remote push has occurred yet.
```

> **Stop here.** Do not suggest any follow-up action (merge, push, PR creation,
> test runs, or anything else). The run is complete. If the user wants to deploy
> or push, they will request it explicitly — do not volunteer it.

---

### 9.5. Explicit Close-Out Menu

This step runs only when the user explicitly asks to close out a completed
branch after Step 9. Do not show it proactively.

Use the structured user-choice mechanism from
`core/rules/capabilities/interactive-question.md`:

- `Merge locally` — merge the completed branch into the selected base branch
  after approval.
- `Push / PR` — push the branch or prepare the configured PR handoff after
  approval.
- `Keep branch` — leave the local branch as-is and record no mutation.
- `Discard` — perform approved cleanup for the branch/worktree only after the
  destructive-action approval gate.

All merge, push, PR, and discard actions remain subject to the centralized
approval gate. A plain-text "shall I?" prompt is still forbidden.

---

### 10. Deployment Approval

> **Explicit deploy requests only.** Steps 10–11 execute only when the user
> explicitly requests deployment after Step 9 — never proactively. When
> deployment is requested, delegate to the **devops agent**. The orchestrator
> must not run `git push` directly. The devops agent owns the approval gate
> (the host's interactive question mechanism — see
> `core/rules/capabilities/interactive-question.md`) and execution.

**Only execute this step when the pipeline included a `devops` stage that will
run CI/CD (i.e., a stage whose agent is `devops`).**

If no `devops` stage was in the pipeline, skip this step entirely and stop after
Step 9. Branches remain local; the user can push manually.

When a `devops` stage is present, first compose and display the deployment plan:

**When N > 1:**

```text
## 🚦 Deployment Plan

\`\`\`
Action        : push main to origin (all task branches merged)
Target remote : origin

Commits to be published (origin/main..HEAD):
  {git log --oneline origin/main..HEAD}

Risk notes:
  - {any merge conflicts detected?}
  - {any blocked tasks?}
\`\`\`
```

**When N == 1:**

```text
## 🚦 Deployment Plan

\`\`\`
Action        : push {BRANCH} to origin
Target remote : origin

Commits to be published:
  {git log --oneline HEAD ^main}

Risk notes:
  - {any merge conflicts detected?}
  - {any blocked tasks?}
\`\`\`
```

Then emit a **structured user-choice intent** (per
`core/rules/capabilities/interactive-question.md`) to request approval. Do not
proceed without it.

**Plain-text approval is FORBIDDEN.** Never ask "Shall I merge and push?", "Should I deploy?", or any equivalent free-form question. The structured user-choice intent (per `core/rules/capabilities/interactive-question.md`) is the only permitted approval method for deployment, push, and merge operations.

**When N > 1:**

Question:
- header: "Deploy"
- question: "Review the deployment plan above. Approve to push main to remote, or cancel to hold."
- options:
  - label: "Approve"
    description: "Push main to origin now"
  - label: "Cancel"
    description: "Hold, do not push (branches remain local)"

**When N == 1:**

Question:
- header: "Deploy"
- question: "Review the deployment plan above. Approve to push to remote, or cancel to hold."
- options:
  - label: "Approve"
    description: "Push the feature branch to origin now"
  - label: "Cancel"
    description: "Hold, do not push (branch remains local)"

If **Approve**:
  - Proceed to Step 11.

If **Cancel**:
  - Print the branch name(s) so the user can push manually later.
  - Stop here. Do not push anything.

---

### 11. Execute Deployment

**When N > 1 (merged into main):**

```bash
git push origin main
```

**When N == 1 (feature branch only):**

```bash
git push origin "${BRANCH}"
```

Report result:

```text
Deployment complete.
Pushed: {main | branch name}
```

If a push conflict occurs, run:

```text
crew:run "resolve merge conflicts"
```

---

## Notes

- **Well-specified prompts skip requirements entirely.** Step 5.pre is a
  deterministic sufficiency check that returns `SUFFICIENT` or `AMBIGUOUS`
  based on signals in the TASK string (scope keyword family, concrete file or
  branch pointer, performance/MVP/dependency constraint). `SUFFICIENT` means
  the REQUIREMENTS block is synthesized inline with no agent spawn — cutting
  requirements overhead from ~22 s to ~2 s on well-formed prompts. `AMBIGUOUS`
  means the requirements agent runs in single-round mode (one structured
  user-choice call (per `core/rules/capabilities/interactive-question.md`)
  asking scope + target + constraints together) unless the interaction policy
  selects `MODE: deep_interview` for high-ambiguity `deep` / `strict` work. The
  default ambiguity threshold is `0.20`; implementation is allowed only when the
  generated requirements report `implementation_allowed: true`. The legacy
  2-round interview remains available for compatibility.
- `crew:run` is the canonical workflow entry point.
- Use plain `crew:<intent>` syntax in user-facing guidance.
- Task dependencies still matter. If tasks depend on each other, pass them as a
  single request so one `supervisor` can sequence the work inside one pipeline.
- **supervisor never pushes to remote.** All remote operations happen here in
  Step 11, only after explicit user approval in Step 10.
- **Step 8 (merge) applies only to parallel runs (N > 1).** For single-task runs,
  the feature branch is pushed directly without merging to main.
- **P4 path (background fan-out)**: When `HAS_AGENT_BACKGROUND == 1`, the
  orchestrator returns immediately after spawning all background supervisors
  (including single-task runs). Steps 7–11 are NOT executed in this turn. To
  wait for results and finalize the session (merge branches, show summary,
  deploy), run `crew:status --collect`.
- **Mid-run task injection**: Because the P4 path returns early, the user may
  immediately run `crew:run "new task"` to inject tasks into the live session.
  The injected tasks join the same `session.json` and are collected together by
  `crew:status --collect`.
- **Fast-path (Step 1.7)**: Trivial operational intents (merge, push, deploy,
  tag, rollback, status, commit-only) are dispatched inline by the orchestrator
  without spawning a supervisor. They still honor the centralized
  structured user-choice approval gate (per
  `core/rules/capabilities/interactive-question.md`) for destructive
  operations. The classifier is conservative — anything containing an
  implementation keyword ("add",
  "implement", "fix", etc.) falls through to the regular pipeline. See
  Step 1.7 for the full pattern list, exclusion rules, and per-intent
  dispatch table.
- If a run is `handoff_ready` or blocked with host bridge handoff issues, follow the documented SOP:
  [Host Bridge Handoff Recovery SOP](core/docs/host-bridge-handoff-sop.md)

### Host Bridge Handoff Recovery

When a run returns:

- `STATUS: handoff_ready`
- `HOST_BRIDGE: current_session_required`
- `BLOCKER: host AI bridge has not completed this handoff`

use this sequence:

1. Open the task output:
   - `TASK_DIR` from run output
   - `cat "${TASK_DIR}/result.md"`
2. In non-hosted/native runs, `STATUS: handoff_ready` is normal. Continue from
   `handoff.md`, then complete manually:
   - `crew repair <TASK_ID> --status completed --note "<summary>"`
3. In current-session fallback runs, `HOST_BRIDGE: current_session_required`
   means the host adapter requires the current host session to continue the
   handoff; no background bridge is still running. Continue from `handoff.md` in
   the current host session, then repair after completion.
   - During current-session closeout, relay the same summary contract before
     `crew repair <TASK_ID> --status completed` or before the final user
     response. Do not replace the structured closeout with a plain prose-only
     update.
     ```text
     **📦 Run Summary**
     {task status, branch/change evidence, blockers if any}
     {Learning Report excerpt from context/evolution-report.md when present}
     {Self-Evolution Proposals excerpt from context/evolution-proposals-summary.txt when present}

     **🛠️ Implementation Summary**
     {merged/local implementation state, commits ready for push, or explicit no-code-change result}
     ```
     Build the summary from `result.md`, task context evidence, and local git
     state where applicable. If no merge, push, deploy, or production-code
     change occurred, say that explicitly in the corresponding block.
   - Before executing any task work, re-apply the same specialist dispatch
     contract the supervisor would have applied: select the appropriate
     agent/user-agent and required agent skill(s) for the normalized task.
     This is a general fallback invariant, not a commit/deploy-specific rule.
   - If a concrete user agent or dispatcher skill is available for the task
     axis, use it or load its instructions before acting. Do not substitute
     ad hoc local execution just because the nested host bridge was refused or
     unavailable.
   - Record the selection in `context/specialist-dispatch.md` when available
     with at least: `selected_agent`, `selection_reason`, and `execution_mode`;
     include any applicable `selected_user_agent`, `selected_subagents`, and
     `selected_skill` / `selected_skills` entries. `crew repair --status
     completed` reports missing or incomplete dispatch coverage as advisory gaps.
   - Load the applicable skill files before acting and record the exact loaded
     skill path(s) in `context/skill-load.md` or `context/skill-load.json` when
     available.
     Automatically loaded skills must come from agent-crew system/user skill
     locations (`~/.agent-crew/system/skills/`, `~/.agent-crew/user/skills/`,
     `~/.agent-crew/skills/`, `~/.agent-crew/system/agents/skills/`) or from the
     active host's agent-crew mirrors (`~/.claude/agent-crew/skills/`,
     `~/.claude/agent-crew/agents/skills/`, `~/.codex/agent-crew/skills/`) or
     agent-crew host wrapper skills (`~/.codex/skills/crew:<intent>/`). Do not
     auto-load unrelated host/plugin skills such as plugin cache skills from
     trigger-description matches. If a
     non-agent-crew skill is needed, ask the user first and record the explicit
     approval in `context/external-skill-approval.md` or `.json`.
     Every selected skill name should have matching load coverage
     (`selected_skill: frontend-typescript-react` maps to
     `frontend-typescript-react.md`, `selected_skill: tdd` maps to `tdd.md`).
     `crew repair --status completed` reports missing or incomplete skill-load
     coverage as advisory gaps. It still rejects unapproved external host/plugin
     skill loads.
   - Optional skill-use notes may be recorded in `context/skill-use.json` or
     `context/skill-use.md`, but they are diagnostic coverage, not required
     proof artifacts. TDD and other loaded skills are covered first by real
     task outcomes, tests, diffs, reviews, pipeline/progress state, reviewer
     quality metrics, and tool events. `crew repair --status completed` should
     report missing or incomplete notes as advisory gaps instead of rejecting
     standard-risk completion.
   - Optional operational understanding notes may be recorded in
     `context/skill-plan.json` or `context/skill-plan.md` and linked from
     `rule_evidence` in `context/skill-use.json`, but these notes are diagnostic
     coverage only. `crew repair --status completed` should surface missing
     skill-plan or rule-evidence notes as advisory gaps when actual task
     outcomes, tests, diffs, reviews, or tool events are sufficient.
   - For implementation or other production-code mutations with a testable
     surface, follow the full Red → Green → Refactor cycle. Identify the focused
     test target, add or update it, and run it before changing production code.
     If no runnable harness or red failure is possible, make the explicit reason
     available before implementation.
   - After green, perform the refactor review or document a no-op refactor
     decision, then rerun the focused verification.
   - `crew repair --status completed` for production-code implementation may
     reject missing runtime quality-loop outcomes or high-risk hard blockers,
     but standard-risk missing phase-note artifacts are advisory coverage gaps.
4. For auto-completion:
   - Pass `--host-bridge-command "<command>"` on `crew run`, or
   - Set `AGENT_CREW_HOST_BRIDGE_COMMAND` in the process environment.
   - The command is parsed into argv and executed without an implicit shell; use
     `bash -c '...'` when shell features are required.
   `.zshrc` is not required; it is only one optional place to persist env.
5. Re-check task state:
   - `crew status --json --task-id <TASK_ID>`
   - `crew telemetry --format json --task-id <TASK_ID>`
6. If bridge blockers keep recurring in normal hosted runs, collect diagnostics:
   - `crew report auto --summary "host bridge blocker pattern"`

This section exists for operator troubleshooting; normal run output intentionally
stays concise.
