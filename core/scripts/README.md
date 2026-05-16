# core/scripts/ — Provider-Neutral Helpers

Helpers that core code and host adapters can invoke without knowing
anything about the calling host. This directory is the canonical home
for **provider-neutral logic** that was previously inlined into host
hooks, agent prose, or `run.md` shell blocks.

## Contract

Every script under `core/scripts/` MUST satisfy:

1. **Stdin / stdout / exit code only.** No host-specific environment
   variables (e.g., `${HOOK_INPUT}` JSON shape) referenced directly. If
   structured input is needed, define it explicitly at the top of the
   script and document the JSON shape.
2. **No host-tool calls.** Never invoke any host-specific tool name
   directly (e.g., a host's native question, task-create, or background-spawn
   tools). Use the abstract capability intents documented under
   `core/rules/capabilities/`. The script computes a fact; the caller
   decides what to do with it.
3. **Idempotent and side-effect-minimal.** Read files, classify input,
   emit a result. Do NOT mutate `pipeline.json`, `progress.log`, or any
   pipeline state. State mutation is the caller's responsibility.
4. **Fail loudly.** Exit codes:
   - `0` — success / "ok"
   - `1` — soft failure (e.g., pattern not matched, threshold not
     exceeded). Caller decides if this is an error.
   - `2` — hard failure (malformed input, unreachable dependency).
     Caller should escalate.
5. **Self-documented.** First 20 lines explain: purpose, inputs,
   outputs, exit-code semantics, example invocation.
6. **Language choice:**
   - Bash (`.sh`) for simple text classification and file checks.
   - Python (`.py`) for anything with structured input/output, JSON
     parsing, or non-trivial logic. Python 3 only; no external deps
     unless agreed in the relevant capability doc.

## Why this directory exists

Two of the Three Invariants in
`core/rules/host-capabilities.md` are enforced here:

- **Invariant 1** (no direct host-tool calls): provider-neutral logic
  lives here so adapters can wire it into their hook mechanisms without
  re-implementing the logic per host.
- **Invariant 3** (no host-tool names in core/): when core needs to do
  something that could conceivably be done with a host-specific tool,
  the algorithm goes here as a script; the adapter decides how to
  invoke it.

## How adapters wire these in

| Adapter | Wiring mechanism |
|---|---|
| claude  | Hook scripts under `core/hooks/*.sh` call these scripts. `adapters/claude/setup.sh` registers the hooks via `settings.json`. |
| codex   | `adapters/codex/skill/agent-crew/SKILL.md` instructs the model to invoke specific scripts at specific lifecycle moments. |
| generic | `adapters/generic/invocation.md` documents the same expectations as guidance; the model invokes them best-effort. |

The capability `hook_system` (see `core/rules/capabilities/hook-system.md`)
gates whether hook-based enforcement is strict or advisory; the scripts
themselves are the same code either way.

## Planned scripts

These scripts are referenced by various capability docs but introduced
in later refactor phases. They do not exist yet — listing them here
documents the planned surface so adapter authors can prepare.

| Script | Phase | Purpose | Referenced by |
|---|---|---|---|
| `classify-trivial-intent.sh` | 0 | Decide whether an input matches one of the 7 trivial operations (merge, push, deploy, tag, rollback, status, commit_only) | `core/commands/run.md` |
| `detect-inject-intent.sh` | 14 | Detect inject-intent phrases ("추가로 해줘", "이것도 부탁해", etc.) and check session liveness | `core/rules/capabilities/hook-system.md` |
| `check-task-injection.py` | 14 | Disambiguate duplicate task injection against `session.json` | `core/rules/capabilities/hook-system.md` |
| `cost-aggregate.py` | E3.3 | Aggregate per-call token data into a per-task / crew-wide summary | `core/commands/cost.md`, `core/rules/capabilities/cost-tracking.md` |
| ~~`handoff-page-out.py`~~ | superseded by Phase 3.5 | Auto-summarize `handoff.md` when it exceeds a threshold (opt-in) — **now implemented via the documenter agent in `MODE=page-out`, not a standalone script**. See `core/agents/documenter.md` § Page-Out Mode and `core/agents/supervisor-stages.md` § Post-stage handoff page-out. | `core/rules/quality-loop.md` § Page-Out As Hygiene Operation |

Each script's introduction PR also adds a corresponding entry in the
relevant adapter (Claude wires it as a hook; Codex documents the
invocation in SKILL.md; generic adds guidance).

## Naming conventions

- Use kebab-case: `check-plaintext-approval.py`, not `check_plaintext_approval.py`.
- Prefix by category when helpful:
  - `check-*` for validators (return 0 = ok, 1 = violation)
  - `detect-*` for classifiers (return matched category or "none")
  - `classify-*` for intent classifiers (return one of N enum values)
  - `validate-*` for structural validators (return 0 = valid, 2 = invalid)
  - `aggregate-*` for collectors (emit JSON on stdout)
  - `cost-*` for cost-tracking (emit JSON on stdout)

## Related files

- `core/rules/host-capabilities.md` — capability registry and the Three Invariants
- `core/rules/capabilities/hook-system.md` — the capability that primarily wires these scripts
- `core/hooks/` — Claude-specific hook scripts; many of them will become thin wrappers around scripts in this directory as later refactor phases proceed
