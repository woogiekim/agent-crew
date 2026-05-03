# DDD 전술 패턴 (Kotlin + Spring Boot)

## Aggregate Root
- 트랜잭션 경계 단위
- 외부에서 내부 Entity에 직접 접근 금지
- Domain Event를 직접 발행

```kotlin
class Order private constructor(
    val id: OrderId,
    private val items: OrderItems,
    private var status: OrderStatus
) {
    private val domainEvents: MutableList<DomainEvent> = mutableListOf()

    companion object {
        fun create(items: OrderItems): Order {
            val order = Order(OrderId.generate(), items, OrderStatus.PENDING)
            order.domainEvents.add(OrderCreated(order.id))
            return order
        }
    }

    fun place(): Order {
        check(status == OrderStatus.PENDING) { "PENDING 상태에서만 주문 가능합니다" }
        status = OrderStatus.PLACED
        domainEvents.add(OrderPlaced(id))
        return this
    }

    fun pullDomainEvents(): List<DomainEvent> {
        val events = domainEvents.toList()
        domainEvents.clear()
        return events
    }
}
```

## Value Object
- 불변
- 동등성은 값으로 비교
- 유효성 검증은 생성 시점에

```kotlin
@JvmInline
value class OrderId(val value: UUID) {
    companion object {
        fun generate() = OrderId(UUID.randomUUID())
        fun of(value: String) = OrderId(UUID.fromString(value))
    }
}
```

## Domain Event
```kotlin
sealed interface DomainEvent {
    val occurredAt: Instant get() = Instant.now()
}
data class OrderCreated(val orderId: OrderId) : DomainEvent
data class OrderPlaced(val orderId: OrderId) : DomainEvent
```

## Repository (인터페이스는 도메인 레이어)
```kotlin
// domain layer
interface OrderRepository {
    fun save(order: Order): Order
    fun findById(id: OrderId): Order?
    fun findAll(): List<Order>
}

// infrastructure layer
@Repository
class OrderJpaRepository(
    private val jpaRepo: OrderJpaEntityRepository
) : OrderRepository {
    override fun save(order: Order) = jpaRepo.save(order.toEntity()).toDomain()
    override fun findById(id: OrderId) = jpaRepo.findById(id.value).map { it.toDomain() }.orElse(null)
    override fun findAll() = jpaRepo.findAll().map { it.toDomain() }
}
```

## 패키지 구조
```
com.example
├── domain
│   ├── order
│   │   ├── Order.kt              ← Aggregate Root
│   │   ├── OrderId.kt            ← Value Object
│   │   ├── OrderItems.kt         ← 일급 컬렉션
│   │   ├── OrderStatus.kt        ← Enum
│   │   ├── OrderRepository.kt    ← Repository 인터페이스
│   │   └── OrderEvents.kt        ← Domain Events
├── application
│   └── order
│       └── OrderService.kt       ← Application Service
├── infrastructure
│   └── order
│       └── OrderJpaRepository.kt ← Repository 구현체
└── presentation
    └── order
        └── OrderController.kt
```
