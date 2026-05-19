---
name: agent-crew
description: Use when the user invokes agent-crew workflow commands in Codex, including crew:setup, crew:run, crew:status, crew:cost, or crew:agent-maker. Also use for natural-language coding, implementation, refactoring, migration, testing, deployment, or agent-crew workflow requests in a workspace initialized with agent-crew. This skill bootstraps agent-crew before project-local AGENTS.md or .codex hooks exist, and prevents Codex from interpreting crew commands as generic repository inspection, verification, CI, Gradle, npm, lint, or direct implementation requests.
---

# Agent Crew Command Bootstrap

This skill handles provider-neutral agent-crew workflow commands inside Codex.

Codex may run without trusted lifecycle hooks, or hooks may inject only advisory
context. This skill is therefore the Codex fallback routing layer. Treat these
rules as authoritative even when `~/.agent-crew/hooks/auto-route.sh` did not
inject `[agent-crew]` context.

## Command Recognition

When the user message begins with one of these command forms, treat it as an
explicit command invocation, not ordinary natural language:

- `crew:setup`
- `crew:run`
- `crew:run "..."`
- `crew:status`
- `crew:cost`
- `crew:agent-maker`

Do not reinterpret these commands as requests to inspect the repository, run
Gradle, run npm, run CI, lint, test, or perform a host-default validation pass.

## Natural-Language Routing

When the user asks Codex to build, implement, create, add, update, fix, remove,
move, change, migrate, refactor, replace, extend, integrate, test, deploy,
merge, roll back, or otherwise perform development work, route the request
through `crew:run`.

`crew:agent` is read-only in Codex. Use it only for explanation, lookup,
investigation, or normalization tasks that do not mutate files, docs, issues,
commits, or any other repo/state artifact. If the request would change
anything, use `crew:run`.

This also covers **artifact and documentation edits** — any request to modify,
save, publish, refine, or update repo/worktree/state artifacts (including
markdown files, issue drafts, work-item descriptions, docs, or any file the
assistant previously saved) must be routed through `crew:run`. Do NOT apply
such edits directly via `apply_patch`, `Edit`, `Write`, or `MultiEdit` tools.

This includes Korean equivalents such as:

- `구현`, `개발`, `추가`, `수정`, `개선`, `보완`
- `변경`, `삭제`, `이동`, `마이그레이션`, `리팩터링`
- `테스트`, `배포`, `머지`, `롤백`, `반영`
- `정리`, `저장`, `발행`, `고쳐`, `업데이트` (artifact/document mutation verbs)

Examples that MUST route through `crew:run` (not handled inline):

- `"여기까지 내용 정리해서 클로드가 저장했던 파일에 수정해주세요"` — artifact update
- `"이슈 초안에 이 내용 반영해줘"` — issue draft edit
- `"문서 업데이트해줘"` — documentation update
- `"저장된 파일에 수정사항 넣어줘"` — saved file edit

Do not start by reading repository files, running shell commands, editing files,
or asking implementation questions unless the loaded command definition requires
that step.

Respond directly only when the user is asking a pure explanation or diagnostic
question, such as "how", "why", "what", "explain", "describe", `어떻게`, `왜`,
`무엇`, or `설명`, and the message does not also request implementation.

## Dependency Inversion Boundary

Keep workflow decisions dependent on the provider-neutral command definitions
under `~/.agent-crew/commands/` and global rules under `~/.agent-crew/AGENTS.md`.
Codex-specific behavior in this skill may only select and invoke those workflow
intents. Do not duplicate supervisor, planner, backend, frontend, resolver, or
approval logic inside this skill.

## Execution Map

Load and follow the matching command definition:

| User command | Command definition |
|---|---|
| `crew:setup` | `~/.agent-crew/commands/setup.md` |
| `crew:run` | `~/.agent-crew/commands/run.md` |
| `crew:status` | `~/.agent-crew/commands/status.md` |
| `crew:cost` | `~/.agent-crew/commands/cost.md` |
| `crew:agent-maker` | `~/.agent-crew/commands/agent-maker.md` |

If the command definition file is missing, tell the user to install agent-crew
globally first.

## `crew:setup` Rules

For `crew:setup`, execute the setup workflow directly:

1. Read `~/.agent-crew/commands/setup.md`.
2. Follow its steps exactly.
3. Run the host adapter setup dispatcher as specified there.
4. Initialize the agent-crew state directory.

Before setup, do not inspect repository build files, package manifests, Gradle
configuration, CI files, or existing source code unless the setup command file
explicitly asks for that.

## `crew:run` Rules

For `crew:run`, execute the full orchestration workflow from
`~/.agent-crew/commands/run.md`:

1. Treat arguments after `crew:run` as task descriptions.
2. If no task description is provided, follow Step 1 of the command definition
   and ask for the task through the host structured input UI.
3. Perform mandatory requirements collection.
4. Delegate to supervisor as defined by the command.
5. Show the required run and implementation summaries.

Never replace `crew:run` with `./gradlew check`, `npm test`, linting, generic
CI, repository validation, or direct implementation.

## Codex Auto-Route Fallback

For a natural-language implementation request, behave as if the user had typed:

```text
crew:run "{original request}"
```

Then execute the full `crew:run` workflow from `~/.agent-crew/commands/run.md`.
Preserve the original user wording as the task input, subject to the command
definition's required normalization and requirements-collection steps.

## Capability fallbacks

Codex does not currently expose a native structured-question tool. The Codex
adapter therefore advertises `interactive_question = false` in its
`capabilities.json` (see `core/rules/host-capabilities.md` and
`core/rules/capabilities/interactive-question.md`).

When core emits an `ask_question(prompt, options[])` intent — for example, at
the `crew:run` Step 1.5 injection prompt, the supervisor Phase 1d plan
approval gate, or the Phase 2.5 stage action gate — Codex MUST fall back to a
**structured markdown question** in the chat. The format is:

```markdown
{prompt}

Pick one (reply with the option number):

1. **{label_1}** — {description_1}
2. **{label_2}** — {description_2}
3. **{label_3}** — {description_3}
0. **cancel**
```

Rules for the markdown fallback:

- Always include numbered options (1..N) plus an explicit `0. **cancel**`.
- Use one option per line; do not collapse into prose.
- After printing, **stop and wait** for the user's reply. Do not infer the
  user's choice from prior context.
- When the user replies with a number, treat the corresponding option as the
  selected `chosen_label` and proceed exactly as `ask_question` would have on
  a host where `interactive_question=true`. When the user replies with `0`,
  `cancel`, `취소`, or any free-text refusal, treat the result as the
  `__cancelled__` sentinel and route to the cancel branch in the calling
  command definition.
- Never ask plain-text yes/no questions ("Should I deploy?", "Shall I merge?")
  — that violates both `core/rules/disambiguation.md` and the centralized
  approval-gate rule in `core/global-agents.md`.
- Cache the user's resolved choice in the task's state directory so a retry
  of the same stage does not re-prompt (see
  `core/rules/disambiguation.md` Implementation Requirements §4).

This fallback is the operational path for every `ask_question` intent emitted
by core when running under the Codex adapter. If a future Codex release
exposes a native elicitation surface, `adapters/codex/setup.sh` may flip
`interactive_question` to `true` and bind the intent to that surface in this
file's "Capability mappings" section (currently absent — Codex has no other
host-bound tool calls today, so no mapping table is yet warranted).

## Memory Contract

Before starting any non-trivial agent-crew workflow (`crew:run`, `crew:agent`,
diagnostics, issue publishing, or document mutation), consult the memory store
and capture substantive findings afterward.

### Before work — Recall

1. Run `mnemos search "<task keywords>"` using 1–3 keywords derived from the
   task description or the user's request.
2. If results are found, summarize them in 1–3 lines in your response before
   proceeding.
3. If mnemos is not installed, note `memory_unavailable` in your response and
   continue without blocking.

```bash
MNEMOS="${HOME}/.local/bin/mnemos"
if command -v "${MNEMOS}" >/dev/null 2>&1; then
  "${MNEMOS}" search "<task keywords>" 2>/dev/null || true
fi
```

### After work — Capture

After substantive findings, decisions, or completed work, run:

```bash
MNEMOS="${HOME}/.local/bin/mnemos"
if command -v "${MNEMOS}" >/dev/null 2>&1; then
  "${MNEMOS}" capture --layer session \
    --content "<insight / decision / root cause>"
fi
```

### Audit line (required in every final response)

Include one of these in every final response to make memory consultation
auditable:

- `Memory consulted: yes (N results)`
- `Memory consulted: no (mnemos unavailable)`

This line is advisory only — it does not gate workflow execution.

## Missing Route Contract

When a routed action is identified (via Natural-Language Routing above or an
explicit `crew:run` invocation) but cannot be executed because any of the
following conditions are true:

- The required user agent is not present in Codex discovery
  (`.codex/agents/<name>.toml` does not exist), OR
- The required adapter skill does not exist
  (`~/.agent-crew/user/skills/<skill>.md` is missing), OR
- No shell `crew` executable is available on PATH, OR
- The `crew:run` dispatch path is unavailable for any other reason

Then you MUST:

1. Output the structured block below in chat — do NOT proceed with direct API
   calls, `curl`, `gh issue create`, REST calls, or any other workaround:

   ```
   STATUS: BLOCKED
   BLOCKER: missing_route — {component} not available
   DETAIL: {one-sentence description of the missing component and how to install it}
   ```

2. Suggest the corrective action to the user, for example:
   - "Run `crew:setup` to install the Codex adapter and materialize user agents."
   - "Add the required skill file to `~/.agent-crew/user/skills/` to enable the missing capability."

**Rationale**: A direct API bypass (e.g. calling `gh issue create` directly when
`issuer` is not in Codex discovery) produces correct-shaped output but bypasses
the agent-crew audit trail, requirement collection, and quality loop. The
`STATUS: BLOCKED` return keeps the workflow observable and correctable.
