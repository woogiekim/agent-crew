# Skill: ui-component-design

## Purpose
Enables the frontend agent to decompose a design specification into an implementable component tree, define clear prop interfaces and state boundaries, and verify compliance against the design spec before committing.

## When to Apply
- During Phase 1 (Implement) when translating `design-spec.md` into source code
- When deciding how to split a screen into reusable components
- When defining the boundary between local state and global/server state
- When establishing API integration point contracts for the backend agent

## Techniques

### Component Tree Decomposition
Break each screen into a hierarchy before writing any code. Use the design spec's component definitions as the starting point.

**Example decomposition for an Order List screen:**
```
OrderListPage
  ├── PageHeader (title, actions)
  ├── OrderFilterBar (status filter, date range)
  ├── OrderTable
  │   ├── OrderTableRow (repeated)
  │   │   ├── OrderStatusBadge
  │   │   └── OrderActionMenu
  └── Pagination
```

Rules:
- A component does one thing — if it does two, split it
- Shared UI elements (Badge, Button, Modal) go in a `components/common/` directory
- Page-level components assemble feature components; they do not contain business logic

### Prop Interface Definition
Define TypeScript (or equivalent) prop types before implementing the component body.

**Example:**
```typescript
interface OrderTableRowProps {
  order: OrderSummary;
  onSelect: (id: string) => void;
  onCancel: (id: string) => void;
}

interface OrderStatusBadgeProps {
  status: 'PENDING' | 'PAID' | 'SHIPPED' | 'CANCELLED';
}
```

### State Boundary Decision
Determine the correct state layer before writing component logic:

| State Type | Tool | When |
|---|---|---|
| Ephemeral UI (toggle, hover) | `useState` / `useSignal` | Component-local only |
| Cross-component shared | Global store (Zustand, Pinia) | When lifted > 2 levels |
| Server data | React Query / SWR | API-fetched, cacheable data |

### API Integration Point Interface
Define the contract between frontend and backend before implementing API calls. Write to `{TASK_DIR}/context/api-contract.md` or inline in `handoff.md`.

**Example:**
```typescript
// GET /orders
interface OrderListRequest {
  status?: OrderStatus;
  page: number;
  pageSize: number;
}
interface OrderListResponse {
  items: OrderSummary[];
  total: number;
}
```

### Design Spec Compliance Verification
After implementing each component, verify it against the design spec:
- Screen name and URL match
- All major UI elements are present
- Interaction flows (form submit, error states, transitions) are implemented
- No elements added that are not in the design spec

## Checklist
- [ ] Component tree drawn for each screen before coding begins
- [ ] Prop interfaces defined as typed interfaces/types
- [ ] State layer chosen (local / global / server) for each piece of state
- [ ] API integration point interfaces documented
- [ ] All screens from design-spec.md implemented
- [ ] No undocumented features added beyond the design spec
- [ ] Type check passes (`npx tsc --noEmit` or equivalent)
- [ ] `handoff.md` updated with component list and API integration specs
