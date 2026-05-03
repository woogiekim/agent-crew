# TDD 사이클 (JUnit 5 + MockK, Kotlin)

## RED → GREEN → REFACTOR

### RED: 실패하는 테스트 먼저
```kotlin
@Test
fun `주문 생성 시 PENDING 상태여야 한다`() {
    // given
    val items = OrderItems(listOf(Item(Money(1000))))

    // when
    val order = Order.create(items)

    // then
    assertThat(order.status).isEqualTo(OrderStatus.PENDING)
}
```
→ `./gradlew test` 실행 → 컴파일 에러 또는 FAIL 확인 필수

### GREEN: 최소 구현
컴파일되고 테스트만 통과하는 가장 단순한 코드 작성.
과도한 추상화 금지.

→ `./gradlew test` 실행 → PASS 확인 필수

### REFACTOR: 원칙 점검
- 중복 제거
- 생활체조 원칙 위반 점검
- Tell Don't Ask 위반 점검
- 의미있는 네이밍으로 개선

→ `./gradlew test` 실행 → 여전히 PASS인지 확인 필수

## MockK 사용 패턴
```kotlin
@ExtendWith(MockKExtension::class)
class OrderServiceTest {

    @MockK
    private lateinit var orderRepository: OrderRepository

    @InjectMockKs
    private lateinit var orderService: OrderService

    @Test
    fun `주문 저장 후 도메인 이벤트가 발행되어야 한다`() {
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

## 테스트 네이밍 규칙
- 한글 backtick 방식: `` `[조건] 시 [결과]여야 한다` ``
- given / when / then 주석 필수

## 테스트 실행 명령
```bash
# 전체 테스트
./gradlew test

# 특정 클래스
./gradlew test --tests "com.example.domain.order.OrderTest"

# 테스트 결과 상세 출력
./gradlew test --info
```
