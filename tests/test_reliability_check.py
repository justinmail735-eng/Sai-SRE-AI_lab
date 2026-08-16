import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "reliability_check.py"


class ReliabilityCheckTests(unittest.TestCase):
    def test_repository_reliability_check_passes(self):
        result = subprocess.run([sys.executable, str(CHECK)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS observability-drift:checkout-api", result.stdout)
        self.assertIn("PASS slo-policy", result.stdout)
        self.assertIn("PASS agent-governance", result.stdout)
        self.assertIn("PASS drill-evidence", result.stdout)
        self.assertIn("PASS workflow-supply-chain-hygiene", result.stdout)

    def test_json_output_reports_each_check(self):
        result = subprocess.run(
            [sys.executable, str(CHECK), "--output", "json"], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["passed"])
        self.assertEqual(
            {item["name"] for item in payload["checks"]},
            {
                "observability-drift:checkout-api",
                "slo-policy",
                "agent-governance",
                "drill-evidence",
                "workflow-supply-chain-hygiene",
            },
        )

    def test_unhealthy_slo_snapshot_fails_continuous_check(self):
        unhealthy = {
            "policy": {"min_requests": 100, "warning_burn_rate": 1, "critical_burn_rate": 2},
            "services": [{
                "name": "checkout-api",
                "owner": "commerce-sre@sai-lab.local",
                "target_availability": 0.999,
                "windows": [{"label": "5m", "minutes": 5, "total_requests": 10000, "error_requests": 500}],
            }],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(unhealthy, handle)
            handle.flush()
            result = subprocess.run(
                [sys.executable, str(CHECK), "--slo-input", handle.name], cwd=ROOT, capture_output=True, text=True
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL slo-policy", result.stdout)
