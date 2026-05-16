# Skill: api-design

## Purpose
Enables the backend agent to design RESTful and domain-driven API contracts before writing implementation code, ensuring the API surface is coherent, versioned, and aligned with the domain model derived from the PRD.

## When to Apply
- During Phase 1 (Requirement Analysis) before any TDD cycle begins
- When the PRD introduces new resources, relationships, or workflows
- When the frontend or designer agent needs an API contract to define integration points
- When refactoring an existing API surface to align with domain model changes

---

## REST Maturity Model (Leonard Richardson, 2008)

Target **Level 2** at minimum; Level 3 (HATEOAS) is optional unless the client is generic.

| Level | Name | Characteristics |
|---|---|---|
| 0 | RPC-style | Single endpoint, POST everything |
| 1 | Resources | Separate URLs per resource |
| 2 | HTTP Verbs | Use GET/POST/PUT/PATCH/DELETE semantics |
| 3 | HATEOAS | Responses embed navigable links |

---

## HTTP Method Semantics

(Reference: RFC 7231 — HTTP/1.1 Semantics and Content)

| Method | Safe | Idempotent | Body | Typical Use |
|---|---|---|---|---|
| GET | ✓ | ✓ | no | Read resource |
| HEAD | ✓ | ✓ | no | Read metadata only |
| POST | ✗ | ✗ | yes | Create; non-idempotent action |
| PUT | ✗ | ✓ | yes | Full replacement |
| PATCH | ✗ | ✗ | yes | Partial update |
| DELETE | ✗ | ✓ | no | Remove resource |

**Safe** = no observable side effect on server state.
**Idempotent** = N identical calls have same effect as one call.

---

## Resource-Oriented URL Design

Model endpoints around domain resources, not actions. Use HTTP verbs for semantics.

```
POST   /orders                       # Create
GET    /orders/{id}                  # Read one
GET    /orders?status=PENDING&page=1 # Read collection with filter
PUT    /orders/{id}                  # Full replace
PATCH  /orders/{id}/status           # Partial update (bounded action)
DELETE /orders/{id}                  # Remove
```

**Rules:**
- Plural nouns for collections (`/orders`, `/products`)
- Nested resources only one level deep (`/orders/{id}/items`, not deeper)
- Actions that don't map to CRUD: use a sub-resource noun (`/orders/{id}/cancellation`)

---

## Request / Response Contract Definition

Define typed shapes before coding. Document in `{TASK_DIR}/context/design.md`.

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

---

## Error Contract — RFC 7807 Problem Details

Standardize error responses using the Problem Details format (RFC 7807):

```kotlin
data class ProblemDetail(
    val type: URI,           // e.g. "https://api.example.com/errors/order-not-found"
    val title: String,       // human-readable summary
    val status: Int,         // HTTP status code
    val detail: String,      // instance-specific explanation
    val instance: URI? = null
)
```

Domain exception → HTTP status mapping:

| Exception | Status | Reason |
|---|---|---|
| `EntityNotFoundException` | 404 | Resource does not exist |
| `DomainRuleViolationException` | 422 | Business invariant violation |
| `ConflictException` | 409 | Concurrent modification / duplicate |
| `UnauthorizedException` | 401 | Not authenticated |
| `ForbiddenException` | 403 | Authenticated but not authorized |
| `ValidationException` | 400 | Invalid input shape |

---

## Pagination Patterns

Choose one strategy per collection endpoint and document it in design.md.

### Offset Pagination (simple, UI-friendly)
```
GET /orders?page=2&pageSize=20
```
```kotlin
data class PageResponse<T>(
    val items: List<T>,
    val total: Long,
    val page: Int,
    val pageSize: Int,
    val hasNext: Boolean
)
```
**Limitation:** unstable under concurrent insertions (items shift between pages).

### Cursor Pagination (stable, preferred for real-time data)
```
GET /orders?after=eyJpZCI6MTIzfQ==&limit=20
```
```kotlin
data class CursorPageResponse<T>(
    val items: List<T>,
    val nextCursor: String?,   // null when no more pages
    val hasMore: Boolean
)
```
**Use when:** feed-style lists, real-time updates, large datasets.

---

## Aggregate Root Alignment (DDD)

Each API resource should correspond to an **Aggregate Root**. Never expose internal entities directly.

**Checklist before coding:**
- Does each endpoint operate on exactly one Aggregate Root?
- Are IDs external (UUID) rather than internal (auto-increment)?
- Are response objects free of lazy-loaded child collections?
- Does the response DTO hide internal domain state?

---

## Conditional Requests — ETag (RFC 7232)

Use ETags to prevent stale updates (optimistic locking over HTTP):

```http
# Server response
HTTP/1.1 200 OK
ETag: "33a64df551425fcc55e4d42a148795d9f25f89d4"
Content-Type: application/json

# Client update (fails with 412 if ETag changed)
PUT /orders/{id}
If-Match: "33a64df551425fcc55e4d42a148795d9f25f89d4"
```

---

## Rate Limiting Headers

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1715865600
Retry-After: 30
```

Return **429 Too Many Requests** when the limit is exceeded.

---

## Versioning Strategy

Document the chosen approach in design.md before any client contract is published:

| Strategy | Example | Notes |
|---|---|---|
| Path-based | `/v2/orders` | Simplest; breaks REST resource identity |
| Header-based | `Accept: application/vnd.api+json;version=2` | Cleanest; harder to test in browser |
| Query param | `/orders?version=2` | Easiest for clients; pollutes query space |

**Preferred for greenfield:** path-based (`/v2/`) — easy to discover and cache.

---

## OpenAPI Contract-First Approach

Write the OpenAPI 3.x spec **before** implementation; generate server stubs and client SDKs from it.

```yaml
# openapi.yaml (abbreviated)
paths:
  /orders:
    post:
      summary: Create a new order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '422':
          $ref: '#/components/responses/UnprocessableEntity'
```

---

## Checklist
- [ ] REST maturity level decided (target ≥ Level 2)
- [ ] All new endpoints listed with HTTP method, path, and purpose
- [ ] HTTP method semantics correct (safe/idempotent properties respected)
- [ ] Request and response types defined as typed DTOs
- [ ] Error contract follows RFC 7807 format; domain exceptions mapped to HTTP status codes
- [ ] Each endpoint corresponds to exactly one Aggregate Root
- [ ] Pagination strategy chosen and documented (offset vs. cursor)
- [ ] IDs are UUIDs (not auto-increment integers)
- [ ] ETag strategy defined for mutable resources that require optimistic locking
- [ ] Rate limiting headers included if public-facing
- [ ] Versioning approach documented
- [ ] API design recorded in `{TASK_DIR}/context/design.md` before any TDD cycle
