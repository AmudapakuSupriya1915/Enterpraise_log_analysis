import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timezone

from analysis import BASE_DIR, analyze, five_minute_bucket, percentile, render_report, write_artifacts


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = analyze(BASE_DIR)

    def test_percentile_handles_empty_and_sorted_values(self):
        self.assertIsNone(percentile([], 0.5))
        self.assertEqual(percentile([9, 1, 5], 0.5), 5)

    def test_five_minute_bucket_preserves_timezone(self):
        timestamp = datetime(2026, 11, 18, 11, 48, 37, tzinfo=timezone.utc)
        self.assertEqual(
            five_minute_bucket(timestamp),
            datetime(2026, 11, 18, 11, 45, tzinfo=timezone.utc),
        )

    def test_request_level_counts_match_dataset(self):
        self.assertEqual(len(self.data["requests"]), 12000)
        self.assertEqual(self.data["status_counts"][200], 10265)
        self.assertEqual(
            sum(count for status, count in self.data["status_counts"].items() if status >= 500),
            1147,
        )
        trace_ids = [row["trace_id"] for row in self.data["requests"]]
        self.assertEqual(len(trace_ids), len(set(trace_ids)))

    def test_report_distinguishes_requests_from_log_events(self):
        report = render_report(self.data)
        self.assertIn("5xx requests: 1,147 (9.56%)", report)
        self.assertIn("These are event counts", report)
        self.assertIn("Failure signature windows", report)
        self.assertIn("not a time-controlled causal comparison", report)
        self.assertIn("Timestamp UTC", report)
        self.assertIn("1 distinct `span_id` value(s)", report)

    def test_generated_artifacts_keep_request_counts_and_real_trace_ids(self):
        with TemporaryDirectory() as directory:
            write_artifacts(self.data, directory)
            reports = Path(directory) / "reports"
            with (reports / "error_timeline.csv").open(newline="", encoding="utf-8") as source:
                timeline = list(csv.DictReader(source))
            self.assertEqual(sum(int(row["request_count"]) for row in timeline), 12000)
            self.assertEqual(sum(int(row["5xx_count"]) for row in timeline), 1147)

            with (reports / "metric_correlation.csv").open(newline="", encoding="utf-8") as source:
                metric_rows = list(csv.DictReader(source))
            self.assertEqual(len(metric_rows), 144)
            self.assertEqual(sum(int(row["request_count"]) for row in metric_rows), 12000)

            with (reports / "worst_intervals.csv").open(newline="", encoding="utf-8") as source:
                worst_intervals = list(csv.DictReader(source))
            self.assertEqual(len(worst_intervals), 10)
            self.assertTrue(all(float(row["difference_from_dataset_baseline_pp"]) >= 0 for row in worst_intervals))

            with (reports / "error_code_summary.csv").open(newline="", encoding="utf-8") as source:
                ranked_codes = list(csv.DictReader(source))
            self.assertEqual(ranked_codes[0]["error_code"], "NULL_CUSTOMER_CONTEXT")
            self.assertGreater(int(ranked_codes[0]["unique_traces"]), 0)

            traces = (reports / "checkout_traces.md").read_text(encoding="utf-8")
            self.assertEqual(traces.count("\n## "), 3)
            for code in ("PAYMENT_PROVIDER_TIMEOUT", "DB_POOL_EXHAUSTED", "NULL_CUSTOMER_CONTEXT"):
                self.assertIn(code, traces)
            self.assertTrue((Path(directory) / "charts" / "error_timeline.png").is_file())


if __name__ == "__main__":
    unittest.main()