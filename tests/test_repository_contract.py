import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from overlay import stable_supersedes_beta

class RepositoryContractTests(unittest.TestCase):
    def test_channel_configs_are_package_owned_and_ordered(self):
        stable = (ROOT / "packages/meo-channel-stable/meo-channel.conf").read_text()
        beta = (ROOT / "packages/meo-channel-beta/meo-channel.conf").read_text()
        self.assertEqual(stable.count("[meo]"), 1)
        self.assertNotIn("meo-beta", stable)
        self.assertLess(beta.index("[meo-beta]"), beta.index("[meo]"))
        self.assertEqual(beta.count("Required TrustedOnly"), 2)

    def test_catalog_has_no_name_prefix_rule(self):
        catalog = json.loads((ROOT / "manifests/package-catalog.json").read_text())
        self.assertIn("omnistore-bin", catalog["packages"])
        self.assertEqual(catalog["channelPackages"]["beta"], "meo-channel-beta")

    def test_meo_release_installs_full_package_and_application_catalogs(self):
        package_catalog = json.loads((ROOT / "packages/meo-release/package-catalog.json").read_text())
        application_catalog = json.loads((ROOT / "packages/meo-release/application-catalog.json").read_text())
        recipe = (ROOT / "packages/meo-release/PKGBUILD").read_text()
        self.assertIn("packages", package_catalog)
        self.assertIn("omnistore-bin", package_catalog["packages"])
        self.assertEqual(application_catalog["applications"]["ark"]["package"], "ark")
        self.assertIn("application-catalog.json", recipe)

    def test_omnistore_package_requires_the_system_alpm_helper(self):
        recipe = (ROOT / "packages/omnistore-bin/PKGBUILD").read_text()
        self.assertIn("'pyalpm'", recipe)
        self.assertIn("meo_stable_rollback.py", recipe)
        self.assertNotIn("python-pyalpm", recipe)

    def test_manifest_requires_real_commit_before_release(self):
        manifest = ROOT / "manifests/stable/2026.08.json"
        result = subprocess.run([sys.executable, ROOT / "scripts/validate_manifest.py", manifest], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pinned 40-character SHA", result.stderr)

    def test_overlay_cleanup_only_when_stable_wins(self):
        self.assertTrue(stable_supersedes_beta("1.7.0-1", "1.7.0beta1-1", 1))
        self.assertFalse(stable_supersedes_beta("1.6.1-1", "1.7.0beta1-1", -1))

    def test_keyring_gate_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, ROOT / "scripts/validate_keyring_payload.py", directory], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

if __name__ == "__main__":
    unittest.main()
