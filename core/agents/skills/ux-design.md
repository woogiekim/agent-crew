# Skill: ux-design

## Purpose
Enables the designer agent to translate a PRD into a concrete, implementation-ready design specification that the frontend agent can use immediately without further design clarification.

## When to Apply
- When `design-spec.md` does not exist and frontend implementation is planned
- When a PRD introduces new screens, flows, or user-facing interactions
- When a significant UX change is required for existing screens
- Before any frontend coding begins

## Techniques

### Screen Inventory from PRD
Derive the complete list of screens from the PRD's core features. For each screen, identify:
- The user goal it serves
- The URL/route path
- Entry points (what triggers navigation to this screen)
- Exit points (where the user goes after)

**Example:**
```
Feature: Order Management
Screens:
  - /orders (Order List) — entry from nav
  - /orders/{id} (Order Detail) — entry from list row
  - /orders/new (Create Order) — entry from list CTA
```

### Layout Structure Definition
For each screen, define the layout skeleton before specifying individual components. Use named regions.

**Example:**
```
Order List Screen
  Layout: AppShell (header + sidebar + main)
  Main region:
    - PageHeader: "Orders" title, "New Order" button
    - FilterBar: status dropdown, date range picker
    - DataTable: sortable columns, row actions
    - Pagination: page size selector, page navigation
```

### Component Specification
For each component, write a spec that can be directly translated to a prop interface:

```markdown
### OrderStatusBadge
- Props: status (PENDING | PAID | SHIPPED | CANCELLED)
- Rendering: colored chip — grey/green/blue/red
- No internal state
- No event handlers
```

### Interaction and State Flow
Document every user interaction that causes a state change or navigation event:

**Example flow:**
```
User clicks "Cancel Order" in OrderActionMenu
  → Confirmation modal opens
  → User clicks "Confirm"
    → DELETE /orders/{id} API call
    → On success: row removed, success toast shown
    → On failure: error toast shown, modal closed
```

### Error State Design
Every screen and form must have explicitly designed error states:
- Empty state (no data): illustration + call-to-action
- Loading state: skeleton loaders, not spinners when possible
- Error state: error message + retry action
- Form validation: inline field errors, not modal alerts

### API Integration Point Specification
For each screen, list the API calls required:

```markdown
Order List Screen:
  - GET /orders?status={filter}&page={n} — fetch paginated list
  - DELETE /orders/{id} — cancel order (row action)
```

This section becomes the source of truth for the backend agent's API design.

## Checklist
- [ ] All screens derived from PRD features are listed
- [ ] URL/route path defined for each screen
- [ ] Layout structure (header/sidebar/main regions) defined for each screen
- [ ] Component definitions include props, state, and event handlers
- [ ] All user interaction flows documented (including error and edge cases)
- [ ] Empty, loading, and error states designed for each screen
- [ ] API integration points listed per screen
- [ ] `design-spec.md` written to `{TASK_DIR}/context/design-spec.md`
- [ ] Spec is concrete enough for the frontend agent to start coding immediately
