# Skill: clean-architecture

## Source
- Robert C. Martin, *Clean Architecture: A Craftsman's Guide to Software Structure and Design*, Prentice Hall, 2017
- Robert C. Martin, *Agile Software Development, Principles, Patterns, and Practices*, Prentice Hall, 2002
- Alistair Cockburn, *Hexagonal Architecture*, https://alistair.cockburn.us/hexagonal-architecture/ (2005)

## When to Apply
- Before designing any new module, package, or service boundary
- Before choosing where to place business logic, data access, or external API calls
- Before deciding on dependencies between layers
- During review: when evaluating whether a change violates architectural invariants

---

## Core Rules

### Rule 1: The Dependency Rule — dependencies point inward only
> Source: Martin, Ch. 22 "The Clean Architecture"

The fundamental architectural invariant: **source code dependencies must point
only inward, toward higher-level policy (domain / use cases)**. Nothing in an
inner layer may know about anything in an outer layer.

```
Outer layers (Frameworks, Drivers, UI, DB, External APIs)
  ↓ depends on
Adapters / Gateways (Controllers, Presenters, Repositories)
  ↓ depends on
Use Cases (Application Services, Commands, Queries)
  ↓ depends on
Entities (Domain Model: Aggregates, Value Objects, Domain Events)
```

**Violation example:**

```kotlin
// BAD — domain entity depends on JPA (outer layer)
@Entity
class Order(
    @Id val id: UUID,
    @Column val status: String   // JPA annotation in domain entity
)

// GOOD — domain entity is pure; JPA mapping lives in adapter layer
data class Order(val id: OrderId, val status: OrderStatus)  // domain layer

@Entity @Table(name = "orders")
class OrderJpaEntity(val id: UUID, val status: String)      // adapter layer
```

### Rule 2: Depend on abstractions, not concretions (DIP)
> Source: Martin, Ch. 11 "The Dependency Inversion Principle"

Use cases and entities depend on interfaces (ports). Concrete implementations
(adapters) are injected at runtime via the DI container — never imported
directly.

```kotlin
// BAD — use case coupled to concrete repository
class PlaceOrderUseCase {
    private val repo = PostgresOrderRepository()   // concrete dep
}

// GOOD — use case depends on interface (port)
class PlaceOrderUseCase(private val repo: OrderRepository) {  // interface
    fun execute(cmd: PlaceOrderCommand): Order { … }
}

// Adapter layer — implements the port
class PostgresOrderRepository(private val db: DataSource) : OrderRepository { … }
```

### Rule 3: Use cases are the primary unit of application behaviour
> Source: Martin, Ch. 17 "Screaming Architecture"; Ch. 20 "Business Rules"

A use case encapsulates a single user goal. It orchestrates domain entities,
calls repositories, and dispatches events. It must NOT contain framework code,
SQL, or HTTP concerns.

```
PlaceOrderUseCase.execute(PlaceOrderCommand):
  1. Validate customer (CustomerRepository)
  2. Create Order aggregate (domain entity)
  3. Save order (OrderRepository)
  4. Publish OrderPlaced event (EventPublisher)
  5. Return Order
```

### Rule 4: Entities and use cases have no framework dependencies
> Source: Martin, Ch. 20 "Business Rules"

Domain entities and use case classes must be plain Kotlin/Java/Python/Go
objects. They must not import Spring, Hibernate, Express, SQLAlchemy, or any
framework class. This makes them independently testable with unit tests — no
application context needed.

```kotlin
// BAD — use case imports Spring
@Service   // ← Spring annotation in use case layer
class PlaceOrderUseCase { … }

// GOOD — plain class, Spring configuration in the adapter layer
class PlaceOrderUseCase(private val repo: OrderRepository) { … }

// Spring adapter
@Service
class PlaceOrderUseCaseBean(repo: OrderRepository) : PlaceOrderUseCase(repo)
```

### Rule 5: Boundaries are crossed by data transfer objects (DTOs), not domain objects
> Source: Martin, Ch. 22 "Crossing Boundaries"

When data crosses a layer boundary (e.g., HTTP request → use case, use case →
DB), it must be mapped to a simple data structure (DTO / command object / view
model). Never pass raw domain entities across boundaries — they carry invariants
the outer layer should not depend on.

```kotlin
// BAD — HTTP controller receives and returns domain entity
@RestController
class OrderController {
    fun place(@RequestBody order: Order): Order { … }   // domain entity as DTO
}

// GOOD — mapping at the boundary
@RestController
class OrderController {
    fun place(@RequestBody req: PlaceOrderRequest): OrderResponse {
        val cmd = PlaceOrderCommand(req.customerId, req.items.map { … })
        val order = useCase.execute(cmd)
        return OrderResponse.from(order)
    }
}
```

### Rule 6: The Common Closure Principle — group things that change together
> Source: Martin, Ch. 13 "Component Cohesion — The CCP"

Classes that change for the same reason and at the same time belong in the
same component. This is SRP at the component level. Feature cohesion trumps
technical cohesion.

```
// BAD — technical layering only
src/
  controllers/   OrderController.java, CustomerController.java
  services/      OrderService.java, CustomerService.java
  repositories/  OrderRepository.java, CustomerRepository.java

// GOOD — feature cohesion (vertical slices)
src/
  orders/
    OrderController.java
    PlaceOrderUseCase.java
    OrderRepository.java (interface)
    Order.java (entity)
  customers/
    CustomerController.java
    …
```

### Rule 7: Stable dependencies — depend toward stability
> Source: Martin, Ch. 14 "Component Coupling — The Stable Dependencies Principle"

A component should depend only on components that are more stable than itself.
Volatile (frequently-changing) components must not be dependencies of stable
(rarely-changing) ones. The domain/entity layer is the most stable — nothing
stable should depend on volatile adapter layers.

### Rule 8: The Humble Object pattern — separate testable logic from I/O
> Source: Martin, Ch. 23 "Presenters and Humble Objects"

I/O-coupled code (GUI rendering, DB queries, HTTP calls) is hard to unit-test.
Extract the testable logic into a "humble" object (view model, presenter,
use case) that can be tested without I/O. The I/O object becomes thin ("humble")
and needs only integration / E2E tests.

---

## Anti-Patterns
- Domain entities annotated with framework annotations (`@Entity`, `@Document`, `@Service`)
- Use cases that `import` specific database drivers or HTTP clients
- Controllers that contain business logic beyond request mapping and validation
- Repository implementations that return domain aggregates with lazy-loaded associations (leaks ORM behaviour into domain)
- Circular dependencies between components
- God classes that violate SRP by combining persistence, business logic, and presentation

## Interaction with Other Skills
- Combine with `tdd.md`: Rule 4 enables fast unit tests on entities and use cases; integration tests cover adapters
- Combine with `domain-driven-design.md`: DDD aggregates are the entities of Clean Architecture
- Combine with `oop-principles.md`: DIP (Rule 2) is the architectural expression of SOLID D
- Combine with language skills (`effective-kotlin.md`, etc.) for language-specific implementation patterns

## References
- Robert C. Martin, *Clean Architecture: A Craftsman's Guide to Software Structure and Design*, Prentice Hall, 2017. ISBN 978-0-13-468599-1.
- Robert C. Martin, *Agile Software Development, Principles, Patterns, and Practices*, Prentice Hall, 2002. ISBN 978-0-13-597444-5.
- Alistair Cockburn, *Hexagonal Architecture*, https://alistair.cockburn.us/hexagonal-architecture/
- Eric Evans, *Domain-Driven Design*, Addison-Wesley, 2003. ISBN 978-0-32-112521-7.
