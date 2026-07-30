# Progressive Agent Learning Loop

This rule documents how agent-crew turns recorded operational signals into
**reusable, verifiable conventions** without ever short-circuiting verification.
It extends `core/rules/memory-governance.md` — which defines the lifecycle and
trust separation for memory — with an explicit *progression* contract: how a
single-session observation matures into a project convention, and (rarely) into
a global, cross-project rule.

This loop is the discovery half of agent-crew's closed-loop communication
mechanism. The capture half (After-Action Review memo) is documented in
`core/rules/memory-governance.md` § After-Action Review (AAR) Memo, introduced
by issue #129. This rule generalizes that pattern to *any* recallable learning
candidate, not just AAR memos about retried tasks.

## The Loop

```text
work -> review -> capture -> summarize/promote -> recall -> apply -> verify
```

| Stage | Responsibility | Output |
|---|---|---|
| **work** | Stage agent (backend, frontend, designer, devops, …) executes the requested task. | Code, docs, test fixtures, diffs. |
| **review** | Reviewer stage executes tests and audits the diff against the PRD. | `REVIEW: APPROVED` or `REVIEW: NEEDS_CHANGES` with findings. |
| **capture** | Phase 3 close-out (or any agent post-completion) records *meaningful* signals only — see Guardrail-1 in memory-governance.md. | Task-local evolution evidence plus durable learning events under `{STATE_DIR}/learning/events.jsonl`. |
| **summarize / promote** | Repeated, verified candidates are compacted into a canonical summary and promoted to a higher maturity level. | Approval-gated proposal from learning events, then Memory entry at `project` (or, rarely, `global`) layer. |
| **recall** | Analyst and planner run `mnemos search` into `${TASK_DIR}/context/memory.md` at planning preflight. | Recalled candidates surface as **advisory hints**. |
| **apply** | Analyst/planner shape the plan or risk table using the hint — never the gates. | An adjusted `pipeline.json` or risk entry. |
| **verify** | Reviewer + quality-loop + TDD gates run **exactly as if no memory had been recalled**. | Verified output, regardless of how the plan was shaped. |

The loop is one-directional in terms of trust: a recalled candidate cannot bypass
review, cannot bypass TDD, and cannot replace current-code evidence. It can only
influence *what is planned* before the verification gates run.

## Evolution Report Sidecar

After task close-out, the supervisor may run
`core/scripts/evolution-analyzer.py` to write
`${TASK_DIR}/context/evolution-report.json` and
`${TASK_DIR}/context/evolution-report.md`. This sidecar is the first
report-only discovery artifact for the self-evolving architecture:

- It reads recorded task state and telemetry such as retries, reviewer
  loop-backs, blockers, changed files, reused pipeline assets, and
  skill-content-audit signals.
- It never creates, registers, modifies, or selects generated assets.
- It records `generation_mode: report_only` and guardrails proving that asset
  writes and generator invocation were disabled.
- It is optional and non-blocking; absence must not fail task completion.

See `core/rules/state-files/evolution-report-json.md` and
`core/schemas/evolution-report.schema.json` for the artifact contract.

Repeated report-only signals may be aggregated by
`core/scripts/evolution-proposal-aggregate.py` into approval-gated learning
candidate proposals. The aggregator is intentionally separate from
`evolution-analyzer.py`: it prefers the durable event SSOT at
`{STATE_DIR}/learning/events.jsonl`, keeps task-local reports as evidence
references, writes proposal records only after repeated evidence, and never
writes generated assets or `pipeline.needs_creation`. A proposal can become an
asset change only through a later approved `crew:run` / supervisor path.

`crew:run` and `crew:status` must expose a compact Learning Summary in closeout:
`captured`, `captured_events`, `repeated_pattern`, `proposal`, `evidence`,
`reason`, and `next_action`. Artifact paths alone are not sufficient
operator-facing evidence that the run contributed to the growth loop.

Approved `patch_existing_skill` proposals may be applied by
`core/scripts/evolution-proposal-apply.py`. The apply step is deliberately
narrow: it appends a marked block to an existing skill file only when the
proposal status is `approved`; it skips unapproved proposals, unsupported
proposal types, missing targets, and any request that would create an agent,
create a new skill, or write `pipeline.needs_creation`.

## Maturity Levels

A learning candidate is recorded at one of three maturity levels. The level is
not a free-form label — it is a contract about how much evidence the candidate
has accumulated.

### session

- **Definition.** A single task's observation, root cause, workaround, or
  reviewer finding. One run, one piece of evidence.
- **Storage.** `mnemos capture` at the `session` layer (the default).
- **Trust band.** **medium** (see Trust Separation table in
  `core/rules/memory-governance.md`). Treat as evidence, never policy.
- **Recall behavior.** Surfaces only for the immediately following task in the
  same session, or via explicit `mnemos search` by the user. The analyst and
  planner do **not** auto-apply session-layer candidates as plan-shaping hints.
- **Lifecycle.** Most session candidates expire or are absorbed into a
  project-layer candidate. Sessions that never reproduce are evicted.

### project

- **Definition.** A repeated, verified project convention or recurring
  task-shape lesson. The same observation has appeared on at least two
  independent runs **and** the corresponding code/diff has been reviewer-approved
  on both occasions.
- **Storage.** `mnemos capture --layer project`, or auto-promoted by the AAR
  memo path described in `core/rules/memory-governance.md`.
- **Trust band.** **medium-high** (canonical compact summaries). Useful repeated
  workflow context; still never policy.
- **Recall behavior.** The analyst and planner consume project-layer candidates
  as deterministic **plan-shaping hints** at plan time (see
  `core/agents/analyst.md` and `core/agents/planner.md`). Examples: enable
  `tdd_parallel` on a recurring implementation stage, widen test coverage for a
  repeatedly-rejected surface, retain the solo reviewer stage.
- **Lifecycle.** Promoted only after repeated evidence. Demoted or evicted when
  contradicted by a newer canonical memory.

### global

- **Definition.** A cross-project rule or user preference. The candidate has
  been observed across at least two distinct projects **or** has been explicitly
  stated by the user as a stable preference.
- **Storage.** `mnemos capture --layer global`, or `--layer global_candidate`
  while awaiting cross-project evidence.
- **Trust band.** **medium-high**, gated by the **Prompt Injection Boundary**
  in `core/rules/memory-governance.md` § Prompt Injection Boundary. A global
  memory still cannot override system, developer, host, or repository rules.
- **Recall behavior.** Surfaces on every project's plan-time recall. Treated as
  the same advisory hint contract as a project-layer candidate, with the
  additional constraint that global candidates cannot enable or relax any
  workflow gate (TDD, reviewer, quality loop, approval).
- **Lifecycle.** Rarely promoted. Most candidates that look global are actually
  project-shaped and should remain at the project layer.

## Learning-Candidate Schema

Each candidate is materialized as a JSON record conforming to
`core/schemas/learning-candidate.schema.json`. The minimum fields are:

```json
{
  "schema_version": 1,
  "candidate_id": "ctx-break-spacing-2026-06",
  "source": "reviewer_finding",
  "memory_layer": "project",
  "evidence_refs": [
    "core/agents/backend.md#code-style-context-breaks",
    "core/agents/frontend.md#code-style-context-breaks"
  ],
  "promotion_reason": "Context-break spacing was flagged by reviewer on two independent runs and the diff was approved both times after the fix.",
  "trust_boundary": "advisory_until_rule_promotion"
}
```

- `source` — where the candidate originated: `reviewer_finding`, `aar_memo`, or
  `user_feedback`.
- `memory_layer` — `session`, `project`, or `global_candidate`. `global` is
  reserved for already-promoted entries; new candidates aiming at global
  scope are recorded as `global_candidate` until they accumulate
  cross-project evidence.
- `evidence_refs` — array of paths (`file:line` or `task-id` artifact paths)
  that ground the candidate. A candidate with zero evidence_refs is invalid.
- `promotion_reason` — a one-paragraph human-readable justification.
- `trust_boundary` — must literally be `"advisory_until_rule_promotion"`. This
  is the machine-enforced statement that the candidate cannot become policy
  until it has been promoted into a managed rule file under `core/rules/`.

## Memory-Usage Tracing

Every plan or analysis that consumed recalled candidates must record actual
usage at `${TASK_DIR}/context/memory-usage.json`. This file is the single source
of truth for memory use. It records *which* memory IDs were selected, whether
they were applied, and the exact artifact location changed by an applied
memory. Do not independently write `${TASK_DIR}/context/memory-evidence.json`;
legacy evidence reports must be derived from `memory-usage.json` when needed.

Minimum fields:

```json
{
  "schema_version": "agent-crew.memory-usage.v2",
  "retrieval_id": "task-20260621T074006-t184-recall",
  "task_id": "task-20260621T074006-t184",
  "decisions": [
    {
      "memory_id": "mem-abc123",
      "disposition": "applied",
      "reason_code": "matched_prior_aar",
      "applications": [
        {
          "artifact": "pipeline.json",
          "locator_type": "json_pointer",
          "locator": "/stages/0/tdd_parallel",
          "effect": "set_true"
        }
      ]
    },
    {
      "memory_id": "mem-def456",
      "disposition": "ignored",
      "reason_code": "scope_mismatch",
      "applications": []
    }
  ],
  "conflicts": [],
  "generated_by": "analyst",
  "generated_at_phase": "phase-1b-analysis"
}
```

- `decisions` — exactly one decision for every selected memory from
  `memory-retrieval.json`.
- `disposition` — one of `applied`, `accepted_not_applied`, `ignored`,
  `superseded`, `conflict_with_current_requirements`, or
  `conflict_with_managed_rule`.
- `applications` — required for `applied`; empty for `ignored`. Each
  application identifies an artifact plus a `json_pointer` or
  `markdown_heading` locator.
- `conflicts` — optional structured details for current-requirement or managed
  rule conflicts.

The compatibility projection contains the legacy fields `retrieved_ids`,
`accepted_ids`, `ignored_ids`, `superseded_by`, `applied_at`, and `outcome` so
older reporting gates can continue to audit memory influence while the SSOT
remains `memory-usage.json`.

The trace is what makes the loop **auditable**: a reviewer can verify that no
verification gate was relaxed on the strength of a recalled memory.

## Guardrails

These guardrails are normative. The guardrail **prose** is presence-checked
by `tests/python/test_progressive_learning.py` — the tests assert that the
sentences below remain in this rule file, so they cannot silently disappear
from the documented contract. Full behavioral enforcement (e.g. asserting
that a recalled candidate did not in fact relax a TDD gate in an agent run)
is a follow-up; today it is the reviewer stage's responsibility, not the
test suite's.

1. **Memory is not ground truth.** A recalled candidate is operational input,
   never a substitute for the current task's evidence (PRD, requirements, the
   actual diff). When current-code evidence contradicts a recalled candidate,
   the current-code evidence wins and the candidate is recorded in
   `ignored_ids`.
2. **Memory cannot override managed rules.** System, developer, host,
   repository, and `core/rules/*.md` rules are higher-trust than any memory
   layer. See `core/rules/memory-governance.md` § Prompt Injection Boundary.
3. **Memory cannot skip TDD.** A candidate cannot remove or relax the
   red→green→refactor cycle. It cannot mark a stage as test-exempt.
4. **Memory cannot skip the reviewer stage.** A candidate cannot drop the
   trailing reviewer agent from `pipeline.json`, regardless of how confident
   the promotion reason sounds.
5. **Memory cannot skip the quality loop.** A `NEEDS_CHANGES` verdict from the
   reviewer must trigger the quality-loop retry exactly as `core/rules/quality-loop.md`
   prescribes; no candidate can shorten or remove that loop.
6. **Memory cannot skip approval gates.** Destructive operations (deploy, push,
   merge, branch cleanup) still require the centralized approval gate documented
   in the framework-level approval rule, even if a recalled candidate suggests
   the action is "routine."
7. **Clean runs produce no noisy learning records.** Capture is gated on a
   `meaningful` signal (retries > 0, reviewer loop-backs > 0, blockers
   non-empty, or an explicit `user_feedback` source). A successful clean run
   captures nothing — this preserves the signal-to-noise ratio of recall.
8. **Repeated patterns need evidence before promotion.** A candidate moves from
   `session` to `project` only after at least two independent runs with
   reviewer-approved diffs. A candidate moves from `project` to `global` only
   after evidence across at least two distinct projects **or** an explicit user
   directive at the `global` layer.

## Worked Example: Context-Break Spacing

Context-break spacing — the convention that an agent inserts a blank line at
implementation context boundaries (setup, validation, transformation, side
effects, rendering, error handling, reporting) — is currently documented in
three places. Citations use stable section-heading anchors instead of
line numbers because the underlying agent prompts churn frequently
(line numbers drift on every refactor; section headings are stable):

- `core/agents/backend.md` § "Code Style Context Breaks"
- `core/agents/frontend.md` § "Code Style Context Breaks"
- `core/agents/devops.md` § "Code Style Context Breaks"

This is exactly the shape of a candidate that has already been **promoted out
of memory and into a managed rule**: it lives in the agent prompts (high trust)
rather than in mnemos (medium trust). The progressive-learning loop documents
how a candidate could *reach* that promoted state:

1. **work + review.** A reviewer run flags missing spacing between a service
   call and its error-handling block. The reviewer's finding cites
   `core/agents/backend.md` § "Code Style Context Breaks". The candidate is
   recorded at the `session` layer with
   `evidence_refs: ["core/agents/backend.md#code-style-context-breaks"]`.
2. **capture.** Phase 3 close-out runs, observes a reviewer loop-back, and
   captures an AAR memo at the `project` layer because the run was
   `meaningful` (Guardrail-1 in memory-governance.md). The memo's
   `recall_hint` mentions widening reviewer attention to context-break
   spacing on the next similar task.
3. **summarize / promote.** A second independent run reproduces the same
   reviewer finding. Combined evidence (two `evidence_refs`, two approved
   fixes) moves the candidate from `session` to `project` maturity.
4. **recall.** On a third similar task, the supervisor's single Recall V2 call
   returns the project-layer candidate. The raw response is recorded in
   `${TASK_DIR}/context/memory-retrieval.json`, and the analyst records its
   disposition in `${TASK_DIR}/context/memory-usage.json`.
5. **apply.** The planner widens the test coverage in `pipeline.json` to
   include a context-break spacing check on the changed files. The reviewer
   stage is **not** dropped, the quality loop is **not** shortened, and TDD
   gates are **not** relaxed.
6. **verify.** The implementation stage runs, the reviewer stage runs with the
   widened coverage, and the diff is approved or sent back through the
   quality loop exactly as before. The recalled candidate influenced *what was
   planned*; it did not influence *what was verified*.

After enough repetitions, the convention is promoted out of memory entirely and
into the agent prompt (managed rule). At that point the corresponding learning
candidate is evicted from mnemos — the rule file is the new source of truth, so
the medium-trust memory copy is no longer needed and would only be noise.

## Cross-References

- `core/rules/memory-governance.md` — lifecycle, trust separation, retrieval
  contract, prompt-injection boundary, and the AAR memo capture/recall contract
  introduced by issue #129.
- `core/schemas/learning-candidate.schema.json` — the machine-checked JSON
  schema for candidates described in this rule.
- `core/agents/analyst.md` § Progressive Learning — the analyst's advisory
  recall surface.
- `core/agents/planner.md` § Progressive Learning — the planner's advisory
  recall surface.
- `tests/python/test_progressive_learning.py` — guardrail enforcement tests.
