# TDD Cycle (JUnit 5 + MockK, Kotlin)

## RED → GREEN → REFACTOR

### RED: Write a Failing Test First
```kotlin
@Test
fun `should have PENDING status when creating an order`() {
    // given
    val items = OrderItems(listOf(Item(Money(1000))))

    // when
    val order = Order.create(items)

    // then
    assertThat(order.status).isEqualTo(OrderStatus.PENDING)
}
```

→ Run `./gradlew test` → Confirm compilation error or FAIL status before proceeding.

### GREEN: Minimal Implementation
Write the simplest possible code that compiles and passes the test.  
Avoid excessive abstraction.

→ Run `./gradlew test` → Confirm PASS status before proceeding.

### REFACTOR: Review Design Principles
- Remove duplication
- Check for Object Calisthenics violations
- Check for Tell Don't Ask violations
- Improve naming to be more meaningful

→ Run `./gradlew test` → Confirm PASS status is maintained after refactoring.

## MockK Usage Pattern
```kotlin
@ExtendWith(MockKExtension::class)
class OrderServiceTest {

    @MockK
    private lateinit var orderRepository: OrderRepository

    @InjectMockKs
    private lateinit var orderService: OrderService

    @Test
    fun `should publish domain event after saving order`() {
        // given
        val order = Order.create(OrderItems(listOf(Item(Money(1000)))))
        every { orderRepository.save(any()) } returns order

        // when
        orderService.placeOrder(order)

        // then
        verify(exactly = 1) { orderRepository.save(order) }
    }
}
```

## Test Naming Convention
- Use backtick naming style: `` `should [result] when [condition]` ``
- `given / when / then` comments are mandatory

## Test Execution Commands
```bash
# Run all tests
./gradlew test

# Run a specific test class
./gradlew test --tests "com.example.domain.order.OrderTest"

# Print detailed test results
./gradlew test --info
```