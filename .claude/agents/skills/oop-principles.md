# 객체지향 생활체조 원칙

## 1. 한 메서드에 오직 한 단계의 들여쓰기
```kotlin
// BAD
fun process(orders: List<Order>) {
    for (order in orders) {
        if (order.isValid()) {
            for (item in order.items) {
                item.apply()
            }
        }
    }
}

// GOOD
fun process(orders: List<Order>) = orders.filter { it.isValid() }.forEach { it.apply() }
```

## 2. else 키워드 사용 금지
```kotlin
// BAD
fun getStatus(order: Order): String {
    if (order.isPaid()) { return "PAID" } else { return "PENDING" }
}

// GOOD — Early return
fun getStatus(order: Order): String {
    if (order.isPaid()) return "PAID"
    return "PENDING"
}
```

## 3. 원시값과 문자열 포장
```kotlin
// BAD
class Order(val amount: Int)

// GOOD
@JvmInline value class Money(val amount: Int) {
    init { require(amount >= 0) { "금액은 0 이상이어야 합니다" } }
}
class Order(val amount: Money)
```

## 4. 일급 컬렉션 사용
```kotlin
// BAD
class Order(val items: List<Item>)

// GOOD
class OrderItems(private val items: List<Item>) {
    init { require(items.isNotEmpty()) { "주문 항목은 비어있을 수 없습니다" } }
    fun totalPrice(): Money = items.sumOf { it.price.amount }.let { Money(it) }
}
class Order(val items: OrderItems)
```

## 5. 한 줄에 점 하나만
```kotlin
// BAD
order.customer.address.city

// GOOD — 디미터 법칙 준수
order.shippingCity()
```

## 6. 축약 금지
- `ord` → `order`
- `mgr` → `manager`
- `calc` → `calculate`

## 7. 모든 엔티티를 작게 유지
- 클래스: 50줄 이하 권장
- 패키지: 10개 파일 이하 권장

## 8. 2개 이상의 인스턴스 변수를 가진 클래스 사용 금지
- 관련 필드는 Value Object로 묶기

## 9. getter/setter/property 사용 금지 (Tell, Don't Ask)
```kotlin
// BAD — 꺼내서 판단
if (order.status == OrderStatus.PAID) { order.status = OrderStatus.SHIPPED }

// GOOD — 객체에게 명령
order.ship()
```
