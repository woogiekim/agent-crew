# Skill: database-design

## Purpose
Enables the backend agent to design normalized, performant database schemas, define indexing strategies, and identify query anti-patterns before writing implementation code.

## When to Apply
- During Phase 1 (Requirement Analysis) when the PRD introduces persistent data
- When designing new tables, collections, or aggregate roots
- When reviewing existing schemas for normalization or performance issues
- Before writing any ORM entity or repository code

---

## Normalization (Codd's Normal Forms, 1970)

Target **3NF** for transactional data. BCNF or 4NF for stricter requirements.

### 1NF — Eliminate repeating groups
- Each column holds atomic (indivisible) values
- No arrays or comma-separated lists in a single column
- Each row is uniquely identifiable

```sql
-- BAD: phone_numbers is multi-valued
CREATE TABLE customers (
    id UUID PRIMARY KEY,
    phone_numbers TEXT  -- "010-1234, 010-5678"
);

-- GOOD: separate table
CREATE TABLE customers (id UUID PRIMARY KEY, name TEXT);
CREATE TABLE customer_phones (
    id UUID PRIMARY KEY,
    customer_id UUID REFERENCES customers(id),
    phone TEXT NOT NULL
);
```

### 2NF — Eliminate partial dependencies (applies only to composite PKs)
- Every non-key column depends on the **whole** primary key, not part of it

```sql
-- BAD: product_name depends only on product_id, not on (order_id, product_id)
CREATE TABLE order_items (
    order_id UUID,
    product_id UUID,
    product_name TEXT,  -- partial dependency on product_id alone
    quantity INT,
    PRIMARY KEY (order_id, product_id)
);

-- GOOD
CREATE TABLE order_items (
    order_id UUID, product_id UUID, quantity INT,
    PRIMARY KEY (order_id, product_id)
);
CREATE TABLE products (id UUID PRIMARY KEY, name TEXT);
```

### 3NF — Eliminate transitive dependencies
- Every non-key column depends on the primary key **only**, not on another non-key column

```sql
-- BAD: zip_code → city (transitive: customer_id → zip_code → city)
CREATE TABLE customers (
    id UUID PRIMARY KEY, zip_code TEXT, city TEXT
);

-- GOOD
CREATE TABLE zip_codes (zip TEXT PRIMARY KEY, city TEXT);
CREATE TABLE customers (id UUID PRIMARY KEY, zip_code TEXT REFERENCES zip_codes(zip));
```

### Intentional Denormalization
Denormalize **only with documented justification** (performance measurement, not assumption):
- Read-heavy aggregates (e.g., pre-computed `order_total`)
- Event-sourcing read models / CQRS projections
- Report tables with SLA requirements

Always record the tradeoff in the schema comment or `design.md`.

---

## Data Types — Choose the Narrowest Correct Type

| Concept | Preferred type | Avoid |
|---|---|---|
| Entity ID | `UUID` | `BIGSERIAL` (leaks cardinality) |
| Monetary amount | `NUMERIC(18,4)` or integer cents | `FLOAT` / `DOUBLE` (rounding) |
| Timestamp | `TIMESTAMPTZ` (with timezone) | `TIMESTAMP` (ambiguous) |
| Enum values | DB ENUM or `SMALLINT` + constraint | `VARCHAR` (no constraint) |
| Boolean | `BOOLEAN` | `INT` or `CHAR(1)` |
| Text (unbounded) | `TEXT` | `VARCHAR(255)` (arbitrary cap) |

---

## Indexing Strategy

(Reference: Use The Index, Luke — Markus Winand, use-the-index-luke.com)

### B-tree index — default for equality and range queries
```sql
-- Single-column: equality lookup
CREATE INDEX idx_orders_customer_id ON orders(customer_id);

-- Composite: leftmost-prefix rule — this index serves:
--   WHERE status = ?
--   WHERE status = ? AND created_at > ?
-- but NOT:
--   WHERE created_at > ?   (skips leading column)
CREATE INDEX idx_orders_status_created ON orders(status, created_at DESC);
```

**Leftmost-prefix rule**: a composite index on `(A, B, C)` can be used for
queries filtering on `A`, `(A, B)`, or `(A, B, C)`, but NOT on `B` or `C` alone.

### Partial index — index only the rows you query
```sql
-- Only pending orders need fast lookup; completed ones rarely queried
CREATE INDEX idx_orders_pending ON orders(customer_id)
WHERE status = 'PENDING';
```

### Covering index — include non-key columns to avoid heap access
```sql
-- Query: SELECT id, status, total FROM orders WHERE customer_id = ?
CREATE INDEX idx_orders_covering ON orders(customer_id) INCLUDE (status, total);
```

### When NOT to index
- Columns with very low cardinality (< 5 distinct values across millions of rows)
- Columns that are updated frequently (write amplification)
- Small tables (< 1000 rows) — sequential scan is faster

---

## N+1 Query Detection and Prevention

N+1 occurs when fetching N records then issuing one query per record.

```kotlin
// BAD — N+1: one query for orders + N queries for each order's items
val orders = orderRepository.findAll()        // SELECT * FROM orders → N rows
orders.forEach { order ->
    val items = itemRepository.findByOrderId(order.id)  // N queries
}

// GOOD — single JOIN query
val orders = orderRepository.findAllWithItems()  // SELECT ... JOIN order_items
```

**Detection in JPA/Hibernate:**
```properties
# Log SQL with execution time
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.stat=DEBUG
```

Look for repeated `select * from order_items where order_id=?` patterns.

**Fix strategies:**
- `JOIN FETCH` in JPQL / `fetch = FetchType.EAGER` scoped to the query
- `@EntityGraph` on repository methods
- Batch fetching: `@BatchSize(size = 50)`
- Separate explicit query returning DTO with all needed fields

---

## Query Optimization Checklist

```sql
-- 1. Use EXPLAIN ANALYZE (PostgreSQL) to see actual execution plan
EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = '...' AND status = 'PENDING';

-- 2. Look for Sequential Scan on large tables → needs an index
-- 3. Look for Hash Join / Nested Loop on unindexed foreign keys
-- 4. Check "rows" estimate vs actual — large discrepancy = stale statistics
ANALYZE orders;  -- refresh statistics

-- 5. Avoid functions on indexed columns (index is not used)
-- BAD
WHERE DATE(created_at) = '2024-01-01'  -- function call prevents index use
-- GOOD
WHERE created_at >= '2024-01-01' AND created_at < '2024-01-02'
```

---

## Schema Evolution — Safe Migration Patterns

(Reference: Evolutionary Database Design, Martin Fowler & Pramod Sadalage)

| Change type | Safe? | Notes |
|---|---|---|
| Add nullable column | ✓ Yes | No lock; default in app code |
| Add column with default | Caution | Table rewrite on large tables (Postgres) |
| Add index `CONCURRENTLY` | ✓ Yes | No table lock |
| Rename column | ✗ No | Add new column → backfill → drop old |
| Change column type | ✗ No | New column → migrate → drop |
| Drop column | After 2 deploys | App must stop reading before drop |
| Add NOT NULL constraint | ✗ No | Backfill first → add constraint |

Always use `CREATE INDEX CONCURRENTLY` to avoid locking in production:
```sql
CREATE INDEX CONCURRENTLY idx_orders_status ON orders(status);
```

---

## Checklist
- [ ] Schema normalized to 3NF (or intentional denormalization documented)
- [ ] Entity IDs use UUID, not auto-increment integers
- [ ] Monetary values use `NUMERIC` or integer cents (never `FLOAT`)
- [ ] Timestamps use `TIMESTAMPTZ`
- [ ] Indexes defined for all foreign keys
- [ ] Composite index column order follows query access patterns (leftmost-prefix)
- [ ] N+1 queries detected via SQL logging; JOIN FETCH or EntityGraph applied
- [ ] `EXPLAIN ANALYZE` run on queries expected to handle > 10k rows
- [ ] Migration uses `CREATE INDEX CONCURRENTLY` and backward-compatible column changes
- [ ] Schema design recorded in `{TASK_DIR}/context/design.md`
