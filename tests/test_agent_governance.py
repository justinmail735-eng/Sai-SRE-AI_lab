import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]

from agents.governance import (
    ActionRequest,
    Approval,
    AuditLog,
    GovernancePolicy,
    IdentityRegistry,
    create_approval,
    verify_approval,
)
from agents.action_broker import execute_action


SECRET = "unit-test-approval-key-that-is-long-enough"
NOW = dt.datetime(2026, 8, 14, 12, 0, tzinfo=dt.timezone.utc)


def request(**overrides):
    values = {
        "api_version": "sentinelsre.io/v1",
        "kind": "ActionRequest",
        "incident_id": "INC-12345",
        "requester": "IncidentInvestigatorAgent",
        "environment": "local",
        "action": "fault.recover",
        "target": "checkout-api",
        "parameters": {"base_url": "http://127.0.0.1:8080"},
        "risk": "medium",
        "evidence": ["fault mode is errors"],
        "verification": ["fault mode is none"],
        "rollback": "Do not restore the injected fault.",
        "created_at": "2026-08-14T11:59:00Z",
    }
    values.update(overrides)
    return ActionRequest.from_dict(values)


class ApprovalTests(unittest.TestCase):
    def test_valid_approval_is_bound_to_request(self):
        action = request()
        approval = create_approval(action, "sai@example.com", SECRET, now=NOW)
        verify_approval(action, approval, SECRET, now=NOW + dt.timedelta(minutes=1))

    def test_tampered_request_is_rejected(self):
        action = request()
        approval = create_approval(action, "sai@example.com", SECRET, now=NOW)
        with self.assertRaisesRegex(ValueError, "exact request"):
            verify_approval(request(target="other-service"), approval, SECRET, now=NOW)

    def test_bad_signature_is_rejected(self):
        action = request()
        value = create_approval(action, "sai@example.com", SECRET, now=NOW).to_dict()
        value["signature"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "signature"):
            verify_approval(action, Approval.from_dict(value), SECRET, now=NOW)

    def test_expired_approval_is_rejected(self):
        action = request()
        approval = create_approval(action, "sai@example.com", SECRET, now=NOW, ttl_minutes=1)
        with self.assertRaisesRegex(ValueError, "expired"):
            verify_approval(action, approval, SECRET, now=NOW + dt.timedelta(minutes=2))

    def test_self_approval_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            create_approval(request(), "IncidentInvestigatorAgent", SECRET, now=NOW)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = GovernancePolicy.load(ROOT / "agents/policy/governance.json")
        self.identities = IdentityRegistry.load(ROOT / "agents/identities/demo-identities.json")

    def test_allowlisted_local_recovery_can_execute(self):
        self.policy.validate(request(), apply=True)

    def test_arbitrary_action_is_denied(self):
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            self.policy.validate(request(action="shell.execute"), apply=True)

    def test_agent_cannot_underclassify_action_risk(self):
        with self.assertRaisesRegex(ValueError, "classified as medium"):
            self.policy.validate(request(risk="low"), apply=True)

    def test_wrong_agent_cannot_propose_action(self):
        with self.assertRaisesRegex(ValueError, "cannot propose"):
            self.policy.validate(request(requester="UnknownAgent"), apply=True)

    def test_production_execution_is_denied(self):
        proposed = request(
            requester="PlatformEngineerAgent", environment="production", action="terraform.plan",
            target="aws-dev", parameters={}, risk="low",
        )
        self.policy.validate(proposed, apply=False)
        with self.assertRaisesRegex(ValueError, "prohibited|draft-only"):
            self.policy.validate(proposed, apply=True)

    def test_scale_blast_radius_is_limited(self):
        proposed = request(
            requester="IncidentCommanderAgent", action="kubernetes.scale",
            target="sentinelsre/checkout-checkout-api", parameters={"replicas": 20}, risk="high",
        )
        with self.assertRaisesRegex(ValueError, "maximum"):
            self.policy.validate(proposed, apply=True)

    def test_authorized_dummy_incident_commander_can_approve_local(self):
        self.identities.require_approver("sai.demo", self.policy, "local")

    def test_observer_and_inactive_identity_cannot_approve(self):
        with self.assertRaisesRegex(ValueError, "lacks an authorized role"):
            self.identities.require_approver("alex.observer", self.policy, "local")
        with self.assertRaisesRegex(ValueError, "inactive"):
            self.identities.require_approver("former.engineer", self.policy, "local")


class AuditTests(unittest.TestCase):
    def test_append_and_verify_hash_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            audit = AuditLog(path)
            first = audit.append({"outcome": "succeeded", "request_id": "ACT-1"})
            second = audit.append({"outcome": "denied", "request_id": "ACT-2"})
            self.assertEqual(second["previous_hash"], first["event_hash"])
            audit.verify()

    def test_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            audit = AuditLog(path)
            record = audit.append({"outcome": "succeeded", "request_id": "ACT-1"})
            record["outcome"] = "failed"
            path.write_text(json.dumps(record) + "\n")
            with self.assertRaisesRegex(ValueError, "invalid"):
                audit.verify()


class AdapterTests(unittest.TestCase):
    def test_scale_adapter_uses_argument_array_and_scoped_target(self):
        runner = Mock(return_value=Mock(stdout="scaled"))
        proposed = request(
            requester="IncidentCommanderAgent", action="kubernetes.scale",
            target="sentinelsre/checkout-checkout-api", parameters={"replicas": 3}, risk="high",
        )
        self.assertEqual(execute_action(proposed, runner=runner), "scaled")
        runner.assert_called_once_with(
            ["kubectl", "scale", "deployment/checkout-checkout-api", "--namespace", "sentinelsre", "--replicas=3"],
            check=True, text=True, capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
