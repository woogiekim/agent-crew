# Faster parallel processing research plan

This note resolves #68 and links the parallel-throughput work back to #66 and
#67. It is scoped to tooling, docs, config, command wiring, scripts, and
validation assets.

## Highest-impact bottlenecks

| Rank | Bottleneck | Why it matters | Measurement |
|---|---|---|---|
| 1 | Supervisor startup and command/agent bootstrap loading | Every task pays this before useful work starts. | Startup latency: `crew:run` invocation to each supervisor `STARTED` event. |
| 2 | Worktree setup for N > 1 | `git worktree add` is I/O-bound and scales with task count. | Per-worktree and total wall-clock for N = 2, 4, 8. |
| 3 | Requirements collection for ambiguous tasks | It blocks supervisor spawn when prompts are underspecified. | Time from task context creation to requirements.md written. |
| 4 | Mnemos calls in routing/prefetch | #66 observed foreground commands that can hang. | Count, duration, timeout count, and result count per phase. |
| 5 | Result collection polling | Fixed polling can add latency after the final result is written. | Time from last `result.md` terminal write to `crew:status --collect` completion. |
| 6 | Approval gates for parallel runs | N independent pauses reduce parallel throughput. | Time spent in Phase 1d and action gates for N = 2, 4, 8. |

## Benchmark scenarios

The benchmark set covers task cardinality and stage fan-out separately:

| Scenario | N | Worktrees | Supervisor spawns | Stage fixture |
|---|---:|---:|---:|---|
| Single task | 1 | 0 | 1 | baseline, TDD, fan-out, combined |
| Small fan-out | 2 | 2 | 2 | baseline, TDD, fan-out, combined |
| Medium fan-out | 4 | 4 | 4 | baseline, TDD, fan-out, combined |
| Large fan-out | 8 | 8 | 8 | baseline, TDD, fan-out, combined |

Stage fixture widths are validated by `core/scripts/bench-parallel.sh`:

| Fixture | Stage shape | Per-task Phase 2 spawns |
|---|---|---:|
| baseline | `["backend"]` | 1 |
| TDD parallel | `{agents:[backend], tdd_parallel:true}` | 2 |
| sub-task fan-out | `{agents:[backend], parallelizable_units:[u1,u2,u3]}` | 3 |
| combined | TDD + three units | 4 |

The Cartesian product gives expected Phase 2 spawn widths:

| N | baseline | TDD | fan-out | combined |
|---:|---:|---:|---:|---:|
| 1 | 1 | 2 | 3 | 4 |
| 2 | 2 | 4 | 6 | 8 |
| 4 | 4 | 8 | 12 | 16 |
| 8 | 8 | 16 | 24 | 32 |

## Measurable before/after targets

| Metric | Baseline | Target |
|---|---|---|
| Multi-task startup latency | Current dry-run documents dispatch width only. | Add wall-clock capture for N = 1, 2, 4, 8. |
| Injection latency | Not currently benchmarked on Codex because `agent_background=false`. | Add a session.json append dry run and status-visibility timing. |
| Bootstrap overhead | Not centrally counted. | Count command/agent/skill files and bytes read per run. |
| Mnemos overhead | Unbounded foreground behavior and Obsidian sync writes were observed in #66 and the sixth commercialization E2E. | Support-path memory search uses read-only FTS first, captures default to local mnemos storage unless `MNEMOS_BACKEND` is explicit, and every fallback CLI call has a visible timeout path. |
| Result collection latency | 5-second file-poll fallback documented. | Prefer progress-buffer/session reads and reduce avoidable fixed waits. |
| Worktree setup cost | Not isolated from agent runtime. | Measure per-worktree and total setup time for N = 2, 4, 8. |

## Recommendations

1. Keep `agent_background`, `task_tools`, and `monitor_tool` as explicit
   capability gates. Codex native subagents are useful for parallel execution,
   but they must not be treated as `agent_background=true` until the active
   runtime exposes a callable background spawn surface plus a later observation
   path. Tool-backed Codex sessions that do not expose such a tool stay on the
   file-based fallback path.
2. Use `core/bin/memory` for support-path memory calls. It provides read-only
   FTS recall, local support captures, and bounded mnemos fallback timeouts.
3. Extend `bench-parallel.sh` output with N = 1, 2, 4, 8 scenario rows and keep
   the existing stage-width fixture checks.
4. Add a future `bench-worktree-setup.sh` that measures `git worktree add`
   independently from any agent runtime.
5. Keep project-local Codex stubs thin and preferred over global stubs; write
   regular `.codex/agents/*.toml` files instead of symlinks so Codex custom
   agent discovery sees the official TOML schema (`name`, `description`,
   `developer_instructions`) consistently.
6. Batch approval only where the host exposes a structured question capability.
   Codex remains on the markdown/fallback route until `interactive_question`
   changes.
7. For Codex-native parallelism, keep `.codex/config.toml` at
   `agents.max_threads = 6` and `agents.max_depth = 1` by default. Increase
   depth only for explicitly recursive delegation, because broad recursive
   fan-out raises token, latency, and local resource costs.

## Relationship to #66 and #67

- #66 supplies the mnemos and runtime-skill verification risks that can slow or
  destabilize parallel runs.
- #67 supplies the Codex routing/stub stabilization work that keeps bootstrap
  overhead bounded.
- #68 narrows those concerns to throughput: startup latency, bootstrap bytes,
  memory-call budgets, result collection latency, and worktree setup cost.
