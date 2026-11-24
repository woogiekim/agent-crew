# Skill: ui-component-design

## Purpose
Turn the design spec into a component tree, typed props, and state boundaries. Verify design compliance before committing.

## When to Apply
- Phase 1 (Implement), when turning `design-spec.md` into code
- Screen decomposition, local/global/server state boundaries, and API contracts for the backend agent

---

## Atomic Design (Brad Frost, "Atomic Design", 2013)

| Level | Examples | Rule |
|---|---|---|
| **Atoms** | Button, Input, Badge, Icon | No internal composition; pure props |
| **Molecules** | SearchBar (Input + Button), FormField (Label + Input + Error) | Composed of atoms; single responsibility |
| **Organisms** | OrderTable, Navbar, OrderFilterBar | Composed of molecules; domain-aware |
| **Templates** | AppShell, DashboardLayout | Page-level structure; no real data |
| **Pages** | OrderListPage, OrderDetailPage | Templates with real data; route entry points |

File layout:
```
src/
  components/
    atoms/      Button.tsx, Badge.tsx
    molecules/  SearchBar.tsx, FormField.tsx
    organisms/  OrderTable.tsx, Navbar.tsx
  templates/    AppShell.tsx
  pages/        OrderListPage.tsx
```

---

## Component Tree Decomposition

Draw each screen’s component tree before coding.

```
OrderListPage                       ← Page
  ├── AppShell                      ← Template
  │     ├── Navbar                  ← Organism
  │     └── Sidebar
  └── main
        ├── PageHeader              ← Molecule
        ├── OrderFilterBar          ← Organism
        ├── OrderTable              ← Organism
        │   └── OrderTableRow       ← Molecule (repeated)
        │       ├── OrderStatusBadge← Atom
        │       └── OrderActionMenu ← Molecule
        └── Pagination              ← Molecule
```

- Give each component one responsibility.
- Pages compose feature components. Keep business logic outside page components.
- Reuse shared UI from `atoms/` or `molecules/`.

---

## Prop Interface Definition

Define TypeScript props before implementing components.

```typescript
// Atoms — minimal, generic
interface BadgeProps {
  variant: 'default' | 'success' | 'warning' | 'error';
  children: React.ReactNode;
}

// Molecules — domain-specific but not page-specific
interface OrderStatusBadgeProps {
  status: 'PENDING' | 'PAID' | 'SHIPPED' | 'CANCELLED';
}

// Organisms — receive data and callbacks; no internal fetching
interface OrderTableRowProps {
  order: OrderSummary;
  onSelect: (id: string) => void;
  onCancel: (id: string) => void;
}
```

---

## State Boundary Decision

Choose the state layer before writing component logic.

| State Type | Tool | When |
|---|---|---|
| Ephemeral UI (toggle, hover, open/close) | `useState` / `useSignal` | Component-local only |
| Cross-component shared within a subtree | `useContext` / `provide-inject` | Lifted ≤ 2 levels |
| Global client state | Zustand / Pinia / Redux | Cross-feature, no server sync |
| Server data (async, cacheable) | React Query / SWR / TanStack Query | API-fetched, needs invalidation |
| URL-driven state | `useSearchParams` / router query | Filter, pagination, tabs |

Use the smallest scope. Lift state only when two unrelated sibling components need it.

---

## Container / Presenter Pattern

Separate fetching from rendering.

```typescript
// Container — owns fetching, error, loading
function OrderListContainer() {
  const { data, isLoading, error } = useOrders();
  if (isLoading) return <Skeleton />;
  if (error) return <ErrorState onRetry={refetch} />;
  return <OrderTable orders={data} onCancel={handleCancel} />;
}

// Presenter — pure rendering; testable without network
function OrderTable({ orders, onCancel }: OrderTableProps) {
  return (
    <table>
      {orders.map(order => (
        <OrderTableRow key={order.id} order={order} onCancel={onCancel} />
      ))}
    </table>
  );
}
```

Keep presenters testable with `renderWithProviders(jsx)` without network mocks.

---

## Performance Patterns

```typescript
// Memoize expensive child renders
const MemoizedOrderTable = React.memo(OrderTable);

// Lazy-load heavy pages (code splitting)
const OrderDetailPage = React.lazy(() => import('./pages/OrderDetailPage'));

// Defer non-critical UI
<Suspense fallback={<Skeleton />}>
  <OrderDetailPage />
</Suspense>

// Avoid re-renders: stable callback references
const handleCancel = useCallback((id: string) => cancelOrder(id), [cancelOrder]);

// Avoid re-renders: derive from existing state, don't duplicate
const pendingCount = useMemo(() => orders.filter(o => o.status === 'PENDING').length, [orders]);
```

---

## Accessibility — WCAG 2.1 Level AA

(Reference: W3C Web Content Accessibility Guidelines 2.1)

| Principle | Check |
|---|---|
| **Perceivable** | Images have `alt` text; color is not the only status indicator |
| **Operable** | All interactions keyboard-navigable; focus is visible |
| **Understandable** | Form errors are descriptive; labels are associated with inputs |
| **Robust** | Semantic HTML (`<button>` not `<div onClick>`); ARIA used only when HTML semantics are insufficient |

```typescript
// GOOD — semantic, keyboard accessible, screen-reader friendly
<button
  onClick={onCancel}
  aria-label={`Cancel order ${order.id}`}
  disabled={order.status === 'CANCELLED'}
>
  Cancel
</button>

// BAD — not keyboard focusable, no ARIA
<div onClick={onCancel}>Cancel</div>
```

---

## API Integration Point Interface

Document API calls in `{TASK_DIR}/context/api-contract.md` before implementing them.

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
  hasNext: boolean;
}
```

---

## Design Spec Compliance Verification

After each component, check against `design-spec.md`:
- Screen name, URL, and all major UI elements
- Interactions including form submits, errors, and transitions
- Loading, empty, and error states
- Spec-defined UI only

---

## Checklist
- [ ] Component tree drawn using Atomic Design levels before coding begins
- [ ] Prop interfaces defined as typed TypeScript interfaces for all new components
- [ ] State layer chosen (local / context / global / server / URL) for each piece of state
- [ ] Container/Presenter pattern applied for data-fetching components
- [ ] Performance: `memo`, `useCallback`, `useMemo`, `lazy` applied where re-render cost is measurable
- [ ] Accessibility: semantic HTML, keyboard navigation, `alt`, `aria-label` checked
- [ ] API integration point interfaces documented
- [ ] All screens from design-spec.md implemented (loading / empty / error states included)
- [ ] No undocumented features added beyond the design spec
- [ ] Type check passes (`npx tsc --noEmit` or equivalent)
- [ ] `handoff.md` updated with component list and API integration specs
