# Skill: api-design

## Purpose
Enables the backend agent to design RESTful and domain-driven API contracts before writing implementation code, ensuring the API surface is coherent, versioned, and aligned with the domain model derived from the PRD.

## When to Apply
- During Phase 1 (Requirement Analysis) before any TDD cycle begins
- When the PRD introduces new resources, relationships, or workflows
- When the frontend or designer agent needs an API contract to define integration points
- When refactoring an existing API surface to align with domain model changes

## Techniques

### Resource-Oriented URL Design
Model endpoints around domain resources, not actions. Use HTTP verbs for semantics.

**Example:**
```
POST   /orders                    # Create a new order
GET    /orders/{id}               # Retrieve an order
PUT    /orders/{id}/status        # Update order status (bounded action)
DELETE /orders/{id}               # Cancel/remove an order
GET    /orders?status=PENDING     # Query with filter
```

### Request / Response Contract Definition
Define typed request/response shapes before coding. Document in `{TASK_DIR}/context/design.md`.

**Example contract:**
```kotlin
// Request
data class CreateOrderRequest(
    val customerId: UUID,
    val items: List<OrderItemRequest>
)
data class OrderItemRequest(val productId: UUID, val quantity: Int)

// Response
data class OrderResponse(
    val id: UUID,
    val status: OrderStatus,
    val totalAmount: Money,
    val createdAt: Instant
)
```

### Error Contract Standardization
Define a consistent error envelope across all endpoints:

```kotlin
data class ApiError(
    val code: String,       // e.g. "ORDER_NOT_FOUND"
    val message: String,
    val details: Map<String, Any> = emptyMap()
)
```

Map domain exceptions to HTTP status codes explicitly:
- `EntityNotFoundException` → 404
- `DomainRuleViolationException` → 422
- `UnauthorizedException` → 401

### Aggregate Root Alignment
Each API resource should correspond to an Aggregate Root in the domain model. Avoid exposing raw database rows or entity internals.

**Checklist before coding:**
- Does each endpoint operate on exactly one Aggregate Root?
- Are IDs external (UUID) rather than internal (auto-increment)?
- Are response objects free of lazy-loaded child collections?

### Versioning Strategy
Document the versioning approach in design.md:
- Header-based: `Accept: application/vnd.api+json;version=2`
- Path-based: `/v2/orders` (simpler, preferred for greenfield)

## Checklist
- [ ] All new endpoints listed with HTTP method, path, and purpose
- [ ] Request and response types defined as Kotlin data classes or equivalent
- [ ] Error contract defined and domain exceptions mapped to HTTP status codes
- [ ] Each endpoint corresponds to exactly one Aggregate Root
- [ ] API design recorded in `{TASK_DIR}/context/design.md` before any TDD cycle
- [ ] Frontend integration point interfaces derived from the API contract
- [ ] Versioning approach documented if multiple versions are needed
