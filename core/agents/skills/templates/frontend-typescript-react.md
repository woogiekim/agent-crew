---
name: frontend-typescript-react
description: >
  Adapter skill for the `frontend` dispatcher (Wave C exemplar). Loaded when
  the dispatcher detects a React + TypeScript manifest (`package.json` with
  `react` and without `next`). Captures the TypeScript/React/Vitest+RTL/
  `npx tsc --noEmit` stack contract that the framework's frontend agent has
  historically embedded inline, now extracted into a Channel B seed template
  per `core/rules/agent-tool-dispatch.md`.
loaded_by: frontend
axis: typescript-react
detection: package.json containing `react` (and not `next`)
---

# frontend-typescript-react — Adapter Skill

This skill is the **Channel B seed template** for the `frontend` dispatcher
when the detected manifest axis is `typescript-react`. It is faithfully
re-packaged from the canonical TypeScript/React + TDD content that
`core/agents/frontend.md` documented prior to the Wave C refactor — see
`core/rules/agent-tool-dispatch.md` § Channel B template seeding for the
runtime contract (`crew:setup` copy-if-absent; never overwrites a user
edit).

## Tech Stack

- **Language**: TypeScript
- **Framework**: React (or project equivalent)
- **Test**: Vitest + React Testing Library (or Jest equivalent)
- **Type check**: `npx tsc --noEmit`

## TDD Cycle (RED → GREEN → REFACTOR)

The frontend agent's TDD contract is non-negotiable. For each component
or behaviour unit, execute the full cycle:

```text
RED      → Write failing component test → npx vitest → confirm failure (test MUST fail at this step)
GREEN    → Write minimal component implementation → npx vitest → confirm pass
REFACTOR → Improve component design, extract sub-components → npx vitest → confirm still passes
```

When the project uses Jest instead of Vitest, substitute the equivalent
runner invocation (`npx jest` or the project's `npm test` script). The
runner choice is project-detected — the dispatcher confirms which runner
the project exposes at Phase 1.

**Test-first enforcement (non-negotiable):**
- Write the failing test FIRST. Component implementation code MUST NOT be
  written until a failing test exists and has been confirmed to fail.
- Every new component MUST have a corresponding test file before the
  component file is created.
- Test files MUST be committed in the same commit as the component they
  cover.

## Test File Naming Convention

| Test type | Filename pattern |
|---|---|
| Component test | `{ComponentName}.test.tsx` |
| Component test (alternate) | `{ComponentName}.spec.tsx` |
| Hook / pure-TS test | `{name}.test.ts` |

Test files live **adjacent to the component file** they cover (sibling
file, not a separate test tree), so a developer reading `Button.tsx`
finds `Button.test.tsx` in the same directory.

## Test Case Name Convention

Test case names follow the language-agnostic nature prefix contract from
`tdd.md`: `<nature-prefix>[(<qualifier>)] - <behavior>`.

Vitest / Jest examples:

```typescript
test("success-case - renders the enabled submit button", () => {})
test("failure-case(validation) - disables submit when the form is invalid", () => {})
```

**Test target naming convention**: default the component, hook result,
rendered wrapper, or other primary system under test variable to `sut`
when a target variable is introduced. Keep props, fixtures, user events,
and query results domain-specific.

**Minimum test coverage per component**: renders without error + at
least one interaction or prop variation test.

## Coverage Gate

**100% changed executable coverage**. Every new or modified component
branch, prop variation, state transition, user interaction, rendering
path, and documented failure mode must be covered by an automated test
or listed as a narrow exception in
`{TASK_DIR}/context/test-coverage.md`.

## Type Safety

- Run `npx tsc --noEmit` before declaring `STATUS: completed`. A type
  error is a completion-blocker.
- Apply `~/.agent-crew/system/agents/skills/effective-typescript.md`
  rules: prefer `unknown` over `any`, discriminated unions over flag
  fields, and strict-mode conventions throughout.

## Component Decomposition + Prop Design

When implementing UI, design the component tree around the principles in
`~/.agent-crew/system/agents/skills/ui-component-design.md`:

- **Single responsibility per component** — a component renders one
  concern. Containers compose; leaves render.
- **Prop design** — props describe what the component needs to render,
  not how it should fetch or mutate state. Lift data-fetching and
  side-effect orchestration to the container.
- **Composition over configuration** — prefer child-rendering and slot
  props over deeply enumerated `variant="..."` switches.

For data-fetching and state management that crosses UI/API boundaries,
additionally consult
`~/.agent-crew/system/agents/skills/clean-architecture.md` to keep UI
components free of business logic.

## React Testing Library Idioms

When using Vitest + RTL (the documented worked example):

- Query by **accessibility role** first (`getByRole('button', { name })`),
  then by visible text, then by test-id. Test-id queries are a last
  resort.
- Drive user interactions via `userEvent` (not `fireEvent`) — RTL's
  user-centric default — so timing semantics match real usage.
- Assert on **user-visible behavior** (rendered text, ARIA state, focus
  movement), not on implementation details (internal state, hook
  return values).

For project codebases that use Jest + RTL, the same idioms apply — only
the runner CLI changes.

## Commit Conventions

- `git commit` is the closing step of every TDD cycle (post-REFACTOR).
- A commit containing only component files (no tests) is a pipeline
  violation and MUST be rejected.
- The commit MUST include both test files and component files.
- All tests must be GREEN (`npx vitest` / `npx jest` / `npm test`) and
  type checks must pass (`npx tsc --noEmit`) before commit.

## Verification Checklist (before STATUS: completed)

- [ ] Every new/modified component has a corresponding test file
- [ ] All component tests pass (`npx vitest` / `npx jest` / `npm test` —
      must exit 0)
- [ ] 100% changed executable coverage is satisfied or every exception
      is narrowly justified in `{TASK_DIR}/context/test-coverage.md`
- [ ] All screens implemented per design-spec
- [ ] Component specs from design-spec satisfied
- [ ] Interaction flows correct
- [ ] API integration interfaces defined
- [ ] Type checks pass (`npx tsc --noEmit`)
- [ ] `{TASK_DIR}/context/tdd_log.md` updated with all TDD cycles

If no test framework is available in the project, halt and report
BLOCKED — do not implement without tests.

## Layered Architecture Notes (React-specific)

When crossing UI/API boundaries (data fetching, state mutation), apply
the Dependency Rule from
`~/.agent-crew/system/agents/skills/clean-architecture.md`. In a
TypeScript/React codebase, this typically means:

- Components depend on hooks; hooks depend on service modules; service
  modules depend on the network/storage adapter — never the inverse.
- Components do not call `fetch` / `axios` directly. They call a hook
  (`useOrder`, `useCart`) which encapsulates the data-fetching contract.
- DTOs are the transport boundary; rendered view models do not leak the
  raw API response shape into the JSX.

## See also

- `core/agents/frontend.md` — the dispatcher that loads this skill when
  the typescript-react axis is resolved.
- `core/rules/agent-tool-dispatch.md` — the 5-step dispatch protocol,
  naming convention, and Channel B template seeding contract.
- `~/.agent-crew/system/agents/skills/tdd.md` — the language-agnostic
  TDD cycle (declared on-demand load).
- `~/.agent-crew/system/agents/skills/effective-typescript.md` —
  TypeScript language best practices (declared on-demand load).
- `~/.agent-crew/system/agents/skills/ui-component-design.md` —
  component decomposition + prop design (declared on-demand load).
