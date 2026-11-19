# ShopSphere Incident RCA

## Executive summary

The supplied synthetic dataset contains 12,000 requests; 1,147 returned 5xx (9.56%). Request-level rows are the denominator; service log lines are not counted as separate customer failures.

## Customer impact

- `ap-south-1`: 79/1,812 5xx requests (4.36%).
- `eu-west-1`: 116/2,356 5xx requests (4.92%).
- `us-east-1`: 952/7,832 5xx requests (12.16%).

## Incident timeline (UTC)

- 2026-11-18T10:45:12.872000+00:00 to 2026-11-18T11:34:10.050000+00:00: `PAYMENT_PROVIDER_TIMEOUT` (179 unique traces).
- 2026-11-18T11:05:09.470000+00:00 to 2026-11-18T11:49:55.152000+00:00: `INVENTORY_DEADLOCK` (387 unique traces).
- 2026-11-18T11:25:14.792000+00:00 to 2026-11-18T12:05:01.292000+00:00: `DB_POOL_EXHAUSTED` (311 unique traces).
- 2026-11-18T11:45:17.800000+00:00 to 2026-11-18T12:39:53.408000+00:00: `NULL_CUSTOMER_CONTEXT` (460 unique traces).
- 2026-11-18T10:46:57.194000+00:00 to 2026-11-18T11:55:09.937000+00:00: `QUEUE_CONSUMER_LAG` (66 unique traces).

Highest-rate intervals (minimum 20 requests), compared with the full-dataset 5xx baseline of 9.56%, are ranked in `worst_intervals.csv`.

## Verified evidence

### Checkout trace samples

- `41f4a967518b03f200b3b941c8dda779` at 2026-11-18T10:45:12.722Z: `PAYMENT_PROVIDER_TIMEOUT` (/api/v1/checkout, HTTP 504).
- `857e4cedd63fdc92adcb140612736285` at 2026-11-18T11:25:14.709Z: `DB_POOL_EXHAUSTED` (/api/v1/checkout, HTTP 503).
- `dcd6c67a92baddd13080881d5d75f821` at 2026-11-18T11:45:31.585Z: `NULL_CUSTOMER_CONTEXT` (/api/v1/checkout, HTTP 500).
Full timestamp-ordered records are in `checkout_traces.md`; parent-child ordering is uncertain because span IDs are not unique.

### Failure signatures

- `AUTH_INVALID_CREDENTIALS`: 2026-11-18T09:55:02.496000+00:00 to 2026-11-18T10:29:46.785000+00:00, 201 unique traces (402 log events).
- `DB_POOL_EXHAUSTED`: 2026-11-18T11:25:14.792000+00:00 to 2026-11-18T12:05:01.292000+00:00, 311 unique traces (622 log events).
- `INVENTORY_DEADLOCK`: 2026-11-18T11:05:09.470000+00:00 to 2026-11-18T11:49:55.152000+00:00, 387 unique traces (774 log events).
- `NULL_CUSTOMER_CONTEXT`: 2026-11-18T11:45:17.800000+00:00 to 2026-11-18T12:39:53.408000+00:00, 460 unique traces (920 log events).
- `PAYMENT_PROVIDER_TIMEOUT`: 2026-11-18T10:45:12.872000+00:00 to 2026-11-18T11:34:10.050000+00:00, 179 unique traces (358 log events).
- `QUEUE_CONSUMER_LAG`: 2026-11-18T10:46:57.194000+00:00 to 2026-11-18T11:55:09.937000+00:00, 66 unique traces (66 log events).
- `SUSPICIOUS_LOGIN`: 2026-11-18T09:55:02.575000+00:00 to 2026-11-18T10:29:46.783000+00:00, 201 unique traces (201 log events).
- `TRANSIENT_FAILURE`: 2026-11-18T09:02:32.495000+00:00 to 2026-11-18T12:59:26.263000+00:00, 197 unique traces (394 log events).

### Infrastructure observations

- `ap-south-1` db_pool_active: 19 connections at 2026-11-18T09:05:00Z.
- `ap-south-1` heap_used_pct: 48 percent at 2026-11-18T09:10:00Z.
- `ap-south-1` provider_p95_ms: 276 milliseconds at 2026-11-18T11:20:00Z.
- `ap-south-1` queue_lag_messages: 6470 messages at 2026-11-18T11:30:00Z.
- `eu-west-1` db_pool_active: 19 connections at 2026-11-18T09:00:00Z.
- `eu-west-1` heap_used_pct: 48 percent at 2026-11-18T09:25:00Z.
- `eu-west-1` provider_p95_ms: 280 milliseconds at 2026-11-18T09:10:00Z.
- `eu-west-1` queue_lag_messages: 6476 messages at 2026-11-18T11:35:00Z.
- `us-east-1` db_pool_active: 30 connections at 2026-11-18T11:25:00Z.
- `us-east-1` heap_used_pct: 96 percent at 2026-11-18T12:45:00Z.
- `us-east-1` provider_p95_ms: 5804 milliseconds at 2026-11-18T10:50:00Z.
- `us-east-1` queue_lag_messages: 6256 messages at 2026-11-18T10:45:00Z.

### Authentication

- Source `198.51.100.77`: 201 failed-login events, 195 distinct non-empty user IDs, 2026-11-18T09:55:02.496000+00:00 to 2026-11-18T10:29:46.695000+00:00 UTC.
  User agents: {'python-requests/2.32': 201}.
Peak five-minute window: 2026-11-18T09:55:00+00:00 UTC (35 failed-login events).

Treat this as a signal for targeted rate limits and account review; a source IP alone is not proof of malicious intent.

### Deployment

- `us-east-1` `/api/v1/cart` `v2.8.0`: 95/360 5xx (26.39%); NULL_CUSTOMER_CONTEXT=92.
- `us-east-1` `/api/v1/checkout` `v2.8.0`: 224/616 5xx (36.36%); NULL_CUSTOMER_CONTEXT=160.
- `us-east-1` `/api/v1/login` `v2.8.0`: 108/417 5xx (25.90%); NULL_CUSTOMER_CONTEXT=103.
- `us-east-1` `/api/v1/orders` `v2.8.0`: 140/355 5xx (39.44%); NULL_CUSTOMER_CONTEXT=105.
- `us-east-1` `/api/v1/products` `v2.8.0`: 5/691 5xx (0.72%); NULL_CUSTOMER_CONTEXT=0.

Version and rollout time are coupled in this dataset, so these route/region rates support a regression hypothesis but do not isolate a causal version effect.

### Notifications

Observed `QUEUE_CONSUMER_LAG` records: 66; HTTP 200 on 66 records. This indicates asynchronous delivery lag, not a failed checkout request by itself.

## Assessment and response

Payment-provider timeouts, inventory conflicts, database pool exhaustion, and the post-rollout null-context signature are distinct observed failure modes. The joined metrics and checkout traces are corroborating evidence, not proof of causation; trace ordering is timestamp-based because span identifiers are not unique.

Prioritize provider circuit breaking with idempotent bounded retries, inventory lock/deadlock review, database pool/backpressure investigation, and a canary/rollback evaluation for the null-context regression. For authentication, use targeted rate limiting and account review rather than blanket blocking. Scale notification consumers and validate delivery independently from checkout success.

| Owner | Immediate mitigation | Permanent follow-up | Validation |
| --- | --- | --- | --- |
| Payments / SRE | Bound retries and enable a provider circuit breaker. | Add idempotency and dependency-timeout budgets. | Provider timeouts and checkout 5xx recover without duplicate charges. |
| Inventory / Database | Apply backpressure and inspect pool saturation. | Fix transaction lock ordering and pool lifecycle. | Deadlocks and pool waits stay within agreed load-test limits. |
| Release / API | Canary rollback or disable the affected checkout feature flag. | Add null-context input validation and rollout guardrails. | Error signature disappears and route-adjusted 5xx stays near baseline. |
| Security | Rate-limit the observed login burst and review affected accounts. | Add risk-based throttles and credential-stuffing alerts. | Abuse declines without a rise in legitimate login failures. |
| Messaging | Scale consumers and inspect retries / dead-letter queues. | Add oldest-message-age SLO and autoscaling. | Queue lag clears while successful order volume remains stable. |

## Validation and limitations

- 401 and 409 are separated from 5xx; they can still be security or inventory-impact signals.
- Metrics are sampled every five minutes; correlation is not causation.
- The generated trace samples do not establish parent-child causality because the source has only one distinct span_id value.
- The dataset is a synthetic teaching simulation; validate mitigations with production telemetry before action.
