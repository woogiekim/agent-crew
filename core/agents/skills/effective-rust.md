# Skill: effective-rust

## Source
- Steve Klabnik & Carol Nichols, *The Rust Programming Language* (2nd ed.), No Starch Press, 2023 (the "Rust Book")
- Jon Gjengset, *Rust for Rustaceans*, No Starch Press, 2021
- Rust API Guidelines, https://rust-lang.github.io/api-guidelines/

## When to Apply
- Before writing any Rust struct, enum, trait, or function
- Before deciding on ownership, borrowing, or lifetimes
- Before choosing between `Result` / `Option` and panicking
- During refactor: when eliminating `unwrap`, `clone`, or unsafe blocks

---

## Core Rules

### Rule 1: Never use `unwrap` or `expect` in production code — propagate errors with `?`
> Source: Rust Book Ch. 9 "Error Handling"; Gjengset Ch. 4

`unwrap` panics at runtime if the value is `None` or `Err`. Use `?` to propagate
errors up the call stack. Reserve `unwrap` / `expect` for tests and provably
safe scenarios with a comment explaining why.

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

Library / domain crates define typed error enums. Application / CLI crates
use `anyhow::Error` for ergonomic error propagation.

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

Cloning is safe but allocates. Pass `&T` when the callee only needs to read.
Pass `&mut T` when it needs to mutate. Clone only when ownership must transfer
and the caller still needs the value.

```rust
// BAD — unnecessary clone
fn format_order(order: Order) -> String { format!("{:?}", order) }

// GOOD — borrow
fn format_order(order: &Order) -> String { format!("{:?}", order) }
```

### Rule 4: Use `Option` and `Result` combinators; avoid nested `match` chains
> Source: Rust Book Ch. 6 "Enums and Pattern Matching"

Prefer `map`, `and_then`, `unwrap_or_else`, `ok_or` to nested `match`. They
express intent more concisely and compose well.

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

Use `dyn Trait` (dynamic dispatch) when the concrete type is not known at
compile time (heterogeneous collections, plugin systems). Use generic bounds
`<T: Trait>` when the concrete type is known at monomorphisation time —
zero-cost dispatch.

```rust
// Static dispatch — zero-cost, requires knowing T at compile time
fn process<R: OrderRepository>(repo: &R) -> Result<(), OrderError> { … }

// Dynamic dispatch — allows heterogeneous repositories at runtime cost
fn process(repo: &dyn OrderRepository) -> Result<(), OrderError> { … }
```

### Rule 6: Leverage the type system for state machines — never represent invalid states
> Source: Gjengset Ch. 3 "Designing Interfaces"; Rust type-state pattern

Use distinct types for each state so invalid transitions are compile errors.
The type-state pattern eliminates runtime state-machine bugs.

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

Run `cargo clippy -- -D warnings` in CI. `rustfmt` is the canonical formatter
(configured via `rustfmt.toml`). Never disable clippy lints without a
`// SAFETY:` comment (for `unsafe`) or `// allow(lint_name): reason` comment.

### Rule 8: Document public API with doc-comments; include examples that compile
> Source: Rust API Guidelines § Documentation; Rust Book Ch. 14

Every public item (`pub fn`, `pub struct`, `pub trait`) must have a doc-comment.
Code examples in doc-comments are run by `cargo test` — use them.

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

`unsafe` bypasses borrow-checker guarantees. If it is unavoidable (FFI,
performance-critical intrinsics), isolate it in a small module, wrap it in a
safe public API, and document with a `// SAFETY:` comment explaining why the
invariants hold.

### Rule 10: Prefer `Arc<Mutex<T>>` over `Rc<RefCell<T>>` in async/threaded code
> Source: Rust Book Ch. 16 "Fearless Concurrency"

`Rc<RefCell<T>>` is single-threaded only. `Arc<Mutex<T>>` is `Send + Sync` and
safe for multi-threaded contexts. When using async (tokio), prefer
`tokio::sync::Mutex` over `std::sync::Mutex` for async-aware locking.

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
