# interactive_question Capability

## Purpose

Core needs to ask the user a structured question with a fixed set of
labeled options (and a cancel option) at disambiguation points — for
example, the `crew:run` intent classifier when input is ambiguous, or
the task-injection planner when a duplicate task is detected. This flag
abstracts the host-specific mechanism (a native interactive tool, a
Codex modal, a future MCP elicitation surface, etc.) so that `core/`
never names a host-specific tool directly.

This is the concrete enabler of Invariant 3 (see
`core/rules/host-capabilities.md`): `core/` markdown files never name
host-specific tool identifiers; they name abstract capability intents.

## Required Adapter Surface (flag=true)

Adapter MUST provide:

| Abstract call | Purpose |
|---|---|
| `askQuestion(prompt, options[]) -> chosen_label \| "__cancelled__"` | Display the question + options, return the user's pick |

Where `options[]` is a list of `{ label, value?, description? }` and
the response is one of the option labels OR the sentinel cancellation
token.

The mechanism itself is the adapter's choice — a native interactive
tool, a modal dialog, a chat button row, an MCP elicitation surface,
whatever the host provides. The adapter binds the abstract call to its
chosen mechanism in `adapters/{host}/invocation.md` under an
"Interactive question mapping" section.

## Consumer Contract (core)

Concrete call sites:

- **`core/commands/run.md` intent classifier** (implemented — Phase A4,
  Step 1.7.5) — when input is ambiguous, the orchestrator routes
  through the disambiguation rule instead of guessing.
- **`core/rules/task-injection.md` disambiguation rule** (implemented
  — Phase A4) — when an injected task is a near-duplicate of an
  in-flight task, the user is asked to merge / queue / cancel.
- **`core/commands/agent-maker.md`** and other command-level "pick one
  of N" prompts as needed.

Call sites use the adapter mapping documented under
`adapters/{host}/invocation.md`. Adapters that cannot expose a native
surface use the markdown fallback documented under "Absence Behavior"
below. Codex is conditional: Plan mode can expose a structured input
surface, while Default mode uses markdown fallback.

Input shape: a list of options. Output shape: the chosen label, or the
cancellation sentinel. Core MUST handle the cancellation case
gracefully — default to a safe no-op, NEVER guess on the user's
behalf.

## Absence Behavior (flag=false)

Core emits a structured markdown question:

```markdown
Pick one (reply with the option number):

1. **{label}** — {description}
2. **{label}** — {description}
0. **cancel**
```

The model interprets the user's natural-language reply and routes
accordingly. This is the lowest-common-denominator UX every adapter
falls back to. The fallback is intentionally restrictive — it produces
a structured prompt, not a free-text yes/no question, which would
violate the plain-text approval prohibition enforced by Phase G6
(`core/scripts/check-plaintext-approval.py`).

## Prompt Language

Per `core/rules/output-language.md`, the question text and option
descriptions SHOULD match the user's input language (Claude does this
naturally). The **option labels** (the values returned by the host
back to core) MUST remain in a fixed canonical form — typically
English short strings like "Approve" / "Cancel" / "Inject" — so the
core routing logic can compare against them. Adapters that render
option labels with localized display strings MUST round-trip the
canonical label back to core unchanged.

## Adapter Examples

| Adapter | interactive_question | How it is implemented |
|---|---|---|
| claude  | true  | Native structured-question tool with labeled options and an implicit cancel. The adapter's `invocation.md` binds `askQuestion` to the native tool (mapping added in a later phase). |
| codex   | conditional | Plan mode maps to `request_user_input` when that tool is available; Default mode uses markdown fallback. |
| generic | false | Markdown fallback. |

## Related Files

Producer:

- `adapters/claude/setup.sh` (sets the flag)
- `adapters/claude/invocation.md` (mapping section to be added in a
  later refactor phase)

Consumer:

- `core/commands/run.md` (intent classifier disambiguation — Phase A4,
  implemented)
- `core/rules/task-injection.md` (duplicate-task disambiguation —
  Phase A4, implemented)

Companion rule:

- `core/rules/disambiguation.md` — the system invariant that decides
  *when* to ask (this capability decides *how*). The two are paired:
  the rule lists the trigger conditions, this doc specifies the
  rendering contract.

Cross-flag:

- Independent of `task_tools`, `hook_system`, etc. The user-facing
  approval UX (which option the user picks) flows through this
  capability; the wakeup signaling (TaskUpdate or 5-second poll) flows
  through `task_tools`. The two work in pairs but are gated
  independently.
