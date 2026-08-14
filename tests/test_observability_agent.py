import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "agents" / "observability_agent.py"
SAMPLE = ROOT / "reliability" / "services" / "checkout-api.json"


def sample_spec():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def run_agent(spec, output_dir: Path, *args: str):
    spec_path = output_dir.parent / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(AGENT), "--spec", str(spec_path), "--output-dir", str(output_dir), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class ObservabilityAgentTests(unittest.TestCase):
    def test_generates_dashboard_rules_and_audit_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            result = run_agent(sample_spec(), output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "dashboard.json").exists())
            self.assertTrue((output / "prometheus-rules.yaml").exists())
            audit = json.loads((output / "agent-result.json").read_text())
            self.assertTrue(audit["successful"])
            self.assertEqual(audit["risk"], "low")
            self.assertFalse(audit["approval_required"])

    def test_dashboard_contains_four_golden_signal_panels(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            run_agent(sample_spec(), output)
            dashboard = json.loads((output / "dashboard.json").read_text())
            self.assertEqual(len(dashboard["panels"]), 4)
            self.assertEqual(
                {panel["title"] for panel in dashboard["panels"]},
                {"Request rate", "Error rate", "Latency p95", "CPU utilization"},
            )
            self.assertFalse(dashboard["editable"])

    def test_rules_include_burn_latency_owner_and_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            run_agent(sample_spec(), output)
            rules = (output / "prometheus-rules.yaml").read_text()
            self.assertIn("error_budget_fast_burn", rules)
            self.assertIn("error_budget_slow_burn", rules)
            self.assertIn("latency_slo_violation", rules)
            self.assertIn("commerce-sre@sai-lab.local", rules)
            self.assertIn("reliability/runbooks/checkout-api.md", rules)

    def test_check_mode_passes_for_fresh_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            spec = sample_spec()
            self.assertEqual(run_agent(spec, output).returncode, 0)
            checked = run_agent(spec, output, "--check")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("PASS drift:dashboard.json", checked.stdout)

    def test_check_mode_detects_dashboard_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            spec = sample_spec()
            run_agent(spec, output)
            dashboard = json.loads((output / "dashboard.json").read_text())
            dashboard["title"] = "Manually edited"
            (output / "dashboard.json").write_text(json.dumps(dashboard))
            checked = run_agent(spec, output, "--check")
            self.assertEqual(checked.returncode, 1)
            self.assertIn("FAIL drift:dashboard.json", checked.stdout)

    def test_check_mode_does_not_modify_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            spec = sample_spec()
            run_agent(spec, output)
            target = output / "dashboard.json"
            before = target.read_bytes()
            run_agent(spec, output, "--check")
            self.assertEqual(target.read_bytes(), before)

    def test_rejects_missing_golden_signal_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = sample_spec()
            del spec["spec"]["metrics"]["latency_p95"]
            result = run_agent(spec, Path(tmp) / "generated")
            self.assertEqual(result.returncode, 2)
            self.assertIn("missing required metrics: latency_p95", result.stderr)

    def test_rejects_invalid_service_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = sample_spec()
            spec["metadata"]["name"] = "Checkout API"
            result = run_agent(spec, Path(tmp) / "generated")
            self.assertEqual(result.returncode, 2)
            self.assertIn("DNS-style", result.stderr)

    def test_rejects_invalid_slo_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = sample_spec()
            spec["spec"]["slo"]["availability_target"] = 1
            result = run_agent(spec, Path(tmp) / "generated")
            self.assertEqual(result.returncode, 2)
            self.assertIn("availability_target", result.stderr)

    def test_rejects_reversed_burn_thresholds(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = sample_spec()
            spec["spec"]["alerts"]["warning_burn_rate"] = 20
            spec["spec"]["alerts"]["critical_burn_rate"] = 10
            result = run_agent(spec, Path(tmp) / "generated")
            self.assertEqual(result.returncode, 2)
            self.assertIn("critical must exceed warning", result.stderr)

    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "one"
            second = root / "two"
            spec = copy.deepcopy(sample_spec())
            run_agent(spec, first)
            run_agent(spec, second)
            self.assertEqual((first / "dashboard.json").read_bytes(), (second / "dashboard.json").read_bytes())
            self.assertEqual((first / "prometheus-rules.yaml").read_bytes(), (second / "prometheus-rules.yaml").read_bytes())
