import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

from agents.governance import (
    ActionRequest,
    Approval,
    AuditLog,
    GovernancePolicy,
    IdentityRegistry,
    create_approval,
    canonical,
    validate_request_freshness,
    verify_approval,
)
from agents.action_broker import execute_action, verify_effect


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


def signed_approval(**overrides):
    value = create_approval(request(), "sai@example.com", SECRET, now=NOW).to_dict()
    value.update(overrides)
    unsigned = dict(value)
    unsigned.pop("signature")
    value["signature"] = hmac.new(
        SECRET.encode(), canonical(unsigned).encode(), hashlib.sha256,
    ).hexdigest()
    return Approval.from_dict(value)


class ApprovalTests(unittest.TestCase):
    def test_action_request_requires_object_contract(self):
        with self.assertRaisesRegex(ValueError, "JSON object"):
            ActionRequest.from_dict([])

    def test_action_request_rejects_invalid_collection_types(self):
        with self.assertRaisesRegex(ValueError, "parameters must be an object"):
            request(parameters=[])
        with self.assertRaisesRegex(ValueError, "evidence must contain"):
            request(evidence="fault mode is errors")
        with self.assertRaisesRegex(ValueError, "verification must contain"):
            request(verification=[""])

    def test_approval_rejects_extra_fields_and_malformed_signature(self):
        value = create_approval(request(), "sai@example.com", SECRET, now=NOW).to_dict()
        with self.assertRaisesRegex(ValueError, "fields must be exactly"):
            Approval.from_dict({**value, "bypass": True})
        value["signature"] = "not-a-digest"
        with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
            Approval.from_dict(value)

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

    def test_verifier_rejects_missing_or_weak_approval_secret(self):
        action = request()
        approval = create_approval(action, "sai@example.com", SECRET, now=NOW)
        for weak_secret in ("", "too-short"):
            with self.subTest(secret=weak_secret), self.assertRaisesRegex(ValueError, "at least 32"):
                verify_approval(action, approval, weak_secret, now=NOW)

    def test_expired_approval_is_rejected(self):
        action = request()
        approval = create_approval(action, "sai@example.com", SECRET, now=NOW, ttl_minutes=1)
        with self.assertRaisesRegex(ValueError, "expired"):
            verify_approval(action, approval, SECRET, now=NOW + dt.timedelta(minutes=2))

    def test_approval_expires_at_exact_expiration_instant(self):
        action = request()
        approval = create_approval(action, "sai@example.com", SECRET, now=NOW, ttl_minutes=1)
        with self.assertRaisesRegex(ValueError, "expired"):
            verify_approval(action, approval, SECRET, now=NOW + dt.timedelta(minutes=1))

    def test_verifier_rejects_oversized_signed_approval_ttl(self):
        approval = signed_approval(expires_at="2026-08-14T13:00:01Z")
        with self.assertRaisesRegex(ValueError, "between 1 and 60 minutes"):
            verify_approval(request(), approval, SECRET, now=NOW)

    def test_verifier_rejects_invalid_signed_approval_chronology(self):
        approval = signed_approval(expires_at="2026-08-14T11:59:59Z")
        with self.assertRaisesRegex(ValueError, "between 1 and 60 minutes"):
            verify_approval(request(), approval, SECRET, now=NOW)

    def test_self_approval_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            create_approval(request(), "IncidentInvestigatorAgent", SECRET, now=NOW)

    def test_stale_request_cannot_be_approved(self):
        stale = request(created_at="2026-08-14T10:59:59Z")
        with self.assertRaisesRegex(ValueError, "stale"):
            create_approval(stale, "sai@example.com", SECRET, now=NOW)

    def test_request_that_ages_out_after_approval_cannot_execute(self):
        action = request(created_at="2026-08-14T11:00:00Z")
        approval = create_approval(action, "sai@example.com", SECRET, now=NOW)
        with self.assertRaisesRegex(ValueError, "stale"):
            verify_approval(action, approval, SECRET, now=NOW + dt.timedelta(seconds=1))

    def test_future_request_is_rejected_beyond_clock_skew(self):
        future = request(created_at="2026-08-14T12:00:31Z")
        with self.assertRaisesRegex(ValueError, "future"):
            validate_request_freshness(future, NOW)

    def test_request_at_freshness_boundaries_is_accepted(self):
        validate_request_freshness(request(created_at="2026-08-14T11:00:00Z"), NOW)
        validate_request_freshness(request(created_at="2026-08-14T12:00:30Z"), NOW)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = GovernancePolicy.load(ROOT / "agents/policy/governance.json")
        self.identities = IdentityRegistry.load(ROOT / "agents/identities/demo-identities.json")

    def test_allowlisted_local_recovery_can_execute(self):
        self.policy.validate(request(), apply=True)

    def test_governance_policy_rejects_unsupported_contract(self):
        policy = json.loads((ROOT / "agents/policy/governance.json").read_text())
        policy["api_version"] = "sentinelsre.io/v2"
        with self.assertRaisesRegex(ValueError, "unsupported governance policy contract"):
            GovernancePolicy(policy)

    def test_identity_registry_rejects_unsupported_contract(self):
        registry = json.loads((ROOT / "agents/identities/demo-identities.json").read_text())
        registry["kind"] = "UntrustedRegistry"
        with self.assertRaisesRegex(ValueError, "unsupported identity registry contract"):
            IdentityRegistry(registry)

    def test_arbitrary_action_is_denied(self):
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            self.policy.validate(request(action="shell.execute"), apply=True)

    def test_agent_cannot_underclassify_action_risk(self):
        with self.assertRaisesRegex(ValueError, "classified as medium"):
            self.policy.validate(request(risk="low"), apply=True)

    def test_wrong_agent_cannot_propose_action(self):
        with self.assertRaisesRegex(ValueError, "cannot propose"):
            self.policy.validate(request(requester="UnknownAgent"), apply=True)

    def test_security_critical_policy_flags_require_booleans(self):
        policy_path = ROOT / "agents/policy/governance.json"
        for section, name, value in (
            ("environments", "local", 0),
            ("actions", "fault.recover", "false"),
        ):
            with self.subTest(section=section, name=name):
                policy = json.loads(policy_path.read_text())
                field = "draft_only" if section == "environments" else "executable"
                policy[section][name][field] = value
                with self.assertRaisesRegex(ValueError, "must be a boolean"):
                    GovernancePolicy(policy).validate(request(), apply=True)

    def test_action_authorization_lists_require_string_arrays(self):
        policy_path = ROOT / "agents/policy/governance.json"
        for field, value in (
            ("requesters", {"IncidentInvestigatorAgent": True}),
            ("environments", {"local": True}),
        ):
            with self.subTest(field=field):
                policy = json.loads(policy_path.read_text())
                policy["actions"]["fault.recover"][field] = value
                with self.assertRaisesRegex(ValueError, "non-empty string list"):
                    GovernancePolicy(policy).validate(request(), apply=True)

    def test_parameter_constraint_schema_fails_closed(self):
        policy_path = ROOT / "agents/policy/governance.json"
        for field, value, message in (
            ("required", "false", "must be a boolean"),
            ("enum", {"http://127.0.0.1:8080": True}, "must be a non-empty list"),
        ):
            with self.subTest(field=field):
                policy = json.loads(policy_path.read_text())
                policy["actions"]["fault.recover"]["parameters"]["base_url"][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    GovernancePolicy(policy).validate(request(), apply=True)

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

    def test_scale_requires_integer_replicas(self):
        for invalid in (2.5, True, "3"):
            with self.subTest(replicas=invalid), self.assertRaisesRegex(ValueError, "must be an integer"):
                self.policy.validate(request(
                    requester="IncidentCommanderAgent", action="kubernetes.scale",
                    target="sentinelsre/checkout-checkout-api", parameters={"replicas": invalid}, risk="high",
                ), apply=True)

    def test_recovery_requires_string_base_url(self):
        with self.assertRaisesRegex(ValueError, "must be a string"):
            self.policy.validate(request(parameters={"base_url": 8080}), apply=True)

    def test_authorized_dummy_incident_commander_can_approve_local(self):
        self.identities.require_approver("sai.demo", self.policy, "local")

    def test_observer_and_inactive_identity_cannot_approve(self):
        with self.assertRaisesRegex(ValueError, "lacks an authorized role"):
            self.identities.require_approver("alex.observer", self.policy, "local")
        with self.assertRaisesRegex(ValueError, "inactive"):
            self.identities.require_approver("former.engineer", self.policy, "local")

    def test_malformed_identity_authorization_fields_fail_closed(self):
        for field, value, message in (
            ("active", "false", "active flag must be a boolean"),
            ("roles", {"incident-commander": True}, "roles must be a non-empty string list"),
        ):
            with self.subTest(field=field):
                registry = json.loads((ROOT / "agents/identities/demo-identities.json").read_text())
                registry["identities"]["sai.demo"][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    IdentityRegistry(registry).require_approver("sai.demo", self.policy, "local")

    def test_malformed_policy_approver_roles_fail_closed(self):
        policy = json.loads((ROOT / "agents/policy/governance.json").read_text())
        policy["environments"]["local"]["approver_roles"] = {"incident-commander": True}
        with self.assertRaisesRegex(ValueError, "non-empty string list"):
            self.identities.require_approver("sai.demo", GovernancePolicy(policy), "local")


class AuditTests(unittest.TestCase):
    def test_append_syncs_audit_event_to_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditLog(Path(directory) / "audit.jsonl")
            with patch("agents.governance.os.fsync") as sync:
                audit.append({"outcome": "succeeded", "request_id": "ACT-1"})
            sync.assert_called_once()
            audit.verify()

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

    def test_executed_request_digest_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditLog(Path(directory) / "audit.jsonl")
            digest = request().digest
            audit.append({"outcome": "succeeded", "request_digest": digest})
            with self.assertRaisesRegex(ValueError, "already been executed"):
                audit.reject_replay(digest)

    def test_new_request_digest_is_not_a_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditLog(Path(directory) / "audit.jsonl")
            audit.append({"outcome": "succeeded", "request_digest": request().digest})
            newer = request(created_at="2026-08-14T12:01:00Z")
            audit.reject_replay(newer.digest)

    def test_execution_transaction_serializes_brokers(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditLog(Path(directory) / "audit.jsonl")
            acquired = threading.Event()

            def wait_for_transaction():
                with audit.execution_transaction():
                    acquired.set()

            with audit.execution_transaction():
                contender = threading.Thread(target=wait_for_transaction)
                contender.start()
                time.sleep(0.05)
                self.assertFalse(acquired.is_set())

            contender.join(timeout=1)
            self.assertFalse(contender.is_alive())
            self.assertTrue(acquired.is_set())


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

    def test_scale_verification_proves_requested_replicas_are_available(self):
        proposed = request(
            requester="IncidentCommanderAgent", action="kubernetes.scale",
            target="sentinelsre/checkout-checkout-api", parameters={"replicas": 3}, risk="high",
        )
        responses = [
            Mock(stdout="deployment successfully rolled out"),
            Mock(stdout=json.dumps({"spec": {"replicas": 3}, "status": {"availableReplicas": 3}})),
        ]
        with patch("agents.action_broker.subprocess.run", side_effect=responses) as runner:
            evidence = verify_effect(proposed)
        self.assertIn("3 desired and 3 available", evidence[1])
        self.assertEqual(runner.call_count, 2)

    def test_scale_verification_rejects_insufficient_available_replicas(self):
        proposed = request(
            requester="IncidentCommanderAgent", action="kubernetes.scale",
            target="sentinelsre/checkout-checkout-api", parameters={"replicas": 3}, risk="high",
        )
        responses = [
            Mock(stdout="deployment successfully rolled out"),
            Mock(stdout=json.dumps({"spec": {"replicas": 3}, "status": {"availableReplicas": 2}})),
        ]
        with patch("agents.action_broker.subprocess.run", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "scale verification failed"):
                verify_effect(proposed)


if __name__ == "__main__":
    unittest.main()
