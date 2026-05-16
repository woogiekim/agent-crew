# Skill: domain-modeling

## Purpose
Enables the planner and backend agents to discover domain concepts through Event Storming, define Aggregate boundaries, establish Bounded Contexts, and produce a domain model that drives the implementation layer.

## When to Apply
- When the PRD introduces new business capabilities not covered by existing entities
- When designing the boundary between microservices or modules
- When refactoring an Anemic Domain Model into a rich domain model
- Before writing any entity, repository, or use-case class

---

## Event Storming (Alberto Brandolini, 2012)

A collaborative modeling technique that discovers the domain by focusing on **Domain Events** (things that happened).

### Workshop flow (condensed — for solo analysis)

1. **Collect Domain Events** — past tense, orange sticky note
   ```
   Order Placed → Payment Received → Inventory Reserved → Order Shipped
   ```

2. **Add Commands** — the action that triggers each event (blue sticky)
   ```
   Place Order → [Order Placed]
   Confirm Payment → [Payment Received]
   ```

3. **Add Actors** — who issues each command (yellow sticky)
   ```
   Customer → Place Order → [Order Placed]
   Payment Gateway → Confirm Payment → [Payment Received]
   ```

4. **Identify Aggregates** — which Aggregates own which events (tan/beige sticky)
   ```
   Order Aggregate: Order Placed, Order Shipped, Order Cancelled
   Inventory Aggregate: Inventory Reserved, Stock Released
   Payment Aggregate: Payment Received, Payment Failed
   ```

5. **Spot Bounded Contexts** — clusters of tightly related Aggregates and Events that use the same ubiquitous language

### Red flags to surface
- **Pivotal events** (major state changes everyone cares about): `Order Placed`, `Payment Received`
- **Policy events** (automated reactions): "Whenever an Order is Placed, reserve inventory"
- **External systems** (pink sticky): Payment Gateway, Inventory Service, Email Service

---

## Bounded Context

(Reference: Eric Evans, "Domain-Driven Design", 2003; Vaughn Vernon, "Implementing Domain-Driven Design", 2013)

A **Bounded Context** is an explicit boundary within which a domain model applies with a consistent meaning of terms. The same word may mean different things in different contexts.

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│ Order Context               │     │ Shipping Context            │
│  Order: payment status      │     │  Order: shipping address    │
│  Customer: billing info     │     │  Customer: delivery prefs   │
│  Product: price, discount   │     │  Product: weight, dimension │
└────────────────┬────────────┘     └────────────────┬────────────┘
                 │  Context Map — Shared Kernel / ACL │
                 └───────────────────────────────────┘
```

### Context Map relationship types

| Relationship | Description | Use when |
|---|---|---|
| **Shared Kernel** | Two contexts share a small subset of the domain model | High coupling acceptable, teams tightly coordinated |
| **Customer/Supplier** | Upstream supplies API; downstream adapts | Upstream owns the contract |
| **Conformist** | Downstream conforms to upstream model without influence | Integrating with external system you don't control |
| **Anti-Corruption Layer (ACL)** | Downstream translates upstream model | Protect your domain model from external model pollution |
| **Published Language** | Well-documented exchange format (OpenAPI, event schema) | Public APIs between teams or services |

---

## Aggregate Design

An **Aggregate** is a cluster of domain objects treated as a unit for data changes. Each Aggregate has a single **Aggregate Root** that controls all access.

### Rules (Vernon, "Implementing DDD")

1. **Reference by identity only** — aggregates reference other aggregates by ID, not by object reference
2. **One transaction = one aggregate** — never modify two aggregates in a single transaction
3. **Eventual consistency across aggregates** — use Domain Events to propagate state changes
4. **Design small aggregates** — start small and add to the boundary only when invariants demand it

```kotlin
// Aggregate Root — controls all invariants
class Order private constructor(
    val id: OrderId,
    private val customerId: CustomerId,       // ref by ID, not Customer object
    private val items: MutableList<OrderItem>,
    private var status: OrderStatus
) {
    companion object {
        fun create(customerId: CustomerId, items: List<OrderItem>): Order {
            require(items.isNotEmpty()) { "Order must have at least one item" }
            return Order(OrderId.generate(), customerId, items.toMutableList(), OrderStatus.PENDING)
        }
    }

    fun addItem(item: OrderItem) {
        check(status == OrderStatus.PENDING) { "Cannot modify a ${status} order" }
        items.add(item)
    }

    fun confirm(): OrderConfirmed {
        check(status == OrderStatus.PENDING) { "Order is already ${status}" }
        status = OrderStatus.CONFIRMED
        return OrderConfirmed(id, customerId, items.toList(), Instant.now())  // Domain Event
    }

    fun totalAmount(): Money = items.map { it.price }.reduce(Money::plus)
}

// OrderItem is a Value Object inside the Order aggregate — not a separate root
data class OrderItem(
    val productId: ProductId,  // ref by ID
    val price: Money,
    val quantity: Int
)
```

---

## Domain Events

Domain Events communicate state changes across Aggregate and Context boundaries.

```kotlin
// Domain Event — immutable record of something that happened
data class OrderConfirmed(
    val orderId: OrderId,
    val customerId: CustomerId,
    val items: List<OrderItem>,
    val confirmedAt: Instant
) : DomainEvent

// Publishing from the Aggregate Root
class Order {
    private val events: MutableList<DomainEvent> = mutableListOf()

    fun confirm(): Order {
        // ... state transition ...
        events.add(OrderConfirmed(id, customerId, items.toList(), Instant.now()))
        return this
    }

    fun pullEvents(): List<DomainEvent> = events.also { events.clear() }
}

// Infrastructure publishes after save
val order = orderRepository.save(updatedOrder)
order.pullEvents().forEach { event -> eventPublisher.publish(event) }
```

---

## Ubiquitous Language

Build a shared vocabulary between domain experts and engineers. Document in `design.md`:

```markdown
## Ubiquitous Language — Order Context

| Term | Meaning |
|---|---|
| Order | A customer's request to purchase one or more products; transitions through PENDING → CONFIRMED → SHIPPED → DELIVERED |
| Line Item | A single product+quantity entry within an Order |
| Fulfillment | The process of picking, packing, and shipping a confirmed Order |
| Backorder | An Order that cannot be immediately fulfilled due to insufficient inventory |
```

**Rule:** Never use a term in code that doesn't appear in the Ubiquitous Language dictionary. Rename classes and methods when the language evolves.

---

## Anemic Domain Model Anti-Pattern

(Reference: Martin Fowler, "Anemic Domain Model", 2003)

```kotlin
// BAD — Order is a data bag; all logic lives in OrderService
data class Order(var status: OrderStatus, var items: List<Item>)
class OrderService {
    fun confirm(order: Order) {
        if (order.status != PENDING) throw Exception("...")
        order.status = CONFIRMED  // violates Tell Don't Ask
    }
}

// GOOD — behavior lives inside the Aggregate
class Order {
    fun confirm(): OrderConfirmed { /* guard + state + event */ }
}
```

---

## Checklist
- [ ] Domain Events listed from Event Storming (past tense, covers all state transitions)
- [ ] Commands mapped to each event; actors identified
- [ ] Aggregate boundaries drawn around invariants (not around database tables)
- [ ] Aggregate Roots enforce all invariants; inner objects not accessible from outside
- [ ] Inter-aggregate references use IDs only (no object references)
- [ ] Domain Events emitted for all meaningful state transitions
- [ ] Bounded Contexts identified; Context Map drawn with relationship type for each boundary
- [ ] Ubiquitous Language dictionary written to `{TASK_DIR}/context/design.md`
- [ ] No anemic domain model (entities have behavior, not just getters/setters)
