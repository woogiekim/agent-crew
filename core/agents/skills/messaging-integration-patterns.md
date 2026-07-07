---
name: messaging-integration-patterns
description: Reliable asynchronous messaging patterns — idempotent consumers, transactional outbox, dead letter channel, correlation IDs, at-least-once delivery.
loaded_by: backend
axis: messaging-integration
detection: kafka OR amqp OR rabbitmq OR message queue OR event driven OR outbox OR dead letter OR build.gradle containing kafka OR build.gradle.kts containing kafka OR pom.xml containing kafka OR package.json containing kafkajs OR package.json containing amqplib OR pyproject.toml containing kafka OR pyproject.toml containing pika OR requirements.txt containing kafka OR requirements.txt containing pika
---

# Skill: messaging-integration-patterns

## Source
- Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns: Designing, Building, and Deploying Messaging Solutions*, 2003
- Modern at-least-once delivery practice (transactional outbox, idempotent consumer) as popularized by Chris Richardson, *Microservices Patterns*, 2018

## When to Apply
- A task mentions kafka, amqp, rabbitmq, a message queue, event-driven work,
  an outbox, or a dead letter channel.
- The project manifest declares a messaging dependency (e.g. `spring-kafka`
  in `build.gradle`, `kafkajs` or `amqplib` in `package.json`, `kafka` or
  `pika` in a Python manifest).
- Designing a producer/consumer, an event handler, or any integration where
  one service reacts to another's message.
- Adding retries, redelivery handling, or failure routing to a message flow.
- Correlating logs/traces across asynchronous service hops.

## Core Rules

### Rule 1: Assume at-least-once delivery as the default
> Source: Hohpe & Woolf, *EIP* — "Guaranteed Delivery"; modern practice

Design every message flow for at-least-once delivery. Exactly-once is an
end-to-end illusion: transports redeliver on ack loss, timeout, or rebalance.
Do not build correctness on a broker's "exactly-once" mode; combine at-least-
once transport with an idempotent consumer (Rule 2) instead.

### Rule 2: Make every consumer idempotent
> Source: Hohpe & Woolf, *EIP* — "Idempotent Receiver"

A consumer must tolerate duplicate delivery of the same message without
duplicating side effects. Use one of:

- a natural idempotent operation (set a value rather than increment it);
- an idempotency key carried on the message plus a dedupe store that records
  processed keys and is checked before acting;
- an upsert keyed by a business identifier.

```text
# GOOD — dedupe on a message-carried key before applying the effect
def handle(message):
    if processed_store.seen(message.id):
        return                      # duplicate — safely ignored
    apply_effect(message)
    processed_store.mark(message.id)
```

### Rule 3: Never publish an event and commit a DB write as two separate writes
> Source: Richardson, *Microservices Patterns* — "Transactional Outbox"

Writing to the database and publishing to the broker in two independent steps
creates a dual-write failure: one can succeed while the other fails, losing or
duplicating the event. Instead, write the event into an **outbox** table inside
the same database transaction as the state change, then relay outbox rows to
the broker asynchronously.

```text
# BAD — dual write, no atomicity
db.save(order); broker.publish(order_placed)   # crash between = lost event

# GOOD — single transaction, then relay
with db.transaction():
    db.save(order)
    db.insert_outbox(order_placed)
# a separate relay reads the outbox and publishes (at-least-once)
```

### Rule 4: Relay the outbox and mark rows only after a confirmed publish
> Source: Richardson, *Microservices Patterns* — "Transactional Outbox" / "Polling Publisher"

A message relay (polling publisher or change-data-capture) reads unsent outbox
rows, publishes them, and marks them sent only after the broker confirms. If
the relay crashes after publish but before marking, the row is re-published —
which is safe precisely because consumers are idempotent (Rule 2).

### Rule 5: Route poison messages to a Dead Letter Channel after bounded retries
> Source: Hohpe & Woolf, *EIP* — "Dead Letter Channel", "Invalid Message Channel"

A message that repeatedly fails processing must not block the queue or retry
forever. After a bounded number of attempts, move it to a Dead Letter Channel
(dead letter queue) for out-of-band inspection and reprocessing. Distinguish an
**invalid message** (malformed, will never succeed) from a **failed delivery**
(transient) and route accordingly.

### Rule 6: Never retry unboundedly
> Source: Hohpe & Woolf, *EIP* — "Dead Letter Channel"; modern practice

Every retry policy must have a finite bound and, ideally, backoff. Unbounded
retry turns one poison message into an infinite loop that starves the consumer
and hides the failure. Cap attempts, then dead-letter.

### Rule 7: Alert on Dead Letter Queue depth
> Source: Hohpe & Woolf, *EIP* — "Control Bus", "Dead Letter Channel"; operations practice

A DLQ that fills silently is a silent outage. Monitor DLQ depth and alert when
it grows; a rising DLQ is the earliest signal that a downstream contract broke
or a consumer is mis-deployed.

### Rule 8: Propagate a Correlation ID across every hop
> Source: Hohpe & Woolf, *EIP* — "Correlation Identifier"

Attach a correlation identifier to each message and carry it, unchanged,
through every subsequent message and log line the flow produces. Without it,
an asynchronous flow spanning several services cannot be traced end-to-end.
Generate one at the entry point if the inbound request has none.

### Rule 9: Include a message identity and enough metadata to dedupe and trace
> Source: Hohpe & Woolf, *EIP* — "Message", "Format Indicator"

Every message carries a stable unique id (for idempotency, Rule 2), the
correlation id (Rule 8), and a schema/version indicator so consumers can evolve
independently. Treat the message envelope as a contract, versioned like any API.

### Rule 10: Acknowledge only after the effect is durable
> Source: Hohpe & Woolf, *EIP* — "Guaranteed Delivery"; modern practice

Do not acknowledge/commit the offset until the consumer's side effect is
durably recorded (committed transaction, persisted outcome). Acknowledging
first and then crashing loses the message; processing first and acknowledging
after (with idempotency to absorb the redelivery) is the safe order.

### Rule 11: Keep patterns broker-neutral in domain and application code
> Source: Hohpe & Woolf, *EIP* — "Message Endpoint", "Messaging Gateway"

Depend on a messaging abstraction (gateway/port), not on a concrete broker
API, inside domain and application layers. Kafka, RabbitMQ/AMQP, SQS, and
others are interchangeable transports; the outbox, idempotency, DLQ, and
correlation rules above apply to all of them. Confine broker-specific code to
an adapter at the boundary.

### Rule 12: Preserve ordering only where the domain requires it, and know its cost
> Source: Hohpe & Woolf, *EIP* — "Resequencer", "Message Sequence"

Global ordering across a partitioned/queued transport is expensive and often
unnecessary. Where the domain needs per-entity ordering, key messages by the
entity id so related messages share a partition/queue; do not assume global
order otherwise, and design consumers to tolerate out-of-order arrival.

## Anti-Patterns
- Relying on broker "exactly-once" mode instead of idempotent consumers.
- Dual-writing to the database and the broker as two separate steps.
- Consumers that duplicate side effects on redelivery (increment, append,
  re-charge) with no dedupe.
- Unbounded or backoff-free retry loops.
- No dead letter channel, so poison messages block or vanish.
- A DLQ nobody monitors or alerts on.
- Dropping the correlation id at a hop, breaking end-to-end tracing.
- Acknowledging/committing the offset before the effect is durable.
- Leaking broker-specific APIs into domain/application code.
- Assuming global message ordering across partitions or queues.

## Interaction with Other Skills
- Works alongside `error-handling.md` — dead letter routing and bounded retry
  are the messaging expression of its failure-contract rules.
- Works alongside `database-design.md` — the transactional outbox is a table
  and a relay; model it with the same persistence-boundary discipline.
- Works alongside `domain-driven-design.md` — messages are typically domain
  events crossing bounded-context boundaries; keep the envelope a versioned
  contract.

## References
- Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns: Designing,
  Building, and Deploying Messaging Solutions*, Addison-Wesley, 2003.
  ISBN 978-0321200686.
- Chris Richardson, *Microservices Patterns: With Examples in Java*, Manning,
  2018. ISBN 978-1617294549.
</content>
</invoke>
