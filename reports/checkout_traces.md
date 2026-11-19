# Failed checkout trace samples

Selected from request-level 5xx checkout rows; timestamps are UTC. Log records are ordered by timestamp. The dataset has a single distinct span_id, so parent_span_id cannot establish a reliable causal waterfall.

## 41f4a967518b03f200b3b941c8dda779

Request: 2026-11-18T10:45:12.722Z | us-east-1 | /api/v1/checkout | HTTP 504 | 4852 ms | PAYMENT_PROVIDER_TIMEOUT

| Timestamp | Service | Event | Level | Error code | HTTP | Latency ms | Span | Parent span |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| 2026-11-18T10:45:12.751Z | auth-service | request.completed | INFO |  | 200 | 63 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T10:45:12.814Z | cart-service | request.completed | INFO |  | 200 | 32 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T10:45:12.846Z | inventory-service | request.completed | INFO |  | 200 | 15 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T10:45:12.861Z | order-service | request.completed | INFO |  | 200 | 11 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T10:45:12.872Z | payment-service | payment.gateway.timeout | ERROR | PAYMENT_PROVIDER_TIMEOUT | 504 | 4702 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T10:45:17.578Z | api-gateway | http.response | ERROR | PAYMENT_PROVIDER_TIMEOUT | 504 | 4852 | 0000000000000000 |  |

## 857e4cedd63fdc92adcb140612736285

Request: 2026-11-18T11:25:14.709Z | us-east-1 | /api/v1/checkout | HTTP 503 | 3958 ms | DB_POOL_EXHAUSTED

| Timestamp | Service | Event | Level | Error code | HTTP | Latency ms | Span | Parent span |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| 2026-11-18T11:25:14.730Z | auth-service | request.completed | INFO |  | 200 | 26 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T11:25:14.756Z | cart-service | request.completed | INFO |  | 200 | 15 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T11:25:14.771Z | inventory-service | request.completed | INFO |  | 200 | 21 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T11:25:14.792Z | order-service | db.pool.exhausted | ERROR | DB_POOL_EXHAUSTED | 503 | 3875 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T11:25:18.671Z | api-gateway | http.response | ERROR | DB_POOL_EXHAUSTED | 503 | 3958 | 0000000000000000 |  |

## dcd6c67a92baddd13080881d5d75f821

Request: 2026-11-18T11:45:31.585Z | us-east-1 | /api/v1/checkout | HTTP 500 | 1345 ms | NULL_CUSTOMER_CONTEXT

| Timestamp | Service | Event | Level | Error code | HTTP | Latency ms | Span | Parent span |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| 2026-11-18T11:45:31.603Z | auth-service | application.exception | ERROR | NULL_CUSTOMER_CONTEXT | 500 | 1327 | 0000000000000000 | 0000000000000000 |
| 2026-11-18T11:45:32.934Z | api-gateway | http.response | ERROR | NULL_CUSTOMER_CONTEXT | 500 | 1345 | 0000000000000000 |  |
