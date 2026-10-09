import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("release_center", ROOT / "tools/release_center.py")
release_center = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_center)


class ReleaseCenterTests(unittest.TestCase):
    def test_manifest_lists_stay_inside_channel(self):
        for channel in ("beta", "stable"):
            entries = release_center.manifests(channel)
            self.assertTrue(entries)
            self.assertTrue(all(path.startswith(f"manifests/{channel}/") for path in entries))

    def test_components_come_from_selected_manifest(self):
        manifest = release_center.manifests("beta")[0]
        components = release_center.manifest_components(manifest, "beta")
        self.assertIn("meo-desktop", components)
        self.assertIn("meoui-qml", components)

    def test_beta_requires_explicit_candidate(self):
        manifest = release_center.manifests("beta")[0]
        result = release_center.validate_selection("beta", manifest, "", full=False)
        self.assertFalse(result["ok"])
        self.assertIn("requires one explicit candidate", result["output"])

    def test_candidate_must_exist_in_manifest(self):
        manifest = release_center.manifests("stable")[0]
        result = release_center.validate_selection("stable", manifest, "definitely-not-a-package", full=False)
        self.assertFalse(result["ok"])
        self.assertIn("not present", result["output"])

    def test_manifest_cannot_cross_channels(self):
        beta = release_center.manifests("beta")[0]
        result = release_center.validate_selection("stable", beta, "", full=False)
        self.assertFalse(result["ok"])
        self.assertIn("select a committed manifest", result["output"])


if __name__ == "__main__":
    unittest.main()
