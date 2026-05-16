# Skill: observability

## Purpose
Enables the devops and backend agents to instrument services with the three pillars of observability — structured logging, distributed tracing, and metrics — so that production failures can be diagnosed without requiring a code change.

## When to Apply
- When adding a new service, endpoint, or background job
- When configuring a CI/CD pipeline or production deployment
- When debugging a production incident (what to look for and how)
- When defining SLOs for a new feature

---

## The Three Pillars of Observability

(Reference: Charity Majors, Liz Fong-Jones, George Miranda — "Observability Engineering", O'Reilly, 2022)

| Pillar | What it answers | Tool examples |
|---|---|---|
| **Logs** | What happened at a specific time | Loki, Elasticsearch, CloudWatch Logs |
| **Metrics** | How healthy is the system right now? Trends over time? | Prometheus, Datadog, CloudWatch Metrics |
| **Traces** | Which code path caused this latency? Which service failed? | Jaeger, Zipkin, OpenTelemetry, AWS X-Ray |

Observability is NOT just logging. A system is observable if you can understand any novel failure mode purely from its external outputs — without deploying new code.

---

## Structured Logging

(Reference: The Twelve-Factor App, Factor XI — Logs; OpenTelemetry logging spec)

### Principles
- Log in JSON (or key=value) — never free-form strings
- Include trace context in every line (`trace_id`, `span_id`, `request_id`)
- Never log sensitive data (PII, secrets, tokens) — log IDs only
- Log at boundaries: request in/out, DB calls, external API calls, domain event emission

### Kotlin + SLF4J + Logback Structured Logging

```kotlin
// logback.xml — JSON output for log aggregators
// Use logstash-logback-encoder or logback-json-encoder

private val log = LoggerFactory.getLogger(OrderService::class.java)

// GOOD — structured key-value pairs
fun placeOrder(command: PlaceOrderCommand): Either<OrderError, Order> {
    log.info("order.placement.started",
        "order_id" to command.orderId.value,
        "customer_id" to command.customerId.value,
        "item_count" to command.items.size
    )
    return processOrder(command)
        .onRight { order ->
            log.info("order.placement.succeeded",
                "order_id" to order.id.value,
                "total_amount" to order.totalAmount().amount
            )
        }
        .onLeft { error ->
            log.error("order.placement.failed",
                "order_id" to command.orderId.value,
                "error_type" to error::class.simpleName,
                "error_message" to error.message
            )
        }
}

// BAD — unstructured, no context
log.info("Order placed for customer ${customerId}")
```

### Log Levels

| Level | Use for |
|---|---|
| `ERROR` | Unexpected failures that need immediate attention; always include trace context |
| `WARN` | Expected failure paths (retry eligible, circuit breaker open) |
| `INFO` | Business-significant events (order placed, payment received, user registered) |
| `DEBUG` | Developer diagnostic information (never in production default config) |
| `TRACE` | Full request/response bodies, detailed state transitions (development only) |

---

## Distributed Tracing — OpenTelemetry

(Reference: opentelemetry.io; OpenTelemetry specification v1.x)

### Core concepts

- **Trace**: the complete path of one request through all services
- **Span**: a single unit of work within a trace (one HTTP call, one DB query)
- **Context Propagation**: W3C TraceContext header (`traceparent`) carries trace ID across service boundaries

### Spring Boot + OpenTelemetry auto-instrumentation

```yaml
# application.yaml — auto-instrumentation; no manual span creation needed for HTTP + DB
management:
  tracing:
    sampling:
      probability: 1.0  # 100% in dev; 0.1 in production
  otlp:
    tracing:
      endpoint: http://jaeger:4318/v1/traces
```

### Manual span for business operations

```kotlin
@Service
class OrderService(private val tracer: Tracer) {
    fun placeOrder(command: PlaceOrderCommand): Either<OrderError, Order> {
        val span = tracer.spanBuilder("order.place")
            .setAttribute("order.id", command.orderId.value.toString())
            .setAttribute("customer.id", command.customerId.value.toString())
            .startSpan()

        return try {
            span.makeCurrent().use {
                processOrder(command)
                    .onRight { span.setStatus(StatusCode.OK) }
                    .onLeft  { span.setStatus(StatusCode.ERROR, it.message ?: "unknown") }
            }
        } finally {
            span.end()
        }
    }
}
```

### Trace context in logs

```kotlin
// Automatically correlate logs to traces using MDC
// Add traceId/spanId to MDC in a filter or interceptor
MDC.put("trace_id", span.spanContext.traceId)
MDC.put("span_id", span.spanContext.spanId)
```

---

## Metrics — Prometheus + Micrometer

(Reference: Prometheus documentation; Brendan Gregg's USE method)

### Four Golden Signals (Google SRE Book, 2016)

| Signal | Description | Example metric |
|---|---|---|
| **Latency** | Time to serve a request | `http_server_requests_seconds` |
| **Traffic** | Rate of requests | `http_server_requests_total` |
| **Errors** | Rate of failed requests | `http_server_requests_total{status="5xx"}` |
| **Saturation** | How full is the system? | `jvm_memory_used_bytes`, `db_pool_pending` |

### Micrometer instrumentation (Spring Boot)

```kotlin
@Component
class OrderMetrics(private val meterRegistry: MeterRegistry) {
    private val placedCounter = meterRegistry.counter("orders.placed")
    private val failedCounter = meterRegistry.counter("orders.failed")
    private val placementTimer = meterRegistry.timer("orders.placement.duration")

    fun recordPlacement(result: Either<OrderError, Order>) {
        result.fold(
            ifLeft  = { failedCounter.increment() },
            ifRight = { placedCounter.increment() }
        )
    }

    fun <T> timedPlacement(block: () -> T): T =
        placementTimer.record(block)!!
}
```

### Custom business metrics

```kotlin
// Gauge — current value (e.g. queue depth)
meterRegistry.gauge("orders.pending.count", orderRepository) { repo ->
    repo.countByStatus(OrderStatus.PENDING).toDouble()
}

// Histogram — distribution (e.g. order value)
val orderValueHistogram = DistributionSummary.builder("orders.value")
    .baseUnit("cents")
    .publishPercentiles(0.5, 0.95, 0.99)
    .register(meterRegistry)
orderValueHistogram.record(order.totalAmount().amount.toDouble())
```

---

## SLO / SLI / SLA Definitions

(Reference: Google SRE Book, Chapter 4)

| Term | Definition | Example |
|---|---|---|
| **SLI** (Service Level Indicator) | Metric that measures service health | `success_rate = successful_requests / total_requests` |
| **SLO** (Service Level Objective) | Target for SLI over a time window | `success_rate ≥ 99.9% over 28 days` |
| **SLA** (Service Level Agreement) | Business contract; breach triggers penalty | `If availability < 99.5%, credit issued` |
| **Error Budget** | `1 - SLO` — allowed failure allowance | `0.1% of 28 days = 40.32 minutes downtime` |

### Define SLOs before deployment

Document in `{TASK_DIR}/context/design.md`:

```markdown
## SLOs — Order Service

| SLI | SLO | Measurement window |
|---|---|---|
| POST /orders success rate | ≥ 99.5% | 7 days |
| POST /orders p99 latency | ≤ 500ms | 7 days |
| GET /orders/{id} p99 latency | ≤ 100ms | 7 days |
| Order placement end-to-end latency | ≤ 2s | 7 days |
```

### Prometheus alert rule for SLO breach

```yaml
# alert.rules.yaml
- alert: OrderPlacementErrorRateHigh
  expr: |
    (
      rate(http_server_requests_seconds_count{uri="/orders",status=~"5.."}[5m])
      /
      rate(http_server_requests_seconds_count{uri="/orders"}[5m])
    ) > 0.005
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Order placement error rate exceeded SLO (> 0.5%)"
```

---

## Health Endpoint

```kotlin
// Spring Boot Actuator — /actuator/health
// Add custom health indicator for critical dependencies

@Component
class DatabaseHealthIndicator(private val dataSource: DataSource) : HealthIndicator {
    override fun health(): Health {
        return try {
            dataSource.connection.use { conn ->
                conn.prepareStatement("SELECT 1").execute()
                Health.up().withDetail("database", "reachable").build()
            }
        } catch (e: Exception) {
            Health.down(e).withDetail("database", "unreachable").build()
        }
    }
}
```

---

## Checklist
- [ ] All logs in structured JSON format (logstash-logback-encoder or equivalent)
- [ ] `trace_id` and `span_id` included in every log line via MDC
- [ ] No PII or secrets in logs (IDs only)
- [ ] Log levels correct (ERROR for unexpected, INFO for business events, DEBUG off in prod)
- [ ] OpenTelemetry auto-instrumentation enabled for HTTP + DB
- [ ] Manual spans added for business operations spanning multiple services
- [ ] W3C `traceparent` header propagated across all outbound calls
- [ ] Four Golden Signals instrumented (latency, traffic, errors, saturation)
- [ ] Business metrics added (domain-specific counters, gauges, histograms)
- [ ] SLOs defined for all new endpoints; Prometheus alert rules written
- [ ] `/actuator/health` endpoint includes custom health indicators for external deps
