import datetime as dt
import unittest

from scripts.npm_audit_check import evaluate, production_exception_failures, validate_allowlist


def audit(package="image-size", direct=False, advisories=("GHSA-1111-2222-3333",)):
    return {"vulnerabilities": {package: {
        "severity": "high",
        "isDirect": direct,
        "via": [{"url": f"https://github.com/advisories/{item}"} for item in advisories],
    }}}


def allowlist(expires="2026-09-14"):
    return {"api_version": "sentinelsre.io/v1", "exceptions": [{
        "package": "image-size",
        "advisories": ["GHSA-1111-2222-3333"],
        "owner": "security-platform",
        "expires": expires,
        "scope": "transitive development dependencies only",
        "rationale": "No fixed release is available.",
    }]}


class NpmAuditPolicyTests(unittest.TestCase):
    def test_allowlist_contract_is_strictly_validated(self):
        self.assertEqual(validate_allowlist(allowlist()), [])
        for field, value, message in (
            ("owner", "", "owner must be a non-empty string"),
            ("advisories", ["CVE-not-ghsa"], "unique GHSA identifiers"),
            ("expires", "tomorrow", "ISO date"),
            ("scope", "all dependencies", "scope must be"),
        ):
            with self.subTest(field=field):
                policy = allowlist()
                policy["exceptions"][0][field] = value
                self.assertIn(message, validate_allowlist(policy)[0])

    def test_duplicate_package_exceptions_are_rejected(self):
        policy = allowlist()
        policy["exceptions"].append(dict(policy["exceptions"][0]))
        failures = validate_allowlist(policy)
        self.assertTrue(any("duplicates package" in failure for failure in failures))

    def test_unknown_allowlist_fields_are_rejected(self):
        policy = allowlist()
        policy["exceptions"][0]["bypass"] = True
        self.assertIn("must contain exactly", validate_allowlist(policy)[0])

    def test_exact_unexpired_transitive_exception_is_accepted(self):
        accepted, failures = evaluate(audit(), allowlist(), dt.date(2026, 8, 14))
        self.assertEqual(len(accepted), 1)
        self.assertEqual(failures, [])

    def test_new_advisory_fails_closed(self):
        _, failures = evaluate(
            audit(advisories=("GHSA-1111-2222-3333", "GHSA-4444-5555-6666")),
            allowlist(),
            dt.date(2026, 8, 14),
        )
        self.assertIn("advisory set changed", failures[0])

    def test_expired_or_direct_exception_is_rejected(self):
        _, expired = evaluate(audit(), allowlist("2026-08-01"), dt.date(2026, 8, 14))
        self.assertIn("expired", expired[0])
        _, direct = evaluate(audit(direct=True), allowlist(), dt.date(2026, 8, 14))
        self.assertIn("transitive", direct[0])

    def test_aggregate_dependency_is_only_accepted_after_leaf(self):
        payload = audit()
        payload["vulnerabilities"]["vinext"] = {"severity": "high", "isDirect": True, "via": ["image-size"]}
        accepted, failures = evaluate(payload, allowlist(), dt.date(2026, 8, 14))
        self.assertEqual(failures, [])
        self.assertTrue(any("aggregate" in item for item in accepted))

    def test_multi_hop_aggregates_resolve_independent_of_report_order(self):
        payload = audit()
        payload["vulnerabilities"] = {
            "application": {"severity": "high", "isDirect": True, "via": ["globber"]},
            "globber": {"severity": "high", "isDirect": False, "via": ["image-size"]},
            **payload["vulnerabilities"],
        }
        accepted, failures = evaluate(payload, allowlist(), dt.date(2026, 8, 14))
        self.assertEqual(failures, [])
        self.assertEqual(len(accepted), 3)

    def test_aggregate_chain_with_unaccepted_leaf_fails_closed(self):
        payload = audit()
        payload["vulnerabilities"]["application"] = {
            "severity": "high", "isDirect": True, "via": ["unknown-package"],
        }
        _, failures = evaluate(payload, allowlist(), dt.date(2026, 8, 14))
        self.assertIn("unknown-package", failures[0])

    def test_risk_accepted_package_must_remain_dev_only(self):
        lockfile = {"packages": {"node_modules/image-size": {"version": "1.0.0", "dev": True}}}
        self.assertEqual(production_exception_failures(lockfile, allowlist()), [])
        lockfile["packages"]["node_modules/image-size"].pop("dev")
        failures = production_exception_failures(lockfile, allowlist())
        self.assertIn("entered production dependency", failures[0])

    def test_nested_production_copy_of_accepted_package_is_rejected(self):
        lockfile = {"packages": {
            "node_modules/image-size": {"version": "1.0.0", "dev": True},
            "node_modules/runtime/node_modules/image-size": {"version": "1.0.0"},
        }}
        failures = production_exception_failures(lockfile, allowlist())
        self.assertIn("runtime/node_modules/image-size", failures[0])

    def test_missing_lockfile_packages_map_fails_closed(self):
        failures = production_exception_failures({}, allowlist())
        self.assertIn("unverifiable", failures[0])

    def test_malformed_package_metadata_fails_closed(self):
        lockfile = {"packages": {"node_modules/image-size": "invalid"}}
        failures = production_exception_failures(lockfile, allowlist())
        self.assertIn("entered production dependency", failures[0])


if __name__ == "__main__":
    unittest.main()
