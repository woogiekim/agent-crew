# TDD (Test-Driven Development)

## Core Cycle — Red → Green → Refactor (Kent Beck, "Test Driven Development: By Example", 2002)

```
RED    → Write a failing test that describes the next behaviour
GREEN  → Write the simplest code that makes the test pass
REFACTOR → Remove duplication; improve design without breaking tests
```

**Invariant**: never write production code without a failing test first.
**Invariant**: never refactor while a test is red.

## Domain Behavior Checklist Gate

Before writing test code, derive the domain behavior checklist from the
requirements. The goal is domain behavior coverage, not more tests and not
line coverage. Line coverage is not sufficient to prove that important domain
behaviors were tested.

Required sequence:

```text
requirements analysis -> test checklist derivation -> checklist-only review -> test code generation -> TC-ID mapping verification
```

The checklist must include these fields:

- TC-ID (`TC-001`, `TC-002`, ...)
- Category
- Given
- When
- Then
- Priority
- MUST / SHOULD / SUGGESTION
- Reason

Mandatory categories to inspect for every feature:

- Normal
- Exception
- Boundary
- Validation
- State Transition
- Authorization
- Ownership
- Idempotency
- Duplicate Request
- Concurrency
- Persistence Side Effect
- Domain Event
- External Dependency Failure
- Regression

If a category does not apply, record `N/A` with the reason. Silent omission is
invalid because it hides missing domain behavior coverage.

After checklist-only review is approved, every generated or updated test must
use descriptive names that communicate behavior through the test naming
contract below. TC-ID is an internal checklist/mapping identifier and is not
required in test names, display names, subtest labels, or docstrings. After
writing tests, produce `context/test-case-mapping.md` so every TC-ID maps to
either a concrete test reference with `Covered = YES` or a reviewer-accepted
explanation for why that case cannot be implemented. Every MUST item must be
implemented or explicitly explained.

```kotlin
// RED — test that does not compile yet
@Test
fun `should calculate total price of order items`() {
    val items = OrderItems(listOf(Item(Money(1000)), Item(Money(2000))))
    assertThat(items.totalPrice()).isEqualTo(Money(3000))
}
// → run ./gradlew test → confirm FAIL or compile error

// GREEN — minimal production code
class OrderItems(private val items: List<Item>) {
    fun totalPrice() = items.map { it.price }.reduce(Money::plus)
}
// → run ./gradlew test → confirm PASS

// REFACTOR — consider duplication, naming, Object Calisthenics
// → run ./gradlew test → confirm still PASS
```

---

## FIRST Principles (Brett L. Schuchert; popularised by Robert C. Martin)

| Letter | Property | Meaning |
|---|---|---|
| F | **Fast** | Tests run in milliseconds; slow tests are skipped |
| I | **Isolated** | Each test is independent; order does not matter |
| R | **Repeatable** | Same result on every machine, every run |
| S | **Self-validating** | Pass or fail — no manual inspection needed |
| T | **Timely** | Written just before the production code they test |

---

## Test Pyramid (Mike Cohn, "Succeeding with Agile", 2009)

```
        /\
       /E2E\          few — slow, brittle, expensive
      /------\
     /Integr. \       moderate — DB, HTTP, Kafka
    /----------\
   /   Unit     \     many — fast, isolated, cheap
  /______________\
```

- **Unit tests**: single class or function in isolation; mocked dependencies.
- **Integration tests**: multiple real components (DB, message broker, HTTP).
- **E2E tests**: full system through the UI or public API.

Target ratio: ≈ 70 % unit / 20 % integration / 10 % E2E.

---

## Test Doubles Taxonomy (Gerard Meszaros, "xUnit Test Patterns", 2007)

| Type | Purpose | MockK API |
|---|---|---|
| **Dummy** | Passed but never used | `mockk(relaxed = true)` |
| **Stub** | Returns fixed values | `every { … } returns …` |
| **Spy** | Real object; verifies calls | `spyk(RealImpl())` |
| **Mock** | Pre-programmed expectations | `mockk()` + `verify { … }` |
| **Fake** | Lightweight real implementation | `InMemoryOrderRepository` |

```kotlin
// Stub — control what the collaborator returns
@Test
fun `should apply seasonal discount from pricing service`() {
    val pricingService = mockk<PricingService>()
    every { pricingService.discountRate(any()) } returns 0.1

    val sut = OrderService(pricingService)

    assertThat(sut.finalPrice(order)).isEqualTo(Money(900))
}

// Mock — verify an interaction occurred
@Test
fun `should save order after placement`() {
    val repo = mockk<OrderRepository>()
    every { repo.save(any()) } just Runs

    val sut = OrderService(repo)

    sut.place(order)

    verify(exactly = 1) { repo.save(order) }
}

// Fake — in-memory implementation; no framework needed
class InMemoryOrderRepository : OrderRepository {
    private val store = mutableMapOf<OrderId, Order>()
    override fun save(order: Order) { store[order.id] = order }
    override fun findById(id: OrderId) = store[id]
}
```

**Guideline**: prefer Fakes for persistence layers; use Mocks sparingly and
only to verify a side-effect that is the **sole purpose** of the test.
(Reference: Martin Fowler, "Mocks Aren't Stubs", martinfowler.com, 2004)

---

## MockK — JUnit 5 Integration (Kotlin)

```kotlin
@ExtendWith(MockKExtension::class)
class OrderServiceTest {

    @MockK
    private lateinit var orderRepository: OrderRepository

    @InjectMockKs
    private lateinit var sut: OrderService

    @Test
    fun `should publish domain event after saving order`() {
        // given
        val order = Order.create(OrderItems(listOf(Item(Money(1000)))))
        every { orderRepository.save(any()) } returns order

        // when
        sut.placeOrder(order)

        // then
        verify(exactly = 1) { orderRepository.save(order) }
    }
}
```

---

## AssertJ Assertion Patterns (AssertJ docs)

```kotlin
// Basic equality
assertThat(result).isEqualTo(expected)
assertThat(result).isNotEqualTo(other)

// Null / presence
assertThat(result).isNotNull()
assertThat(optional).isPresent().get().isEqualTo(value)

// Collections
assertThat(list).hasSize(3)
assertThat(list).containsExactlyInAnyOrder(a, b, c)
assertThat(list).allMatch { it.isValid() }
assertThat(list).noneMatch { it.isDeleted() }

// Exception assertion
assertThatThrownBy { service.place(invalidOrder) }
    .isInstanceOf(IllegalArgumentException::class.java)
    .hasMessageContaining("invalid")

// Soft assertions — collect all failures
assertSoftly { s ->
    s.assertThat(order.status).isEqualTo(OrderStatus.PAID)
    s.assertThat(order.total).isEqualTo(Money(3000))
}
```

---

## Parameterized Tests (JUnit 5)

```kotlin
@ParameterizedTest
@MethodSource("discountScenarios")
fun `should apply correct discount for each tier`(
    tier: Tier, price: Money, expected: Money
) {
    assertThat(discountPolicy(tier).apply(price)).isEqualTo(expected)
}

companion object {
    @JvmStatic
    fun discountScenarios() = Stream.of(
        Arguments.of(Tier.BRONZE, Money(1000), Money(1000)),
        Arguments.of(Tier.SILVER, Money(1000), Money(900)),
        Arguments.of(Tier.GOLD,   Money(1000), Money(800)),
    )
}
```

---

## Test Naming Convention

Test name = `<nature-prefix>[(<qualifier>)] - <behavior>`

The nature prefix declares the case type before the behavior. Project teams may
localize the prefix words, but the structure is the contract:

- `success-case` / `성공케이스` — happy path or explicitly valid input.
- `failure-case` / `실패케이스` — error, exception, rejection, rollback, or
  validation path.
- Optional qualifier in parentheses names the mechanism or condition, for
  example `(boundary)`, `(validation)`, `(timeout)`, `(concurrency)`,
  `(propagation-rollback)`, or `(ordering-effect)`.

Use the canonical display string when the framework supports free-form test
names. When the framework requires identifier names, encode the same structure
in the identifier and keep the canonical display string in a docstring,
comment, subtest name, or closest equivalent.

Positive examples across supported test families:

```kotlin
// Kotest
test("성공케이스 - 정상 upsert면 byline과 profile이 모두 커밋된다") { }
test("실패케이스(전파 롤백) - profile 저장 실패면 byline INSERT가 롤백된다") { }

// JUnit5
@DisplayName("failure-case(validation) - rejects a blank nickname")
@Test
fun rejectsBlankNickname() { }
```

```typescript
// Jest / Vitest
test("success-case(boundary) - accepts a 500-char URL at the limit", () => {})
test("failure-case(timeout) - shows retry affordance when lookup times out", () => {})
```

```python
# pytest
def test_failure_case_validation_rejects_blank_nickname():
    """failure-case(validation) - rejects a blank nickname."""
```

```go
// Go testing
func TestValidateNicknameFailureCaseValidation(t *testing.T) {
    t.Run("failure-case(validation) - rejects a blank nickname", func(t *testing.T) {})
}
```

```rust
// Rust test
#[test]
fn failure_case_validation_rejects_blank_nickname() {
    // failure-case(validation) - rejects a blank nickname
}
```

```scala
// ScalaTest / MUnit
test("success-case(boundary) - accepts a nickname at the length limit") { }
```

```swift
// XCTest
func testFailureCaseValidationRejectsBlankNickname() {
    // failure-case(validation) - rejects a blank nickname
}
```

Reviewer guidance: flag changed tests whose test name, display name, subtest
name, or documented equivalent lacks a nature prefix as
`missing_test_nature_prefix`.

`given / when / then` comments are mandatory in every test body.

## Test Target Variable Naming

Default the object, function wrapper, component instance, hook result, or other
primary test target to `sut` (system under test) when a test introduces a local
variable or field for it.

Use domain-specific names for collaborators, inputs, expected values, fixtures,
and observed results. Do not rename those to `sut`; only the primary target
being exercised gets the `sut` name. If an existing project has an explicit,
documented test-target naming convention, follow the project convention and
record the exception in the TDD log.

---

## Transformation Priority Premise (Robert C. Martin, "8thlight.com blog", 2013)

When choosing the simplest GREEN implementation, prefer higher-priority
transformations over lower-priority ones:

| Priority | Transformation |
|---|---|
| 1 (highest) | `{}` → `nil` (return nothing) |
| 2 | `nil` → constant |
| 3 | constant → variable |
| 4 | unconditional → conditional (`if`) |
| 5 | scalar → array / collection |
| 6 | statement → recursion |
| 7 (lowest) | `if` → `while` / iteration |

Choosing a lower-priority transformation when a higher one suffices produces
harder-to-understand code and may hide design problems.

---

## Test Execution Commands (Gradle / Kotlin)

```bash
# Run all tests
./gradlew test

# Run a specific test class
./gradlew test --tests "com.example.domain.order.OrderServiceTest"

# Run a specific test method
./gradlew test --tests "com.example.domain.order.OrderServiceTest.should save order after placement"

# Verbose output
./gradlew test --info

# Continuous test runner
./gradlew test --continuous
```

---

## Spring Boot Testing Annotations (reference only)

| Annotation | Slice loaded | Use for |
|---|---|---|
| `@SpringBootTest` | Full application context | E2E / integration |
| `@WebMvcTest` | Web layer only | Controller unit tests |
| `@DataJpaTest` | JPA + embedded DB | Repository tests |
| `@MockBean` | Spring-managed mock | Replace beans in slice tests |

For domain logic (entities, services, value objects) prefer plain JUnit 5 +
MockK — no Spring context needed, orders of magnitude faster.
