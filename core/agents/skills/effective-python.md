# Skill: effective-python

## Source
- Brett Slatkin, *Effective Python: 90 Specific Ways to Write Better Python* (2nd ed.), Addison-Wesley, 2020
- Guido van Rossum et al., *PEP 8 – Style Guide for Python Code*, https://peps.python.org/pep-0008/
- Python Steering Council, *PEP 20 – The Zen of Python*, https://peps.python.org/pep-0020/

## When to Apply
- Before writing any Python function, class, or module
- Before choosing between a list, generator, dict, or dataclass
- Before using metaclasses, decorators, or context managers
- During refactor: when simplifying or type-annotating existing Python code

---

## Core Rules

### Rule 1: Follow PEP 8; use a linter (ruff / flake8) and formatter (black)
> Source: PEP 8; Slatkin, Item 2

Consistent style reduces cognitive load. Configure `pyproject.toml` with ruff
or black. Never commit code that fails the linter. Line length ≤ 88 (black
default) unless project overrides.

```python
# BAD — inconsistent spacing, naming
def getOrderById(id):return repository.get( id )

# GOOD — PEP 8 compliant
def get_order_by_id(order_id: str) -> Order | None:
    return repository.get(order_id)
```

### Rule 2: Use type annotations on all public functions and class attributes
> Source: Slatkin, Items 90; PEP 484, PEP 526

Type annotations are verified by mypy/pyright. They serve as machine-checked
documentation. All public functions must have full annotations. Internal helpers
at minimum annotate return types.

```python
# BAD
def calculate_total(items):
    return sum(i.price for i in items)

# GOOD
from decimal import Decimal
def calculate_total(items: list[OrderItem]) -> Decimal:
    return sum(item.price for item in items, start=Decimal(0))
```

### Rule 3: Prefer dataclasses or named tuples for value objects
> Source: Slatkin, Item 37 "Compose Classes Instead of Nesting Many Levels of Built-in Types"

Use `@dataclass(frozen=True)` for immutable value objects. Use `@dataclass` for
mutable entities. Never use plain dicts or tuples for structured domain data.

```python
# BAD — dict masquerading as a domain object
order = {"id": "123", "total": 99.99, "customer": "alice"}

# GOOD
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "KRW"

@dataclass
class Order:
    id: str
    total: Money
    customer_id: str
```

### Rule 4: Prefer generators over list comprehensions for large sequences
> Source: Slatkin, Items 31–32 "Use Generator Expressions for Large List Comprehensions"

Generators are lazy — they do not materialise the entire sequence in memory.
Use `(x for x in …)` when you only iterate once and the sequence may be large.

```python
# BAD — materialises entire list
totals = [order.total for order in all_orders()]  # OOM risk for millions of orders

# GOOD — lazy generator
totals = (order.total for order in all_orders())
grand_total = sum(totals)
```

### Rule 5: Use context managers for resource management; never rely on `__del__`
> Source: Slatkin, Item 66 "Consider contextlib and with Statements for Reusable try/finally Behavior"

Context managers guarantee cleanup even on exceptions. Use `contextlib.contextmanager`
for lightweight cases. Never rely on `__del__` for resource release.

```python
# BAD — resource leak on exception
conn = db.connect()
result = conn.execute(query)
conn.close()

# GOOD
with db.connect() as conn:
    result = conn.execute(query)
# conn.close() guaranteed
```

### Rule 6: Raise specific exceptions; never swallow exceptions silently
> Source: Slatkin, Item 87 "Define a Root Exception to Insulate Callers from APIs"

Define a domain exception hierarchy rooted at a single base class. Catch only
the specific exception(s) you can handle. Never `except Exception: pass`.

```python
# BAD
try:
    order = repository.get(order_id)
except Exception:
    pass  # silently swallows programming errors

# GOOD
class DomainError(Exception): pass
class OrderNotFoundError(DomainError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order not found: {order_id}")

try:
    order = repository.get(order_id)
except OrderNotFoundError:
    return None  # expected absence
```

### Rule 7: Use `__slots__` in high-volume classes; avoid premature optimisation
> Source: Slatkin, Item 48 "Accept Functions Instead of Classes for Simple Interfaces"

For classes instantiated millions of times (e.g., value objects in bulk processing),
`__slots__` reduces memory footprint significantly. For typical domain objects,
skip `__slots__` until profiling shows it necessary.

### Rule 8: Prefer keyword-only arguments for functions with many parameters
> Source: Slatkin, Item 25 "Enforce Clarity with Keyword-Only and Positional-Only Arguments"

Functions with boolean flags or more than three positional arguments should use
keyword-only arguments (after `*`) to prevent caller confusion.

```python
# BAD — bool trap, order matters
def create_order(customer_id, items, send_confirmation, apply_discount):
    ...

# GOOD — keyword-only after *
def create_order(
    customer_id: str,
    items: list[OrderItem],
    *,
    send_confirmation: bool = True,
    apply_discount: bool = False,
) -> Order:
    ...
```

### Rule 9: Use `pathlib.Path` over `os.path` string manipulation
> Source: Slatkin, Item 3; PEP 428

`pathlib.Path` provides a type-safe, platform-agnostic API. String manipulation
of paths is fragile and error-prone.

```python
# BAD
import os
config_path = os.path.join(os.path.dirname(__file__), "config", "settings.json")

# GOOD
from pathlib import Path
config_path = Path(__file__).parent / "config" / "settings.json"
```

### Rule 10: Test with pytest; use fixtures, parametrize, and monkeypatch
> Source: Slatkin, Item 76 "Verify Related Behaviors in TestCase Subclasses"; pytest docs

- Fixtures (`@pytest.fixture`) for reusable test objects
- `@pytest.mark.parametrize` for data-driven tests
- `monkeypatch` for dependency injection in tests — never mock globally

---

## Anti-Patterns
- `import *` — pollutes namespace and breaks static analysis
- Mutable default arguments (`def f(items=[])`) — use `None` sentinel and initialise inside
- `isinstance` chains — use polymorphism, `functools.singledispatch`, or protocol matching
- Catching `BaseException` or bare `except:` — always specify the exception type
- String-based configuration (`if env == "prod":`) — use typed config classes or `pydantic.BaseSettings`
- `global` state outside module-level constants — use dependency injection

## Interaction with Other Skills
- Combine with `tdd.md`: pytest + fixtures are the Python TDD toolchain
- Combine with `clean-architecture.md`: dataclasses (Rule 3) are domain entities; repositories are adapters
- Combine with `error-handling.md`: Rule 6 above defines the Python slice of the error-handling contract

## References
- Brett Slatkin, *Effective Python: 90 Specific Ways to Write Better Python* (2nd ed.), Addison-Wesley, 2020. ISBN 978-0-13-485398-7.
- Guido van Rossum et al., *PEP 8 – Style Guide for Python Code*, https://peps.python.org/pep-0008/
- Python Steering Council, *PEP 20 – The Zen of Python*, https://peps.python.org/pep-0020/
- pytest documentation, https://docs.pytest.org/
