# Skill: effective-scala

## Source
- Twitter Engineering, *Effective Scala*, https://twitter.github.io/effectivescala/ (canonical)
- Martin Odersky, Lex Spoon & Bill Venners, *Programming in Scala* (5th ed.), Artima, 2021
- Typelevel, *Scala Best Practices*, https://nrinaudo.github.io/scala-best-practices/

## When to Apply
- Before writing any Scala class, trait, case class, or object
- Before choosing between `val`/`var`, `Option` / `Either` / `Try`, and collection operations
- Before using implicits, type classes, or higher-kinded types
- During refactor: when eliminating `null`, `throw`, or mutable state in Scala code

---

## Core Rules

### Rule 1: Prefer immutability — `val`, immutable collections, case classes
> Source: Twitter Effective Scala § Immutability; Odersky Ch. 4

Mutable state is a concurrency hazard and a source of reasoning bugs. Prefer
`val` over `var`. Use `scala.collection.immutable.*` by default. Model value
objects as `case class` (immutable, `copy`-able).

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

Pattern matching is exhaustive on sealed hierarchies, readable, and
prevents `ClassCastException`. Never use `isInstanceOf` in application code.

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

Sealed traits restrict subclasses to the current file — the compiler warns on
non-exhaustive pattern matches.

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

Implicits are powerful but make code hard to trace. Use `given`/`using`
(Scala 3) or `implicit` (Scala 2) only for type-class instances and context
propagation. Never use implicits for domain logic or to save typing.

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

For-comprehensions desugar to `flatMap` / `map` / `withFilter` but are more
readable for sequences of monadic operations.

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

`List` is O(1) prepend, O(n) indexed access — good for functional recursion.
`Vector` is effectively O(1) random access — good for general purpose.
Never use `ArrayBuffer` / `ListBuffer` in public APIs.

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

Mutable `object` state is effectively global mutable state. Use `lazy val` for
expensive once-computed values; use dependency injection for services.

### Rule 10: Format with `scalafmt`; lint with `scalafix`; both enforced in CI
> Source: Scala community consensus

`scalafmt` is the canonical formatter. `scalafix` rules (`OrganizeImports`,
`RemoveUnused`, `DisableSyntax`) prevent accumulation of dead code and
dangerous constructs.

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
