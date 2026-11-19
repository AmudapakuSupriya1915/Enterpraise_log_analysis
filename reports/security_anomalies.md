# Authentication anomaly findings

- Source `198.51.100.77`: 201 failed-login events, 195 distinct non-empty user IDs, 2026-11-18T09:55:02.496000+00:00 to 2026-11-18T10:29:46.695000+00:00 UTC.
  User agents: {'python-requests/2.32': 201}.
Peak five-minute window: 2026-11-18T09:55:00+00:00 UTC (35 failed-login events).

Treat this as a signal for targeted rate limits and account review; a source IP alone is not proof of malicious intent.
