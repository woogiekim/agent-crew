# Skill: effective-rust

## Source
- Steve Klabnik & Carol Nichols, *The Rust Programming Language* (2nd ed.), No Starch Press, 2023 (the "Rust Book")
- Jon Gjengset, *Rust for Rustaceans*, No Starch Press, 2021
- Rust API Guidelines, https://rust-lang.github.io/api-guidelines/

## When to Apply
- Writing Rust structs, enums, traits, or functions
- Choosing ownership, borrowing, or lifetimes
- Choosing `Result`, `Option`, or panic
- Removing `unwrap`, `clone`, or unsafe blocks during refactoring

---

## Core Rules

### Rule 1: Never use `unwrap` or `expect` in production code — propagate errors with `?`
> Source: Rust Book Ch. 9 "Error Handling"; Gjengset Ch. 4

Propagate errors with `?`. Use `unwrap` or `expect` only in tests or provably
safe cases. Document why any such case is safe.

```rust
// BAD
let order = repository.find(id).unwrap();

// GOOD
let order = repository.find(id)?;     // propagates Err to caller

// Acceptable in tests
let order = repository.find(id).expect("test fixture must have order ORD-1");
```

### Rule 2: Model domain errors with `enum` and `thiserror`; use `anyhow` only at application boundaries
> Source: Gjengset Ch. 4 "Error Handling"; Rust API Guidelines § Error types

Use typed error enums in libraries and domain crates. Use `anyhow::Error` at application and CLI boundaries.

```rust
// Domain crate — typed errors
use thiserror::Error;
#[derive(Debug, Error)]
pub enum OrderError {
    #[error("Order {0} not found")]
    NotFound(String),
    #[error("Order already confirmed")]
    AlreadyConfirmed,
}

// Application main — anyhow for ergonomics
use anyhow::{Context, Result};
fn main() -> Result<()> {
    let order = repo.find(id).context("loading order")?;
    Ok(())
}
```

### Rule 3: Prefer borrowing over cloning; clone only at ownership boundaries
> Source: Rust Book Ch. 4 "Ownership"; Gjengset Ch. 1

Pass `&T` for reads and `&mut T` for mutation. Clone only when the callee
needs ownership and the caller must retain the value.

```rust
// BAD — unnecessary clone
fn format_order(order: Order) -> String { format!("{:?}", order) }

// GOOD — borrow
fn format_order(order: &Order) -> String { format!("{:?}", order) }
```

### Rule 4: Use `Option` and `Result` combinators; avoid nested `match` chains
> Source: Rust Book Ch. 6 "Enums and Pattern Matching"

Prefer `map`, `and_then`, `unwrap_or_else`, or `ok_or` to nested `match`.

```rust
// BAD — nested match
let total = match calculate(items) {
    Ok(t) => match t.to_money() { Ok(m) => m, Err(_) => Money::zero() },
    Err(_) => Money::zero(),
};

// GOOD — combinator chain
let total = calculate(items)
    .and_then(|t| t.to_money())
    .unwrap_or_else(|_| Money::zero());
```

### Rule 5: Define trait objects with `dyn Trait`; prefer generics for zero-cost abstraction
> Source: Rust Book Ch. 17 "Object Oriented Features"; Gjengset Ch. 2

Use `dyn Trait` for runtime dispatch in heterogeneous collections or plugin
systems. Use `<T: Trait>` for static dispatch when the concrete type is known.

```rust
// Static dispatch — zero-cost, requires knowing T at compile time
fn process<R: OrderRepository>(repo: &R) -> Result<(), OrderError> { … }

// Dynamic dispatch — allows heterogeneous repositories at runtime cost
fn process(repo: &dyn OrderRepository) -> Result<(), OrderError> { … }
```

### Rule 6: Leverage the type system for state machines — never represent invalid states
> Source: Gjengset Ch. 3 "Designing Interfaces"; Rust type-state pattern

Give each state a type so invalid transitions fail at compile time.

```rust
// BAD — runtime check for every transition
struct Order { status: String }

// GOOD — compile-time enforcement
struct PendingOrder { … }
struct ConfirmedOrder { … }
impl PendingOrder {
    fn confirm(self, confirmed_at: DateTime) -> ConfirmedOrder { … }
}
// cannot call confirm() on ConfirmedOrder — it doesn't exist
```

### Rule 7: Use `clippy` and `rustfmt`; treat warnings as errors in CI
> Source: Rust API Guidelines § Documentation; Rust community consensus

Run `cargo clippy -- -D warnings` in CI and format with `rustfmt` using
`rustfmt.toml`. Explain any lint suppression with `// SAFETY:` for `unsafe`
or `// allow(lint_name): reason`.

### Rule 8: Document public API with doc-comments; include examples that compile
> Source: Rust API Guidelines § Documentation; Rust Book Ch. 14

Document every public item. Add compilable doc-comment examples that `cargo test` exercises.

```rust
/// Calculates the total price of all items in an order.
///
/// # Examples
/// ```
/// let order = Order::new(vec![Item::new(1000)]);
/// assert_eq!(order.total(), Money::new(1000));
/// ```
pub fn total(&self) -> Money { … }
```

### Rule 9: Avoid `unsafe` unless absolutely necessary; document every unsafe block
> Source: Rust Book Ch. 19 "Unsafe Rust"; Gjengset Ch. 8

If `unsafe` is unavoidable, as with FFI or performance-critical intrinsics,
isolate it behind a safe public API in a small module. In each `// SAFETY:`
comment, explain why the invariants hold.

### Rule 10: Prefer `Arc<Mutex<T>>` over `Rc<RefCell<T>>` in async/threaded code
> Source: Rust Book Ch. 16 "Fearless Concurrency"

Keep `Rc<RefCell<T>>` single-threaded. Use `Arc<Mutex<T>>` for threaded
sharing. For async-aware locking in Tokio, prefer `tokio::sync::Mutex` over
`std::sync::Mutex`.

---

## Anti-Patterns
- `unwrap()` in library code — use `?` or typed errors
- `clone()` as the first instinct for borrow-checker fights — analyse ownership first
- `Box<dyn Error>` as a library return type — too opaque; use typed `enum` errors
- `mem::transmute` outside well-documented unsafe modules
- `Mutex::lock().unwrap()` — handle poisoning explicitly or use `unwrap_or_else`
- Exposing `pub` fields on structs that should be immutable from outside — use accessors

## Interaction with Other Skills
- Combine with `tdd.md`: `cargo test` is the Rust TDD runner; doc-test examples run too
- Combine with `clean-architecture.md`: traits (Rule 3/5) are the Rust expression of ports; structs are adapters
- Combine with `error-handling.md`: Rule 1 and Rule 2 define the Rust-specific error contract

## References
- Steve Klabnik & Carol Nichols, *The Rust Programming Language* (2nd ed.), No Starch Press, 2023. https://doc.rust-lang.org/book/
- Jon Gjengset, *Rust for Rustaceans*, No Starch Press, 2021. ISBN 978-1-7185-0185-6.
- Rust API Guidelines, https://rust-lang.github.io/api-guidelines/
- `thiserror` crate, https://github.com/dtolnay/thiserror
- `anyhow` crate, https://github.com/dtolnay/anyhow
