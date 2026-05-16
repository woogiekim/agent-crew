# Bench fixture: 3-endpoint API addition

This is a **mock specification** used solely by `core/scripts/bench-parallel.sh`
to drive dry-run dispatch counts and prefetch timing measurements. It is NOT
production planner output and MUST NOT be referenced by any live pipeline.

## Scenario

Add three independent REST endpoints to a hypothetical `orders` service:

| Unit | Endpoint              | Purpose                             | Files (mock)                     |
|------|-----------------------|-------------------------------------|----------------------------------|
| u1   | `POST /orders`        | Create a new order                  | `app/api/orders_create.py`       |
| u2   | `GET /orders/:id`     | Fetch a single order by id          | `app/api/orders_get.py`          |
| u3   | `PATCH /orders/:id`   | Update mutable fields on an order   | `app/api/orders_update.py`       |

Each endpoint owns a single source file; the file globs are disjoint, so
the planner is free to either bundle all three into one backend stage or
fan them out into three parallel units.

## Variants exercised

`bench-parallel.sh` generates three pipeline.json variants from this
specification and reports the agent-spawn count Phase 2 dispatch would
issue for each:

- **A — baseline**: single backend stage covering all three endpoints.
- **B — TDD parallel**: single backend stage with `tdd_parallel: true`,
  co-spawning a test-writer alongside the implementer.
- **C — sub-task fan-out**: single backend stage with
  `parallelizable_units: [u1, u2, u3]`, dispatching three backend
  agents concurrently — one per endpoint.

A theoretical **B + C** (TDD parallel AND fan-out on the same stage) is
computed for documentation; the planner is steered toward at most one of
the two flags per stage in MVP (see `core/agents/planner.md` § Interaction
with `tdd_parallel`).

## Why dry-run only

Live agent benchmarks would consume token budget and surface false
positives from network jitter and adapter cold-starts. The dispatch
contract in `core/agents/supervisor-stages.md` is deterministic — given
a pipeline.json shape, the spawn count is a pure function of the
encoding — so dry-run is sufficient to validate the routing logic.
Wall-clock savings are demonstrated separately by the Phase 1d prefetch
timing block, which exercises real shell I/O without any agent spawn.
