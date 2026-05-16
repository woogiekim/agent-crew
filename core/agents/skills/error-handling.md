# Skill: error-handling

## Purpose
Enables the backend and frontend agents to design explicit, composable error flows using typed error hierarchies, Railway-Oriented Programming, and structured error contracts — eliminating silent failures and untyped exception paths.

## When to Apply
- When designing any function that can fail (I/O, validation, domain rule violation)
- When defining API error contracts
- When refactoring try/catch spaghetti into typed error flows
- Before writing any repository, service, or controller code

---

## Exception Hierarchy Design

Structure exceptions in three layers. Each layer has a distinct owner and propagation rule.

```kotlin
// Layer 1 — Domain exceptions (business rule violations; always intentional)
sealed class DomainException(message: String) : RuntimeException(message)
class OrderAlreadyPaidException(orderId: OrderId)
    : DomainException("Order ${orderId.value} is already paid")
class InsufficientInventoryException(productId: ProductId, requested: Int, available: Int)
    : DomainException("Insufficient inventory for ${productId.value}: requested=$requested, available=$available")

// Layer 2 — Application exceptions (use-case / orchestration failures)
sealed class ApplicationException(message: String, cause: Throwable? = null)
    : RuntimeException(message, cause)
class OrderNotFoundException(orderId: OrderId)
    : ApplicationException("Order not found: ${orderId.value}")
class ExternalServiceException(service: String, cause: Throwable)
    : ApplicationException("External service failed: $service", cause)

// Layer 3 — Infrastructure exceptions (I/O, persistence, network)
// Use standard library or framework exceptions; wrap at the boundary
```

**Rule:** Domain exceptions must never contain infrastructure concerns. Infrastructure exceptions must be caught at the boundary and translated to Application or Domain exceptions before crossing into business logic.

---

## Railway-Oriented Programming (Scott Wlaschin, "Domain Modeling Made Functional", 2018)

Model operations as a railway: success stays on the happy track, failures switch to the error track without throwing.

```kotlin
// Result type (Kotlin Arrow or stdlib Result)
// Using Arrow's Either: Either<Error, Value>

sealed interface OrderError {
    data class NotFound(val id: OrderId) : OrderError
    data class AlreadyPaid(val id: OrderId) : OrderError
    data class InsufficientInventory(val productId: ProductId) : OrderError
    data class PersistenceFailed(val cause: Throwable) : OrderError
}

// Each step returns Either — compose with flatMap / bind
fun processOrder(orderId: OrderId): Either<OrderError, Order> =
    findOrder(orderId)                           // Either<OrderError, Order>
        .flatMap { order -> validatePayment(order) }  // Either<OrderError, Order>
        .flatMap { order -> reserveInventory(order) } // Either<OrderError, Order>
        .flatMap { order -> saveOrder(order) }        // Either<OrderError, Order>

// Callers handle both tracks explicitly — no surprise exceptions
when (val result = processOrder(id)) {
    is Either.Right -> renderSuccess(result.value)
    is Either.Left  -> when (val err = result.value) {
        is OrderError.NotFound           -> respond(404, err)
        is OrderError.AlreadyPaid        -> respond(409, err)
        is OrderError.InsufficientInventory -> respond(422, err)
        is OrderError.PersistenceFailed  -> respond(500, err)
    }
}
```

**Benefits:** errors are explicit in the return type, compose without nesting, and cannot be silently swallowed.

---

## Kotlin Result / Arrow Either — When to Use Each

| Tool | Use when | Notes |
|---|---|---|
| `kotlin.Result<T>` | Single-error path; simple success/failure | Built-in; no dep. Limited to `Throwable` error |
| `Either<L, R>` (Arrow) | Typed error variants; composable chains | Richer API; `flatMap`, `mapLeft`, `recover` |
| `sealed class Error` enum-style | Multiple distinct failure modes | Combine with either; exhaustive `when` |
| Plain `throw` | Programming errors (bugs, illegal state) | Errors the caller cannot meaningfully handle |

**Rule:** `throw` for programmer errors (contract violations, impossible states). Return `Either` / `Result` for expected failures that the caller is expected to handle.

---

## Validation — Accumulating Errors

Use a validation applicative (Arrow `Validated` / `Either` with `zip`) to collect ALL errors before reporting — not fail-fast.

```kotlin
// Fail-fast (Either) — stops at first error
fun validateOrder(req: CreateOrderRequest): Either<OrderError, ValidatedOrder> =
    validateCustomerId(req.customerId)
        .flatMap { customerId -> validateItems(req.items).map { items -> customerId to items } }
        .map { (customerId, items) -> ValidatedOrder(customerId, items) }

// Accumulating (Arrow Raise / Validated) — collects all errors
context(Raise<NonEmptyList<ValidationError>>)
fun validateOrder(req: CreateOrderRequest): ValidatedOrder {
    val customerId = validate(req.customerId, ::validateCustomerId)
    val items = validate(req.items, ::validateItems)
    return ValidatedOrder(customerId, items)
}
```

Prefer accumulating validation at API boundaries (show all field errors at once). Prefer fail-fast in domain logic (stop at first invariant violation).

---

## Error Boundary Patterns

### Repository Boundary — Translate infrastructure to domain

```kotlin
class JpaOrderRepository(private val jpa: OrderJpaRepository) : OrderRepository {
    override fun findById(id: OrderId): Either<OrderError, Order> =
        try {
            jpa.findByIdOrNull(id.value)
                ?.toDomain()
                ?.right()
                ?: OrderError.NotFound(id).left()
        } catch (e: DataAccessException) {
            OrderError.PersistenceFailed(e).left()
        }
}
```

### Controller Boundary — Translate domain to HTTP

```kotlin
@ExceptionHandler(DomainException::class)
fun handleDomain(ex: DomainException): ResponseEntity<ProblemDetail> =
    when (ex) {
        is OrderAlreadyPaidException -> ResponseEntity
            .status(409)
            .body(ProblemDetail.of(409, "ORDER_ALREADY_PAID", ex.message))
        is InsufficientInventoryException -> ResponseEntity
            .status(422)
            .body(ProblemDetail.of(422, "INSUFFICIENT_INVENTORY", ex.message))
    }
```

**Rule:** never let infrastructure exceptions (`DataAccessException`, `IOException`, `HttpClientErrorException`) propagate past their boundary layer. Always catch, log, and translate.

---

## Logging at Error Sites

(Reference: "The Art of Logging", SRE Book chapter 8)

```kotlin
// GOOD — structured logging with context
log.error("Order placement failed",
    "order_id" to orderId.value,
    "customer_id" to customerId.value,
    "error" to error::class.simpleName,
    "cause" to error.message
)

// BAD — no context, swallowed or rethrown raw
log.error(e.message)
throw e
```

**Rules:**
- Log at the boundary where the error is **translated** (not where it's re-thrown)
- Never log sensitive data (PII, tokens, passwords) — log the ID or type only
- Include correlation IDs in every error log line (`trace_id`, `request_id`)

---

## Checklist
- [ ] Exception hierarchy designed in 3 layers (Domain / Application / Infrastructure)
- [ ] Infrastructure exceptions caught and translated at every boundary
- [ ] Railway-oriented flow used for operations with multiple expected failure modes
- [ ] Validation at API boundary accumulates all errors (not fail-fast)
- [ ] Domain logic validation uses fail-fast (stop at first invariant violation)
- [ ] `throw` used only for programmer errors (impossible states, contract violations)
- [ ] Controller maps domain/application exceptions to RFC 7807 Problem Details
- [ ] Error logs include context (entity ID, user ID, trace ID) without PII
- [ ] No empty `catch` blocks; no swallowed exceptions
- [ ] Error contract defined in `{TASK_DIR}/context/design.md`
