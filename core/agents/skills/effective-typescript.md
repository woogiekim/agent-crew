# Skill: effective-typescript

## Source
- Dan Vanderkam, *Effective TypeScript: 83 Specific Ways to Improve Your TypeScript*, O'Reilly, 2023 (2nd ed.)
- TypeScript Team, *TypeScript Handbook*, https://www.typescriptlang.org/docs/handbook/

## When to Apply
- Before writing any TypeScript type, interface, or function signature
- Before choosing between `interface` and `type`, `unknown` and `any`, `enum` and union
- Before writing generic code, type guards, or mapped/conditional types
- During refactor: when tightening type safety in existing TypeScript code

---

## Core Rules

### Rule 1: Understand the difference between TypeScript and JavaScript runtime
> Source: Vanderkam, Items 1–3 "TypeScript and JavaScript" chapter

TypeScript type annotations are erased at runtime. Never rely on them for
runtime validation. Validate external data (API responses, user input) with
a runtime parser (Zod, io-ts, etc.) — types alone are insufficient.

```typescript
// BAD — type assertion without validation
const order = response.json() as Order;   // no guarantee at runtime

// GOOD — validated at the boundary
import { z } from 'zod';
const OrderSchema = z.object({ id: z.string(), total: z.number() });
const order = OrderSchema.parse(await response.json());
```

### Rule 2: Avoid `any`; prefer `unknown` for truly unknown values
> Source: Vanderkam, Items 5, 41 "Use unknown Instead of any"

`any` disables type checking everywhere the value flows. `unknown` forces the
caller to narrow before use — preserving safety without losing flexibility.

```typescript
// BAD
function processEvent(event: any) {
    console.log(event.payload.userId);  // no type check
}

// GOOD
function processEvent(event: unknown) {
    if (isOrderEvent(event)) {
        console.log(event.payload.userId);  // narrowed
    }
}
```

### Rule 3: Use structural typing; prefer interfaces for public API shapes
> Source: Vanderkam, Items 4, 11 "Distinguish Between Type and Interface"

TypeScript uses structural (duck) typing. Prefer `interface` for public API
shapes (they can be extended / merged by consumers). Use `type` for aliases,
unions, intersections, and mapped types.

```typescript
// PREFER interface for shapes that may be extended
interface OrderRepository {
    findById(id: string): Promise<Order | null>;
    save(order: Order): Promise<void>;
}

// PREFER type for computed/union/intersection shapes
type OrderStatus = 'pending' | 'confirmed' | 'shipped' | 'cancelled';
type PartialOrder = Partial<Order> & { id: string };
```

### Rule 4: Prefer union types and discriminated unions over optional fields
> Source: Vanderkam, Items 28, 32 "Prefer Unions of Interfaces to Interfaces of Unions"

Optional fields hide invariants. Discriminated unions make valid states
explicit and eliminate impossible states.

```typescript
// BAD — isConfirmed could be true while confirmedAt is undefined
interface Order {
    id: string;
    isConfirmed?: boolean;
    confirmedAt?: Date;
}

// GOOD — impossible states cannot be represented
type Order =
    | { id: string; status: 'pending' }
    | { id: string; status: 'confirmed'; confirmedAt: Date };
```

### Rule 5: Use type guards and narrowing; never cast with `as`
> Source: Vanderkam, Items 22, 9 "Prefer Type Declarations to Type Assertions"

Type assertions (`as T`) bypass type-checking. Use user-defined type guards
(`is` predicates) or `instanceof` checks to narrow correctly.

```typescript
// BAD
const order = data as Order;   // no evidence data is an Order

// GOOD
function isOrder(value: unknown): value is Order {
    return typeof value === 'object' && value !== null && 'id' in value;
}
if (isOrder(data)) { /* safely narrowed */ }
```

### Rule 6: Prefer `readonly` for immutable data; use `as const` for literals
> Source: Vanderkam, Items 17 "Use readonly to Avoid Errors Associated with Mutation"

Immutable references prevent accidental mutation in functions and callbacks.
Use `as const` to infer literal types for config objects and lookup tables.

```typescript
// BAD — array can be mutated by called function
function processItems(items: OrderItem[]) { items.push(…); }

// GOOD
function processItems(items: readonly OrderItem[]) { … }

// as const for exhaustive lookup tables
const ORDER_STATUS_LABELS = {
    pending:   'Awaiting confirmation',
    confirmed: 'Order confirmed',
    shipped:   'On the way',
} as const;
```

### Rule 7: Prefer mapped types and `keyof`/`typeof` over manual type duplication
> Source: Vanderkam, Items 35, 14 "Use Type Operations and Generics to Avoid Repeating Yourself"

When two types share shape, derive one from the other. Manual duplication
causes drift.

```typescript
// BAD — two types maintained separately
interface Order { id: string; customerId: string; total: number; }
interface OrderDTO { id: string; customerId: string; total: number; }

// GOOD — pick or map from the source of truth
type OrderDTO = Pick<Order, 'id' | 'customerId' | 'total'>;
type PartialOrderUpdate = Partial<Pick<Order, 'total' | 'customerId'>>;
```

### Rule 8: Avoid `enum`; prefer union types or `as const` objects
> Source: Vanderkam, Item 53 "Prefer ECMAScript Features to TypeScript-Specific Features"

TypeScript `enum` generates runtime code, has surprising `const enum` pitfalls,
and cannot be extended. Union types are zero-cost and more composable.

```typescript
// BAD
enum OrderStatus { Pending, Confirmed, Shipped }

// GOOD — zero runtime cost, composable
type OrderStatus = 'pending' | 'confirmed' | 'shipped';
// or, for reverse-lookup needs:
const OrderStatus = { Pending: 'pending', Confirmed: 'confirmed' } as const;
type OrderStatus = typeof OrderStatus[keyof typeof OrderStatus];
```

### Rule 9: Enable strict mode; treat compiler errors as bugs
> Source: Vanderkam, Item 2 "Know Which TypeScript Options You're Using"

Always enable `"strict": true` in `tsconfig.json`. This enables `strictNullChecks`,
`noImplicitAny`, `strictFunctionTypes`, and more. Never suppress errors with
`@ts-ignore`; fix the root cause instead.

```json
// tsconfig.json — minimum strict config
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  }
}
```

### Rule 10: Write small, composable functions; leverage type inference for internal helpers
> Source: Vanderkam, Items 26, 23 "Be Consistent in Your Use of Type Declarations"

Explicit return types are mandatory on public functions (API surface). Internal
helpers may use inference when the type is obvious from the implementation.

```typescript
// Public API — explicit return type
export function placeOrder(command: PlaceOrderCommand): Promise<Order> { … }

// Internal helper — inference acceptable
const formatOrderId = (id: string) => `ORD-${id.toUpperCase()}`;
```

---

## Anti-Patterns
- `any` in production code — use `unknown` + narrowing
- `!` non-null assertion outside test helpers — use optional chaining `?.` or explicit guard
- `interface` with index signature `[key: string]: unknown` — use `Map<string, unknown>` or discriminated union
- Synchronous `JSON.parse` on untrusted input without schema validation
- `namespace` declarations — use ES modules instead
- Circular type references without `type` aliases to break cycles

## Interaction with Other Skills
- Combine with `tdd.md`: type-level tests (e.g., `@ts-expect-error`) verify type contracts
- Combine with `clean-architecture.md`: interfaces (Rule 3) are the ports; implementations are adapters
- Combine with `ui-component-design.md`: prop types are TypeScript interfaces, not inline objects

## References
- Dan Vanderkam, *Effective TypeScript: 83 Specific Ways to Improve Your TypeScript* (2nd ed.), O'Reilly, 2023. ISBN 978-1-098-14182-2.
- TypeScript Team, *TypeScript Handbook*, https://www.typescriptlang.org/docs/handbook/
- TypeScript Team, *TypeScript Deep Dive*, https://basarat.gitbook.io/typescript/
