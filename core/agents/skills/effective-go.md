# Skill: effective-go

## Source
- The Go Team, *Effective Go*, https://go.dev/doc/effective_go (canonical)
- Uber, *Uber Go Style Guide*, https://github.com/uber-go/guide/blob/master/style.md
- Dave Cheney, *Practical Go: Real World Advice for Writing Maintainable Go Programs*, https://dave.cheney.net/practical-go

## When to Apply
- Writing Go packages, structs, and interfaces
- Choosing value or pointer receivers and using goroutines or channels
- Handling errors, defining interfaces, or adding package-level variables
- Refactoring Go code

---

## Core Rules

### Rule 1: Return errors explicitly; never panic for expected failure
> Source: Effective Go § Error handling; Cheney "Errors" chapter

Return `error` last, as in `(value, error)`, and check it at the call site.
Reserve `panic` for programming errors such as nil dereferences or bounds
violations, and for package initialization failures.

```go
// BAD — panic for expected failure
func FindOrder(id string) *Order {
    order, ok := repository[id]
    if !ok { panic("order not found") }
    return order
}

// GOOD — explicit error
func FindOrder(id string) (*Order, error) {
    order, ok := repository[id]
    if !ok { return nil, fmt.Errorf("order %s not found", id) }
    return order, nil
}
```

### Rule 2: Wrap errors with context; use `fmt.Errorf("…: %w", err)`
> Source: Effective Go; Go 1.13 errors wrapping (pkg/errors pattern)

Add context at each layer. Wrap with `%w` so `errors.Is` and `errors.As`
can inspect the original error.

```go
// BAD — opaque error
return nil, err

// GOOD — contextual wrapping
return nil, fmt.Errorf("findOrder(%s): %w", id, err)
```

### Rule 3: Prefer small interfaces; accept interfaces, return structs
> Source: Effective Go § Interfaces; Cheney "Interface segregation"

Keep interfaces to 1–3 methods. Accept interfaces for testability and return
structs to expose concrete behavior.

```go
// BAD — large interface forces mock complexity
type OrderService interface {
    Create(…) (Order, error)
    Update(…) error
    Delete(…) error
    FindById(…) (Order, error)
    ListByCustomer(…) ([]Order, error)
    // … 10 more methods
}

// GOOD — narrow interfaces at call site
type OrderReader interface { FindById(id string) (Order, error) }
type OrderWriter interface { Save(order Order) error }
```

### Rule 4: Use goroutines and channels for concurrency; always handle cancellation
> Source: Effective Go § Goroutines; Go blog "Pipelines and Cancellation"

Pass `context.Context` first to any function that may block.
Cancel it and stop its goroutines when the caller no longer needs them.

```go
// BAD — goroutine leak
go func() { result := doWork(); ch <- result }()

// GOOD — context-aware, cancellable
func ProcessOrder(ctx context.Context, id string) error {
    ch := make(chan error, 1)
    go func() { ch <- doWork(ctx, id) }()
    select {
    case err := <-ch: return err
    case <-ctx.Done(): return ctx.Err()
    }
}
```

### Rule 5: Initialise structs with named fields; avoid positional literals
> Source: Uber Go Style Guide § Initializing Structs

Name fields for clarity and to keep literals stable as structs evolve.

```go
// BAD
order := Order{"ORD-1", customerId, items, time.Now()}

// GOOD
order := Order{
    ID:         "ORD-1",
    CustomerID: customerId,
    Items:      items,
    PlacedAt:   time.Now(),
}
```

### Rule 6: Use `defer` for cleanup; keep deferred functions simple
> Source: Effective Go § Defer

Use simple deferred calls for cleanup on exit, including panic recovery
(e.g. close, unlock, end a span).

```go
func loadConfig(path string) (Config, error) {
    f, err := os.Open(path)
    if err != nil { return Config{}, err }
    defer f.Close()     // guaranteed cleanup
    return parse(f)
}
```

### Rule 7: Package names are lowercase, single-word; avoid `util`, `common`, `helpers`
> Source: Effective Go § Package names; Cheney "Package design"

Name packages by purpose, such as `orders`, `payments`, or `events`. The name is part of the API.

```go
// BAD
package util    // what does this do?
package helpers // vague

// GOOD
package orders  // domain context clear
package events  // clear responsibility
```

### Rule 8: Table-driven tests with `t.Run` subtests
> Source: Go blog "Using Subtests and Sub-benchmarks"; Uber Go Style Guide

Add cases to the table and name each `t.Run` subtest so failures identify the case.

```go
func TestCalculateTotal(t *testing.T) {
    cases := []struct {
        name  string
        items []OrderItem
        want  Money
    }{
        {"empty", nil, Money{0, "KRW"}},
        {"single item", []OrderItem{{Price: Money{1000, "KRW"}}}, Money{1000, "KRW"}},
    }
    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            got := calculateTotal(tc.items)
            if got != tc.want { t.Errorf("got %v, want %v", got, tc.want) }
        })
    }
}
```

### Rule 9: Avoid global mutable state; use dependency injection via constructors
> Source: Uber Go Style Guide § Global Variables; Cheney "Dependency injection"

Pass dependencies to constructors to expose coupling and keep tests deterministic.

```go
// BAD
var defaultRepo = NewPostgresRepository()  // global

// GOOD
type OrderService struct { repo OrderRepository }
func NewOrderService(repo OrderRepository) *OrderService {
    return &OrderService{repo: repo}
}
```

### Rule 10: `gofmt` and `golangci-lint` are mandatory
> Source: Effective Go § Formatting; Go community consensus

Enforce `gofmt` and `golangci-lint` in CI on all Go code. Enable at least
`errcheck`, `staticcheck`, and `unused`.

---

## Anti-Patterns
- Ignoring returned errors (`_ = doThing()`) in non-test code
- Returning `nil` error when the function signature says `error` — callers trust the contract
- Embedding structs to inherit methods — prefer explicit delegation
- `init()` functions with side effects — use explicit `Setup()` / dependency injection
- Channels as a synchronisation primitive when a `sync.Mutex` suffices
- `interface{}` / `any` in domain code — use generics (Go 1.18+) or specific interfaces

## Interaction with Other Skills
- Combine with `tdd.md`: table-driven tests (Rule 8) are the Go TDD idiom
- Combine with `clean-architecture.md`: small interfaces (Rule 3) are the Go expression of ports
- Combine with `error-handling.md`: Rule 1 and Rule 2 above are the Go-specific slice

## References
- The Go Team, *Effective Go*, https://go.dev/doc/effective_go
- Uber Technologies, *Uber Go Style Guide*, https://github.com/uber-go/guide/blob/master/style.md
- Dave Cheney, *Practical Go*, https://dave.cheney.net/practical-go
- The Go Blog, *Error Handling in Go*, https://go.dev/blog/error-handling-and-go
