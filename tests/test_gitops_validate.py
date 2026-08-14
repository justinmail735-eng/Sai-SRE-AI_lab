import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gitops_validate", ROOT / "scripts/gitops_validate.py")
gitops_validate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(gitops_validate)


class GitOpsContractTests(unittest.TestCase):
    def test_repository_contract_passes(self):
        checks = gitops_validate.validate_contract()
        self.assertIn("drift self-healing", checks)
        self.assertIn("signature enforcement", checks)

    def test_disabled_self_healing_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            gitops = Path(directory)
            for source in gitops_validate.GITOPS.iterdir():
                if source.is_file():
                    (gitops / source.name).write_text(source.read_text())
            app = gitops / "checkout-application.yaml"
            app.write_text(app.read_text().replace("selfHeal: true", "selfHeal: false"))
            with patch.object(gitops_validate, "GITOPS", gitops):
                with self.assertRaisesRegex(ValueError, "drift self-healing"):
                    gitops_validate.validate_contract()


if __name__ == "__main__":
    unittest.main()
