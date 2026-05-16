# Skill: ux-design

## Purpose
Enables the designer agent to translate a PRD into a concrete, implementation-ready design specification that the frontend agent can use immediately without further design clarification.

## When to Apply
- When `design-spec.md` does not exist and frontend implementation is planned
- When a PRD introduces new screens, flows, or user-facing interactions
- When a significant UX change is required for existing screens
- Before any frontend coding begins

---

## Nielsen's 10 Usability Heuristics (Jakob Nielsen, 1994)

Apply these principles to every screen design. Violations become `WARNING` findings.

| # | Heuristic | What to check |
|---|---|---|
| 1 | **Visibility of system status** | Loading states, progress indicators, success/error feedback |
| 2 | **Match between system and real world** | Labels use user's vocabulary, not developer jargon |
| 3 | **User control and freedom** | Cancel, undo, back — escape routes on every destructive action |
| 4 | **Consistency and standards** | Same action always uses the same label and placement |
| 5 | **Error prevention** | Confirm dialogs for irreversible actions; form validation before submit |
| 6 | **Recognition over recall** | Options visible in UI; user doesn't need to memorize |
| 7 | **Flexibility and efficiency** | Keyboard shortcuts; filters; bulk actions for power users |
| 8 | **Aesthetic and minimalist design** | No irrelevant information; hierarchy guides attention |
| 9 | **Help recognize, diagnose, recover from errors** | Error messages say what went wrong and how to fix it |
| 10 | **Help and documentation** | Tooltips, empty states with calls-to-action, inline hints |

---

## Screen Inventory from PRD

Derive the complete list of screens from the PRD's core features:

```
Feature: Order Management
Screens:
  - /orders        (Order List)   — entry from nav; shows paginated order list
  - /orders/{id}   (Order Detail) — entry from list row; shows full order detail
  - /orders/new    (Create Order) — entry from list CTA; guided order creation form
```

For each screen record: user goal, URL/route, entry points, exit points.

---

## Layout Structure Definition

For each screen, define the layout skeleton before specifying individual components. Use named regions.

```
Order List Screen
  Layout: AppShell (header + sidebar + main)
  Main region:
    - PageHeader: "Orders" title | "New Order" primary button
    - FilterBar: status dropdown (All / Pending / Paid / Shipped / Cancelled), date range picker
    - DataTable: sortable columns (ID, Customer, Status, Amount, Date), row actions (View, Cancel)
    - Pagination: page size selector (10 / 20 / 50), page navigation
```

---

## Component Specification

For each component, write a spec that can be directly translated to a prop interface:

```markdown
### OrderStatusBadge
- Props: status (PENDING | PAID | SHIPPED | CANCELLED)
- Rendering: colored chip — grey / green / blue / red
- Color is NOT the only status indicator (text label also shown — WCAG 1.4.1)
- No internal state
- No event handlers
```

---

## Interaction and State Flow

Document every user interaction that causes a state change or navigation event:

```
User clicks "Cancel Order" in OrderActionMenu
  → Confirmation modal opens ("Cancel this order?" with order summary)
  → User clicks "Confirm Cancel"
    → DELETE /orders/{id}
    → On success: row status updates to CANCELLED, success toast "Order cancelled"
    → On failure: error toast "Failed to cancel — please try again", modal closes
  → User clicks "Go Back"
    → Modal closes, no state change (Heuristic 3: user control)
```

---

## Error State Design (Heuristic 9)

Every screen and form must have explicitly designed error, loading, and empty states:

| State | Design requirement |
|---|---|
| **Loading** | Skeleton loaders matching the final layout (not spinners for > 300ms waits) |
| **Empty** | Illustration + descriptive message + primary call-to-action |
| **Error** | Error message in plain language + retry action |
| **Form validation** | Inline field errors below the field, not modal alerts |
| **Partial failure** | If some items loaded and some failed, show partial data + inline error for failed section |

---

## Gestalt Principles (Reference: Gestalt Psychology, Wertheimer 1923)

Apply to establish visual hierarchy:

| Principle | Application |
|---|---|
| **Proximity** | Group related controls (filter bar elements) close together; separate unrelated sections |
| **Similarity** | Consistent button styles for same-priority actions; same badge colours across all screens |
| **Continuity** | Align elements along a grid; visual flow guides the eye to the primary action |
| **Closure** | Cards and containers give incomplete shapes a perceived boundary |
| **Figure/Ground** | Primary action button stands out from the background; destructive actions are secondary |

---

## Accessibility Considerations — WCAG 2.1 Level AA

(Reference: W3C Web Content Accessibility Guidelines 2.1)

For each screen, specify:

| Area | Requirement |
|---|---|
| **Color contrast** | Text on background ≥ 4.5:1 ratio (3:1 for large text) |
| **Focus order** | Logical tab order matching visual flow |
| **Status indicators** | Never use color alone (add icon or text label) |
| **Form labels** | Every input has a visible label; error messages reference the field name |
| **Modals** | Focus trapped inside modal while open; `Escape` closes modal |

---

## Mobile-First Responsive Design

Design for the smallest viewport first, then enhance for larger screens.

| Breakpoint | Min width | Layout change |
|---|---|---|
| Mobile | 0 | Single column, stacked controls |
| Tablet | 768px | Sidebar appears, table gains columns |
| Desktop | 1024px | Full layout, extended filters |

Note touch targets: minimum 44 × 44 px for interactive elements on mobile.

---

## API Integration Point Specification

For each screen, list the API calls required. This becomes the source of truth for the backend agent.

```markdown
Order List Screen:
  - GET /orders?status={filter}&page={n}&pageSize={size} — paginated list
  - DELETE /orders/{id} — cancel order (row action; requires confirmation)

Order Detail Screen:
  - GET /orders/{id} — full order data
  - PUT /orders/{id}/status — status update (supervisor action)
```

---

## Checklist
- [ ] All screens derived from PRD features are listed with URL and user goal
- [ ] Layout structure (named regions) defined for each screen
- [ ] Nielsen's 10 Heuristics checked for each screen
- [ ] Component definitions include props, state, and event handlers
- [ ] All user interaction flows documented (including confirmation dialogs and error paths)
- [ ] Loading, empty, and error states explicitly designed for each screen
- [ ] Gestalt principles applied to establish visual hierarchy
- [ ] WCAG 2.1 AA requirements checked (contrast, focus order, status indicators, labels)
- [ ] Mobile-first layout defined; touch target sizes noted
- [ ] API integration points listed per screen (source of truth for backend agent)
- [ ] `design-spec.md` written to `{TASK_DIR}/context/design-spec.md`
- [ ] Spec is concrete enough for the frontend agent to start coding immediately without further design clarification
