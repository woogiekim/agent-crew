# Repository / Workspace Evaluation

This evaluation compares long-term structures for agent-crew, mnemos, and host
adapters while preserving the stable memory provider contract.

## Options

| Option | Strengths | Risks | Release implications |
|---|---|---|---|
| Separate repositories with compatibility matrix | Preserves independent ownership and release cadence; smallest migration cost. | Integration drift is possible without explicit compatibility checks. | Publish matrix updates with agent-crew releases; mnemos can release independently. |
| Separate repositories plus shared contract package | Makes memory/provider schemas explicit and reusable across projects. | Adds a third artifact that must be versioned and installed. | Contract package needs semantic versioning; both repos pin compatible ranges. |
| Workspace / monorepo with strict package boundaries | Strongest integrated testing for host install, hooks, memory, and adapters. | Easy to accidentally introduce direct imports or path dependencies. | Coordinated releases become simpler, but independent patch releases need package-level versioning. |

## Boundaries

If a workspace is chosen, package boundaries should be:

```text
ai-runtime/
  packages/agent-crew/        # workflow, agents, hooks, host adapters
  packages/mnemos/            # memory backend and storage implementation
  packages/host-adapters/     # optional shared adapter packaging
  packages/shared-contracts/  # JSON schemas and CLI/API contract tests
  tests/integration/          # cross-package black-box tests
```

agent-crew may depend on `shared-contracts` schemas and command behavior, but
must not import mnemos code, read mnemos repository files, or assume mnemos
storage paths.

## Recommendation

Use separate repositories plus an explicit compatibility matrix now. Add a
shared contract package only when a second memory provider or a second consumer
needs the same schemas. Defer a monorepo until integrated release testing costs
exceed the overhead of coordinated package boundaries.

## Migration Plan

1. Keep `core/bin/memory` as the only runtime memory boundary.
2. Publish and maintain `docs/memory-provider-contract.md` and
   `docs/compatibility-matrix.md`.
3. Add contract tests in agent-crew that use stub mnemos CLIs instead of real
   mnemos storage.
4. Mirror the same tests in mnemos once fast JSON search is implemented there.
5. If drift persists, extract the JSON schemas and CLI fixtures into a shared
   contract package.
6. Only after the contract package stabilizes, evaluate a workspace/monorepo
   migration with package-level release automation.

This path improves integration confidence without coupling agent-crew to mnemos
internals.
