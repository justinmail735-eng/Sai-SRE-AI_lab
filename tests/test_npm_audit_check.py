import datetime as dt
import unittest

from scripts.npm_audit_check import evaluate


def audit(package="image-size", direct=False, advisories=("GHSA-one",)):
    return {"vulnerabilities": {package: {
        "severity": "high",
        "isDirect": direct,
        "via": [{"url": f"https://github.com/advisories/{item}"} for item in advisories],
    }}}


def allowlist(expires="2026-09-14"):
    return {"exceptions": [{
        "package": "image-size", "advisories": ["GHSA-one"], "owner": "security-platform", "expires": expires,
    }]}


class NpmAuditPolicyTests(unittest.TestCase):
    def test_exact_unexpired_transitive_exception_is_accepted(self):
        accepted, failures = evaluate(audit(), allowlist(), dt.date(2026, 8, 14))
        self.assertEqual(len(accepted), 1)
        self.assertEqual(failures, [])

    def test_new_advisory_fails_closed(self):
        _, failures = evaluate(audit(advisories=("GHSA-one", "GHSA-two")), allowlist(), dt.date(2026, 8, 14))
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


if __name__ == "__main__":
    unittest.main()
