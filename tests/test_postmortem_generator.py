import json
import tempfile
import unittest
from pathlib import Path

from agents.governance import ActionRequest, AuditLog
from scripts.postmortem_generator import build_postmortem, load_evidence, markdown


def request():
    return ActionRequest.from_dict({
        "api_version": "sentinelsre.io/v1",
        "kind": "ActionRequest",
        "incident_id": "INC-TEST",
        "requester": "IncidentInvestigatorAgent",
        "environment": "local",
        "action": "fault.recover",
        "target": "checkout-api",
        "parameters": {"base_url": "http://127.0.0.1:8080"},
        "risk": "medium",
        "evidence": ["GET /checkout returned HTTP 503", "fault mode is errors"],
        "verification": ["fault mode is none"],
        "rollback": "Do not restore the injected fault.",
        "created_at": "2026-08-14T12:00:00Z",
    })


def investigation(action):
    return {
        "api_version": "sentinelsre.io/v1",
        "kind": "IncidentInvestigation",
        "incident_id": action.incident_id,
        "agent": "IncidentInvestigatorAgent",
        "mode": "read-only",
        "observed_at": "2026-08-14T11:59:30Z",
        "evidence": action.evidence,
        "hypotheses": [{
            "summary": "local demo fault injection is set to errors",
            "confidence": 0.99,
            "supporting_evidence": ["fault mode is errors"],
            "contradicting_evidence": [],
        }],
        "recommended_action": {"request_id": action.request_id, **action.to_dict()},
    }


class PostmortemTests(unittest.TestCase):
    def make_files(self, directory):
        action = request()
        investigation_path = Path(directory) / "investigation.json"
        investigation_path.write_text(json.dumps(investigation(action)))
        audit_path = Path(directory) / "audit.jsonl"
        AuditLog(audit_path).append({
            "request_id": action.request_id,
            "request_digest": action.digest,
            "approver": "sai.demo",
            "started_at": "2026-08-14T12:01:00Z",
            "completed_at": "2026-08-14T12:01:01Z",
            "outcome": "succeeded",
            "output": "checkout fault mode set to none",
            "verification": ["fault mode is none", "health endpoint returned HTTP 200"],
        })
        return investigation_path, audit_path

    def test_builds_resolved_evidence_linked_postmortem(self):
        with tempfile.TemporaryDirectory() as directory:
            investigation_path, audit_path = self.make_files(directory)
            evidence, action, event = load_evidence(investigation_path, audit_path)
            result = build_postmortem(evidence, action, event)
        self.assertEqual(result["status"], "resolved")
        self.assertIn("No production users", result["impact"])
        self.assertEqual(result["evidence"]["request_digest"], action.digest)
        rendered = markdown(result)
        self.assertIn("## Root cause", rendered)
        self.assertIn("## Action items", rendered)
        self.assertIn("blameless", rendered)

    def test_tampered_audit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            investigation_path, audit_path = self.make_files(directory)
            record = json.loads(audit_path.read_text())
            record["approver"] = "attacker"
            audit_path.write_text(json.dumps(record) + "\n")
            with self.assertRaisesRegex(ValueError, "audit chain"):
                load_evidence(investigation_path, audit_path)

    def test_request_identifier_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            investigation_path, audit_path = self.make_files(directory)
            value = json.loads(investigation_path.read_text())
            value["recommended_action"]["request_id"] = "ACT-FORGED"
            investigation_path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "identifier"):
                load_evidence(investigation_path, audit_path)


if __name__ == "__main__":
    unittest.main()
