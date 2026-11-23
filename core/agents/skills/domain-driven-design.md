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

Name every class, method, variable, and module in the language agreed with domain experts.
Forbid technical names such as `Manager`, `Handler`, `Processor`, and `Helper` in the domain layer.

```kotlin
// BAD — technical naming
class OrderProcessor { fun process(data: OrderData): ProcessResult { … } }

// GOOD — ubiquitous language
class OrderPlacementService { fun place(command: PlaceOrderCommand): Order { … } }
```

### Rule 2: Aggregate — one root per consistency boundary; one repository per aggregate
> Source: Evans, Ch. 6 "The Life Cycle of a Domain Object"; Vernon, Ch. 10

An **Aggregate** groups domain objects under one **Aggregate Root**, which controls all access and enforces invariants.
External objects may reference only the root. Each aggregate has exactly one repository.

```kotlin
// BAD — external object holds reference to inner entity
val item = orderRepository.findItemById(itemId)  // bypasses Order root

// GOOD — access items only through the Aggregate Root
val order = orderRepository.findById(orderId)
val item = order.findItem(itemId)
```

### Rule 3: Entities have identity; Value Objects have no identity
> Source: Evans, Ch. 5 "A Model Expressed in Software"

- **Entity**: has a stable identity, such as `OrderId`. Distinct identities stay distinct when other fields match.
- **Value Object**: immutable and interchangeable when all attributes match, as with two `Money(1000, KRW)` instances.

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

Keep mutable internal collections private. Enforce invariants in behavior methods.

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

Name domain events in the past tense. Include all data subscribers need to react to the fact.

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

Use a stateless **Domain Service** for operations spanning aggregates or lacking a natural entity owner.
Keep application use-case orchestration in Application Services.

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

Give each **Bounded Context** its own Ubiquitous Language and model.
Translate across contexts through an **Anti-Corruption Layer (ACL)** to keep models isolated.

```
Orders Context    ← ACL →    Inventory Context
  Order.status              InventoryItem.availability
  (domain: placed/confirmed) (domain: in_stock/reserved)
```

### Rule 8: Repository interface in domain layer; implementation in infrastructure layer
> Source: Evans, Ch. 6; Vernon, Ch. 12

Keep `OrderRepository` in the domain and its implementation, such as `PostgresOrderRepository`, in infrastructure.
The domain never imports infrastructure classes.

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

### Rule 9: Continuous Model Integration — keep code and docs in one shared model
> Source: Evans, Ch. 2 "Communication and the Use of Language"; Beck, Ch. 7 "Continuous Integration"

In DDD, documentation is part of the shared model. Before integration, update durable documentation
that carries the Ubiquitous Language whenever a domain concept is added, removed, renamed, or reinterpreted.

Treat these artifacts as model-integration surfaces:

- README or guide sections that define operator-facing workflow language
- PRDs, handoffs, and architecture docs that explain bounded contexts,
  aggregates, invariants, or domain events
- Agent skills and rules that teach future agents the domain vocabulary
- Changelog or migration notes when behavior, workflow, or meaning changes

Every domain-affecting task must leave a short Ubiquitous Language ledger in
its handoff, PRD, review, or result artifact:

```markdown
## Ubiquitous Language ledger
- Added: `OrderReservation` means inventory has been held for an order.
- Changed: `confirmed` now means payment authorized and inventory reserved.
- Docs synchronized: `docs/orders.md`, `README.md`
```

When no tracked documentation needs an update, record `doc_impact: none` and explain why.

---

## Anti-Patterns
- Anemic Domain Model — entities with only getters/setters and all logic in service classes
- God Aggregate — one aggregate that spans the entire domain (no bounded context isolation)
- Leaking persistence annotations (`@Entity`, `@Column`) into domain entities
- Referencing one aggregate's internal entities from another aggregate directly
- Domain Events named in present tense or imperative mood (`ProcessOrder`, `PayingOrder`)
- Repositories that return DTOs instead of domain aggregates
- Code, tests, or prompts that change the Ubiquitous Language while leaving
  the corresponding README, PRD, handoff, or architecture guide stale

## Interaction with Other Skills
- Combine with `clean-architecture.md`: DDD aggregates are the entities of Clean Architecture; bounded contexts map to components
- Combine with `oop-principles.md`: Rule 4 (protect aggregate invariants) is SRP + Tell-Don't-Ask in domain terms
- Combine with `tdd.md`: domain model classes are the primary unit-test targets
- Combine with `agile-xp.md`: Continuous Integration includes keeping the
  shared domain model coherent across code, tests, and documentation

## References
- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software*, Addison-Wesley, 2003. ISBN 978-0-32-112521-7.
- Vaughn Vernon, *Implementing Domain-Driven Design*, Addison-Wesley, 2013. ISBN 978-0-32-183457-2.
- Vaughn Vernon, *Domain-Driven Design Distilled*, Addison-Wesley, 2016. ISBN 978-0-13-443442-1.
