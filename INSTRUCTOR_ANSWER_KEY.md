# Instructor answer key — keep separate from students

All data are generated. Intervals below are planted root-cause windows, not independently proven production findings.

1. **Credential-stuffing/login failures**, roughly **09:55–10:30 UTC** (55–90 minutes from start). Repeated `auth.login.failed`, `security.brute_force_indicator` and source `198.51.100.77`. Expect elevated 401s and `python-requests` user agents. Recommend credential-stuffing controls and rate limits, not a blanket ban on all 401s.
2. **External payment gateway timeout**, roughly **10:45–11:35 UTC** (105–155). `payment.gateway.timeout`, `PAYMENT_PROVIDER_TIMEOUT`, upstream `PayBridge`; primarily `us-east-1`. Provider p95 metric spikes. Recommend bounded retries with jitter, circuit breaking, idempotency, provider escalation.
3. **Inventory transaction deadlocks**, roughly **11:05–11:50 UTC** (125–170). `INVENTORY_DEADLOCK`, 409. Query SKU and lock-wait pattern. Recommend consistent lock order, reduced transaction scope, safe retry and inventory consistency checks.
4. **Order database pool exhausted**, roughly **11:25–12:05 UTC** (145–185). `DB_POOL_EXHAUSTED`, 503, pool active at maximum of 30 in `us-east-1`. Recommend pool sizing with load tests, backpressure, query optimization, connection leak investigation.
5. **Deployment regression**, new version `v2.8.0` only in `us-east-1` beginning **11:45 UTC** (minute 165). Planted `NULL_CUSTOMER_CONTEXT`, often 500 on affected auth/order/payment paths, observed through **12:40 UTC** (minute 220). Compare with same-region baseline and with other regions; rollback/disable `new-checkout-context` feature flag.
6. **Queue notification lag**, roughly **10:45–11:55 UTC** (105–175). `queue.consumer.lag` plus `queue_lag_messages` telemetry. Occurs even if checkout returned 200; analyze downstream business impact separately. Recommend worker capacity tuning, retry/DLQ, queue lag alerts.

Caution: The generator uses a conditional request path and fail-fast logic. An earlier failing service may mask later failures in the same trace. Some incidents overlap and should not be assigned all checkout errors in their time windows. `details` contains serialized JSON; parse it. User requests/tenant IDs are fake. Some 500s are randomly seeded transient noise.

Suggested student checkpoints:
- 12,000 unique request rows, 42,354 application log rows, 576 metric rows.
- HTTP status counts: 200=10,265; 500=657; 409=387; 503=311; 401=201; 504=179.
- 5xx requests: 1,147 / 12,000 (9.56%).
- 401 and 409 are non-5xx, but should still be studied from a security or application-consistency perspective.
