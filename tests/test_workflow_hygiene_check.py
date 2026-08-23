import tempfile
import unittest
from pathlib import Path

from scripts.workflow_hygiene_check import (
    artifact_uploads_without_retention,
    checkouts_with_persisted_credentials,
    jobs_without_timeouts,
    outdated_actions,
    unpinned_actions,
    workflows_without_concurrency,
)


class WorkflowHygieneCheckTests(unittest.TestCase):
    def test_repository_workflows_use_node24_compatible_actions(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(outdated_actions(root / ".github" / "workflows"), [])

    def test_repository_actions_are_pinned_to_commits(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(unpinned_actions(root / ".github" / "workflows"), [])

    def test_repository_checkouts_do_not_persist_credentials(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(checkouts_with_persisted_credentials(root / ".github" / "workflows"), [])

    def test_repository_workflows_control_concurrency(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(workflows_without_concurrency(root / ".github" / "workflows"), [])

    def test_repository_jobs_have_execution_budgets(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(jobs_without_timeouts(root / ".github" / "workflows"), [])

    def test_repository_artifacts_have_explicit_retention(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(artifact_uploads_without_retention(root / ".github" / "workflows"), [])

    def test_deprecated_first_party_action_is_reported_with_location(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("steps:\n  - uses: actions/checkout@v4\n")
            findings = outdated_actions(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("ci.yml:2", findings[0])
        self.assertIn("must be v5 or newer", findings[0])

    def test_mutable_action_tag_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "release.yml").write_text("steps:\n  - uses: vendor/release-action@v3\n")
            findings = unpinned_actions(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("release.yml:2", findings[0])
        self.assertIn("immutable 40-character commit SHA", findings[0])

    def test_indented_mutable_action_tag_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "release.yml").write_text(
                "steps:\n  - id: build\n    uses: vendor/build-action@v6\n"
            )
            findings = unpinned_actions(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("vendor/build-action@v6", findings[0])

    def test_checkout_with_default_credentials_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text(
                "steps:\n  - uses: actions/checkout@0123456789012345678901234567890123456789\n"
                "  - run: tests\n"
            )
            findings = checkouts_with_persisted_credentials(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("persist-credentials: false", findings[0])

    def test_workflow_without_concurrency_policy_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text(
                "name: ci\non: push\njobs:\n  test:\n    timeout-minutes: 5\n    steps:\n      - run: tests\n"
            )
            findings = workflows_without_concurrency(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("concurrency group", findings[0])

    def test_job_without_timeout_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text(
                "name: ci\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
            )
            findings = jobs_without_timeouts(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("job test", findings[0])
        self.assertIn("positive timeout-minutes", findings[0])

    def test_artifact_without_retention_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "evidence.yml").write_text(
                "jobs:\n  evidence:\n    timeout-minutes: 5\n    steps:\n"
                "      - uses: actions/upload-artifact@0123456789012345678901234567890123456789\n"
                "        with:\n          path: evidence.json\n"
            )
            findings = artifact_uploads_without_retention(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("retention-days between 1 and 90", findings[0])
