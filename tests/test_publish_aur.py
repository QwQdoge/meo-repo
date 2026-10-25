import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publish_aur  # noqa: E402

COMPONENT = {
    "repository": "QwQdoge/MeoUI",
    "commit": "b8ed876b66a5e69fd4986385c734b1a83c567be7",
    "sourceUrl": "https://codeload.github.com/QwQdoge/MeoUI/tar.gz/b8ed876b66a5e69fd4986385c734b1a83c567be7",
    "sourceSha256": "a" * 64,
    "expectedVersion": "1.0.4beta3-5",
}


class RenderRecipeTest(unittest.TestCase):
    def test_empty_source_recipe_gets_pinned_tarball_and_checksum(self):
        recipe = (ROOT / "packages" / "meoui-qml" / "PKGBUILD").read_text()
        text = publish_aur.render_recipe(recipe, COMPONENT)
        self.assertIn("_srcdir=MeoUI-b8ed876b66a5e69fd4986385c734b1a83c567be7", text)
        self.assertIn(f"::{COMPONENT['sourceUrl']}", text)
        self.assertIn(f"sha256sums=('{'a' * 64}')", text)
        self.assertNotIn("$srcdir/source", text)
        self.assertNotIn("Rendered by the protected release job", text)
        self.assertIn("pkgver=1.0.4beta3", text)
        self.assertIn("pkgrel=5", text)

    def test_existing_sources_keep_their_checksums_after_the_tarball(self):
        recipe = (ROOT / "packages" / "meo-plasma-login-manager" / "PKGBUILD").read_text()
        component = dict(COMPONENT, repository="QwQdoge/meo-login-manager", expectedVersion="6.8.1-2")
        text = publish_aur.render_recipe(recipe, component)
        sources = re.search(r"^source=\((.*?)\)\n", text, re.M | re.S).group(1)
        sums = re.search(r"^sha256sums=\((.*?)\)\n", text, re.M | re.S).group(1)
        self.assertEqual(len(re.findall(r"'([^']+)'", sources)), 2)
        self.assertEqual(re.findall(r"'([0-9a-f]{64})'", sums)[0], "a" * 64)
        self.assertIn("meo-session.conf", sources)
        self.assertIn("pkgver=6.8.1", text)

    def test_unsupported_version_is_rejected(self):
        with self.assertRaises(publish_aur.AurError):
            publish_aur.split_version("nonsense")


class ComponentPolicyTest(unittest.TestCase):
    def test_every_aur_component_has_a_public_recipe_and_files(self):
        for name, extras in publish_aur.AUR_COMPONENTS.items():
            package = ROOT / "packages" / name
            self.assertTrue((package / "PKGBUILD").is_file(), name)
            for extra in extras:
                self.assertTrue((package / extra).exists(), f"{name}/{extra}")

    def test_private_source_components_are_never_published_to_the_aur(self):
        self.assertNotIn("meo-account", publish_aur.AUR_COMPONENTS)

    def test_aur_components_exist_in_the_latest_beta_manifest(self):
        latest = sorted((ROOT / "manifests" / "beta").glob("*.json"), key=lambda p: [int(x) for x in re.findall(r"\d+", p.name)])[-1]
        components = json.loads(latest.read_text())["components"]
        for name in publish_aur.AUR_COMPONENTS:
            self.assertIn(name, components)


class WorkflowContractTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.job = self.workflow.split("  publish-aur:", 1)[1]

    def test_aur_job_runs_only_after_a_full_stable_release(self):
        self.assertIn("needs: [sign-and-publish, remote-pacman-smoke]", self.job)
        self.assertIn("inputs.channel == 'stable' && inputs.candidate == ''", self.job)
        self.assertIn("environment: release", self.job)

    def test_missing_secret_skips_without_failing_and_key_is_never_echoed(self):
        self.assertIn("AUR_SSH_KEY is not configured", self.job)
        self.assertIn("exit 0", self.job)
        # The key may only be written to its 0600 file, never echoed or logged.
        self.assertNotRegex(self.job, r"echo[^\n]*\$\{?AUR_SSH_KEY")
        self.assertNotRegex(self.job, r"set -x|--debug|cat[^\n]*aur_key")
        self.assertEqual(len(re.findall(r"secrets\.", self.job)), 1)
        self.assertIn("secrets.AUR_SSH_KEY", self.job)

    def test_script_help_runs(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "publish_aur.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
