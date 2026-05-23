# Tool Sandboxing

Tool sandboxing in agent-crew is enforced by workflow policy, state gates, and
hooks. It does not claim to provide an operating-system sandbox unless a host
adapter explicitly advertises that capability.

## Layers

1. Capability manifest: role entries list `allowed_capabilities`,
   `denied_capabilities`, destructive permissions, and approval requirements.
2. Pipeline preflight: planned stages are checked against the manifest before
   runtime execution.
3. Direct-edit guard: source writes are blocked when no active crew task marker
   exists.
4. Dangerous-command guard: merge, push, deploy, and destructive commands need
   command-bound approval.
5. Forbidden-command guard: force push, `sudo`, and credential access are denied
   even when an approval marker exists.
6. Audit and reporting: guard decisions are written to local audit state and
   infrastructure failure signals can be captured by automatic issue reporting.

## Command-Bound Approval

Approvals must bind to the exact command and action kind. A reused, expired,
mismatched, or missing approval marker is treated as a blocker. Approval markers
are consumed after use, with a narrow duplicate grace window only for host
retries of the same command.

## Host Boundary

Adapters may map these controls to native surfaces such as hooks, task tools,
or sandbox modes. The core framework must remain correct when those surfaces
are unavailable by falling back to local files, explicit state, and structured
blockers.
