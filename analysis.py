"""Analyze ShopSphere request, service-log, and monitoring CSV data."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def load_csv(path):
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def percentile(values, proportion):
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[round((len(ordered) - 1) * proportion)]


def five_minute_bucket(timestamp):
    return timestamp.replace(minute=(timestamp.minute // 5) * 5, second=0, microsecond=0)


def analyze(data_dir=BASE_DIR):
    requests = load_csv(data_dir / "requests.csv")
    logs = load_csv(data_dir / "application_logs.csv")
    metrics = load_csv(data_dir / "metrics.csv")

    for row in requests:
        row["status"] = int(row["status"])
        row["latency_ms"] = int(row["latency_ms"])
        row["dt"] = parse_timestamp(row["timestamp"])

    request_statuses = Counter(row["status"] for row in requests)
    request_errors = Counter(
        (row["region"], row["error_code"])
        for row in requests if row["error_code"]
    )
    request_groups = defaultdict(list)
    regional_requests = defaultdict(lambda: {"total": 0, "5xx": 0})
    for row in requests:
        request_groups[(five_minute_bucket(row["dt"]), row["region"], row["endpoint"])].append(row)
        regional_requests[row["region"]]["total"] += 1
        regional_requests[row["region"]]["5xx"] += row["status"] >= 500

    log_errors = Counter(
        (row["service"], row["error_code"], row["http_status"])
        for row in logs if row["error_code"]
    )
    trace_logs = defaultdict(list)
    failure_signatures = defaultdict(lambda: {"events": 0, "traces": set(), "timestamps": []})
    auth_sources = Counter()
    auth_agents = Counter()
    auth_users = set()
    auth_timestamps = []
    for row in logs:
        trace_logs[row["trace_id"]].append(row)
        if row["event"] == "auth.login.failed":
            details = json.loads(row["details"] or "{}")
            auth_sources[details.get("source_ip", "(missing)")] += 1
            auth_agents[details.get("user_agent", "(missing)")] += 1
            auth_users.add(row["user_id"])
            auth_timestamps.append(parse_timestamp(row["timestamp"]))
        if row["error_code"]:
            signature = failure_signatures[row["error_code"]]
            signature["events"] += 1
            signature["traces"].add(row["trace_id"])
            signature["timestamps"].append(parse_timestamp(row["timestamp"]))

    metric_values = defaultdict(list)
    for row in metrics:
        key = (parse_timestamp(row["timestamp"]), row["region"], row["metric"])
        metric_values[key].append(float(row["value"]))

    return {
        "requests": requests,
        "logs": logs,
        "metrics": metrics,
        "status_counts": request_statuses,
        "error_counts": request_errors,
        "request_groups": request_groups,
        "regional_requests": regional_requests,
        "log_error_counts": log_errors,
        "failure_signatures": failure_signatures,
        "auth_sources": auth_sources,
        "auth_agents": auth_agents,
        "auth_users": auth_users,
        "auth_timestamps": auth_timestamps,
        "trace_logs": trace_logs,
        "metric_values": metric_values,
    }


def render_report(data):
    requests = data["requests"]
    total = len(requests)
    failed_5xx = sum(row["status"] >= 500 for row in requests)
    latencies = [row["latency_ms"] for row in requests]
    duplicate_traces = total - len({row["trace_id"] for row in requests})
    distinct_span_ids = len({row["span_id"] for row in data["logs"]})
    request_groups = data["request_groups"]
    eligible_buckets = [
        item for item in request_groups.items() if len(item[1]) >= 20
    ]
    peak_bucket = max(
        eligible_buckets,
        key=lambda item: sum(row["status"] >= 500 for row in item[1]) / len(item[1]),
    ) if eligible_buckets else (None, [])
    peak_key, peak_requests = peak_bucket
    peak_failures = sum(row["status"] >= 500 for row in peak_requests)
    peak_rate = peak_failures / len(peak_requests) * 100 if peak_requests else 0

    lines = [
        "# ShopSphere Incident Analysis",
        "",
        "## Scope and method",
        "",
        "This report uses request rows for customer-impact denominators, service logs for failure signatures, and five-minute metrics for corroboration. Log-event totals are not treated as unique failed requests.",
        "",
        "## Request impact",
        "",
        f"- Requests analyzed: {total:,}",
        f"- 5xx requests: {failed_5xx:,} ({failed_5xx / total * 100:.2f}%)" if total else "- 5xx requests: 0",
        f"- HTTP status counts: {dict(sorted(data['status_counts'].items()))}",
        f"- Latency p50/p95/p99: {percentile(latencies, 0.50)}/{percentile(latencies, 0.95)}/{percentile(latencies, 0.99)} ms",
        f"- Duplicate request trace IDs: {duplicate_traces}",
        f"- Highest five-minute region/endpoint 5xx rate (minimum 20 requests): {peak_key[0].isoformat()} {peak_key[1]} {peak_key[2]}: {peak_failures}/{len(peak_requests)} ({peak_rate:.1f}%)" if peak_key else "- No request buckets with at least 20 requests",
        "",
        "### Regional request impact",
        "",
        "| Region | Requests | 5xx requests | 5xx rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for region, counts in sorted(data["regional_requests"].items()):
        rate = counts["5xx"] / counts["total"] * 100 if counts["total"] else 0
        lines.append(f"| {region} | {counts['total']} | {counts['5xx']} | {rate:.2f}% |")
    lines.extend([
        "",
        "## Request errors by region and code",
        "",
        "| Region | Error code | Requests |",
        "| --- | --- | ---: |",
    ])
    lines.extend(
        f"| {region} | {code} | {count} |"
        for (region, code), count in data["error_counts"].most_common()
    )
    lines.extend([
        "",
        "## Service log error events",
        "",
        "These are event counts; gateway responses may duplicate a service-side failure.",
        "",
        "| Service | Error code | HTTP status | Events |",
        "| --- | --- | ---: | ---: |",
    ])
    lines.extend(
        f"| {service} | {code} | {status} | {count} |"
        for (service, code, status), count in data["log_error_counts"].most_common()
    )
    lines.extend([
        "",
        "## Authentication signal",
        "",
    ])
    auth_times = data["auth_timestamps"]
    lines.append(f"- `auth.login.failed` events: {len(auth_times)}")
    lines.append(f"- Source IP counts: {dict(data['auth_sources'].most_common())}")
    lines.append(f"- User-agent counts: {dict(data['auth_agents'].most_common())}")
    lines.append(f"- Unique user IDs affected: {len(data['auth_users'])}")
    if auth_times:
        lines.append(
            f"- Observed window: {min(auth_times).isoformat()} to {max(auth_times).isoformat()}"
        )
    lines.extend([
        "",
        "## Failure signature windows",
        "",
        "Times come from logs; unique traces reduce duplicate service/gateway events.",
        "",
        "| Error code | First seen UTC | Last seen UTC | Unique traces | Log events |",
        "| --- | --- | --- | ---: | ---: |",
    ])
    for code, signature in sorted(data["failure_signatures"].items()):
        timestamps = signature["timestamps"]
        lines.append(
            f"| {code} | {min(timestamps).isoformat()} | {max(timestamps).isoformat()} | {len(signature['traces'])} | {signature['events']} |"
        )
    lines.extend([
        "",
        "## Deployment comparison by region, endpoint, and version",
        "",
        "| Region | Endpoint | Version | Requests | 5xx | 5xx rate |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ])
    deploy_groups = defaultdict(list)
    for row in requests:
        deploy_groups[(row["region"], row["endpoint"], row["version"])].append(row)
    for (region, endpoint, version), rows in sorted(deploy_groups.items()):
        errors = sum(row["status"] >= 500 for row in rows)
        lines.append(
            f"| {region} | {endpoint} | {version} | {len(rows)} | {errors} | {errors / len(rows) * 100:.2f}% |"
        )
    lines.extend([
        "",
        "These are aggregate associations, not a time-controlled causal comparison; version and rollout time are coupled in the supplied data.",
    ])
    lines.extend([
        "",
        "## Monitoring signals",
        "",
        "| Region | Metric | Peak | Timestamp UTC | Unit |",
        "| --- | --- | --- | --- | --- |",
    ])
    metric_peaks = {}
    for row in data["metrics"]:
        key = (row["region"], row["metric"])
        value = float(row["value"])
        if key not in metric_peaks or value > metric_peaks[key][0]:
            metric_peaks[key] = (value, row["timestamp"])
    units = {row["metric"]: row["unit"] for row in data["metrics"]}
    lines.extend(
        f"| {region} | {metric} | {value:g} | {timestamp} | {units.get(metric, '')} |"
        for (region, metric), (value, timestamp) in sorted(metric_peaks.items())
    )
    lines.extend([
        "",
        "## Incident assessment and response",
        "",
        "- **External payments:** `PAYMENT_PROVIDER_TIMEOUT` is concentrated in `us-east-1`; compare its 10:45–11:34 UTC signature window with the provider p95 peak above. This supports provider degradation as a checkout contributor, not the sole incident cause.",
        "- **Inventory and database:** `INVENTORY_DEADLOCK` returned 409s and `DB_POOL_EXHAUSTED` returned 503s. The order DB pool reached its 30-connection observed maximum at 11:25 UTC; overlapping failures mean trace-level ordering is needed before assigning individual requests.",
        "- **Release regression:** `NULL_CUSTOMER_CONTEXT` begins at 11:45 UTC in `us-east-1`, where `v2.8.0` was deployed. The route/version table shows elevated 5xx associations, but rollout time and version are coupled, so this is strong evidence for rollback/flag evaluation, not a controlled causal estimate.",
        "- **Notifications:** queue-lag events have HTTP 200 in the worker logs; treat these as delayed downstream email delivery, not failed checkout requests.",
        "- **Authentication:** the single-source, single-agent pattern warrants targeted abuse controls and account review. A blanket block of all 401 responses would create false positives.",
        "",
        "| Owner | Action | Validation |",
        "| --- | --- | --- |",
        "| Payments / SRE | Add bounded retries with jitter, idempotency, and a provider circuit breaker; escalate sustained upstream latency. | Provider timeout rate and checkout 5xx return to baseline without duplicate charges. |",
        "| Inventory / Database | Review lock ordering and transaction duration; investigate pool saturation, leaks, and backpressure. | Deadlock/503 rates fall under load tests and pool wait time stays below the agreed threshold. |",
        "| Release / API | Disable `new-checkout-context` or roll back `v2.8.0` in the affected region, then canary the fix. | `NULL_CUSTOMER_CONTEXT` disappears and route-adjusted 5xx rates remain near baseline during canary. |",
        "| Security | Apply risk-based login rate limits and investigate the source and affected accounts. | Failed-login burst is contained without materially increasing legitimate login failures. |",
        "| Messaging | Scale consumers and verify retry/DLQ behavior for order email events. | Queue lag and oldest-message age recover while successful order counts remain stable. |",
        "",
        "## Interpretation and caveats",
        "",
        "- HTTP 401 and 409 responses are not 5xx outages, but can still represent authentication abuse or inventory/customer-impacting conflicts.",
        "- A request may have multiple service logs. Use `trace_id` to associate logs with a request; use the request table for customer-impact counts.",
        f"- The logs contain {distinct_span_ids} distinct `span_id` value(s); parent-span reconstruction is not reliable for this dataset.",
        "- Metrics are sampled every five minutes and indicate correlation, not proof of causation. Deployment comparisons should account for time and route mix.",
        "- This is synthetic teaching data; conclusions are limited to the supplied simulation.",
        "",
    ])
    return "\n".join(lines)


def write_artifacts(data, output_dir):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    reports_dir = output_dir / "reports"
    charts_dir = output_dir / "charts"
    reports_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    def write_csv(path, fields, rows):
        with path.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def pearson(left, right):
        if len(left) < 2 or len(left) != len(right):
            return None
        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)
        numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
        left_norm = sum((x - left_mean) ** 2 for x in left) ** 0.5
        right_norm = sum((y - right_mean) ** 2 for y in right) ** 0.5
        if not left_norm or not right_norm:
            return None
        return numerator / (left_norm * right_norm)

    request_buckets = defaultdict(list)
    for row in data["requests"]:
        request_buckets[(five_minute_bucket(row["dt"]), row["region"])].append(row)
    timeline_rows = []
    for (timestamp, region), rows in sorted(request_buckets.items()):
        client_errors = sum(400 <= row["status"] < 500 for row in rows)
        server_errors = sum(row["status"] >= 500 for row in rows)
        timeline_rows.append({
            "timestamp": timestamp.isoformat(),
            "region": region,
            "request_count": len(rows),
            "4xx_count": client_errors,
            "5xx_count": server_errors,
            "5xx_rate_pct": round(server_errors / len(rows) * 100, 4),
            "p95_latency_ms": percentile([row["latency_ms"] for row in rows], 0.95),
        })
    write_csv(
        reports_dir / "error_timeline.csv",
        ["timestamp", "region", "request_count", "4xx_count", "5xx_count", "5xx_rate_pct", "p95_latency_ms"],
        timeline_rows,
    )
    dataset_5xx_rate = sum(row["status"] >= 500 for row in data["requests"]) / len(data["requests"]) * 100
    worst_intervals = sorted(
        (row for row in timeline_rows if int(row["request_count"]) >= 20),
        key=lambda row: row["5xx_rate_pct"], reverse=True,
    )[:10]
    worst_rows = [
        {"rank": rank, **row, "dataset_5xx_baseline_pct": round(dataset_5xx_rate, 4),
         "difference_from_dataset_baseline_pp": round(row["5xx_rate_pct"] - dataset_5xx_rate, 4)}
        for rank, row in enumerate(worst_intervals, 1)
    ]
    write_csv(reports_dir / "worst_intervals.csv",
              ["rank", "timestamp", "region", "request_count", "4xx_count", "5xx_count", "5xx_rate_pct",
               "p95_latency_ms", "dataset_5xx_baseline_pct", "difference_from_dataset_baseline_pp"], worst_rows)

    timeline_by_time = defaultdict(lambda: {"requests": 0, "4xx": 0, "5xx": 0})
    for row in timeline_rows:
        point = timeline_by_time[parse_timestamp(row["timestamp"])]
        point["requests"] += row["request_count"]
        point["4xx"] += row["4xx_count"]
        point["5xx"] += row["5xx_count"]
    times = sorted(timeline_by_time)
    fig, axis = plt.subplots(figsize=(12, 5))
    axis.plot(times, [timeline_by_time[t]["5xx"] for t in times], label="5xx requests", color="#b33b32")
    axis.plot(times, [timeline_by_time[t]["4xx"] for t in times], label="4xx requests", color="#d39b27")
    axis.set(title="ShopSphere request failures by five-minute interval", ylabel="Requests", xlabel="UTC")
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=times[0].tzinfo if times else None))
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(charts_dir / "error_timeline.png", dpi=140)
    plt.close(fig)

    service_groups = defaultdict(lambda: {"events": 0, "traces": set()})
    service_trace_sets = defaultdict(set)
    for row in data["logs"]:
        if row["error_code"]:
            key = (row["service"], row["region"], row["event"], row["level"], row["error_code"])
            service_groups[key]["events"] += 1
            service_groups[key]["traces"].add(row["trace_id"])
        if row["level"] == "ERROR":
            service_trace_sets[(row["service"], row["region"])].add(row["trace_id"])
    service_rows = [
        {"service": key[0], "region": key[1], "event": key[2], "level": key[3], "error_code": key[4],
         "log_events": values["events"], "unique_traces": len(values["traces"])}
        for key, values in sorted(service_groups.items())
    ]
    write_csv(reports_dir / "service_errors.csv",
              ["service", "region", "event", "level", "error_code", "log_events", "unique_traces"], service_rows)
    code_groups = defaultdict(lambda: {"events": 0, "traces": set()})
    for row in data["logs"]:
        if row["error_code"]:
            code_groups[row["error_code"]]["events"] += 1
            code_groups[row["error_code"]]["traces"].add(row["trace_id"])
    ranked_codes = sorted(code_groups.items(), key=lambda item: item[1]["events"], reverse=True)
    write_csv(reports_dir / "error_code_summary.csv",
              ["rank", "error_code", "log_events", "unique_traces"],
              [{"rank": rank, "error_code": code, "log_events": values["events"],
                "unique_traces": len(values["traces"])}
               for rank, (code, values) in enumerate(ranked_codes, 1)])

    services = sorted({key[0] for key in service_trace_sets})
    regions = sorted({key[1] for key in service_trace_sets})
    matrix = [[len(service_trace_sets[(service, region)]) for region in regions] for service in services]
    fig, axis = plt.subplots(figsize=(8, max(3, len(services) * 0.45)))
    image = axis.imshow(matrix, cmap="YlOrRd", aspect="auto")
    axis.set_xticks(range(len(regions)), regions)
    axis.set_yticks(range(len(services)), services)
    axis.set_title("Unique traces with ERROR-level logs")
    for service_index, service in enumerate(services):
        for region_index, region in enumerate(regions):
            axis.text(region_index, service_index, matrix[service_index][region_index], ha="center", va="center")
    fig.colorbar(image, ax=axis, label="Unique traces")
    fig.tight_layout()
    fig.savefig(charts_dir / "service_error_heatmap.png", dpi=140)
    plt.close(fig)

    failed_checkouts = []
    for code in ("PAYMENT_PROVIDER_TIMEOUT", "DB_POOL_EXHAUSTED", "NULL_CUSTOMER_CONTEXT"):
        matching = [row for row in data["requests"]
                    if row["endpoint"] == "/api/v1/checkout" and row["status"] >= 500 and row["error_code"] == code]
        if matching:
            failed_checkouts.append(min(matching, key=lambda row: row["dt"]))
    trace_lines = [
        "# Failed checkout trace samples", "",
        "Selected from request-level 5xx checkout rows; timestamps are UTC. Log records are ordered by timestamp. "
        "The dataset has a single distinct span_id, so parent_span_id cannot establish a reliable causal waterfall.", "",
    ]
    trace_plot_data = []
    for request in failed_checkouts:
        records = sorted(data["trace_logs"].get(request["trace_id"], []), key=lambda row: parse_timestamp(row["timestamp"]))
        trace_lines.extend([
            f"## {request['trace_id']}", "",
            f"Request: {request['timestamp']} | {request['region']} | {request['endpoint']} | HTTP {request['status']} | "
            f"{request['latency_ms']} ms | {request['error_code'] or 'no error code'}", "",
            "| Timestamp | Service | Event | Level | Error code | HTTP | Latency ms | Span | Parent span |",
            "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ])
        origin = min((parse_timestamp(row["timestamp"]) for row in records), default=request["dt"])
        for record in records:
            timestamp = parse_timestamp(record["timestamp"])
            trace_lines.append(
                f"| {record['timestamp']} | {record['service']} | {record['event']} | {record['level']} | "
                f"{record['error_code']} | {record['http_status']} | {record['latency_ms']} | {record['span_id']} | {record['parent_span_id']} |"
            )
            trace_plot_data.append((request["trace_id"], record, (timestamp - origin).total_seconds() * 1000))
        if not records:
            trace_lines.append("No matching application log records.")
        trace_lines.append("")
    (reports_dir / "checkout_traces.md").write_text("\n".join(trace_lines), encoding="utf-8")

    fig, axis = plt.subplots(figsize=(11, max(3, len(trace_plot_data) * 0.3)))
    labels = [f"{trace_id[:8]} {record['service']}:{record['event']}" for trace_id, record, _ in trace_plot_data]
    starts = [offset for _, _, offset in trace_plot_data]
    widths = [max(float(record["latency_ms"] or 1), 1) for _, record, _ in trace_plot_data]
    axis.barh(range(len(trace_plot_data)), widths, left=starts, color="#397b73")
    axis.set_yticks(range(len(labels)), labels, fontsize=7)
    axis.invert_yaxis()
    axis.set(title="Failed checkout log events (relative timestamp and reported latency)", xlabel="Milliseconds from first event")
    axis.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(charts_dir / "checkout_trace.png", dpi=140)
    plt.close(fig)

    metric_points = defaultdict(dict)
    for row in data["metrics"]:
        timestamp = five_minute_bucket(parse_timestamp(row["timestamp"]))
        metric_points[(timestamp, row["region"])][row["metric"]] = float(row["value"])
    metric_fields = sorted({metric for point in metric_points.values() for metric in point})
    metric_rows = []
    aligned_points = []
    for key in sorted(set(request_buckets) | set(metric_points)):
        timestamp, region = key
        requests_at_time = request_buckets.get(key, [])
        failures = sum(row["status"] >= 500 for row in requests_at_time)
        point = metric_points.get(key, {})
        joined = {"timestamp": timestamp.isoformat(), "region": region,
                  "request_count": len(requests_at_time), "5xx_count": failures,
                  "5xx_rate_pct": round(failures / len(requests_at_time) * 100, 4) if requests_at_time else None}
        joined.update({metric: point.get(metric) for metric in metric_fields})
        metric_rows.append(joined)
        if requests_at_time:
            aligned_points.append(joined)
    metric_csv_fields = ["timestamp", "region", "request_count", "5xx_count", "5xx_rate_pct"] + metric_fields
    write_csv(reports_dir / "metric_correlation.csv", metric_csv_fields, metric_rows)

    correlations = []
    for metric in metric_fields:
        pairs = [(row["5xx_rate_pct"], row[metric]) for row in aligned_points if row["5xx_rate_pct"] is not None and row[metric] is not None]
        coefficient = pearson([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        correlations.append((metric, coefficient, len(pairs)))
    correlation_lines = [
        "# Request and infrastructure metric correlation", "",
        "Requests and metrics are aligned by region and floored five-minute UTC timestamp. Pearson coefficients are descriptive only; "
        "shared time trends, rollout timing, and other confounders prevent causal claims.", "",
        "| Metric | Pearson r vs 5xx rate | Aligned samples |", "| --- | ---: | ---: |",
    ]
    for metric, coefficient, count in correlations:
        correlation_lines.append(f"| {metric} | {coefficient:.3f} | {count} |" if coefficient is not None else f"| {metric} | n/a | {count} |")
    (reports_dir / "metric_correlation.md").write_text("\n".join(correlation_lines) + "\n", encoding="utf-8")

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    plot_metrics = [("5xx_rate_pct", "5xx rate (%)"), ("provider_p95_ms", "Provider p95 (ms)"),
                    ("db_pool_active", "DB pool active connections"), ("queue_lag_messages", "Notification queue lag")]
    for axis, (metric, label) in zip(axes.flat, plot_metrics):
        for region in regions:
            points = sorted((parse_timestamp(row["timestamp"]), row[metric]) for row in aligned_points
                            if row["region"] == region and row.get(metric) is not None)
            if points:
                axis.plot([point[0] for point in points], [point[1] for point in points], label=region)
        axis.set_ylabel(label)
        axis.grid(alpha=0.2)
        axis.legend(fontsize=7)
    axes[0, 0].set_title("Requests and infrastructure")
    for axis in axes[1, :]:
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=times[0].tzinfo if times else None))
    fig.tight_layout()
    fig.savefig(charts_dir / "metric_correlation.png", dpi=140)
    plt.close(fig)

    security_events = [row for row in data["logs"] if row["event"] == "auth.login.failed"]
    security_sources = defaultdict(lambda: {"events": 0, "users": set(), "agents": Counter(), "times": []})
    security_buckets = Counter()
    for row in security_events:
        try:
            details = json.loads(row["details"] or "{}")
        except json.JSONDecodeError:
            details = {}
        source = details.get("source_ip", "(missing)")
        group = security_sources[source]
        group["events"] += 1
        if row["user_id"]:
            group["users"].add(row["user_id"])
        group["agents"][details.get("user_agent", "(missing)")] += 1
        event_time = parse_timestamp(row["timestamp"])
        group["times"].append(event_time)
        security_buckets[five_minute_bucket(event_time)] += 1
    security_lines = ["# Authentication anomaly findings", ""]
    if not security_sources:
        security_lines.append("No auth.login.failed events found.")
    for source, group in sorted(security_sources.items(), key=lambda item: item[1]["events"], reverse=True):
        security_lines.extend([
            f"- Source `{source}`: {group['events']} failed-login events, {len(group['users'])} distinct non-empty user IDs, "
            f"{min(group['times']).isoformat()} to {max(group['times']).isoformat()} UTC.",
            f"  User agents: {dict(group['agents'].most_common())}.",
        ])
    security_lines.extend(["", "Treat this as a signal for targeted rate limits and account review; a source IP alone is not proof of malicious intent."])
    if security_buckets:
        peak_time, peak_count = max(security_buckets.items(), key=lambda item: item[1])
        security_lines.insert(-2, f"Peak five-minute window: {peak_time.isoformat()} UTC ({peak_count} failed-login events).")
    (reports_dir / "security_anomalies.md").write_text("\n".join(security_lines) + "\n", encoding="utf-8")

    deploy_groups = defaultdict(lambda: {"requests": 0, "5xx": 0, "null_context": 0})
    for row in data["requests"]:
        key = (row["region"], row["endpoint"], row["version"])
        deploy_groups[key]["requests"] += 1
        deploy_groups[key]["5xx"] += row["status"] >= 500
        deploy_groups[key]["null_context"] += row["error_code"] == "NULL_CUSTOMER_CONTEXT"
    deployment_rows = [
        {"region": key[0], "endpoint": key[1], "version": key[2], "requests": value["requests"],
         "5xx_count": value["5xx"], "5xx_rate_pct": round(value["5xx"] / value["requests"] * 100, 4),
         "null_customer_context": value["null_context"]}
        for key, value in sorted(deploy_groups.items())
    ]
    write_csv(reports_dir / "deployment_comparison.csv",
              ["region", "endpoint", "version", "requests", "5xx_count", "5xx_rate_pct", "null_customer_context"],
              deployment_rows)

    total = len(data["requests"])
    server_errors = sum(row["status"] >= 500 for row in data["requests"])
    regional_lines = [
        f"- `{region}`: {counts['5xx']:,}/{counts['total']:,} 5xx requests ({counts['5xx'] / counts['total'] * 100:.2f}%)."
        for region, counts in sorted(data["regional_requests"].items())
    ]
    timeline_codes = ("PAYMENT_PROVIDER_TIMEOUT", "INVENTORY_DEADLOCK", "DB_POOL_EXHAUSTED",
                      "NULL_CUSTOMER_CONTEXT", "QUEUE_CONSUMER_LAG")
    timeline_lines = []
    for code in timeline_codes:
        signature = data["failure_signatures"].get(code)
        if signature:
            timestamps = signature["timestamps"]
            timeline_lines.append(f"- {min(timestamps).isoformat()} to {max(timestamps).isoformat()}: `{code}` "
                                  f"({len(signature['traces'])} unique traces).")
    trace_reference_lines = [
        f"- `{row['trace_id']}` at {row['timestamp']}: `{row['error_code']}` ({row['endpoint']}, HTTP {row['status']})."
        for row in failed_checkouts
    ]
    deployment_evidence = [
        f"- `{row['region']}` `{row['endpoint']}` `{row['version']}`: {row['5xx_count']}/{row['requests']} 5xx "
        f"({row['5xx_rate_pct']:.2f}%); NULL_CUSTOMER_CONTEXT={row['null_customer_context']}."
        for row in deployment_rows if row["version"] == "v2.8.0"
    ]
    queue_events = [row for row in data["logs"] if row["error_code"] == "QUEUE_CONSUMER_LAG"]
    signature_lines = []
    for code, signature in sorted(data["failure_signatures"].items()):
        stamps = signature["timestamps"]
        signature_lines.append(f"- `{code}`: {min(stamps).isoformat()} to {max(stamps).isoformat()}, "
                               f"{len(signature['traces'])} unique traces ({signature['events']} log events).")
    peaks = defaultdict(lambda: (float("-inf"), ""))
    for row in data["metrics"]:
        key = (row["region"], row["metric"])
        value = float(row["value"])
        if value > peaks[key][0]:
            peaks[key] = (value, row["timestamp"])
    peak_lines = [f"- `{region}` {metric}: {value:g} {next(row['unit'] for row in data['metrics'] if row['region'] == region and row['metric'] == metric)} at {stamp}."
                  for (region, metric), (value, stamp) in sorted(peaks.items())]
    rca = [
        "# ShopSphere Incident RCA", "",
        "## Executive summary", "",
        f"The supplied synthetic dataset contains {total:,} requests; {server_errors:,} returned 5xx "
        f"({server_errors / total * 100:.2f}%). Request-level rows are the denominator; service log lines are not counted as separate customer failures.", "",
        "## Customer impact", "", *regional_lines, "",
        "## Incident timeline (UTC)", "", *timeline_lines, "",
        "Highest-rate intervals (minimum 20 requests), compared with the full-dataset 5xx baseline of "
        f"{dataset_5xx_rate:.2f}%, are ranked in `worst_intervals.csv`.", "",
        "## Verified evidence", "",
        "### Checkout trace samples", "", *trace_reference_lines,
        "Full timestamp-ordered records are in `checkout_traces.md`; parent-child ordering is uncertain because span IDs are not unique.", "",
        "### Failure signatures", "", *signature_lines, "",
        "### Infrastructure observations", "", *peak_lines, "",
        "### Authentication", "", *security_lines[2:], "",
        "### Deployment", "",
        *deployment_evidence, "",
        "Version and rollout time are coupled in this dataset, so these route/region rates support a regression hypothesis but do not isolate a causal version effect.", "",
        "### Notifications", "",
        f"Observed `QUEUE_CONSUMER_LAG` records: {len(queue_events)}; HTTP 200 on "
        f"{sum(row['http_status'] == '200' for row in queue_events)} records. This indicates asynchronous delivery lag, not a failed checkout request by itself.", "",
        "## Assessment and response", "",
        "Payment-provider timeouts, inventory conflicts, database pool exhaustion, and the post-rollout null-context signature are distinct observed failure modes. "
        "The joined metrics and checkout traces are corroborating evidence, not proof of causation; trace ordering is timestamp-based because span identifiers are not unique.", "",
        "Prioritize provider circuit breaking with idempotent bounded retries, inventory lock/deadlock review, database pool/backpressure investigation, and a canary/rollback evaluation for the null-context regression. "
        "For authentication, use targeted rate limiting and account review rather than blanket blocking. Scale notification consumers and validate delivery independently from checkout success.", "",
        "| Owner | Immediate mitigation | Permanent follow-up | Validation |",
        "| --- | --- | --- | --- |",
        "| Payments / SRE | Bound retries and enable a provider circuit breaker. | Add idempotency and dependency-timeout budgets. | Provider timeouts and checkout 5xx recover without duplicate charges. |",
        "| Inventory / Database | Apply backpressure and inspect pool saturation. | Fix transaction lock ordering and pool lifecycle. | Deadlocks and pool waits stay within agreed load-test limits. |",
        "| Release / API | Canary rollback or disable the affected checkout feature flag. | Add null-context input validation and rollout guardrails. | Error signature disappears and route-adjusted 5xx stays near baseline. |",
        "| Security | Rate-limit the observed login burst and review affected accounts. | Add risk-based throttles and credential-stuffing alerts. | Abuse declines without a rise in legitimate login failures. |",
        "| Messaging | Scale consumers and inspect retries / dead-letter queues. | Add oldest-message-age SLO and autoscaling. | Queue lag clears while successful order volume remains stable. |", "",
        "## Validation and limitations", "",
        "- 401 and 409 are separated from 5xx; they can still be security or inventory-impact signals.",
        "- Metrics are sampled every five minutes; correlation is not causation.",
        "- The generated trace samples do not establish parent-child causality because the source has only one distinct span_id value.",
        "- The dataset is a synthetic teaching simulation; validate mitigations with production telemetry before action.", "",
    ]
    (reports_dir / "INCIDENT_RCA.md").write_text("\n".join(rca), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=BASE_DIR)
    parser.add_argument("--report", type=Path, help="Write the Markdown report to this path")
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR, help="Directory for reports/ and charts/")
    args = parser.parse_args()
    data = analyze(args.data_dir)
    report = render_report(data)
    write_artifacts(data, args.output_dir)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
        print(f"Wrote report: {args.report}")
    else:
        print(f"Wrote lab reports and charts under: {args.output_dir}")


if __name__ == "__main__":
    main()
