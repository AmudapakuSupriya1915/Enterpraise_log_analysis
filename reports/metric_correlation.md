# Request and infrastructure metric correlation

Requests and metrics are aligned by region and floored five-minute UTC timestamp. Pearson coefficients are descriptive only; shared time trends, rollout timing, and other confounders prevent causal claims.

| Metric | Pearson r vs 5xx rate | Aligned samples |
| --- | ---: | ---: |
| db_pool_active | 0.415 | 144 |
| heap_used_pct | 0.247 | 144 |
| provider_p95_ms | 0.235 | 144 |
| queue_lag_messages | 0.277 | 144 |
