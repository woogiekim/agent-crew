# Skill: domain-driven-design

## Source
- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software*, Addison-Wesley, 2003
- Vaughn Vernon, *Implementing Domain-Driven Design*, Addison-Wesley, 2013
- Vaughn Vernon, *Domain-Driven Design Distilled*, Addison-Wesley, 2016

## When to Apply
- Before modeling any domain concept (aggregate, entity, value object, service)
- Before designing module or bounded context boundaries
- Before naming classes, methods, or variables — use the Ubiquitous Language
- During review: when evaluating whether the code reflects the domain model accurately

---

## Core Rules

### Rule 1: Ubiquitous Language — name classes and methods after domain concepts
> Source: Evans, Ch. 2 "Communication and the Use of Language"

Every class, method, variable, and module name must come from the business
domain language agreed upon with domain experts. Technical names
(`Manager`, `Handler`, `Processor`, `Helper`) are forbidden in the domain layer.

```kotlin
// BAD — technical naming
class OrderProcessor { fun process(data: OrderData): ProcessResult { … } }

// GOOD — ubiquitous language
class OrderPlacementService { fun place(command: PlaceOrderCommand): Order { … } }
```

### Rule 2: Aggregate — one root per consistency boundary; one repository per aggregate
> Source: Evans, Ch. 6 "The Life Cycle of a Domain Object"; Vernon, Ch. 10

An **Aggregate** is a cluster of domain objects with a single **Aggregate Root**
that controls all invariant enforcement and access. External objects hold
references to the root only (never to internal entities). Each aggregate has
exactly one Repository.

```kotlin
// BAD — external object holds reference to inner entity
val item = orderRepository.findItemById(itemId)  // bypasses Order root

// GOOD — access items only through the Aggregate Root
val order = orderRepository.findById(orderId)
val item = order.findItem(itemId)
```

### Rule 3: Entities have identity; Value Objects have no identity
> Source: Evans, Ch. 5 "A Model Expressed in Software"

- **Entity**: defined by a continuous identity (e.g., `Order` with `OrderId`).
  Two orders are different entities even if all their fields are equal.
- **Value Object**: defined entirely by its attributes (e.g., `Money`, `Address`).
  Two `Money(1000, KRW)` instances are interchangeable. Value Objects are immutable.

```kotlin
// Entity — identity matters
data class Order(val id: OrderId, val status: OrderStatus)  // id is the identity

// Value Object — identity is irrelevant, equality is by value
data class Money(val amount: BigDecimal, val currency: Currency) {
    operator fun plus(other: Money): Money {
        require(currency == other.currency) { "Cannot add different currencies" }
        return copy(amount = amount + other.amount)
    }
}
```

### Rule 4: Protect aggregate invariants — never expose internal collections as mutable
> Source: Evans, Ch. 6; Vernon, Ch. 10

Aggregates enforce business rules. Never expose mutable internal collections
directly. Provide behaviour methods that enforce invariants.

```kotlin
// BAD — invariant can be bypassed
class Order {
    val items: MutableList<OrderItem> = mutableListOf()  // caller can mutate directly
}

// GOOD — invariant enforced by the aggregate
class Order(private val _items: MutableList<OrderItem> = mutableListOf()) {
    val items: List<OrderItem> get() = _items.toList()

    fun addItem(item: OrderItem) {
        require(_items.size < MAX_ITEMS) { "Order cannot exceed $MAX_ITEMS items" }
        _items.add(item)
    }
}
```

### Rule 5: Domain Events — publish what happened, not what to do
> Source: Vernon, Ch. 8 "Domain Events"; Evans (supplemental patterns)

Domain Events represent facts that have occurred in the domain. They are named
in the past tense and contain all the data a subscriber needs to react.

```kotlin
// BAD — command-style event (imperative)
data class ProcessPayment(val orderId: OrderId, val amount: Money)

// GOOD — event-style (past tense fact)
data class OrderPlaced(
    val orderId: OrderId,
    val customerId: CustomerId,
    val totalAmount: Money,
    val occurredAt: Instant,
) : DomainEvent
```

### Rule 6: Domain Services for operations that don't naturally belong to any entity
> Source: Evans, Ch. 5 "Domain Services"

When a domain operation involves multiple aggregates or does not fit as a method
on a single entity, use a **Domain Service**. Domain Services are stateless.
They are not the same as Application Services (use cases).

```kotlin
// Domain Service — cross-aggregate invariant check
class TransferFundsService(
    private val accounts: AccountRepository,
) {
    fun transfer(from: AccountId, to: AccountId, amount: Money) {
        val source = accounts.findById(from)
        val target = accounts.findById(to)
        source.debit(amount)  // invariant checked on source aggregate
        target.credit(amount) // invariant checked on target aggregate
        accounts.save(source)
        accounts.save(target)
    }
}
```

### Rule 7: Bounded Contexts — explicit model boundaries; Anti-Corruption Layer at boundaries
> Source: Evans, Ch. 14 "Maintaining Model Integrity"; Vernon, Ch. 2

Each **Bounded Context** has its own Ubiquitous Language and model. When two
contexts interact, map between them via an **Anti-Corruption Layer (ACL)** —
never leak one context's model into another.

```
Orders Context    ← ACL →    Inventory Context
  Order.status              InventoryItem.availability
  (domain: placed/confirmed) (domain: in_stock/reserved)
```

### Rule 8: Repository interface in domain layer; implementation in infrastructure layer
> Source: Evans, Ch. 6; Vernon, Ch. 12

The `OrderRepository` interface belongs in the domain layer. The
`PostgresOrderRepository` (JPA, Hibernate, etc.) belongs in the infrastructure layer.
The domain layer never imports infrastructure classes.

```kotlin
// Domain layer
interface OrderRepository {
    fun findById(id: OrderId): Order?
    fun save(order: Order)
}

// Infrastructure layer
class PostgresOrderRepository(private val jpa: OrderJpaRepository) : OrderRepository {
    override fun findById(id: OrderId) = jpa.findById(id.value).orElse(null)?.toDomain()
    override fun save(order: Order) = jpa.save(order.toEntity())
}
```

---

## Anti-Patterns
- Anemic Domain Model — entities with only getters/setters and all logic in service classes
- God Aggregate — one aggregate that spans the entire domain (no bounded context isolation)
- Leaking persistence annotations (`@Entity`, `@Column`) into domain entities
- Referencing one aggregate's internal entities from another aggregate directly
- Domain Events named in present tense or imperative mood (`ProcessOrder`, `PayingOrder`)
- Repositories that return DTOs instead of domain aggregates

## Interaction with Other Skills
- Combine with `clean-architecture.md`: DDD aggregates are the entities of Clean Architecture; bounded contexts map to components
- Combine with `oop-principles.md`: Rule 4 (protect aggregate invariants) is SRP + Tell-Don't-Ask in domain terms
- Combine with `tdd.md`: domain model classes are the primary unit-test targets

## References
- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software*, Addison-Wesley, 2003. ISBN 978-0-32-112521-7.
- Vaughn Vernon, *Implementing Domain-Driven Design*, Addison-Wesley, 2013. ISBN 978-0-32-183457-2.
- Vaughn Vernon, *Domain-Driven Design Distilled*, Addison-Wesley, 2016. ISBN 978-0-13-443442-1.
