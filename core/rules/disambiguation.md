---
name: disambiguation
description: >
  Apply at every point where intent, state, or routing is uncertain.
  Forbids heuristic guessing or silent defaults; requires routing the
  uncertainty to the user via the interactive_question capability with
  structured options. Caches the resolved decision to keep retries
  idempotent.
applies-to: run.md, task-injection.md, supervisor, replay, migration, all classifiers
---

# Disambiguation Rule

When intent is uncertain, route to structured user choice. Heuristic
guessing fails — it produces silently wrong answers that propagate
through the pipeline and are expensive to undo. This rule is a system
invariant: **no code path may silently default on uncertain input**.

## Principle

For every decision the system makes:

- If the input is **unambiguous**, decide and proceed.
- If the input is **ambiguous**, ask the user with a structured set of
  options. Never auto-decide.
- After the user picks, **cache the decision** to the task's state so
  the question is not asked again on retry.

This rule and the `interactive_question` capability (see
`core/rules/capabilities/interactive-question.md`) are paired: this
rule says *when* to ask; the capability says *how* to render the
asking.

## Triggers

The rule applies at every point in the pipeline where uncertainty
arises. Concrete trigger conditions:

| Trigger | Where | Resolution options |
|---|---|---|
| Intent classifier returns `ambiguous` | `core/commands/run.md` Step 1.7 (trivial-intent classifier) → resolved by Step 1.7.5 | (a) treat as trivial X, (b) treat as full dev task, (c) cancel and rephrase |
| Inject-phrase detector returns `maybe-inject` (false-positive risk) | `core/hooks/auto-route.sh` + the planned `core/scripts/detect-inject-intent.sh` | (a) inject into live session, (b) start independent task, (c) cancel |
| State file shape unexpected (migration scenarios) | `core/commands/update.md`, supervisor Phase 0 bootstrap | (a) attempt resume, (b) archive and start fresh, (c) abort |
| Multiple resume candidates | planned `crew:replay` command | (a) replay stage N, (b) replay stage M, (c) cancel |
| Duplicate task detection | `core/commands/run.md` Step 1.6 (dedup against live session, post-Step-1.5 injection detection) | (a) show in-flight status, (b) start as a new task anyway, (c) cancel |
| Concurrent session detected | `core/commands/run.md` Step 1.5 | (a) join the live session, (b) start a new session, (c) cancel |
| Workflow origin vs target scope ambiguity | `core/commands/run.md`, host wrapper skills, and review commands following `core/rules/lean-workflow-methodology.md` | (a) treat command token as workflow origin, (b) treat command/wrapper/SKILL.md as review target, (c) cancel and rephrase |

Any future trigger MUST be added to this table when introduced.

## Implementation Requirements

A code path that triggers disambiguation MUST satisfy all of the
following:

1. **Route through `interactive_question`.** Emit a logical
   `askQuestion(prompt, options[])` intent. The adapter's mapping
   layer fulfills it as either a native structured-question call (if
   `interactive_question=true`) or a structured markdown prompt (if
   `false`). Either way, the contract is the same: the user picks a
   labeled option.

2. **Always offer at least three options.** Two explicit choices plus
   a cancel option. The cancel option is mandatory — the user must
   always have a path that does nothing irreversible. (When more
   choices are needed, up to four total options is the practical
   ceiling.)

3. **Never auto-decide based on heuristic confidence.** "70% sure
   it's option A" is not acceptable grounds for proceeding without
   asking. The only acceptable auto-decision is when classification
   is fully unambiguous (regex-exact match, file-exists check, etc.).

4. **Cache the resolved decision** into the task's state (e.g.,
   `{TASK_DIR}/register.json` or `pipeline.json`) so that:
   - A retry of the same stage does not re-prompt the user.
   - A resume after interruption does not re-prompt the user.
   - The decision is part of the task's audit trail.

5. **Handle cancellation gracefully.** The cancel option (or the
   `__cancelled__` sentinel from `askQuestion`) MUST result in a safe
   no-op or a clean abort — never a partial state mutation.

## Forbidden

The following patterns are prohibited under this rule:

- **Heuristic majority-vote selection.** "Score each candidate, pick
  the highest" without offering the user the slate. Scoring is fine
  internally; silently selecting is not.
- **Silent default to "most likely" interpretation.** "Probably they
  meant X, going with that." The user does not see the alternatives.
- **Free-text yes/no questions** such as "Should I proceed?" or
  "Shall I merge and push?" — these violate both this rule and the
  plain-text-approval prohibition (enforced by Phase G6 hook —
  `core/scripts/check-plaintext-approval.py`).
  All questions MUST be structured options.
- **Implicit retry without re-asking.** If a stage retries after a
  cancelled disambiguation, the system MUST treat the cancellation as
  the cached answer and not silently re-prompt or silently proceed.
- **Asking the same question twice in one task.** Once cached, the
  decision is final for the lifetime of the task. If the user wants
  to change it, they cancel the task and rephrase.

## Adapter Compatibility

This rule is provider-neutral. Adapters fulfill it via the
`interactive_question` capability:

- `interactive_question=true` → adapter's native structured-question
  mechanism (mapped in `adapters/{host}/invocation.md`).
- `interactive_question=false` → core emits a structured markdown
  prompt; the model interprets the user's natural-language reply and
  routes accordingly. This is the lowest-common-denominator
  fulfillment and is always safe.

In both modes, the contract is identical: labeled options,
mandatory cancel, no free-text yes/no.

## Consumer Implementation Notes

Code paths that need to disambiguate MUST avoid naming any host tool
directly. The pattern is:

```
# Detect ambiguity (deterministic — no LLM)
result = classifier(input)
if result == "ambiguous":
    candidates = enumerate_candidates(input)
    options = [
        {"label": "Option A", "description": "..."},
        {"label": "Option B", "description": "..."},
        {"label": "Cancel",   "description": "Abort and rephrase"},
    ]
    chosen = ask_question(
        prompt=f"Input matched multiple intents: {candidates}",
        options=options,
    )
    if chosen == "__cancelled__":
        abort_gracefully()
    else:
        persist_decision_to_task_state(chosen)
        proceed_with(chosen)
```

The `ask_question` call here is a logical capability intent — the
adapter binds it to its host's tool in `invocation.md`. Core never
imports or references a specific tool name.

## Related Files

- `core/rules/capabilities/interactive-question.md` — the capability
  that fulfills this rule's "how to ask" half
- `core/rules/host-capabilities.md` — the Three Invariants
  (especially Invariant 3, which this rule operationalizes)
- `core/commands/run.md` — primary consumer (Step 1.5 injection
  detection, Step 1.6 duplicate-task detection, Step 1.7 trivial-intent
  classifier, Step 1.7.5 ambiguous-input handler)
- `core/rules/task-injection.md` — consumer (duplicate-task
  disambiguation, concurrent-session disambiguation)
- `core/commands/update.md` — consumer (state migration scenarios)
- planned `core/scripts/check-task-injection.py` — produces the
  `maybe-inject` signal this rule routes to user choice
