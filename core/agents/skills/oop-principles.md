# OOP Principles

## Scope

These principles apply to all code written by agents, regardless of language,
tool, framework, host adapter, or runtime environment. Kotlin examples in this
file are illustrative only; apply the same rules to Java, JSP/JSPF, Python,
TypeScript, JavaScript, Go, Rust, Ruby, Shell, SQL, Groovy, Scala, Swift, PHP,
C/C++, C#, Dart, Vue, Svelte, XML, YAML, and comparable source files.

When this skill and `core/rules/code-quality.md` overlap, treat them as the
same baseline. Language-specific skills may add stricter guidance, but they do
not make these principles Kotlin-only.

## SOLID (Robert C. Martin, "Agile Software Development", 2002)

### S — Single Responsibility Principle
> "A class should have one, and only one, reason to change."

```kotlin
// BAD — invoice printing and calculation in one class
class Invoice {
    fun calculateTotal(): Money = TODO()
    fun printToPDF(): ByteArray = TODO()   // separate concern
    fun saveToDatabase() = TODO()           // separate concern
}

// GOOD
class Invoice {
    fun calculateTotal(): Money = TODO()
}
class InvoicePrinter(private val invoice: Invoice) {
    fun toPDF(): ByteArray = TODO()
}
class InvoiceRepository {
    fun save(invoice: Invoice) = TODO()
}
```

### O — Open/Closed Principle
> "Software entities should be open for extension, but closed for modification."

```kotlin
// BAD — adding a new discount type requires modifying this function
fun applyDiscount(order: Order, type: String): Money =
    when (type) {
        "SEASONAL" -> order.total * 0.9
        "LOYALTY"  -> order.total * 0.85
        else       -> order.total
    }

// GOOD — each strategy is a separate extension point
interface DiscountPolicy {
    fun apply(order: Order): Money
}
class SeasonalDiscount : DiscountPolicy {
    override fun apply(order: Order) = order.total * 0.9
}
class LoyaltyDiscount : DiscountPolicy {
    override fun apply(order: Order) = order.total * 0.85
}
class OrderService(private val discountPolicy: DiscountPolicy) {
    fun finalPrice(order: Order) = discountPolicy.apply(order)
}
```

### L — Liskov Substitution Principle
> "Subtypes must be substitutable for their base types." (Barbara Liskov, 1987)

```kotlin
// BAD — Square violates Rectangle's post-conditions
open class Rectangle(open var width: Int, open var height: Int) {
    fun area() = width * height
}
class Square(size: Int) : Rectangle(size, size) {
    override var width  = size set(v) { field = v; height = v }
    override var height = size set(v) { field = v; width  = v }
}
// rectangle.width = 5; rectangle.height = 10 → area() should be 50
// but Square(5).apply { width = 5; height = 10 }.area() == 100

// GOOD — separate abstractions
interface Shape { fun area(): Int }
class Rectangle(val width: Int, val height: Int) : Shape {
    override fun area() = width * height
}
class Square(val side: Int) : Shape {
    override fun area() = side * side
}
```

### I — Interface Segregation Principle
> "Clients should not be forced to depend upon interfaces they do not use."

```kotlin
// BAD — implementors are forced to implement unused operations
interface Worker {
    fun work()
    fun eat()
    fun sleep()
}

// GOOD
interface Workable { fun work() }
interface Feedable  { fun eat()   }
interface Restable  { fun sleep() }

class HumanWorker    : Workable, Feedable, Restable { /* ... */ }
class RobotWorker    : Workable                     { /* ... */ }
```

### D — Dependency Inversion Principle
> "High-level modules should not depend on low-level modules. Both should depend on abstractions."

```kotlin
// BAD — high-level service hardcodes a low-level implementation
class OrderService {
    private val repo = MySQLOrderRepository()  // concrete dependency
    fun place(order: Order) = repo.save(order)
}

// GOOD
interface OrderRepository { fun save(order: Order) }

class OrderService(private val repo: OrderRepository) {
    fun place(order: Order) = repo.save(order)
}
class MySQLOrderRepository : OrderRepository {
    override fun save(order: Order) = TODO()
}
```

---

## Object Calisthenics (Jeff Bay, "The ThoughtWorks Anthology", 2008)

Nine rules that make SOLID concrete at the method/class level.

### 1. Only One Level of Indentation per Method

```kotlin
// BAD
fun process(orders: List<Order>) {
    for (order in orders) {
        if (order.isValid()) {
            for (item in order.items) {
                item.apply()
            }
        }
    }
}

// GOOD
fun process(orders: List<Order>) =
    orders.filter { it.isValid() }
          .forEach { it.apply() }
```

### 2. Do Not Use the `else` Keyword

```kotlin
// BAD
fun getStatus(order: Order): String {
    if (order.isPaid()) { return "PAID" } else { return "PENDING" }
}

// GOOD — early return
fun getStatus(order: Order): String {
    if (order.isPaid()) return "PAID"
    return "PENDING"
}
```

### 3. Wrap Primitive Types and Strings

```kotlin
// BAD
class Order(val amount: Int)

// GOOD — encapsulates validation and domain behaviour
@JvmInline value class Money(val amount: Int) {
    init { require(amount >= 0) { "Amount must be non-negative" } }
    operator fun plus(other: Money) = Money(amount + other.amount)
    operator fun times(factor: Double) = Money((amount * factor).toInt())
}
class Order(val amount: Money)
```

### 4. Use First-Class Collections

```kotlin
// BAD
class Order(val items: List<Item>)

// GOOD
class OrderItems(private val items: List<Item>) {
    init { require(items.isNotEmpty()) { "Order must have at least one item" } }

    fun totalPrice(): Money =
        items.map { it.price }
             .reduce(Money::plus)

    fun count() = items.size
}
class Order(val items: OrderItems)
```

### 5. Use Only One Dot per Line (Law of Demeter)

> "Only talk to your immediate friends." (Ian Holland, 1987)
> A method should only call methods on: itself, its parameters, objects it creates, its direct fields.

```kotlin
// BAD — traverses the object graph: violates LoD
val city = order.customer.address.city

// GOOD — delegate to the object that owns the data
class Order(private val customer: Customer) {
    fun shippingCity(): City = customer.city()
}
```

### 6. Do Not Abbreviate

| Avoid | Prefer |
|---|---|
| `ord` | `order` |
| `mgr` | `manager` |
| `calc` | `calculate` |
| `repo` (in prod code) | `repository` |

### 7. Keep All Entities Small

- Classes: ≤ 50 lines (excluding blank lines and comments)
- Packages/modules: ≤ 10 files

### 8. No More Than Two Instance Variables per Class

Group cohesive fields into Value Objects.

```kotlin
// BAD — four fields; Address is a distinct concept
class Customer(
    val name: String,
    val street: String,
    val city: String,
    val zip: String,
)

// GOOD
class Address(val street: String, val city: String, val zip: String)
class Customer(val name: String, val address: Address)
```

### 9. Tell, Don't Ask (Martin Fowler, "Refactoring", 1999)

> "Don't ask an object for its state and then make decisions for it — tell it what to do."

```kotlin
// BAD — extracting state, deciding externally
if (order.status == OrderStatus.PAID) {
    order.status = OrderStatus.SHIPPED
}

// GOOD — behaviour lives inside the object
class Order {
    private var status: OrderStatus = OrderStatus.PENDING

    fun markPaid()    { check(status == OrderStatus.PENDING) { "Already paid" }; status = OrderStatus.PAID }
    fun ship()        { check(status == OrderStatus.PAID)    { "Not yet paid"  }; status = OrderStatus.SHIPPED }
    fun isPaid()      = status == OrderStatus.PAID
}
order.ship()
```

---

## Value Objects vs. Entities (Eric Evans, "Domain-Driven Design", 2003)

| | Value Object | Entity |
|---|---|---|
| Identity | Defined by its **attributes** | Defined by a **unique id** |
| Mutability | Immutable | May have mutable state |
| Equality | Structural (`==`) | By id |
| Examples | `Money`, `Address`, `Color` | `Order`, `Customer`, `Product` |

```kotlin
// Value Object — immutable, equality by value
@JvmInline value class Money(val amount: Int) {
    operator fun plus(other: Money) = Money(amount + other.amount)
}

// Entity — equality by id, encapsulates lifecycle transitions
class Order(val id: OrderId) {
    private var status: OrderStatus = OrderStatus.PENDING
    fun ship() { /* state transition with invariant guard */ }
    override fun equals(other: Any?) = other is Order && id == other.id
    override fun hashCode() = id.hashCode()
}
```
