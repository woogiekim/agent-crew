# TDD (Test-Driven Development)

## Core Cycle — Red → Green → Refactor (Kent Beck, "Test Driven Development: By Example", 2002)

```
RED    → Write a failing test that describes the next behaviour
GREEN  → Write the simplest code that makes the test pass
REFACTOR → Remove duplication; improve design without breaking tests
```

**Invariant**: never write production code without a failing test first.
**Invariant**: never refactor while a test is red.

## 구현 전 기존 계약과 실제 실행

운영 코드 수정 전에 변경 전 코드와 호출자를 따라 정상·실패·경계, 응답·예외·저장·rollback·관찰 가능한 부작용을 식별한다. 보존 계약, 이번 요청이 명시적으로 바꾸는 계약, 미확인을 나눈다. API 외의 파일·이벤트·도구 출력도 같은 원칙을 따른다.

보존 TC는 변경 전 구현에서 먼저 통과해야 한다. 적절한 기존 TC는 재사용하고 중복 TC를 만들지 않는다. 새 요구/버그 수정은 별도 실패 TC로 시작하며, 변경 후 구현에서 기대값을 가져와 기존 계약의 근거로 쓰지 않는다. 사후 보강 TC를 구현 전 TDD 증거로 소급 인정하지 않는다.

계획의 구현 stage에는 `contract_preservation`으로 `applicable`, `production_paths`, `contract_sources`, `preserved_test_targets`, `change_test_targets`를 연결한다. 신규 코드 등 보존 계약이 비적용이면 사유를 적되 새 동작의 Red를 면제하지 않는다. 누락된 계획을 구현 agent가 임의 승인하지 않고 supervisor에 반환한다.

native `crew run`/variants가 최초 source baseline을 고정한다. current-session fallback도 그 기준과 `core/scripts/tdd_execution.py`의 명시적 실행 수집을 사용한다. 예를 들어 보존 TC는 다음과 같이 실행한다(경로/선택자는 실제 계획에 맞춘다).

```bash
python3 "${AGENT_CREW_HOME:-${HOME}/.agent-crew}/scripts/tdd_execution.py" --task-dir "$TASK_DIR" --project-root "$PROJECT_ROOT" --phase characterization --test-target tests/test_legacy.py -- python3 -m pytest tests/test_legacy.py
```

`red`, `green`, `refactor`도 실제 대상/argv로 실행한다. helper는 기준 상태·전후 소스/TC fingerprint·실제 결과를 기존 `tool-events.jsonl`에 연결한다. 최초 characterization → 요구별 Red → Green → Refactor와 계약 회귀 순서를 지킨다. 여러 요구의 반복은 앞선 실제 Green/refactor에 연결되며 새 baseline으로 기존 상태를 덮어쓰지 않는다.

pytest 실행은 helper가 개별 node 결과를 출력하도록 argv에 `--verbosity=1 --color=no`를 추가한다. 계획의 요구 선택자는 실제 `FAILED`와 이후 `PASSED`에 연결해야 하며, 다른 선택자 실패나 `-k`/`-m`/`--deselect`로 제외된 TC는 증거가 아니다. 모듈 전체 성공은 필터 없는 실제 실행에만 부여한다. 제한된 명시 Python script 실행 외의 runner나 확인할 수 없는 선택/출력 형식은 미검증으로 남긴다. 확정된 문서·비코드 계획은 이전 `inline_tdd` 힌트보다 우선하며, 미확정 계획과 신규 코드의 보존 계약 비적용은 새 동작 Red 면제가 아니다.

시작 실패·의존성 실패·timeout·취소는 assertion Red나 성공이 아니다. 실행 불가라면 구현 전에 helper의 `record_exception`으로 대상·사유·대체 근거·잔여 위험과 당시 소스 상태를 기록한다. 기술 hook에 판단이나 정식 검증 문서 생성을 추가하지 않는다.

파일 fingerprint의 차이만으로 기대값 변경을 단정하지 않는다. 보존 TC 변경은 변경 전 코드·호출자와 diff를 독립 reviewer가 검토하고, 기대값 변경은 명시적 요청/승인 근거에 연결한다. `contract_tdd.tdd_verified`와 완료 허용은 별개다. legacy 문서/실패→성공 trace나 `gates: passed`는 실제 TDD 수행으로 승격하지 않는다. 분기 누락·실패 원인·기대값 타당성의 의미 검토는 자동 증명의 대상이 아니다.

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

## Durable Contract vs Temporary Repair Evidence

Before keeping a new or changed test in the final diff, classify it as one of:

- **durable product-contract test**: verifies behavior backed by public API
  behavior, product requirement, security policy, data rule, legacy parity, or
  compatibility requirement.
- **temporary internal-repair evidence**: supports local diagnosis, repair, or
  revert confidence but is not itself a durable product contract.

Do not keep a test that only proves that a bad intermediate implementation was
reverted. For revert-only or internal-repair work, prefer temporary local
checks, focused command output, diff evidence, or task-context notes. Temporary
repair evidence can be mentioned in task artifacts, review notes, or command
logs, but it should not widen the product contract by remaining as a permanent
test.

Durable regression tests are still required when the behavior is backed by a
real contract source. Record that source in the checklist reason, test-case
mapping, test name/docstring, or nearby task evidence so reviewers can
distinguish valid regression coverage from short-lived repair evidence.

## Behavior Contract Before Implementation Detail

Do not write tests that justify an accidental implementation detail. A test
should pin a policy, contract, side effect, or regression that matters outside
the implementation shape. If a patch sets a field to null, adds a null
assignment, extracts a helper, skips a branch, or calls a new method, the
durable test should prove the
observable behavior that required that choice, not the mechanical detail
itself.

When responsibility moves into a domain object, consider a focused unit test
for that domain behavior instead of relying only on a broad service test that
passes by accident. Service tests remain useful for orchestration and external
side effects; domain behavior tests make the owned decision explicit.

## Boundary Contract Test Matrix

When the behavior under test touches normalization, serialization, filtering,
external boundaries, shared helpers, or producer/consumer transport, derive
tests from the observable contract described in
`core/rules/contract-first-feedback-fidelity.md`
`BOUNDARY_CONTRACT_REVIEW`. Do not maintain a role-local copy of that matrix;
use the canonical rule as the source of truth when deriving checklist rows.

Keep helper-call assertions secondary. A durable test must prove the boundary
contract a consumer can observe, not only that a new helper or guard was used.

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
        val order = Order.create(OrderItems(listOf(Item(Money(1000)))))
        every { orderRepository.save(any()) } returns order

        sut.placeOrder(order)

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

Korean canonical form: `{케이스타입}(qualifier) - {message}`

The nature prefix declares the case type before the behavior. The optional
qualifier declares the purpose or verification axis. Project teams may localize
the prefix words, but the structure is the contract:

- `success-case` / `성공케이스` — happy path or explicitly valid input.
- `boundary-case` / `경계케이스` — boundary, null, empty, unknown, partial,
  special-code, edge, or branch input that should still be handled as defined.
- `failure-case` / `실패케이스` — error, exception, rejection, rollback, or
  validation path.

Simplified qualifier taxonomy:

- `회귀` / `regression` — confirms existing behavior does not change.
- `계약` / `contract` — verifies request values, DTOs, external API payloads,
  or response shape.
- `부수효과` / `side-effect` — verifies DB changes, external calls, emitted
  events, or calls that must not happen.
- `보안` / `security` — verifies authentication, authorization, ownership, or
  visibility boundaries.
- `멱등성` / `idempotency` — verifies repeated requests, retries, duplicate
  clicks, or duplicate delivery handling.
- `동시성` / `concurrency` — verifies consistency under simultaneous requests.
- `제한` / `limit` — verifies large input, timeout, pagination, max size, or
  resource limits.
- `감사` / `audit` — verifies logs, audit records, events, or metrics.

Do not force a boundary input into `success-case` just because the expected
behavior is non-error handling. Use `boundary-case(contract)` or
`경계케이스(계약)` when the scenario shape is boundary-like and the purpose is
contract verification. TC-ID remains checklist/mapping metadata, not part of
the human-facing test name.

Use the canonical display string when the framework supports free-form test
names. When the framework requires identifier names, encode the same structure
in the identifier and keep the canonical display string in a docstring,
subtest name, table-case label, display-name annotation, or closest equivalent.

Do not write Given/When/Then phase-marker comments in generated or changed test
bodies unless a project-local convention explicitly requires them. Prefer the
test name, display name, helper names, local variable names, blank lines, and
clear arrange/act/assert ordering to communicate structure. Reviewers should
treat low-signal phase-marker comments such as `given`, `when`, or `then` as
review noise when the code is already readable without them.

Positive examples across supported test families:

```kotlin
// Kotest
test("성공케이스 - 정상 upsert면 byline과 profile이 모두 커밋된다") { }
test("경계케이스(계약) - contentType/status 가 null 이면 enum 필드도 null 이다") { }
test("실패케이스(전파 롤백) - profile 저장 실패면 byline INSERT가 롤백된다") { }

// JUnit5
@DisplayName("failure-case(validation) - rejects a blank nickname")
@Test
fun rejectsBlankNickname() { }
```

```typescript
// Jest / Vitest
test("boundary-case(limit) - accepts a 500-char URL at the limit", () => {})
test("failure-case(timeout) - shows retry affordance when lookup times out", () => {})
```

```python
# pytest
def test_boundary_case_contract_maps_out_of_range_enum_code_to_null_without_throwing():
    """boundary-case(contract) - maps an out-of-range enum code to null without throwing."""

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

Reviewer guidance: flag changed tests that add unnecessary Given/When/Then
phase-marker comments as `test_phase_marker_comment_noise` unless a
project-local convention explicitly requires those comments.

### 실제 선행 검토 증거

모든 TDD mode는 동일한 선행 검토를 따른다. 새 explicit run/variants는 최초
source_baseline과 pipeline에 `checklist_evidence_version=1`을 고정한다.
기존 `tdd_execution.observe_checklist_phase`의 `review_begin`, `review_end`,
`test_write_open`은 실제 파일 inventory와 정확한 checklist/output digest,
독립 host identity/span/lifecycle 및 task/stage/attempt를 관찰한다.
`checklist_preflight_status`가 유효한 뒤 테스트를 작성한다. red/green/refactor는
같은 preflight를 subprocess 전에 검사한다. characterization은 baseline에서
변경되지 않은 기존 TC 실행만 허용하며 새 테스트 작성 인증을 만들지 않는다.
자가 시각·mtime·승인 문자열·무관한 reviewer 이벤트는 증거가 아니다. 기존 완료
기록과 baseline은 다시 만들지 않으며 legacy 예외는 v1 proof를 면제하지 않는다.


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
