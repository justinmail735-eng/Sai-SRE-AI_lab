import unittest
from unittest.mock import patch

from agents.incident_investigator import active_fault, investigate


class IncidentInvestigatorTests(unittest.TestCase):
    def test_active_fault_reads_metric_gauge(self):
        self.assertEqual(active_fault('sentinel_sre_fault_mode{service="checkout-api",mode="latency"} 1\n'), "latency")

    def test_investigation_proposes_recovery_from_live_evidence(self):
        responses = [
            (200, '{"status":"ok"}'),
            (503, '{"error":"injected"}'),
            (200, 'sentinel_sre_fault_mode{service="checkout-api",mode="errors"} 1\n'),
        ]
        with patch("agents.incident_investigator.fetch", side_effect=responses):
            report = investigate("http://127.0.0.1:8080", "INC-DEMO", "2026-08-14T12:00:00Z")
        action = report["recommended_action"]
        self.assertEqual(action["action"], "fault.recover")
        self.assertEqual(action["requester"], "IncidentInvestigatorAgent")
        self.assertEqual(report["hypotheses"][0]["confidence"], 0.99)

    def test_healthy_service_produces_no_mutation(self):
        responses = [
            (200, '{"status":"ok"}'),
            (200, '{"status":"accepted"}'),
            (200, 'sentinel_sre_fault_mode{service="checkout-api",mode="none"} 1\n'),
        ]
        with patch("agents.incident_investigator.fetch", side_effect=responses):
            report = investigate("http://127.0.0.1:8080", "INC-HEALTHY", "2026-08-14T12:00:00Z")
        self.assertIsNone(report["recommended_action"])


if __name__ == "__main__":
    unittest.main()
