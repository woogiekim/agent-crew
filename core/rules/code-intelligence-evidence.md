---
name: code-intelligence-evidence
description: >
  Language-agnostic and provider-agnostic evidence contract for grounding code
  edits in semantic code facts before implementation and review.
applies-to: backend, frontend, reviewer, and any implementation agent that changes code
---

# Code Intelligence Evidence Rule

Implementation agents must ground code edits in first-party semantic evidence
instead of unsupported guesses. This rule is language-agnostic and
provider-agnostic: it defines the evidence contract, not a specific LSP,
compiler, IDE, host plugin, or vendor tool.

TypeScript LSP is one provider example. It is useful for TypeScript and
JavaScript projects, but the generic gate MUST NOT name the generic gate after TypeScript
or require TypeScript-specific tooling for non-TypeScript projects.

## Evidence Contract

When a task changes code and semantic tooling is available, write the evidence
to:

```text
{TASK_DIR}/context/code-intelligence-evidence.json
```

The artifact must be a JSON object with these fields:

```json
{
  "schema_version": 1,
  "language": "typescript | python | go | rust | java | kotlin | other | unknown",
  "provider": "typescript-lsp | pyright | gopls | rust-analyzer | jdtls | kotlin-lsp | compiler | fallback-static",
  "capabilities": ["definition", "references", "diagnostics", "type_info", "rename"],
  "queried_symbols": [
    {
      "symbol": "UserService.create",
      "purpose": "confirm existing API shape before adding caller",
      "evidence": "path/to/file.ext:42"
    }
  ],
  "caller_graph": {
    "scope": "approved module, public API, command, route, or target symbol",
    "entrypoints": [],
    "direct_callers": [],
    "indirect_callers": [],
    "callees": [],
    "consumers": [],
    "producers": [],
    "configuration_or_registration_paths": [],
    "tests": [],
    "coverage": "exhaustive_within_scope | partial | no_references_found | not_applicable",
    "unknowns": []
  },
  "diagnostics_before": [],
  "diagnostics_after": [],
  "unsupported_capabilities": [],
  "confidence": "high | medium | low"
}
```

The exact provider output may be summarized, but the artifact must preserve
enough first-party references for a reviewer to understand which definitions,
references, diagnostics, compiler checks, or static searches informed the code
change.

## Provider Selection

Choose the strongest available semantic evidence provider for the project:

| Language / stack | Preferred provider examples | Fallback |
|---|---|---|
| TypeScript / JavaScript | TypeScript LSP, `tsserver` | `tsc --noEmit`, ESLint, static search |
| Python | Pyright, Jedi, language server | `mypy`, `ruff`, `pytest`, static search |
| Go | `gopls` | `go test`, `go vet`, static search |
| Rust | `rust-analyzer` | `cargo check`, `cargo test`, static search |
| Java | JDT Language Server | `mvn test`, `gradle test`, compiler diagnostics |
| Kotlin | Kotlin language server or IDE metadata | Gradle compiler/test diagnostics |

If no semantic provider is available, use `fallback-static`, record the missing
capabilities in `unsupported_capabilities`, and lower confidence. Static search
or compiler output is acceptable fallback evidence only when the artifact says
what could not be verified semantically.

## Implementation Gate

Before modifying production code, implementation agents should query evidence
for the specific symbols, APIs, fields, imports, and call sites they intend to
touch. For low-risk docs-only changes this artifact is not required.

For a shared module, public API, route, command, persistence mapper,
serializer, schema, hook, adapter, or other cross-boundary change, include a
bounded caller graph inventory before implementation. Capture the reachable
entrypoints, direct and indirect callers, callees, consumers, producers,
configuration or registration paths, and tests that define observable behavior.
If static or semantic tooling cannot prove a path because of dynamic wiring,
generated code, reflection, external runtime state, or missing provider
capabilities, mark the graph `partial` and list the unknowns instead of
claiming exhaustive coverage.

Use `no_references_found` for the `No references found` claim state defined in
`core/rules/evidence-grounded-reasoning.md`: the stated search or
semantic-reference method found no references. It does not prove the behavior
is unused outside the declared search scope.

For code changes, do not invent:

- imports or module paths without repository evidence;
- method, field, event, route, schema, or configuration names without
  definitions or references;
- runtime guarantees from type annotations alone;
- casts, `any`-style escapes, broad exception handling, or ignore directives to
  silence diagnostics without a documented reason.

After implementation, rerun the best available diagnostics provider and record
`diagnostics_after`. If diagnostics cannot be run, record the explicit reason
and the fallback verification that was run instead.

## Reviewer Gate

Reviewer agents must read `context/code-intelligence-evidence.json` for code
changes when it exists. If a change introduces or rewires symbols, imports,
public APIs, routes, schemas, or cross-file calls and the artifact is missing,
the reviewer should return `NEEDS_CHANGES` unless the implementation recorded a
narrow exception explaining why semantic evidence was unavailable.

Reviewer conclusions must remain narrower than the evidence. LSP, compiler, or
static-search evidence can support symbol correctness and diagnostics status;
it does not prove product behavior, requirement coverage, authorization,
performance, or runtime data validity. Tests and other existing quality gates
still apply.

## Relationship To Other Rules

- `core/rules/evidence-grounded-reasoning.md` governs analysis, planning, and
  review claims. This rule applies the same first-party evidence discipline to
  code-change decisions.
- `core/rules/evidence-grounded-reasoning.md` also defines the
  Exhaustive Caller Graph Discipline. This rule records the implementation-side
  evidence for that discipline when code changes cross caller, contract, or
  side-effect boundaries.
- `core/rules/agent-tool-dispatch.md` governs how agents select provider
  adapters without leaking provider-specific behavior into generic agents.
- `core/agents/skills/tdd.md` remains mandatory for testable production-code
  changes. Semantic evidence does not replace Red -> Green -> Refactor.
