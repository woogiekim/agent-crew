# Skill: effective-swift

## Source
- Apple, *The Swift Programming Language*, https://docs.swift.org/swift-book/
- Paul Hudson, *Hacking with Swift* and *Pro Swift* (2023 editions), https://www.hackingwithswift.com/
- Swift.org, *API Design Guidelines*, https://www.swift.org/documentation/api-design-guidelines/

## When to Apply
- Before writing any Swift struct, class, protocol, or enum
- Before choosing between `struct` and `class`, `enum` with associated values, or `protocol` with `associatedtype`
- Before writing async/await, Combine, or SwiftUI code
- During refactor: when eliminating optionals misuse, reference cycles, or excessive `class` usage

---

## Core Rules

### Rule 1: Prefer `struct` over `class` for value semantics; use `class` only for shared identity
> Source: Swift Book Ch. "Structures and Classes"; Apple WWDC 2015 "Building Better Apps with Value Types"

`struct` uses value semantics — no shared mutable state, no reference cycles.
Use `class` only when you need shared identity (e.g., view controllers,
delegate objects, or reference counting semantics).

```swift
// BAD — class for a pure value object
class Money {
    var amount: Decimal
    var currency: String
}

// GOOD — struct for value semantics
struct Money: Equatable, Hashable {
    let amount: Decimal
    let currency: String
}
```

### Rule 2: Never force-unwrap (`!`) in production code — use `guard let` or `if let`
> Source: Swift Book Ch. "Optional Chaining"; Swift API Design Guidelines

Force-unwrap crashes on `nil`. Use `guard let` for early-exit unwrapping and
`if let` for conditional execution. Use `?? defaultValue` for safe fallbacks.

```swift
// BAD
let order = repository.find(id)!   // crash if nil

// GOOD — guard let for early exit
guard let order = repository.find(id) else {
    return .failure(.notFound(id))
}
// order is non-optional here

// GOOD — nil-coalescing for defaults
let label = order.label ?? "No label"
```

### Rule 3: Use `enum` with associated values for typed domain errors
> Source: Swift Book Ch. "Enumerations"; Apple WWDC 2016 "Swift Error Handling"

Swift's `Error` protocol + `enum` produces exhaustive, typed error handling that
the compiler enforces.

```swift
// BAD — string-based errors, unchecked
throw NSError(domain: "orders", code: 404)

// GOOD — typed, exhaustive
enum OrderError: Error {
    case notFound(id: String)
    case alreadyConfirmed
    case paymentDeclined(reason: String)
}

func placeOrder(_ command: PlaceOrderCommand) throws -> Order {
    guard let customer = findCustomer(command.customerId) else {
        throw OrderError.notFound(id: command.customerId)
    }
    // …
}
```

### Rule 4: Use `async`/`await` over completion handlers; never block the main thread
> Source: Swift Book Ch. "Concurrency"; Apple WWDC 2021 "Meet async/await in Swift"

`async`/`await` is the canonical Swift concurrency model since Swift 5.5.
Mark functions `async throws` for async-failable operations. Use
`@MainActor` on UI-update functions. Never call blocking APIs on the main thread.

```swift
// BAD — callback pyramid
repository.findOrder(id: id) { result in
    switch result {
    case .success(let order): self.process(order) { … }
    case .failure(let error): self.handle(error)
    }
}

// GOOD — async/await
func loadOrder(id: String) async throws -> Order {
    let order = try await repository.findOrder(id: id)
    return try await process(order)
}
```

### Rule 5: Protocols over inheritance for polymorphism; use `protocol` + `extension` for default behaviour
> Source: Swift API Design Guidelines; Apple WWDC 2015 "Protocol-Oriented Programming"

Swift's protocol-oriented design prefers composition. Provide default
implementations via `extension` rather than requiring subclassing.

```swift
// BAD — class hierarchy for shared behaviour
class Animal { func sound() -> String { "" } }
class Dog: Animal { override func sound() -> String { "Woof" } }

// GOOD — protocol + extension
protocol Animal { var sound: String { get } }
extension Animal { var description: String { "I say \(sound)" } }
struct Dog: Animal { let sound = "Woof" }
```

### Rule 6: `let` over `var`; immutable by default
> Source: Swift Book Ch. "The Basics"; Swift API Design Guidelines

Declare `let` by default. Switch to `var` only when mutation is genuinely
needed. Immutable properties are thread-safe and easier to reason about.

### Rule 7: Use descriptive names at call sites; omit redundant words
> Source: Swift API Design Guidelines § Naming

Swift API design guideline: name should read fluently at the call site.
- Use first argument label as part of the name: `insert(_ value: T, at index: Int)`
- Omit words that merely repeat the type: `removeElement(element:)` → `remove(_ element:)`
- Boolean properties: `isEnabled`, `isEmpty`, `hasItems`

```swift
// BAD — redundant "Order" in method name on OrderService
orderService.cancelOrder(order: order)

// GOOD — reads fluently
orderService.cancel(order)
```

### Rule 8: Test with XCTest; use `XCTUnwrap`, not force-unwrap
> Source: Apple Developer Documentation; Swift community consensus

```swift
func testOrderTotal() throws {
    let items = [OrderItem(price: Money(amount: 1000, currency: "KRW"))]
    let order = try XCTUnwrap(Order(items: items))  // safe unwrap in tests
    XCTAssertEqual(order.total, Money(amount: 1000, currency: "KRW"))
}
```

### Rule 9: `Codable` for serialisation; never hand-roll JSON parsing
> Source: Swift Book Ch. "Encoding and Decoding Types"

Use `Codable` (`Encodable + Decodable`) for all model serialisation.
Use `CodingKeys` to map between Swift naming and JSON keys.

```swift
struct Order: Codable {
    let id: String
    let total: Money
    let placedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, total
        case placedAt = "placed_at"
    }
}
```

### Rule 10: Avoid retain cycles — use `[weak self]` in closures that outlive the current scope
> Source: Swift Book Ch. "Automatic Reference Counting"

Strong captures in escaping closures create retain cycles when `self` owns the
closure (e.g., stored as a property or passed to a long-lived object).

```swift
// BAD — retain cycle
service.load { [self] result in  // self strongly retained
    self.process(result)
}

// GOOD — weak capture with guard
service.load { [weak self] result in
    guard let self else { return }
    self.process(result)
}
```

---

## Anti-Patterns
- `!` force-unwrap outside test helpers
- Subclassing `UIViewController` for shared behaviour — prefer composition + protocols
- `DispatchQueue.main.async` for every UI update — use `@MainActor` instead
- `@objc` annotations in Swift-only targets
- `Any` or `AnyObject` in domain types — use protocols or generics
- Mutating `@State` from outside a SwiftUI view — use `@Binding` or `@StateObject`

## Interaction with Other Skills
- Combine with `tdd.md`: XCTest is the Swift TDD runner; use `XCTUnwrap` not `!`
- Combine with `clean-architecture.md`: protocols (Rule 5) are the Swift ports; structs / implementations are adapters
- Combine with `ui-component-design.md`: SwiftUI views are components; follow the same decomposition rules

## References
- Apple, *The Swift Programming Language*, https://docs.swift.org/swift-book/
- Apple, *Swift API Design Guidelines*, https://www.swift.org/documentation/api-design-guidelines/
- Paul Hudson, *Pro Swift* (2023), https://www.hackingwithswift.com/
- Apple WWDC 2015, *Protocol-Oriented Programming in Swift*, https://developer.apple.com/videos/play/wwdc2015/408/
- Apple WWDC 2021, *Meet async/await in Swift*, https://developer.apple.com/videos/play/wwdc2021/10132/
