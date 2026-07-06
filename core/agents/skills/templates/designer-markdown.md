---
name: designer-markdown
description: >
  Generic markdown design-spec output contract — fallback for the designer
  dispatcher when no vendor design tool is detected. Loaded when the designer
  agent's Step 0 axis resolves to `markdown` (no `.figma/`, no `*.sketch`, no
  `.penpot/` markers) OR when a vendor axis is detected but the corresponding
  `designer-<tool>` user-layer skill is not installed (degraded-fallback path).
  Captures the screen-list / component-definitions / interaction-flow /
  API-integration-points contract that `core/agents/designer.md` has always
  produced, now extracted into a Channel B seed template per
  `core/rules/agent-tool-dispatch.md`.
loaded_by: designer
axis: markdown
detection: |
  No vendor design tool detected (no .figma/ directory, no *.sketch files, no
  .penpot/ markers). Also used as the always-on degraded-fallback contract
  when a vendor axis is detected but its adapter skill is not installed.
---

Seed point — fallback for the designer dispatcher when no vendor design tool is detected.

# designer-markdown — Adapter Skill

This skill is the **Channel B seed template** for the `designer` dispatcher
when the detected axis is `markdown`. It is faithfully re-packaged from the
canonical screen-list / component-definitions / interaction-flow /
API-integration-points content that `core/agents/designer.md` and
`core/agents/skills/ux-design.md` already document — see
`core/rules/agent-tool-dispatch.md` § Channel B template seeding for the
runtime contract (`crew:setup` copy-if-absent; never overwrites a user edit).

## Output Contract

The designer agent's deliverable is a single markdown file:

- **Path**: `{TASK_DIR}/context/design-spec.md`
- **Format**: Markdown (no vendor-specific binary attachments, no Figma
  frame links required, no Sketch artboard references)
- **Return shape from the dispatcher**:
  `STATUS: completed | DESIGN_SPEC: {path} | SCREENS: {count}`

`design-spec.md` MUST contain the four sections defined below, in the order
listed:

1. Screen List
2. Component Definitions
3. User Interaction Flow
4. API Integration Points

The dispatcher updates `{TASK_DIR}/handoff.md` with the design-spec path,
recommended stack, and implementation priority **only when running
standalone** (skip when the prompt says "do not modify handoff.md").

## Screen List Format

Enumerate every screen the PRD's core features imply. For each screen
record at minimum:

| Field | Description |
|---|---|
| `id` | Stable identifier (kebab-case, e.g. `order-list`, `order-detail`) |
| `name` | Human-readable screen name (e.g. "Order List") |
| `url` | Route / URL path (e.g. `/orders`, `/orders/{id}`) |
| `purpose` | One-line user goal for the screen |
| `entry_points` | Where the user arrives from (nav, list row, CTA, deep link) |
| `exit_points` | Where the user leaves to (success / cancel / error destinations) |
| `primary_actions` | The 1–3 buttons that own the screen's primary intent |

Worked example (from `ux-design.md` § Screen Inventory):

```
Feature: Order Management
Screens:
  - id: order-list
    name: Order List
    url: /orders
    purpose: Show paginated order list with status filter
    entry_points: top nav, deep link
    exit_points: row click → /orders/{id}; CTA → /orders/new
    primary_actions: [New Order, Filter, Sort]

  - id: order-detail
    name: Order Detail
    url: /orders/{id}
    purpose: Show full order detail with line items and status
    entry_points: order-list row, deep link
    exit_points: Edit → /orders/{id}/edit; Back → /orders
    primary_actions: [Edit, Cancel Order, Print]
```

## Component Definitions Format

For each reusable UI component, write a spec that can be directly translated
to a prop interface by the frontend agent:

| Field | Description |
|---|---|
| `name` | PascalCase component name (e.g. `OrderStatusBadge`, `FilterBar`) |
| `props` | Typed inputs: each prop's name, type (or enum), and required/optional |
| `states` | Visible states (idle / loading / empty / error / success) |
| `event_handlers` | Outgoing events the parent must wire (e.g. `onCancel`, `onSelect`) |
| `accessibility_notes` | WCAG 2.1 AA requirements specific to this component |

Worked example (from `ux-design.md` § Component Specification):

```markdown
### OrderStatusBadge
- Props: status (PENDING | PAID | SHIPPED | CANCELLED)
- Rendering: colored chip — grey / green / blue / red
- Color is NOT the only status indicator (text label also shown — WCAG 1.4.1)
- No internal state
- No event handlers
```

Apply these tool-agnostic rules to every component spec:

- Color is never the only signal — every status indicator pairs color with
  an icon or text label (WCAG 1.4.1).
- Every interactive component lists its keyboard shortcut and focus order
  position when relevant.
- Loading / empty / error states are explicitly enumerated, not assumed.

## Interaction Flow Format

Document every user interaction that causes a state change or navigation
event. Use the from-screen → action → to-screen / state-change format:

```
User clicks "Cancel Order" in OrderActionMenu (on order-detail)
  → Confirmation modal opens ("Cancel this order?" with order summary)
  → User clicks "Confirm Cancel"
    → DELETE /orders/{id}
    → On success: row status updates to CANCELLED, success toast "Order cancelled"
    → On failure: error toast "Failed to cancel — please try again", modal closes
  → User clicks "Go Back"
    → Modal closes, no state change (Heuristic 3: user control and freedom)
```

Required coverage:

- Every primary action enumerated in the Screen List has at least one
  interaction flow entry.
- Every destructive action (delete, cancel, overwrite) shows the
  confirmation dialog and the escape route (Nielsen Heuristic 3).
- Every API call lists its success and failure paths explicitly.
- Empty / loading / error states for the screen are described, not just
  for individual components.

## API Integration Points Format

For each screen, list the API calls the frontend agent will need to wire.
This section becomes the contract handed to the backend agent (or to the
backend dispatcher's TDD cycle when a parallel backend stage is planned):

```markdown
Order List Screen (/orders):
  - GET /orders?status={filter}&page={n}&pageSize={size} — paginated list
  - DELETE /orders/{id} — cancel order (row action; requires confirmation)

Order Detail Screen (/orders/{id}):
  - GET /orders/{id} — full order data
  - PUT /orders/{id}/status — status update (supervisor action only)
```

Per endpoint, document at minimum:

- Method + path (templated with `{param}` placeholders)
- Query parameters (with type and default)
- Request body shape (reference the PRD schema by name; do NOT duplicate
  the schema definition — that lives in the PRD or backend handoff)
- Expected success response (status code + shape reference)
- Expected error response shapes (4xx / 5xx with user-facing message
  guidance)
- Authorization / authentication requirement, when not the screen default

## Quality Gates (before STATUS: completed)

Reference the checklist in `~/.agent-crew/system/agents/skills/ux-design.md`
§ Checklist. The dispatcher MUST verify the following before returning
`STATUS: completed`:

- [ ] All screens derived from PRD features are listed with URL and user goal
- [ ] Layout structure (named regions) defined for each screen
- [ ] Component definitions include props, state, and event handlers
- [ ] All user interaction flows documented (including confirmation dialogs and error paths)
- [ ] Loading, empty, and error states explicitly designed for each screen
- [ ] WCAG 2.1 AA requirements checked (contrast, focus order, status indicators, labels)
- [ ] Mobile-first layout defined; touch target sizes noted
- [ ] API integration points listed per screen
- [ ] `design-spec.md` written to `{TASK_DIR}/context/design-spec.md`
- [ ] Spec is concrete enough for the frontend agent to start coding immediately

## Future Vendor Adapters (NON-NORMATIVE)

This is the **seed point** for the designer dispatcher. Future vendor
adapters MAY ship as additional Channel B templates in the same flat
directory:

| Adapter | Resolved when | Likely additions on top of this contract |
|---|---|---|
| `designer-figma` | `.figma/`, `figma.config.json`, or `FIGMA_FILE_KEY` detected | Live Figma frame export; component-library lookup; design-token sync |
| `designer-sketch` | `*.sketch` file present | Artboard reference; symbol library lookup |
| `designer-penpot` | `.penpot/` or `penpot.config.json` detected | Penpot file pull; component library export |

Every future vendor adapter MUST keep this template's output contract:
the same four sections (Screen List, Component Definitions, Interaction
Flow, API Integration Points) written to
`{TASK_DIR}/context/design-spec.md`. This invariant is what makes the
frontend agent (and any downstream tooling that reads `design-spec.md`)
vendor-agnostic — `designer-markdown.md` is the contract; the vendor
adapters extend it without breaking it.

The dispatcher itself, `core/agents/designer.md`, does NOT need to
change when a new vendor adapter is added — the 5-step dispatch
protocol (`core/rules/agent-tool-dispatch.md`) already handles discovery
and load.

## See also

- `core/agents/designer.md` — the dispatcher that loads this skill when
  the markdown axis is resolved (or as the degraded-fallback target
  when a vendor axis is detected but its adapter skill is not installed).
- `core/rules/agent-tool-dispatch.md` — the 5-step dispatch protocol,
  naming convention, and Channel B template seeding contract.
- `~/.agent-crew/system/agents/skills/ux-design.md` — Nielsen heuristics,
  Gestalt principles, WCAG 2.1 AA, mobile-first responsive layout
  (declared agent-associated upfront load on the dispatcher side; this template
  references its content but does not re-document it).
- `core/agents/skills/templates/backend-kotlin-spring.md` — the parallel
  Wave-B exemplar shape this template mirrors structurally.
- `core/agents/skills/templates/issuer-plane.md` — the parallel Wave-B
  exemplar with full vendor-specific content (for reference once a
  future `designer-figma.md` adapter ships).
