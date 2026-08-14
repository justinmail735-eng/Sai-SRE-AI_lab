import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("promote_image", ROOT / "scripts/promote_image.py")
promote_image = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(promote_image)


class ImagePromotionTests(unittest.TestCase):
    def test_replaces_exactly_one_digest(self):
        digest = "sha256:" + "b" * 64
        result = promote_image.render_promotion('image:\n  digest: "sha256:' + "a" * 64 + '"\n', digest)
        self.assertIn(digest, result)
        self.assertNotIn("a" * 64, result)

    def test_rejects_tag_instead_of_digest(self):
        with self.assertRaisesRegex(ValueError, "digest must be"):
            promote_image.render_promotion('digest: "sha256:' + "a" * 64 + '"\n', "main")

    def test_rejects_missing_or_ambiguous_target(self):
        digest = "sha256:" + "b" * 64
        with self.assertRaisesRegex(ValueError, "exactly one"):
            promote_image.render_promotion("digest: latest\n", digest)


if __name__ == "__main__":
    unittest.main()
