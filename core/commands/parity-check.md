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

3. **Static verification** (when MODE includes static)
   - Decompose `CONTRACT` into atomic, checkable assertions (e.g. "field `X` exists with type
     `Y`", "param `Z` is required", "response always includes `W`", "enum value `V` means the
     same thing on both sides").
   - For each assertion, search every repo in `REPOS` for the relevant symbol, endpoint, DTO
     field, table/column, or config key — read the actual defining source, not just a grep hit.
   - Classify each assertion:
     - **MATCH** — consistent evidence found in every repo where a definition should exist, with
       `file:line` citations from each side.
     - **MISMATCH** — evidence found but inconsistent (different name/type/nullability/semantics)
       — always include a concrete failure scenario: what breaks, for whom, under what input.
     - **UNVERIFIABLE** — no evidence found in one or more repos. State plainly whether this
       looks like a genuine absence, or whether it's plausibly generated/reflection-based/
       config-driven and out of static reach — do not guess which.

4. **API-based verification** (when MODE includes api)
   - If a reachable base URL, port, or credential is not obvious from repo config, ask the user
     (structured choice) rather than assuming a default environment.
   - Compose the smallest possible **read-only** requests that exercise `CONTRACT`.
   - Compare the actual request/response shapes across the involved services side by side.
   - **Never perform a mutating/destructive call** without going through the same centralized
     approval gate `crew:run` uses for destructive actions (structured choice with an explicit
     PLAN summary) — this command does not get its own weaker approval path.

5. **Synthesize the parity report**
   - Group all findings under `MATCH` / `MISMATCH` / `UNVERIFIABLE`.
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
MATCH: <N>
MISMATCH: <N>
UNVERIFIABLE: <N>
ARTIFACTS: <report path, if saved — otherwise "none">
```

## Rules

- Never hardcode a project name, repo path, or service name into the verification logic — every
  concrete detail comes from `CONTRACT`/`REPOS`/`MODE` at invocation time.
- Read-only by default. API mode may only mutate state after the same destructive-action
  approval gate `crew:run` enforces — no shortcut approval path for this command.
- A `MATCH` requires cited evidence from the producer side, not merely "no evidence of
  disagreement" — silence is `UNVERIFIABLE`.
- Keep every `MISMATCH` concrete: file:line or request/response evidence plus a real failure
  scenario, never a vague "may be inconsistent."
