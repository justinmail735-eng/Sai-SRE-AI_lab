import unittest

from scripts.showcase import Check, Showcase, render_report


class ShowcaseReportTests(unittest.TestCase):
    def test_report_summarizes_capability_results_and_scope(self):
        showcase = Showcase("2026-08-14T12:00:00Z")
        showcase.checks = [Check("terraform", "AWS and Azure Terraform", True, 1.25, "validated")]
        rendered = render_report(showcase)
        self.assertIn("**Outcome:** PASS", rendered)
        self.assertIn("AWS and Azure Terraform", rendered)
        self.assertIn("no cloud apply", rendered)

    def test_empty_or_failed_showcase_does_not_pass(self):
        self.assertFalse(Showcase("2026-08-14T12:00:00Z").passed)
        showcase = Showcase("2026-08-14T12:00:00Z")
        showcase.checks = [Check("failure", "tests", False, 0.1, "failed")]
        self.assertFalse(showcase.passed)


if __name__ == "__main__":
    unittest.main()
