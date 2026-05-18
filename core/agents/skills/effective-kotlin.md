# Skill: effective-kotlin

## Source
- Marcin Moskala, *Effective Kotlin: Best Practices*, Kt. Academy, 2022 (2nd ed.)
- JetBrains, *Kotlin Coding Conventions*, https://kotlinlang.org/docs/coding-conventions.html

## When to Apply
- Before writing any Kotlin class, function, or data model
- Before choosing between `var` and `val`, class and data class, interface and abstract class
- Before writing extension functions, lambdas, or coroutine-based async code
- During refactor: when simplifying existing Kotlin code

---

## Core Rules

### Rule 1: Prefer immutability — `val` over `var`, immutable collections
> Source: Moskala, Item 1 "Limit mutability"

Mutable state is a source of bugs. Prefer `val` for properties; use
`List`/`Set`/`Map` (not `MutableList`) in public APIs. Change state only
through dedicated mutation functions that return new values.

```kotlin
// BAD
var total = 0
items.forEach { total += it.price }

// GOOD
val total = items.sumOf { it.price }
```

### Rule 2: Eliminate platform types — annotate Java interop return types
> Source: Moskala, Item 3 "Eliminate platform types as soon as possible"

When calling Java code, annotate the result immediately at the call site to
prevent `NullPointerException`s from propagating:

```kotlin
// BAD — javaApi.getUser() returns a platform type T!
val user = javaApi.getUser()          // nullable leak

// GOOD
val user: User? = javaApi.getUser()   // explicit at the boundary
```

### Rule 3: Specify return types explicitly on public functions
> Source: Moskala, Item 4 "Infer return types of public functions carefully"

Public API functions must have explicit return types. Inferred types in public
interfaces cause unexpected signature changes after refactoring.

```kotlin
// BAD
fun getActiveOrders() = repository.findAll().filter { it.isActive }

// GOOD
fun getActiveOrders(): List<Order> = repository.findAll().filter { it.isActive }
```

### Rule 4: Prefer data classes for value objects; no logic in data classes
> Source: Moskala, Item 37 "Use data modifier to represent a bundle of data"

Data classes are for pure data bundles. Do not add business logic to them —
that logic belongs in the aggregate or domain service.

```kotlin
// BAD — business logic in data class
data class Money(val amount: Int, val currency: String) {
    fun convert(target: String): Money = currencyService.convert(this, target)
}

// GOOD — logic in domain service, data class stays pure
data class Money(val amount: Int, val currency: String)
class CurrencyConverter { fun convert(money: Money, target: String): Money = TODO() }
```

### Rule 5: Use sealed classes / sealed interfaces for exhaustive when
> Source: Moskala, Item 39 "Prefer sealed classes and interfaces to represent restricted hierarchies"

When branching on a type hierarchy, `sealed class`/`sealed interface` + `when`
gives compile-time exhaustiveness. Never use string literals or open class
hierarchies for discriminated unions.

```kotlin
// BAD
fun handle(event: DomainEvent) {
    if (event is OrderPlaced) { … }
    // OrderCancelled silently ignored
}

// GOOD
sealed interface DomainEvent
data class OrderPlaced(val orderId: OrderId) : DomainEvent
data class OrderCancelled(val orderId: OrderId) : DomainEvent

fun handle(event: DomainEvent) = when (event) {
    is OrderPlaced    -> processPlacement(event)
    is OrderCancelled -> processCancellation(event)
    // compiler error if a new subtype is added and not handled
}
```

### Rule 6: Prefer extension functions to utility classes
> Source: Moskala, Item 46 "Use extension functions instead of utility functions"

Kotlin extension functions attach cleanly to the type they extend, are
discoverable via IDE completion, and avoid Util / Helper class proliferation.

```kotlin
// BAD
object OrderUtils {
    fun calculateTax(order: Order): Money = TODO()
}

// GOOD
fun Order.calculateTax(): Money = TODO()
```

### Rule 7: Use scope functions sparingly and consistently
> Source: Moskala, Item 15 "Consider referencing receivers explicitly"

Choose the correct scope function for the intent:
- `let` — nullable safe-call chain, result transformation
- `apply` — object configuration (returns receiver)
- `run` — computation on receiver, result needed
- `with` — multiple operations on non-null receiver (avoid for nullable)
- `also` — side effects (logging, validation) without consuming result

Do not nest scope functions more than two levels deep.

### Rule 8: Avoid checked exceptions — use Result / Either for domain errors
> Source: Moskala, Item 7 "Prefer Null or Failure Result when the lack of result is expected"

Domain errors are not exceptional. Use `Result<T>` or a domain-specific
`Either<Error, T>` to make failure paths explicit in the type system. Reserve
exceptions for programming errors and infrastructure failures.

```kotlin
// BAD
fun findOrder(id: OrderId): Order = throw OrderNotFoundException(id)

// GOOD
fun findOrder(id: OrderId): Result<Order> =
    repository.findById(id)?.let { Result.success(it) }
        ?: Result.failure(OrderNotFoundException(id))
```

### Rule 9: Coroutines — structured concurrency, never GlobalScope
> Source: Moskala, Item 52 "Use structured concurrency"; JetBrains Coroutine Best Practices

All coroutines must be launched within a `CoroutineScope` whose lifecycle
matches the caller (e.g., `viewModelScope`, `lifecycleScope`, or an
injected scope). `GlobalScope.launch` leaks work and bypasses cancellation.

```kotlin
// BAD
fun fetchOrders() = GlobalScope.launch { … }

// GOOD
class OrderViewModel(private val scope: CoroutineScope) {
    fun fetchOrders() = scope.launch { … }
}
```

### Rule 10: Name functions as verbs, properties as nouns; test methods as sentences
> Source: Kotlin Coding Conventions § Naming rules

- Functions: `calculateTotal()`, `placeOrder()` — verb phrase
- Properties: `totalPrice`, `orderStatus` — noun phrase
- Boolean properties: `isActive`, `hasItems` — `is`/`has`/`can` prefix
- Test methods: backtick sentence — `` `should return empty list when no orders exist`() ``

---

## Anti-Patterns
- `var` for state that never changes after initialization
- `!!` (non-null assertion) outside test code — use `?: error(…)` or `requireNotNull`
- `Object` / companion-object-based singletons for domain logic — prefer DI
- `internal` visibility suppression of unit-testable public logic
- Mixing coroutine context without `withContext(Dispatchers.IO)` for blocking calls
- `@JvmStatic` in Kotlin-only codebases (no Java callers)

## Interaction with Other Skills
- Combine with `tdd.md`: RED → GREEN → REFACTOR loop applies to every Kotlin unit
- Combine with `clean-architecture.md`: data classes live in domain layer; coroutines in application layer
- Combine with `oop-principles.md`: SOLID principles apply — Rule 5 above directly implements OCP

## References
- Marcin Moskala, *Effective Kotlin: Best Practices* (2nd ed.), Kt. Academy, 2022.
- JetBrains, *Kotlin Coding Conventions*, https://kotlinlang.org/docs/coding-conventions.html
- Roman Elizarov et al., *Coroutines Guide*, https://kotlinlang.org/docs/coroutines-guide.html
