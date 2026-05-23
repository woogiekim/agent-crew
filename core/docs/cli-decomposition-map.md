# Core CLI Decomposition Map

`core/bin/crew` remains the stable command entrypoint. New behavior should move
behind focused helpers when a responsibility can be tested without changing the
user-facing command surface.

## Extracted

- Cleanup dispatch: `core/scripts/crew-cli-cleanup.sh`
  - Owns `cleanup-state` and `cleanup-host-bridge` help text, helper lookup,
    and script execution.
  - `core/bin/crew` still performs runtime asset refresh before delegating.

## Remaining Candidates

- Sync responsibilities: asset drift detection, source checkout discovery, and
  managed PATH binary refresh.
- Report responsibilities: native report command dispatch and publication
  backend selection.
- Diagnostics responsibilities: doctor/config/debug command wrappers.
- State transitions: `run`, `agent`, `resume`, and `repair` state mutation
  dispatch.

## Migration Rule

Extract one command family at a time. Preserve existing stdout/stderr and exit
codes unless a task explicitly changes behavior, then cover that boundary with
focused tests before extracting another family.
