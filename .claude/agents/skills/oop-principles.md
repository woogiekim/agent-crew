# Object Calisthenics Principles

## 1. Only One Level of Indentation per Method

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

---

## 2. Do Not Use the `else` Keyword

```kotlin
// BAD
fun getStatus(order: Order): String {
    if (order.isPaid()) { return "PAID" } else { return "PENDING" }
}

// GOOD — Early return
fun getStatus(order: Order): String {
    if (order.isPaid()) return "PAID"
    return "PENDING"
}
```

---

## 3. Wrap Primitive Types and Strings

```kotlin
// BAD
class Order(val amount: Int)

// GOOD
@JvmInline value class Money(val amount: Int) {
    init { require(amount >= 0) { "Amount must be greater than or equal to zero" } }
}
class Order(val amount: Money)
```

---

## 4. Use First-Class Collections

```kotlin
// BAD
class Order(val items: List<Item>)

// GOOD
class OrderItems(private val items: List<Item>) {
    init { require(items.isNotEmpty()) { "Order items cannot be empty" } }

    fun totalPrice(): Money =
        items.sumOf { it.price.amount }
            .let { Money(it) }
}

class Order(val items: OrderItems)
```

---

## 5. Use Only One Dot per Line

```kotlin
// BAD
order.customer.address.city

// GOOD — Follows the Law of Demeter
order.shippingCity()
```

---

## 6. Do Not Abbreviate

- `ord` → `order`
- `mgr` → `manager`
- `calc` → `calculate`

---

## 7. Keep All Entities Small

- Classes: recommended to stay under 50 lines
- Packages: recommended to stay under 10 files

---

## 8. Do Not Use Classes with More Than Two Instance Variables

- Group related fields into a Value Object

---

## 9. Do Not Use Getter/Setter/Property Access (Tell, Don't Ask)

```kotlin
// BAD — Extracting state and making decisions externally
if (order.status == OrderStatus.PAID) {
    order.status = OrderStatus.SHIPPED
}

// GOOD — Tell the object what to do
order.ship()
```