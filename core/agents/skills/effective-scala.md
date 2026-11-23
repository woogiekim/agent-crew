# Skill: effective-scala

## Source
- Twitter Engineering, *Effective Scala*, https://twitter.github.io/effectivescala/ (canonical)
- Martin Odersky, Lex Spoon & Bill Venners, *Programming in Scala* (5th ed.), Artima, 2021
- Typelevel, *Scala Best Practices*, https://nrinaudo.github.io/scala-best-practices/

## When to Apply
- Writing Scala classes, traits, case classes, or objects
- Choosing `val` or `var`, `Option` / `Either` / `Try`, or collection operations
- Using implicits, type classes, or higher-kinded types
- Removing `null`, `throw`, or mutable state during refactoring

---

## Core Rules

### Rule 1: Prefer immutability — `val`, immutable collections, case classes
> Source: Twitter Effective Scala § Immutability; Odersky Ch. 4

Default to `val` and `scala.collection.immutable.*`. Model value objects
as immutable case classes with `copy`.

```scala
// BAD
var total = 0
items.foreach(item => total += item.price)

// GOOD
val total = items.map(_.price).sum
```

### Rule 2: Use `Option`, `Either`, and `Try` instead of null / throw
> Source: Twitter Effective Scala § Functional programming; Typelevel best practices

- `Option[T]` for values that may be absent (not a failure)
- `Either[E, T]` for typed domain failures (left = error, right = success)
- `Try[T]` only when wrapping third-party code that throws

```scala
// BAD
def findOrder(id: OrderId): Order = {
  val order = repository.get(id)
  if (order == null) throw new OrderNotFoundException(id)
  order
}

// GOOD
def findOrder(id: OrderId): Either[OrderError, Order] =
  Option(repository.get(id))
    .toRight(OrderError.NotFound(id))
```

### Rule 3: Pattern matching over `isInstanceOf` / `asInstanceOf`
> Source: Twitter Effective Scala § Pattern matching; Odersky Ch. 15

Use pattern matching for exhaustiveness checks on sealed types and to avoid cast failures.
Never use `isInstanceOf` in application code.

```scala
// BAD
if (event.isInstanceOf[OrderPlaced])
  process(event.asInstanceOf[OrderPlaced])

// GOOD
event match {
  case OrderPlaced(id, at) => process(id, at)
  case OrderCancelled(id)  => cancel(id)
}
```

### Rule 4: Sealed traits for domain discriminated unions — exhaustiveness enforced
> Source: Twitter Effective Scala § Types; Odersky Ch. 15

Sealed traits confine subclasses to one file and let the compiler flag incomplete matches.

```scala
sealed trait OrderStatus
case object Pending    extends OrderStatus
case object Confirmed  extends OrderStatus
case object Cancelled  extends OrderStatus

def label(status: OrderStatus): String = status match {
  case Pending   => "Awaiting confirmation"
  case Confirmed => "Confirmed"
  // compiler error if Cancelled is not covered
}
```

### Rule 5: Keep implicits narrow and explicit — prefer explicit parameters when readable
> Source: Twitter Effective Scala § Implicits; Typelevel best practices

Reserve Scala 3 `given`/`using` and Scala 2 `implicit` for type-class instances
and context propagation. Pass domain logic and convenience arguments explicitly.

```scala
// BAD — implicit conversion for convenience
implicit def intToMoney(n: Int): Money = Money(n)
val total: Money = 100   // where did the conversion come from?

// GOOD — explicit type-class instance
given Ordering[Money] with
  def compare(a: Money, b: Money): Int = a.amount.compareTo(b.amount)
```

### Rule 6: Prefer for-comprehensions over nested `map`/`flatMap` chains
> Source: Twitter Effective Scala § Functional programming

Use for-comprehensions to express monadic sequences clearly. They desugar to `flatMap`, `map`, and `withFilter`.

```scala
// BAD — nested
def placeOrder(cmd: PlaceOrderCommand): Either[DomainError, Order] =
  validateCustomer(cmd.customerId).flatMap(c =>
    validateItems(cmd.items).flatMap(items =>
      createOrder(c, items)))

// GOOD — for-comprehension
def placeOrder(cmd: PlaceOrderCommand): Either[DomainError, Order] =
  for {
    customer <- validateCustomer(cmd.customerId)
    items    <- validateItems(cmd.items)
    order    <- createOrder(customer, items)
  } yield order
```

### Rule 7: Avoid mutable collections; use `Vector` for indexed, `List` for prepend-heavy
> Source: Twitter Effective Scala § Collections

Use `List` for recursive, prepend-heavy work (O(1) prepend, O(n) indexing).
Use `Vector` for general use and effectively O(1) random access.
Never expose `ArrayBuffer` or `ListBuffer` in public APIs.

### Rule 8: ScalaTest / MUnit — descriptive test names, avoid `AnyFlatSpec` boilerplate
> Source: ScalaTest documentation; community consensus

Test names should read as specifications:

```scala
class OrderServiceSpec extends AnyFunSpec {
  describe("OrderService") {
    it("returns NotFound when the order does not exist") { … }
    it("places an order and emits an OrderPlaced event") { … }
  }
}
```

### Rule 9: No `var` in `object` scope; use `lazy val` for deferred initialisation
> Source: Twitter Effective Scala § Objects; Typelevel best practices

Use `lazy val` for expensive one-time initialization. Inject services as dependencies.

### Rule 10: Format with `scalafmt`; lint with `scalafix`; both enforced in CI
> Source: Scala community consensus

Format with `scalafmt`. Use `OrganizeImports`, `RemoveUnused`, and `DisableSyntax` in `scalafix`.

---

## Anti-Patterns
- `null` return values — use `Option`
- `throw` for domain errors — use `Either` or `Try`
- `var` for state that is written once — use `val`
- Implicit conversions for domain types — use type classes with `given`
- `return` statements inside `for` / `map` — use early `Either.left`
- `@unchecked` annotation on pattern matches — fix the exhaustiveness gap instead

## Interaction with Other Skills
- Combine with `tdd.md`: ScalaTest / MUnit + property-based testing with ScalaCheck
- Combine with `clean-architecture.md`: sealed traits (Rule 4) model domain entities; traits model ports
- Combine with `oop-principles.md`: SOLID applies — sealed hierarchies enforce OCP

## References
- Twitter Engineering, *Effective Scala*, https://twitter.github.io/effectivescala/
- Martin Odersky, Lex Spoon & Bill Venners, *Programming in Scala* (5th ed.), Artima, 2021. ISBN 978-0-9815316-8-7.
- Typelevel, *Scala Best Practices*, https://nrinaudo.github.io/scala-best-practices/
- `scalafmt`, https://scalameta.org/scalafmt/
- `scalafix`, https://scalacenter.github.io/scalafix/
