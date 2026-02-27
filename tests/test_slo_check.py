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


if __name__ == "__main__":
    unittest.main()
