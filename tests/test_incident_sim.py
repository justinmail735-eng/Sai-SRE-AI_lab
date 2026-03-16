import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "incident_sim.py"


def run_sim(*args: str):
    cmd = [sys.executable, str(SCRIPT), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


class IncidentSimBasicTests(unittest.TestCase):
    def test_default_run_exits_zero(self):
        result = run_sim()
        self.assertEqual(result.returncode, 0)
        self.assertIn("Incident :", result.stdout)

    def test_json_output_is_valid(self):
        result = run_sim("--output", "json")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        for key in ("scenario_id", "fault_type", "severity", "affected_service",
                    "start_time", "duration_sec", "runbook", "timeline"):
            self.assertIn(key, data)

    def test_markdown_output_contains_sections_and_table(self):
        result = run_sim("--output", "markdown", "--seed", "5")
        self.assertEqual(result.returncode, 0)
        self.assertIn("# Incident Scenario", result.stdout)
        self.assertIn("## Timeline", result.stdout)
        self.assertIn("| Offset | Event Time (UTC) | Event | Detail |", result.stdout)

    def test_seed_produces_deterministic_output(self):
        r1 = run_sim("--fault-type", "latency_spike", "--seed", "42", "--output", "json")
        r2 = run_sim("--fault-type", "latency_spike", "--seed", "42", "--output", "json")
        self.assertEqual(r1.stdout, r2.stdout)

    def test_different_seeds_differ(self):
        r1 = run_sim("--fault-type", "error_rate", "--seed", "1", "--output", "json")
        r2 = run_sim("--fault-type", "error_rate", "--seed", "9999", "--output", "json")
        d1, d2 = json.loads(r1.stdout), json.loads(r2.stdout)
        # At minimum the scenario_id should differ between seeds
        self.assertNotEqual(d1["scenario_id"], d2["scenario_id"])

    def test_unknown_fault_type_exits_nonzero(self):
        result = run_sim("--fault-type", "not-a-fault")
        # argparse will reject this before our code runs (choices enforcement)
        self.assertNotEqual(result.returncode, 0)

    def test_invalid_start_time_exits_two(self):
        result = run_sim("--start-time", "not-a-time")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--start-time must be ISO-8601", result.stderr)

    def test_list_runbooks_exits_zero(self):
        result = run_sim("--list-runbooks")
        self.assertEqual(result.returncode, 0)
        self.assertIn("default", result.stdout)


class IncidentSimFaultTypeTests(unittest.TestCase):
    def _json_for_fault(self, fault: str, severity: str = "P2") -> dict:
        result = run_sim("--fault-type", fault, "--severity", severity,
                         "--seed", "7", "--output", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_latency_spike_scenario(self):
        data = self._json_for_fault("latency_spike")
        self.assertEqual(data["fault_type"], "latency_spike")
        self.assertTrue(len(data["timeline"]) > 0)
        event_types = {e["event_type"] for e in data["timeline"]}
        self.assertIn("anomaly_detected", event_types)
        self.assertIn("resolved", event_types)

    def test_error_rate_scenario(self):
        data = self._json_for_fault("error_rate")
        self.assertEqual(data["fault_type"], "error_rate")
        event_types = {e["event_type"] for e in data["timeline"]}
        self.assertIn("alert_fired", event_types)
        self.assertIn("mitigation_started", event_types)

    def test_dependency_timeout_scenario(self):
        data = self._json_for_fault("dependency_timeout")
        self.assertEqual(data["fault_type"], "dependency_timeout")
        details = " ".join(e["detail"] for e in data["timeline"])
        # should mention a real dependency name
        self.assertTrue(
            any(dep in details for dep in ["postgres", "redis", "payment-gateway", "auth-service"])
        )

    def test_cascade_scenario_has_propagation_events(self):
        data = self._json_for_fault("cascade", severity="P1")
        self.assertEqual(data["fault_type"], "cascade")
        event_types = [e["event_type"] for e in data["timeline"]]
        self.assertIn("cascade_propagation", event_types)
        # P1 cascade should be longer than P4
        p4 = json.loads(
            run_sim("--fault-type", "cascade", "--severity", "P4",
                    "--seed", "7", "--output", "json").stdout
        )
        self.assertGreater(data["duration_sec"], p4["duration_sec"])

    def test_cascade_p1_has_escalation_runbook(self):
        data = self._json_for_fault("cascade", severity="P1")
        self.assertIn("incident commander", data["runbook"].lower())

    def test_error_rate_p1_has_escalation_runbook(self):
        data = self._json_for_fault("error_rate", severity="P1")
        self.assertIn("status-page", data["runbook"].lower())


class IncidentSimSeverityTests(unittest.TestCase):
    def test_severity_defaults_from_fault_type(self):
        result = run_sim("--fault-type", "cascade", "--output", "json")
        data = json.loads(result.stdout)
        self.assertEqual(data["severity"], "P1")

    def test_explicit_severity_overrides_default(self):
        result = run_sim("--fault-type", "cascade", "--severity", "P3", "--output", "json")
        data = json.loads(result.stdout)
        self.assertEqual(data["severity"], "P3")

    def test_timeline_has_ascending_time_offsets(self):
        result = run_sim("--fault-type", "error_rate", "--seed", "42", "--output", "json")
        data = json.loads(result.stdout)
        offsets = [e["time_offset_sec"] for e in data["timeline"]]
        self.assertEqual(offsets, sorted(offsets))

    def test_json_timeline_includes_event_time(self):
        result = run_sim("--fault-type", "error_rate", "--seed", "42", "--output", "json")
        data = json.loads(result.stdout)
        self.assertTrue(all("event_time" in e for e in data["timeline"]))

    def test_start_time_sets_first_event_timestamp(self):
        result = run_sim(
            "--fault-type", "error_rate",
            "--seed", "42",
            "--start-time", "2026-03-16T06:01:00Z",
            "--output", "json",
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["start_time"], "2026-03-16T06:01:00Z")
        first_event = min(data["timeline"], key=lambda e: e["time_offset_sec"])
        self.assertEqual(first_event["event_time"], "2026-03-16T06:01:00Z")

    def test_resolved_event_time_equals_duration(self):
        result = run_sim("--fault-type", "latency_spike", "--seed", "1", "--output", "json")
        data = json.loads(result.stdout)
        resolved = [e for e in data["timeline"] if e["event_type"] == "resolved"]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["time_offset_sec"], data["duration_sec"])

    def test_markdown_output_escapes_table_pipe_characters(self):
        result = run_sim("--fault-type", "dependency_timeout", "--severity", "P2", "--seed", "2", "--output", "markdown")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("| payment-gateway |", result.stdout)


if __name__ == "__main__":
    unittest.main()
