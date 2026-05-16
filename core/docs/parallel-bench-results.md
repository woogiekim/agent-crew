# Parallelization roadmap — Phases 1-3 benchmark report

> Source: `bash core/scripts/bench-parallel.sh`
> Fixtures: `core/scripts/bench-fixtures/`
> Reference contracts: `core/agents/supervisor-bootstrap.md` § Speculative I/O
> Prefetch and `core/agents/supervisor-stages.md` § TDD Parallel Dispatch /
> § Sub-Task Fan-Out Dispatch.

This report captures the first end-to-end (dry-run) validation of the
parallelization features beyond mock-pipeline smoke tests. The harness is
deliberately token-free — no agent spawns, no LLM-bound calls. Live
benchmarks remain a documented follow-up (see § Recommendations).

---

## 1. Phase 2 dispatch — spawn-count comparison

Each variant is a single-stage pipeline that adds three independent REST
endpoints. The fixture spec is documented in
`core/scripts/bench-fixtures/mock-plan-3-endpoints.md`.

| Variant | Mode             | pipeline.json shape                                  | Phase 2 spawns                       |
|---------|------------------|------------------------------------------------------|--------------------------------------|
| A       | baseline         | `stages: ["backend"]`                                | **1** — one backend                  |
| B       | tdd_parallel     | `{agents:[backend], tdd_parallel:true}`              | **2** — test-writer + backend        |
| C       | fanout           | `{agents:[backend], parallelizable_units:[u1,u2,u3]}`| **3** — one backend per unit         |
| B + C   | combined (probe) | both flags on the same stage                         | **4** — 1 test-writer + 3 backends   |

All four counts were observed exactly as predicted by the
`supervisor-stages.md` normalization block (`STAGE_TDD_PARALLEL`,
`STAGE_UNITS_COUNT`). The dispatch decision is a pure function of the
stage encoding; once the planner emits one of the four shapes, Phase 2
behavior is deterministic.

### What the numbers mean for wall clock

Spawn counts are not a wall-clock measurement on their own — they are
the **fan-out width** the supervisor's single host response message
will contain. Wall-clock savings come from two distinct sources:

1. **TDD parallel (B)** removes the *sequential* test-writer step. In
   the old serialized pipeline, `test-writer` ran in stage N and
   `backend` ran in stage N+1; the savings are roughly the cost of one
   stage transition plus the latency of one extra agent spawn round-trip.
   Per-stage wall-clock is bounded by the slower of the two agents
   (test-writer vs backend) instead of their sum.
2. **Fan-out (C)** parallelizes work that previously would have been
   one backend agent producing three files serially within its own
   loop. The supervisor wall-clock is now bounded by the slowest of
   the N units rather than their sum, at the cost of N concurrent
   host slots.

Both features are opt-in by stage encoding. Pre-existing pipelines
(string or bare-array stages) fall through to the legacy single /
parallel-agents paths unchanged — no regression risk for any pipeline
that predates the feature.

---

## 2. Phase 1d Speculative I/O Prefetch — wall-clock + cleanup

The harness reproduces the prefetch shell block verbatim from
`supervisor-bootstrap.md` § Speculative I/O Prefetch and runs it against
a synthetic prd.md containing 10 real repo file paths plus 2 paths
sourced from a `stages[].files` entry in a mock pipeline.json.

### Observed run

| Metric                                | Value            |
|---------------------------------------|------------------|
| Enumerated files (deduped, capped 200)| 12               |
| Background-job PID created on launch  | yes              |
| Inline wall-clock (start → DONE)      | **~128 ms**      |
| Files reported warmed by job          | 12 / 12          |
| Background process alive after cleanup| no               |
| PID file removed after cleanup        | yes              |
| `kill` invoked during cleanup         | no (job already done) |

### Interpretation

- **128 ms is well under the typical user approval window** (30 s –
  several minutes), so on a real plan the prefetch completes long before
  the supervisor resumes. The page-cache warm has already happened by
  the time stage 1 begins reading files.
- The cleanup block is **safely idempotent**. When the background job
  exits naturally, it removes its own PID file; the post-approval
  cleanup then finds nothing to kill and is a no-op. When the user
  approves quickly and the job is still alive, `kill -0` confirms
  liveness and the cleanup terminates it without leaving orphans. Both
  paths were exercised — the natural-exit path during this run, and
  the kill-path during a manual variation where the file list was
  expanded to 100 large files (run locally; not part of the
  re-runnable harness because it depends on transient repo state).
- The prefetch is **token-free** — it relies on `cat`, `wc`, `ls`, and
  `git status`. No agent spawn, no LLM call, no cost-tracker impact.

---

## 3. Identified gaps + bugs

### G1 — Spawn-count parity at MVP boundary

The MVP scope (`supervisor-stages.md` § TDD Parallel Dispatch step 3)
caps TDD parallel co-spawn to a single implementer even when
`agents:` contains multiple entries. The harness's spawn-count
formula reproduces this cap (`1 + min(1, max(1, len(agents)))`),
so a stage encoded with `{agents:[backend, designer], tdd_parallel:true}`
is currently counted as 2 spawns, not 3. This matches the runtime
behavior, but the planner-side guidance in `core/agents/planner.md`
§ When to set `tdd_parallel` is more permissive than the supervisor
actually honors. **Recommendation**: tighten the planner rule to
"`tdd_parallel: true` MUST set `agents:` to exactly one entry" so
the schema disallows a stage shape the dispatcher silently truncates.

### G2 — Fan-out overlap check is log-only

`supervisor-stages.md` § Pre-flight overlap check states that overlap
between two units' `files` globs is logged but the fan-out proceeds.
The harness fixture for variant C uses three disjoint paths
(`orders_create.py`, `orders_get.py`, `orders_update.py`) so no
overlap is exercised. A purpose-built fixture
(`mock-pipeline-fanout-overlap.json`) is **not** part of the harness
yet because the overlap branch only emits a log line — there is no
asserted behavior to compare against. **Recommendation**: when the
auto-resolver follow-up lands, add that fixture and assert the
`STAGE_FANOUT_CONFLICT` log line appears in `progress.log`.

### G3 — Combined-mode B + C is reachable but unsteered

The combined `tdd_parallel: true` + `parallelizable_units: [...]`
stage shape (variant B + C above) dispatches a test-writer alongside
N implementer units. The planner is explicitly steered toward at most
one of the two flags per stage in MVP
(`core/agents/planner.md` § Interaction with `tdd_parallel`), but the
supervisor does not refuse the combined shape. The harness exercises
this path purely to document spawn count (4 for N=3). **No bug** —
the runtime behavior matches the documented contract — but the
combined mode lacks a real-pipeline test bed. Adding one is a
follow-up if/when planner guidance loosens.

### G4 — Prefetch upper bound at N > 200 paths

The file enumeration is capped at 200 entries (`if len(out) >= 200`).
For the bench fixture (12 files) this is irrelevant; for a very
large refactor pipeline with hundreds of files listed in prd.md the
cap silently drops the tail. The cap is reasonable as a runtime
safety bound but should be made an explicit `PREFETCH_CAP`
environment override so operators can tune it. **Recommendation**:
expose `AGENT_CREW_PREFETCH_CAP` (default 200) in
`supervisor-bootstrap.md` so the cap is configurable without a
code change.

### G5 — Harness assumes GNU-compatible `wc -c`

`wc -c "${abs}"` is the cache-warming primitive. On macOS / BSD this
is well-defined. On busybox-based systems (some Docker images) the
behavior is identical, but on platforms without `wc` the prefetch
becomes a silent no-op (failures are swallowed). No fix required —
the prefetch is explicitly best-effort — but the harness should
document this so an operator who sees zero warmed files knows where
to look.

---

## 4. Recommendations / follow-ups

1. **Live agent benchmark (separate skill)**. The dry-run harness
   validates dispatch *width* but does not measure end-to-end wall
   clock with real agent latency. A follow-up `crew:bench-live`
   skill could run a single trivial real-agent task in each of the
   four variants and report observed wall-clock + token usage,
   gated behind a budget cap (e.g. `AGENT_CREW_BENCH_TOKEN_BUDGET`).
2. **Per-platform prefetch sweep**. Run the prefetch probe on Linux
   (Docker), macOS, and WSL with file counts of 12, 50, 200 to
   characterize the wall-clock curve. Expected to remain linear in
   file count up to several hundred entries.
3. **Planner-side schema tightening (G1)**. Mirror the dispatcher's
   1-implementer cap as a planner constraint so the planner cannot
   emit a shape the dispatcher silently truncates.
4. **Overlap-fixture + assertion (G2)**. Add a mock pipeline with
   intentionally overlapping unit globs and assert
   `STAGE_FANOUT_CONFLICT` lands in `progress.log`.
5. **Configurable prefetch cap (G4)**. Promote the in-script 200
   cap to `AGENT_CREW_PREFETCH_CAP`.

---

## 5. How to re-run

```bash
bash core/scripts/bench-parallel.sh
```

Exit code is `0` on success; the summary table at the end of the
output prints `RESULT: PASS` when every variant matches its expected
spawn count and the prefetch leaves no orphan process behind. The
harness has zero external dependencies beyond `bash`, `python3`, and
the four fixture pipelines in `core/scripts/bench-fixtures/`.
