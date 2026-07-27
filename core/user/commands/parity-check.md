# /parity-check — Cross-repo contract parity verification

## Purpose

Given a specific contract, behavior, or feature that spans **two or more independent local
repositories** (e.g. a consumer service and the upstream/producer service(s) it calls, or
several services that must agree on a shared field/endpoint/schema), verify that the
implementations are actually consistent with each other — and report exactly where they agree,
disagree, or can't be confirmed.

This command is **fully general-purpose**: it does not hardcode any specific project, service
name, or repo path. The repo set, the contract being checked, and the verification method are
all supplied (or discovered) at invocation time.

## Trigger

- User names a specific contract/feature/endpoint/field and points at 2+ related local
  codebases to cross-check ("우리 쪽 구현이 실제 X 서비스 스펙이랑 맞는지 확인해줘",
  "이 필드가 다른 저장소 응답이랑 일치하는지 검증해줘").
- `/parity-check <contract description> <repo-path-1> <repo-path-2> [...]`

## Skip

- Only one repository is involved (that's an ordinary code review, not a parity check —
  use `/review` instead).
- None of the named repo paths are locally readable (nothing to compare against — report this
  and stop rather than guessing from memory).

## Inputs

- `CONTRACT` — free-text description of what is being verified (e.g. "회원 프로필 조회 API의
  필드/파라미터 정합성", "주문 상태 enum 값 일치").
- `REPOS` — 2+ local repo root paths to compare. Order is informational only (by convention the
  first is the "consumer"/implementation under test and the rest are "producer"/upstream
  sources), but every repo is read with equal rigor — no repo is assumed correct by default.
- `MODE` (optional) — `static` | `api` | `both` | other (caller-described method). If not given,
  ask via a structured choice.

## Flow

1. **Resolve REPOS**
   - If not provided as arguments, ask the user for the repo paths via a structured choice or
     free-text prompt. Do not guess paths from training data or prior sessions.
   - Verify each path exists and is readable (prefer a git repo, but a plain readable directory
     is acceptable for static mode). For any path that fails, report it and continue with the
     remaining repos — do not silently drop it from the final report.

2. **Resolve MODE**
   - If not specified, present a structured choice:
     - **정적 코드 비교만** — read/grep source across all REPOS, no network calls.
     - **실제 API 호출만** — exercise live endpoints and compare request/response shapes
       (requires a reachable environment).
     - **둘 다** — static first, then API calls to confirm anything static analysis left
       ambiguous.
     - **기타** — let the user describe a different verification method (e.g. comparing DB
       schemas directly, comparing config files, comparing generated client SDKs) and follow
       their description instead of forcing one of the above.

3. **Target discovery** (when MODE includes static)
   - Treat supplied documents, endpoints, symbols, and the contract description as
     starting points, not an upper bound on reachable scope. Freeze the declared work scope before
     following connections so discovery is exhaustive inside that boundary rather than an
     unbounded scan of every repository.
   - Discover every in-scope entrypoint that can reach the contract:
     - UI/client entrypoints such as JavaScript, TypeScript, JSX/TSX, JSP, PHP, HTML or other
       server templates, Vue or Svelte components, mobile clients, and GraphQL operations.
     - Server/process entrypoints such as routes, controllers, resolvers, consumers, jobs,
       schedulers, CLI handlers, and other framework-registered handlers.
   - When a UI/client surface exists, read the complete entrypoint file and every directly
     loaded in-scope child, model, component, or handler. Inventory every reachable API call,
     form action, event handler, message publish/consume operation, RPC, query, and downstream
     call; do not stop after finding the first documented endpoint.
   - When no UI/client surface exists, record the source evidence that established the relevant
     server/process entrypoints and report `UI_COVERAGE: not_applicable` with the reason.
   - Build an evidence-backed dependency graph for every reachable operation:

     ```text
     entrypoint
     -> handler/controller/resolver/consumer
     -> service/usecase
     -> client/DAO/repository
     -> helper/shared
     -> downstream API/message/database
     ```

     Every node and edge records the repository, `file:line`, symbol or method, and
     call direction. An endpoint string or grep hit that is not connected to the dependency
     graph is not parity evidence.
   - Classify every discovered operation:
     - `IN_SCOPE` — directly reachable from the declared user or system flow.
     - `OUT_OF_SCOPE` — discovered but excluded with a concrete boundary reason.
     - `CONTRACT_GAP` — reachable in code but absent from the supplied contract or documents.
     - `COVERAGE_GAP` — the call chain cannot be completed because source, dynamic wiring,
       generation, reflection, configuration, credentials, or runtime evidence is unavailable.
   - Target discovery is `completed` only when all in-scope entrypoints and dependency-graph
     edges are accounted for. Missing or unreadable evidence makes it `incomplete` or `blocked`;
     it never silently narrows the scope.

4. **Static verification** (when MODE includes static)
   - Decompose `CONTRACT` into atomic, checkable assertions (e.g. "field `X` exists with type
     `Y`", "param `Z` is required", "response always includes `W`", "enum value `V` means the
     same thing on both sides").
   - Apply the assertions to every `IN_SCOPE` operation from target discovery. Search every repo
     in `REPOS` for the relevant symbol, endpoint, DTO field, table/column, or config key and read
     both the defining source and the connected call path, not just a grep hit.
   - Classify each assertion:
     - **MATCH** — consistent evidence found in every repo where a definition should exist, with
       `file:line` citations from each side.
     - **MISMATCH** — evidence found but inconsistent (different name/type/nullability/semantics)
       — always include a concrete failure scenario: what breaks, for whom, under what input.
     - **UNVERIFIABLE** — no evidence found in one or more repos. State plainly whether this
       looks like a genuine absence, or whether it's plausibly generated/reflection-based/
       config-driven and out of static reach — do not guess which.

5. **API-based verification** (when MODE includes api)
   - If a reachable base URL, port, or credential is not obvious from repo config, ask the user
     (structured choice) rather than assuming a default environment.
   - Compose the smallest possible **read-only** requests that exercise `CONTRACT`.
   - Compare the actual request/response shapes across the involved services side by side.
   - In API-only mode, report source-level entrypoints and dependency edges that were not traced
     as `UNVERIFIABLE`; live response parity does not prove implementation-graph parity.
   - **Never perform a mutating/destructive call.** If verification would require one, stop and
     return the proposed action, scope, and risk. The user may continue only through a separate,
     explicit `crew:task` or `crew:workflow` request governed by the centralized Approval
     Service; this read-only command cannot cross that execution boundary.

6. **Synthesize the parity report**
   - Group all findings under `MATCH` / `MISMATCH` / `UNVERIFIABLE`.
   - Before reporting an overall result, verify that every in-scope reachable operation and every
     atomic assertion appears exactly once in those groups. Any unreviewed operation remains an
     explicit `UNVERIFIABLE` item and is included in the totals.
   - Every `MISMATCH` must carry: the concrete discrepancy, evidence from every side involved
     (file:line, or captured request/response), and a one-line "so what" (what actually breaks).
   - Never report a `MATCH` without cited evidence — absence of contradicting evidence is
     `UNVERIFIABLE`, not `MATCH`.
   - Offer to save the report to a markdown file (default: the invoking repo's
     `docs/parity/parity-check-<slug>-<timestamp>.md`). Ask before writing to any path outside
     the current repo.

## Output

```text
STATUS: completed | blocked | cancelled
SCOPE: <CONTRACT>
REPOS: <list of repo paths actually compared>
MODE: static | api | both | <custom>
TARGET_DISCOVERY: completed | incomplete | blocked
ENTRYPOINTS_READ: <repo, path, entrypoint symbol, or "none with reason">
IN_SCOPE_OPERATIONS: <reachable operations with file:line evidence>
OUT_OF_SCOPE_OPERATIONS: <excluded operations with boundary reasons>
CONTRACT_GAPS: <reachable operations absent from supplied contract/docs>
DEPENDENCY_GRAPH: <node and edge evidence for each in-scope operation>
UI_COVERAGE: completed | not_applicable | incomplete
COVERAGE_GAPS: <untraced paths and reasons, or "none">
MATCH: <N>
MISMATCH: <N>
UNVERIFIABLE: <N>
ARTIFACTS: <report path, if saved — otherwise "none">
```

## Rules

- Never hardcode a project name, repo path, or service name into the verification logic — every
  concrete detail comes from `CONTRACT`/`REPOS`/`MODE` at invocation time.
- Read-only in every mode. A required mutating action is reported but never executed by this
  command; it requires a separate explicit Task or Workflow request.
- A `MATCH` requires cited evidence from the producer side, not merely "no evidence of
  disagreement" — silence is `UNVERIFIABLE`.
- Incomplete target discovery or dependency-graph coverage MUST NOT report an overall `MATCH`.
- Endpoint-name-only comparison, an endpoint string or grep hit without its connected
  class/method graph, and document-only comparison are insufficient for `MATCH`.
- Every in-scope reachable operation and assertion must appear exactly once under `MATCH`,
  `MISMATCH`, or `UNVERIFIABLE`; unreviewed items cannot disappear from the report.
- Keep every `MISMATCH` concrete: file:line or request/response evidence plus a real failure
  scenario, never a vague "may be inconsistent."
