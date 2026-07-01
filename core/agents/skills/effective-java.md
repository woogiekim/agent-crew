# Skill: effective-java

## Source
- Joshua Bloch, *Effective Java* (3rd ed.), Addison-Wesley, 2018
- Robert C. Martin, *Clean Code*, Prentice Hall, 2008

## When to Apply
- Before writing any Java class, interface, or enum
- Before choosing between inheritance and composition
- Before writing generic code, lambdas, or streams
- During refactor: when simplifying existing Java code

---

## Core Rules

### Rule 1: Static factory methods over constructors
> Source: Bloch, Item 1 "Consider static factory methods instead of constructors"

Static factories have names, can return cached instances, and can return subtypes.

```java
// BAD — unnamed constructor, no caching opportunity
new BigInteger(numBits, certainty, rng)

// GOOD — named, self-documenting, can return optimised instances
BigInteger.probablePrime(numBits, rng)
Order.of(customerId, items)
```

### Rule 2: Builder pattern for classes with many parameters
> Source: Bloch, Item 2 "Consider a builder when faced with many constructor parameters"

When a class has more than three or four parameters, use the Builder pattern.
Telescoping constructors are unreadable and error-prone.

```java
// BAD
new Order(customerId, items, discount, shippingAddress, billingAddress, couponCode);

// GOOD
Order.builder()
    .customerId(customerId)
    .items(items)
    .shippingAddress(shippingAddress)
    .build();
```

### Rule 3: Singletons via enum; avoid double-checked locking
> Source: Bloch, Item 3 "Enforce the singleton property with a private constructor or an enum type"

A single-element enum is the most concise, correct, and serialisation-safe
singleton. Avoid `static volatile + synchronized` gymnastics.

```java
// GOOD — serialisation-safe, reflection-resistant singleton
public enum EventBus {
    INSTANCE;
    public void publish(DomainEvent event) { … }
}
```

### Rule 4: Prefer interfaces over abstract classes
> Source: Bloch, Item 20 "Prefer interfaces to abstract classes"

Interfaces allow multiple-type simulation and retrofitting. Abstract classes
restrict the implementation class hierarchy. Use abstract skeletal implementations
(e.g., `AbstractList`) to combine the benefits.

```java
// PREFER
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}

// USE ABSTRACT ONLY when providing shared implementation, not contract definition
```

### Rule 5: Override equals, hashCode, and toString consistently
> Source: Bloch, Items 10–12

If you override `equals`, you MUST override `hashCode` with the same fields.
Always override `toString` for domain objects to aid debugging. Use
`Objects.equals` and `Objects.hash` to avoid NPE.

```java
@Override public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof Order)) return false;
    Order order = (Order) o;
    return Objects.equals(orderId, order.orderId);
}

@Override public int hashCode() { return Objects.hash(orderId); }

@Override public String toString() {
    return "Order{id=" + orderId + ", status=" + status + "}";
}
```

### Rule 6: Prefer generics to raw types; use bounded wildcards correctly
> Source: Bloch, Items 26–31 "Generics" chapter

Never use raw types in new code. Use bounded wildcards for flexibility:
- `? extends T` — producer (read-only collections)
- `? super T` — consumer (write-only collections)
- PECS: Producer Extends, Consumer Super

```java
// BAD — raw type, loses type safety
List items = new ArrayList();

// GOOD
List<OrderItem> items = new ArrayList<>();

// PECS example
public void addAll(Iterable<? extends OrderItem> src, Collection<? super OrderItem> dst) {
    for (OrderItem item : src) dst.add(item);
}
```

### Rule 7: Prefer lambdas and streams; avoid anonymous classes for functional interfaces
> Source: Bloch, Items 42–48 "Lambdas and Streams" chapter

Use lambda expressions for single-method functional interfaces. Use streams for
sequence operations. Avoid side effects inside stream pipelines.

```java
// BAD — verbose anonymous class
orders.sort(new Comparator<Order>() {
    @Override public int compare(Order a, Order b) {
        return a.placedAt().compareTo(b.placedAt());
    }
});

// GOOD — lambda
orders.sort(Comparator.comparing(Order::placedAt));

// BAD — side-effecting stream
orders.stream().forEach(o -> totalMap.put(o.id(), o.total())); // mutation

// GOOD — collector
Map<OrderId, Money> totals = orders.stream()
    .collect(toMap(Order::id, Order::total));
```

### Rule 8: Prefer Optional to null for method return types
> Source: Bloch, Item 55 "Return optionals judiciously"

Use `Optional<T>` only as a method return type when absence is a valid outcome.
Never use `Optional` as a field type, parameter type, or in collections.

```java
// BAD
public Order findById(OrderId id) { return null; }  // caller must null-check

// GOOD
public Optional<Order> findById(OrderId id) {
    return Optional.ofNullable(repository.get(id));
}
```

### Rule 9: Minimize mutability and prefer safely shareable values
> Source: Bloch, Item 17 "Minimize mutability"

Immutable objects are simpler, thread-safe, and can be shared freely. Make
classes immutable when practical: keep fields `private final`, avoid mutators,
validate constructor inputs, and never expose mutable internals.

When a value is intentionally read-only or shared, prefer a canonical immutable
instance over allocating a fresh mutable object.

```java
// BAD — a mutable object represents a read-only absence value
Map<Long, String> names = new HashMap<Long, String>();

// GOOD — canonical immutable empty value communicates read-only intent
Map<Long, String> names = Collections.emptyMap();
```

### Rule 10: Make defensive copies at trust boundaries
> Source: Bloch, Item 50 "Make defensive copies when needed"

Copy mutable inputs and outputs when an object must protect its invariants.
Do not store caller-owned mutable collections directly, and do not return
internal mutable state.

```java
public final class Schedule {
    private final List<Instant> runs;

    public Schedule(List<Instant> runs) {
        this.runs = List.copyOf(runs);
    }

    public List<Instant> runs() {
        return runs;
    }
}
```

### Rule 11: Return empty collections or arrays, not nulls
> Source: Bloch, Item 54 "Return empty collections or arrays, not nulls"

Never return `null` for collection or array results. Return the appropriate
empty value so callers can iterate without defensive null checks.

Use canonical immutable empty values when the fallback is read-only:

- `Collections.emptyMap()`
- `Collections.emptyList()`
- `Collections.emptySet()`
- Java 9+ `List.of()`, `Map.of()`, `Set.of()`

Reviewer checklist: when a read-only fallback collection is represented by a
fresh mutable allocation such as `new HashMap<Long, String>()`, prefer
`Collections.emptyMap()` or the matching canonical immutable empty value unless
the caller is expected to mutate the returned collection.

```java
// BAD — forces null checks
return null;

// BAD — mutable allocation for a read-only fallback collection
return new HashMap<Long, String>();

// GOOD — safe to iterate and share
return Collections.emptyMap();
```

### Rule 12: Use checked exceptions only for recoverable conditions
> Source: Bloch, Item 70 "Use checked exceptions for recoverable conditions and runtime exceptions for programming errors"

- Checked exceptions: conditions the caller can reasonably recover from (e.g., `IOException`)
- Unchecked (`RuntimeException`): programming errors, contract violations
- Domain errors: use custom unchecked exceptions or a Result type rather than checked exceptions

```java
// BAD — checked exception for unrecoverable logic error
public void placeOrder(Order order) throws OrderAlreadyPlacedException { … }

// GOOD — unchecked for invariant violation
public void placeOrder(Order order) {
    if (order.isAlreadyPlaced()) throw new IllegalStateException("Order already placed: " + order.id());
    …
}
```

### Rule 13: Favour composition over inheritance
> Source: Bloch, Item 18 "Favour composition over inheritance"; Martin, Ch. 10

Inheritance breaks encapsulation. Extend only when the relationship is a genuine
"is-a" and you control the superclass. Otherwise, wrap via composition.

```java
// BAD — fragile inheritance
class InstrumentedHashSet<E> extends HashSet<E> {
    private int addCount = 0;
    @Override public boolean add(E e) { addCount++; return super.add(e); } // wrong: addAll calls add
}

// GOOD — composition + delegation
class InstrumentedSet<E> implements Set<E> {
    private final Set<E> delegate;
    private int addCount = 0;
    public InstrumentedSet(Set<E> delegate) { this.delegate = delegate; }
    @Override public boolean add(E e) { addCount++; return delegate.add(e); }
    // … delegate all other methods
}
```

---

## Anti-Patterns
- Raw types (`List` instead of `List<Order>`)
- Returning `null` from public API methods — use `Optional<T>` or throw
- Mutable public fields — encapsulate with accessors
- Fresh mutable empty fallback collections (`new HashMap<>()`,
  `new ArrayList<>()`) when a canonical immutable empty value communicates the
  read-only contract
- Exposing caller-owned or internal mutable collections without defensive copies
- `instanceof` chains — use polymorphism or pattern matching (Java 16+)
- `synchronized` at method level when finer-grained locking suffices
- String concatenation in loops — use `StringBuilder`

## Interaction with Other Skills
- Combine with `tdd.md`: all rules should be verified by tests first
- Combine with `clean-architecture.md`: Item 20 (prefer interfaces) directly supports dependency inversion
- Combine with `oop-principles.md`: Items 18+20 enforce SOLID OCP and DIP

## References
- Joshua Bloch, *Effective Java* (3rd ed.), Addison-Wesley Professional, 2018. ISBN 978-0-13-468599-1.
- Robert C. Martin, *Clean Code: A Handbook of Agile Software Craftsmanship*, Prentice Hall, 2008. ISBN 978-0-13-235088-4.
