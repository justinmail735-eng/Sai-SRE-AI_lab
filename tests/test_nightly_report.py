import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nightly_report.py"


def run_report(payload: dict, *args: str):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(payload, tmp)
        tmp_path = tmp.name
    cmd = [sys.executable, str(SCRIPT), "--input", tmp_path, *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def healthy_payload():
    return {
        "policy": {
            "min_requests": 100,
            "warning_burn_rate": 1.0,
            "critical_burn_rate": 2.0,
        },
        "services": [
            {
                "name": "payments-api",
                "owner": "sre@example.com",
                "target_availability": 0.999,
                "windows": [
                    {"label": "5m", "minutes": 5, "total_requests": 10000, "error_requests": 1},
                    {"label": "1h", "minutes": 60, "total_requests": 100000, "error_requests": 5},
                ],
            }
        ],
    }


def warning_payload():
    """5m window at ~1.5x burn (warning), 1h at ~1x (border)."""
    payload = healthy_payload()
    # 0.999 target → budget=0.001; 1.5% error rate → burn=15x... let's be precise:
    # For warning: burn >= 1.0x, i.e. error_rate > 0.1% = 0.001
    # 200/10000 = 2% → burn = 0.02 / 0.001 = 20x (critical — too high)
    # Use 20 errors / 10000 = 0.2% → burn = 0.002/0.001 = 2x (critical).
    # Use 15 errors / 10000 = 0.15% → burn = 0.0015/0.001 = 1.5x (warning).
    payload["services"][0]["windows"][0]["error_requests"] = 15
    # Keep 1h healthy: 5 errors is fine.
    return payload


def critical_payload():
    """5m window above critical threshold (2x burn)."""
    payload = healthy_payload()
    # 30/10000 = 0.3% → burn = 0.003/0.001 = 3x (critical)
    payload["services"][0]["windows"][0]["error_requests"] = 30
    return payload


def insufficient_data_payload():
    payload = healthy_payload()
    payload["services"][0]["windows"][0]["total_requests"] = 50
    payload["services"][0]["windows"][0]["error_requests"] = 0
    return payload


class NightlyReportTextTests(unittest.TestCase):
    def test_healthy_run_exits_zero(self):
        result = run_report(healthy_payload())
        self.assertEqual(result.returncode, 0)

    def test_text_output_contains_header(self):
        result = run_report(healthy_payload())
        self.assertIn("Nightly SLO Report", result.stdout)

    def test_text_output_shows_service_name(self):
        result = run_report(healthy_payload())
        self.assertIn("payments-api", result.stdout)

    def test_text_output_shows_summary_line(self):
        result = run_report(healthy_payload())
        self.assertIn("SUMMARY:", result.stdout)
        self.assertIn("1 service(s)", result.stdout)

    def test_text_output_shows_window_details(self):
        result = run_report(healthy_payload())
        self.assertIn("5m", result.stdout)
        self.assertIn("1h", result.stdout)
        self.assertIn("burn=", result.stdout)

    def test_critical_state_exits_nonzero(self):
        result = run_report(critical_payload())
        self.assertEqual(result.returncode, 1)

    def test_critical_state_shows_alerts_section(self):
        result = run_report(critical_payload())
        self.assertIn("ALERTS:", result.stdout)

    def test_warning_default_exits_zero(self):
        result = run_report(warning_payload())
        self.assertEqual(result.returncode, 0)

    def test_fail_on_warning_exits_nonzero_for_warning(self):
        result = run_report(warning_payload(), "--fail-on-warning")
        self.assertEqual(result.returncode, 1)

    def test_insufficient_data_default_exits_zero(self):
        result = run_report(insufficient_data_payload())
        self.assertEqual(result.returncode, 0)

    def test_fail_on_insufficient_data_exits_nonzero(self):
        result = run_report(insufficient_data_payload(), "--fail-on-insufficient-data")
        self.assertEqual(result.returncode, 1)

    def test_invalid_policy_exits_two(self):
        bad = {"policy": {}, "services": []}
        result = run_report(bad)
        self.assertEqual(result.returncode, 2)
        self.assertIn("nightly-report: failed to evaluate policy", result.stderr)

    def test_multi_service_summary_counts_both(self):
        payload = healthy_payload()
        payload["services"].append({
            "name": "checkout-worker",
            "owner": "platform@example.com",
            "target_availability": 0.995,
            "windows": [
                {"label": "5m", "minutes": 5, "total_requests": 5000, "error_requests": 1},
                {"label": "1h", "minutes": 60, "total_requests": 50000, "error_requests": 10},
            ],
        })
        result = run_report(payload)
        self.assertEqual(result.returncode, 0)
        self.assertIn("2 service(s)", result.stdout)
        self.assertIn("checkout-worker", result.stdout)


class NightlyReportJsonTests(unittest.TestCase):
    def test_json_output_is_valid(self):
        result = run_report(healthy_payload(), "--output", "json")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIn("generated_at", data)
        self.assertIn("services", data)
        self.assertIn("summary", data)

    def test_json_services_have_expected_keys(self):
        result = run_report(healthy_payload(), "--output", "json")
        data = json.loads(result.stdout)
        svc = data["services"][0]
        for key in ("name", "owner", "target", "budget", "state", "windows"):
            self.assertIn(key, svc)

    def test_json_windows_have_expected_keys(self):
        result = run_report(healthy_payload(), "--output", "json")
        data = json.loads(result.stdout)
        window = data["services"][0]["windows"][0]
        for key in ("label", "minutes", "total_requests", "error_requests",
                    "availability", "burn_rate", "budget_requests_remaining", "state"):
            self.assertIn(key, window)

    def test_json_summary_counts_pass(self):
        result = run_report(healthy_payload(), "--output", "json")
        data = json.loads(result.stdout)
        self.assertEqual(data["summary"].get("pass"), 1)

    def test_json_critical_exits_nonzero(self):
        result = run_report(critical_payload(), "--output", "json")
        self.assertEqual(result.returncode, 1)

    def test_json_critical_summary_reflects_state(self):
        result = run_report(critical_payload(), "--output", "json")
        data = json.loads(result.stdout)
        self.assertEqual(data["services"][0]["state"], "critical")


class NightlyReportMarkdownTests(unittest.TestCase):
    def test_markdown_output_has_h1_header(self):
        result = run_report(healthy_payload(), "--output", "markdown")
        self.assertEqual(result.returncode, 0)
        self.assertIn("# Nightly SLO Report", result.stdout)

    def test_markdown_output_has_service_table(self):
        result = run_report(healthy_payload(), "--output", "markdown")
        self.assertIn("| Service | Owner |", result.stdout)
        self.assertIn("payments-api", result.stdout)

    def test_markdown_output_has_summary_section(self):
        result = run_report(healthy_payload(), "--output", "markdown")
        self.assertIn("## Summary", result.stdout)
        self.assertIn("**pass**", result.stdout)

    def test_markdown_shows_alerts_section_for_critical(self):
        result = run_report(critical_payload(), "--output", "markdown")
        self.assertIn("## Alerts", result.stdout)
        self.assertIn("CRITICAL", result.stdout)

    def test_markdown_no_alerts_section_when_healthy(self):
        result = run_report(healthy_payload(), "--output", "markdown")
        self.assertNotIn("## Alerts", result.stdout)

    def test_markdown_generated_at_timestamp_present(self):
        result = run_report(healthy_payload(), "--output", "markdown")
        self.assertIn("Generated:", result.stdout)


if __name__ == "__main__":
    unittest.main()
