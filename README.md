# ShopSphere | Enterprise Log Analysis

This project analyzes a four-hour, synthetic production incident for ShopSphere, a fictional e-commerce service. The data covers **2026-11-18 09:00–13:00 UTC** and contains deliberately planted payment, inventory, database, authentication, notification, and deployment signals. Names, users, hosts, IPs, and transactions are fictional; documentation-only IP ranges are used.

## Run the analysis

Python 3 is required. The analyzer uses the standard library for data processing and `matplotlib` to create charts.

```bash
python3 -m pip install matplotlib
python3 analysis.py
```

The command reads the three CSV inputs from the project directory and writes the Markdown/CSV reports to `reports/` and PNG charts to `charts/`. Use `--data-dir` to read inputs from another directory, `--output-dir` to choose where generated folders are written, and `--report` to additionally write the console-style Markdown summary to a chosen path.

```bash
python3 analysis.py --help
python3 -m unittest discover -s . -v
```

To regenerate all synthetic input data deterministically, run:

```bash
python3 generate_logs.py
```

This overwrites the generated `application_logs.jsonl`, `application_logs.csv`, `requests.csv`, and `metrics.csv` in the project directory.

## Inputs

- `requests.csv`: 12,000 request-level rows, one per trace. This is the authoritative denominator for request counts, status rates, and latency percentiles.
- `application_logs.csv` and `application_logs.jsonl`: 42,354 service and gateway log events. A request can create multiple events, so log-event counts are not request counts. The `details` field contains serialized JSON.
- `metrics.csv`: 576 five-minute measurements across three regions, covering active DB connections, gateway heap utilization, notification queue lag, and payment-provider p95 latency.

## Generated outputs

`analysis.py` produces the following files under `reports/` and `charts/`:

- `reports/INCIDENT_RCA.md`: impact, timeline, evidence, limitations, and recommended actions.
- `reports/error_timeline.csv` and `reports/worst_intervals.csv`: five-minute request counts, 4xx/5xx rates, p95 latency, and highest-error intervals.
- `reports/service_errors.csv` and `reports/error_code_summary.csv`: service/error event counts alongside unique trace counts.
- `reports/checkout_traces.md`: timestamp-ordered samples of failed checkout logs.
- `reports/security_anomalies.md`: failed-login sources, affected users, user agents, and time window.
- `reports/deployment_comparison.csv`: request and 5xx counts by region, endpoint, and version.
- `reports/metric_correlation.csv` and `reports/metric_correlation.md`: five-minute request/metric join and descriptive Pearson correlations.
- `charts/error_timeline.png`, `charts/service_error_heatmap.png`, `charts/checkout_trace.png`, and `charts/metric_correlation.png`.

## Current findings

The generated incident report analyzes 12,000 requests, of which 1,147 returned 5xx (9.56%). The major observed signatures are payment-provider timeouts in `us-east-1`, inventory deadlocks, order database pool exhaustion, failed-login activity, notification queue lag, and a `NULL_CUSTOMER_CONTEXT` error associated with the `v2.8.0` rollout in `us-east-1`. The detailed evidence and response recommendations are in [reports/INCIDENT_RCA.md](reports/INCIDENT_RCA.md).

## Interpretation notes

- Use request rows for customer-impact denominators. Counting service and gateway error logs together double-counts many failures.
- 401 authentication failures and 409 inventory conflicts are not 5xx outages, but can still indicate security or customer-impact issues.
- The span IDs in this dataset are not unique, so `parent_span_id` cannot support reliable causal reconstruction. Trace samples are ordered by timestamp and should not be read as validated waterfalls.
- Version and rollout time are coupled in the generated data. The version/region/route comparison indicates an association, not an isolated causal estimate.
- Infrastructure measurements are sampled every five minutes; correlations are descriptive and do not prove causation. Queue lag can occur after an otherwise successful checkout.
- This is a teaching simulation, not production telemetry. The separate [INSTRUCTOR_ANSWER_KEY.md](INSTRUCTOR_ANSWER_KEY.md) contains planted scenario details.
