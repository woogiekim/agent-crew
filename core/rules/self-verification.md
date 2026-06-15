---
name: self-verification
description: >
  Applies to backend, frontend, test-writer, and any generic implementer.
  Requires each non-reviewer implementation agent to RUN its tests/build
  and quote fresh execution evidence before claiming STATUS: completed,
  instead of returning a static file list.
applies-to: backend, frontend, test-writer, generic-implementer
---

# Self-Verification Rule

## Intent

Every non-reviewer implementation agent must actually run its tests or
build command and quote a fresh, this-spawn execution result before
emitting `STATUS: completed`. Today these agents return only a static
file list as evidence (`TESTS: {file list}`) and defer all execution to
the reviewer's quality-loop gate. That single point of verification
inflates reviewer loop-backs for trivial "the file you wrote does not
parse / does not pass" defects and lets a stage legitimately claim
completion without ever running a test. This rule extends the existing
Issue #3 reviewer enforcement surface (`core/rules/quality-loop.md`)
with an implementer-side self-verification discipline. Its source is
the `docs/superpowers-benchmark/findings.md §3.2` re-analysis backlog
candidate #1.

## The Four-Step Gate

Before emitting `STATUS: completed`, the implementer MUST perform all
four steps in this exact order:

1. **IDENTIFY** the correct verification command for the change. This is
   the project's test/build runner discovered from manifests (e.g.
   `./gradlew test`, `mvn test`, `npx vitest run`, `pytest`, `cargo test`,
   `go test ./...`) — never an invented or partial subset, never an old
   transcript.
2. **RUN** that full command **fresh in this spawn**. Re-running is
   required even if "it just passed" earlier in the session.
3. **READ** the captured output: the exit code, the
   passed/failed/total counts, and the failure tail if any.
4. **VERIFY** that the run actually exercises the changed surface and
   that the result is acceptable for completion (passing run, or a
   documented skip via the Exception Path below).

Only after step 4 may the agent write `STATUS: completed`. Quoting an
old or cached run output as if it were fresh is forbidden (see
Anti-Fabrication Clause).

## Mandatory Completion-Report Evidence Line

Every `STATUS: completed` block from an in-scope agent MUST contain
exactly one `VERIFIED:` line with this shape:

```text
VERIFIED: tests=<RESULT> cmd=<CMD> exit=<CODE>
```

Where:

- `<RESULT>` is one of:
  - `<N>/<M>` — two non-negative integers, with `N` the passing-or-
    expected-to-pass count and `M` the total run count
    (`N <= M`). Example: `42/42`. The degenerate form `0/0` (no tests
    enumerated) is also valid; it indicates a legitimate run with
    zero discovered tests.
  - `skipped:<reason>` — a non-empty reason describing why no test
    run is possible. The two canonical reasons recognized by the
    reviewer are:
    - `no_runnable_harness` (or the equivalent kebab form
      `no-runnable-harness`) — there is no test framework wired to
      the change (pure markdown rule, docs-only, scaffold-only,
      red-phase test-writer whose implementer module does not yet
      exist).
    - `opt_out` — the planner set `requires_test_execution: false`
      on the reviewer stage and the agent legitimately has no
      runnable surface to verify.
- `<CMD>` is a non-empty token describing the command run, or `n/a`
  / `none` when `<RESULT>` is a `skipped:*` form (an empty `cmd=`
  field is invalid in any form).
- `<CODE>` is an integer exit code from step 3 (parseable by
  `int()`). For `skipped:*` forms the conventional value is `0`.

The line MUST appear in the agent's return block. It is in addition to
(not a replacement for) the existing artifact lines such as
`TESTS: {file list}` or `FILES: …` — those describe what was written;
the `VERIFIED:` line proves it was executed.

The default reviewer-side gate validates the **shape**, not the test
outcome: a pass form with a non-zero exit code is structurally valid,
and the reviewer's existing `STATUS: REJECTED REASON: tests_failed`
gate covers a failing run. The optional `--require-passed` enforcement
flag (`core/scripts/check-verification-evidence.py --require-passed`)
upgrades the gate to also reject `N < M`.

## Exception Path

When no runnable test harness exists for the change (pure markdown
rule, docs-only, scaffold-only) the agent MUST:

1. Emit the skip form `VERIFIED: tests=skipped:<reason> cmd=none exit=0`
   with `<reason>` set to `no_runnable_harness` or `opt_out` per the
   definitions above.
2. Write `{TASK_DIR}/context/tdd-exception.md` recording the reason and
   referencing the changed paths. The file's presence is the auditable
   trail; the reviewer cross-references it.

This mirrors the existing `REQUIRES_TEST_EXECUTION: false` semantics
documented in `core/agents/reviewer.md` § Inputs and
`core/agents/planner.md` § Reviewer opt-out. When the planner has set
`requires_test_execution: false`, the agent uses
`tests=skipped:opt_out`; otherwise (no runner at all, change is
docs-only) the agent uses `tests=skipped:no_runnable_harness`.

`tests=skipped:opt_out` is automatically valid when the planner has
set `requires_test_execution: false` on the reviewer stage. No other
skip reason is accepted.

## Anti-Fabrication Clause

The agent MUST NOT claim verification by quoting old, cached, or
remembered output from an earlier session, an earlier turn, or a
hypothesized run. The `VERIFIED:` line MUST be derived from a command
that was executed in **this** spawn, on the working tree as it stands
at completion. Reviewers and the optional enforcement script validate
the line's shape; the implementer is on its honor for freshness, and
fabrication is a quality-loop violation that the reviewer's existing
loop-back machinery handles.

## Reviewer-Side Cross-Reference

The reviewer's quality-loop gate (`core/rules/quality-loop.md` §
"Test execution requirement") rejects a `STATUS: completed` that lacks
a valid `VERIFIED:` line. The rejection signal is
`STATUS: REJECTED REASON: missing_verification_evidence`, which feeds
the existing Issue #3 loop-back budget — no parallel framework. The
reviewer accepts `tests=skipped:opt_out` as automatically valid when
the planner set `requires_test_execution: false` on the reviewer
stage; otherwise the skip reason MUST be `no_runnable_harness` and a
`{TASK_DIR}/context/tdd-exception.md` MUST exist.

The optional enforcement script
`core/scripts/check-verification-evidence.py` mechanically validates
the line's shape (stdlib-only Python 3, mirrors the convention of
`core/scripts/check-plaintext-approval.py`).

## Examples

### Valid pass forms

```text
VERIFIED: tests=42/42 cmd=./gradlew test exit=0
VERIFIED: tests=18/18 cmd=npx vitest run exit=0
VERIFIED: tests=126/126 cmd=python3 -m pytest tests/ exit=0
```

### Valid skip forms

```text
VERIFIED: tests=skipped:no_runnable_harness cmd=none exit=0
VERIFIED: tests=skipped:no-runnable-harness cmd=n/a exit=0
VERIFIED: tests=skipped:opt_out cmd=none exit=0
```

### Invalid lines (rejected by the gate)

```text
# Missing line entirely (no VERIFIED line at all)
STATUS: completed
TESTS: tests/foo_test.py

# Empty skip reason
VERIFIED: tests=skipped: cmd=pytest exit=0

# Non-integer exit
VERIFIED: tests=10/10 cmd=./gradlew test exit=success

# Wrong field order or missing field
VERIFIED: cmd=./gradlew test exit=0
VERIFIED: tests=10/10 exit=0
VERIFIED: tests=10/10 cmd=pytest

# N > M (more passing than total)
VERIFIED: tests=15/12 cmd=./gradlew test exit=0

# Empty cmd
VERIFIED: tests=12/12 cmd= exit=0
```

## Scope

In scope: `backend`, `frontend`, `test-writer`, and any generic
implementer.

Out of scope this rule (covered elsewhere or excluded by design):
- `devops` runs PLAN → approval → execute with a different
  verification shape.
- `qa-owner` is the verification owner, not a self-verification target.
- `reviewer` body — the reviewer's Issue #3 quality-loop flow already
  covers the new `missing_verification_evidence` reason via this
  rule's cross-reference.
