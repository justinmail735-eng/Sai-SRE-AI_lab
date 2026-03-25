import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "slo_check.py"


def run_slo(payload: dict, *args: str):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(payload, tmp)
        tmp_path = tmp.name

    cmd = [sys.executable, str(SCRIPT), "--input", tmp_path, *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def base_payload():
    return {
        "policy": {
            "min_requests": 100,
            "warning_burn_rate": 1.0,
            "critical_burn_rate": 2.0,
        },
        "services": [
            {
                "name": "api",
                "owner": "platform@sai-lab.local",
                "target_availability": 0.999,
                "windows": [
                    {"label": "5m", "minutes": 5, "total_requests": 10000, "error_requests": 2},
                    {"label": "1h", "minutes": 60, "total_requests": 100000, "error_requests": 10},
                ],
            }
        ],
    }


class SloCheckTests(unittest.TestCase):
    def test_json_output_is_machine_readable(self):
        result = run_slo(base_payload(), "--output", "json")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed[0]["name"], "api")
        self.assertEqual(parsed[0]["owner"], "platform@sai-lab.local")
        self.assertEqual(parsed[0]["windows"][0]["label"], "5m")

    def test_fail_on_warning_returns_nonzero(self):
        payload = base_payload()
        payload["services"][0]["windows"][0]["error_requests"] = 1
        payload["services"][0]["windows"][1]["error_requests"] = 100

        normal = run_slo(payload)
        strict = run_slo(payload, "--fail-on-warning")

        self.assertEqual(normal.returncode, 0)
        self.assertEqual(strict.returncode, 1)

    def test_duplicate_window_labels_fail_validation(self):
        payload = base_payload()
        payload["services"][0]["windows"][1]["label"] = "5m"

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate window label", result.stderr)

    def test_fail_on_insufficient_data_returns_nonzero(self):
        payload = base_payload()
        payload["services"][0]["windows"][0]["total_requests"] = 50
        payload["services"][0]["windows"][0]["error_requests"] = 0

        normal = run_slo(payload)
        strict = run_slo(payload, "--fail-on-insufficient-data")

        self.assertEqual(normal.returncode, 0)
        self.assertEqual(strict.returncode, 1)

    def test_require_owner_fails_when_missing(self):
        payload = base_payload()
        del payload["services"][0]["owner"]

        result = run_slo(payload, "--require-owner")

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing required non-empty owner", result.stderr)

    def test_service_state_is_insufficient_data_when_any_window_lacks_volume(self):
        payload = base_payload()
        payload["services"][0]["windows"][0]["total_requests"] = 50
        payload["services"][0]["windows"][0]["error_requests"] = 0

        result = run_slo(payload, "--output", "json")

        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed[0]["state"], "insufficient-data")

    def test_required_windows_policy_rejects_missing_label(self):
        payload = base_payload()
        payload["policy"]["required_windows"] = ["5m", "6h"]

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing required windows: 6h", result.stderr)

    def test_owner_email_domain_policy_rejects_mismatch(self):
        payload = base_payload()
        payload["policy"]["owner_email_domain"] = "example.com"

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("does not match required domain 'example.com'", result.stderr)

    def test_owner_email_domain_policy_accepts_matching_domain(self):
        payload = base_payload()
        payload["policy"]["owner_email_domain"] = "sai-lab.local"

        result = run_slo(payload)

        self.assertEqual(result.returncode, 0)

    def test_service_with_no_windows_fails_validation(self):
        payload = base_payload()
        payload["services"][0]["windows"] = []

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("must define at least one window", result.stderr)

    def test_window_burn_rate_override_can_raise_window_to_critical(self):
        payload = base_payload()
        payload["services"][0]["windows"][0]["error_requests"] = 12

        baseline = run_slo(payload, "--output", "json")

        payload["policy"]["window_burn_rate_overrides"] = {
            "5m": {"warning_burn_rate": 1.0, "critical_burn_rate": 1.1}
        }
        overridden = run_slo(payload, "--output", "json")

        self.assertEqual(baseline.returncode, 0)
        base_parsed = json.loads(baseline.stdout)
        self.assertEqual(base_parsed[0]["windows"][0]["state"], "warning")

        parsed = json.loads(overridden.stdout)
        self.assertEqual(parsed[0]["windows"][0]["state"], "critical")
        self.assertEqual(parsed[0]["state"], "critical")

    def test_window_burn_rate_override_validation_rejects_invalid_thresholds(self):
        payload = base_payload()
        payload["policy"]["window_burn_rate_overrides"] = {
            "5m": {"warning_burn_rate": 4.0, "critical_burn_rate": 3.0}
        }

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("warning_burn_rate cannot exceed critical_burn_rate", result.stderr)

    def test_min_requests_override_can_mark_specific_window_insufficient_data(self):
        payload = base_payload()
        payload["policy"]["min_requests_overrides"] = {"1h": 120000}

        result = run_slo(payload, "--output", "json")

        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        by_label = {w["label"]: w for w in parsed[0]["windows"]}
        self.assertEqual(by_label["5m"]["state"], "pass")
        self.assertEqual(by_label["1h"]["state"], "insufficient-data")
        self.assertEqual(parsed[0]["state"], "insufficient-data")

    def test_min_requests_override_validation_rejects_negative_values(self):
        payload = base_payload()
        payload["policy"]["min_requests_overrides"] = {"5m": -1}

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("policy.min_requests_overrides['5m'] must be >= 0", result.stderr)

    def test_window_minutes_policy_rejects_unexpected_minutes_for_label(self):
        payload = base_payload()
        payload["policy"]["window_minutes"] = {"5m": 5, "1h": 60}
        payload["services"][0]["windows"][1]["minutes"] = 55

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("window '1h' has minutes=55, expected 60", result.stderr)

    def test_window_minutes_policy_accepts_matching_minutes(self):
        payload = base_payload()
        payload["policy"]["window_minutes"] = {"5m": 5, "1h": 60}

        result = run_slo(payload)

        self.assertEqual(result.returncode, 0)

    def test_window_minutes_policy_validation_rejects_non_positive_values(self):
        payload = base_payload()
        payload["policy"]["window_minutes"] = {"5m": 0}

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("policy.window_minutes['5m'] must be > 0", result.stderr)

    def test_max_insufficient_windows_allows_limited_insufficient_data(self):
        payload = base_payload()
        payload["services"][0]["windows"][0]["total_requests"] = 50
        payload["services"][0]["windows"][0]["error_requests"] = 0

        baseline = run_slo(payload, "--output", "json")

        payload["policy"]["max_insufficient_windows"] = 1
        tolerated = run_slo(payload, "--output", "json")

        self.assertEqual(baseline.returncode, 0)
        self.assertEqual(tolerated.returncode, 0)

        baseline_parsed = json.loads(baseline.stdout)
        tolerated_parsed = json.loads(tolerated.stdout)

        self.assertEqual(baseline_parsed[0]["state"], "insufficient-data")
        self.assertEqual(tolerated_parsed[0]["state"], "pass")

    def test_max_insufficient_windows_validation_rejects_negative_values(self):
        payload = base_payload()
        payload["policy"]["max_insufficient_windows"] = -1

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("policy.max_insufficient_windows must be >= 0", result.stderr)

    def test_min_requests_overrides_rejects_unknown_window_labels(self):
        payload = base_payload()
        payload["policy"]["min_requests_overrides"] = {"6h": 1000}

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("policy.min_requests_overrides contains unknown window labels: 6h", result.stderr)

    def test_window_burn_rate_overrides_rejects_unknown_window_labels(self):
        payload = base_payload()
        payload["policy"]["window_burn_rate_overrides"] = {
            "6h": {"warning_burn_rate": 1.0, "critical_burn_rate": 2.0}
        }

        result = run_slo(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("policy.window_burn_rate_overrides contains unknown window labels: 6h", result.stderr)

    def test_service_regex_filters_output_to_matching_services(self):
        payload = base_payload()
        payload["services"].append({
            "name": "worker",
            "owner": "batch@sai-lab.local",
            "target_availability": 0.999,
            "windows": [
                {"label": "5m", "minutes": 5, "total_requests": 20000, "error_requests": 1},
            ],
        })

        result = run_slo(payload, "--output", "json", "--service-regex", "^work")

        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "worker")

    def test_service_regex_rejects_invalid_patterns(self):
        result = run_slo(base_payload(), "--service-regex", "*(invalid")

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid --service-regex pattern", result.stderr)

    def test_service_regex_rejects_when_no_services_match(self):
        result = run_slo(base_payload(), "--service-regex", "^does-not-exist$")

        self.assertEqual(result.returncode, 2)
        self.assertIn("matched no services", result.stderr)

    def test_owner_regex_filters_output_to_matching_owners(self):
        payload = base_payload()
        payload["services"].append({
            "name": "worker",
            "owner": "batch@sai-lab.local",
            "target_availability": 0.999,
            "windows": [
                {"label": "5m", "minutes": 5, "total_requests": 20000, "error_requests": 1},
            ],
        })

        result = run_slo(payload, "--output", "json", "--owner-regex", "^batch@")

        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "worker")

    def test_owner_regex_rejects_invalid_patterns(self):
        result = run_slo(base_payload(), "--owner-regex", "*(invalid")

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid --owner-regex pattern", result.stderr)

    def test_owner_regex_rejects_when_no_services_match(self):
        result = run_slo(base_payload(), "--owner-regex", "^does-not-exist$")

        self.assertEqual(result.returncode, 2)
        self.assertIn("matched no services", result.stderr)

    # ------------------------------------------------------------------
    # --only-state filtering
    # ------------------------------------------------------------------

    def test_only_state_filters_to_matching_service_states(self):
        payload = base_payload()
        payload["services"].append({
            "name": "critical-worker",
            "owner": "batch@sai-lab.local",
            "target_availability": 0.999,
            "windows": [
                {"label": "5m", "minutes": 5, "total_requests": 10000, "error_requests": 300},
            ],
        })

        result = run_slo(payload, "--output", "json", "--only-state", "critical")

        self.assertEqual(result.returncode, 1)
        parsed = json.loads(result.stdout)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "critical-worker")
        self.assertEqual(parsed[0]["state"], "critical")

    def test_only_state_rejects_invalid_state_values(self):
        result = run_slo(base_payload(), "--only-state", "critical,banana")

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid --only-state value(s): banana", result.stderr)

    def test_only_state_rejects_when_no_services_match(self):
        result = run_slo(base_payload(), "--only-state", "critical")

        self.assertEqual(result.returncode, 2)
        self.assertIn("matched no services", result.stderr)

    # ------------------------------------------------------------------
    # budget_requests_remaining
    # ------------------------------------------------------------------

    def test_json_output_includes_budget_requests_remaining(self):
        result = run_slo(base_payload(), "--output", "json")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        for window in parsed[0]["windows"]:
            self.assertIn("budget_requests_remaining", window)

    def test_budget_requests_remaining_is_correct_for_healthy_window(self):
        # 10000 total, 2 errors, budget=0.001 → budget_requests_remaining = int(10000*0.001 - 2) = 8
        result = run_slo(base_payload(), "--output", "json")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        by_label = {w["label"]: w for w in parsed[0]["windows"]}
        self.assertEqual(by_label["5m"]["budget_requests_remaining"], 8)

    def test_budget_requests_remaining_is_zero_when_over_budget(self):
        payload = base_payload()
        # 10000 total, 15 errors → error_rate=0.0015, budget=0.001 → over budget → clamp to 0
        payload["services"][0]["windows"][0]["error_requests"] = 15
        result = run_slo(payload, "--output", "json")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        by_label = {w["label"]: w for w in parsed[0]["windows"]}
        self.assertEqual(by_label["5m"]["budget_requests_remaining"], 0)

    def test_budget_requests_remaining_is_zero_for_zero_traffic_window(self):
        payload = base_payload()
        payload["services"][0]["windows"][0]["total_requests"] = 0
        payload["services"][0]["windows"][0]["error_requests"] = 0
        payload["policy"]["min_requests"] = 0
        result = run_slo(payload, "--output", "json")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        by_label = {w["label"]: w for w in parsed[0]["windows"]}
        self.assertEqual(by_label["5m"]["budget_requests_remaining"], 0)
        self.assertEqual(by_label["5m"]["state"], "pass")

    def test_text_output_includes_budget_remaining(self):
        result = run_slo(base_payload())
        self.assertEqual(result.returncode, 0)
        self.assertIn("budget_remaining=", result.stdout)

    # ------------------------------------------------------------------
    # Summary line in text render
    # ------------------------------------------------------------------

    def test_text_output_includes_summary_line(self):
        result = run_slo(base_payload())
        self.assertEqual(result.returncode, 0)
        self.assertIn("SUMMARY:", result.stdout)
        self.assertIn("1 service(s)", result.stdout)

    def test_summary_line_counts_multiple_services(self):
        payload = base_payload()
        # Add a second service that is in critical state
        payload["services"].append({
            "name": "slow-service",
            "owner": "infra@sai-lab.local",
            "target_availability": 0.999,
            "windows": [
                {"label": "5m", "minutes": 5, "total_requests": 10000, "error_requests": 300},
            ],
        })
        result = run_slo(payload)
        self.assertEqual(result.returncode, 1)
        self.assertIn("SUMMARY:", result.stdout)
        self.assertIn("2 service(s)", result.stdout)
        self.assertIn("1 critical", result.stdout)
        self.assertIn("1 pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
