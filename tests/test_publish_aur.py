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


class FlattenTest(unittest.TestCase):
    def test_license_files_are_flattened_into_sources_and_the_recipe_uses_srcdir(self):
        recipe = (ROOT / "packages" / "meoui-qml" / "PKGBUILD").read_text()
        text = publish_aur.render_recipe(recipe, COMPONENT, {"Apache-2.0.txt": "b" * 64})
        self.assertIn("'Apache-2.0.txt'", text)
        self.assertIn("'" + "b" * 64 + "'", text)
        self.assertNotIn("$startdir/licenses", text)
        self.assertIn('"$srcdir/$notice"', text)

    def test_rendered_repository_has_no_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = sorted((ROOT / "manifests" / "beta").glob("*.json"), key=lambda p: [int(x) for x in re.findall(r"\d+", p.name)])[-1]
            try:
                target = publish_aur.render_package(manifest, "meoui-qml", Path(tmp))
            except subprocess.CalledProcessError as exc:
                self.fail("makepkg --printsrcinfo failed: " + str(exc.stderr))
            except FileNotFoundError:
                self.skipTest("makepkg is not installed")
            self.assertEqual([p.name for p in target.iterdir() if p.is_dir()], [])


class BinRecipeTest(unittest.TestCase):
    INFO = """pkgdesc = Meo Account broker
url = https://github.com/QwQdoge/MeoArch-account
arch = x86_64
license = GPL-3.0-or-later
backup = etc/meo-account/broker.conf
depend = qt6-base
depend = meoui-qml>=1.0.4beta1
"""

    def test_bin_recipe_repackages_the_published_package_and_provides_the_component(self):
        component = {"expectedVersion": "0.1.0-11"}
        text = publish_aur.render_bin_recipe(
            "meo-account", component, publish_aur.parse_pkginfo(self.INFO),
            "meo-account-0.1.0-11-x86_64.pkg.tar.zst",
            "https://packages.meoarch.org/meo/os/x86_64/meo-account-0.1.0-11-x86_64.pkg.tar.zst", "c" * 64)
        self.assertIn("pkgname=meo-account-bin", text)
        self.assertIn("provides=('meo-account=0.1.0-11')", text)
        self.assertIn("conflicts=('meo-account')", text)
        self.assertIn("depends=('qt6-base' 'meoui-qml>=1.0.4beta1')", text)
        self.assertIn("backup=('etc/meo-account/broker.conf')", text)
        self.assertIn("sha256sums=('" + "c" * 64 + "')", text)
        self.assertIn("--exclude=.PKGINFO", text)

    def test_private_source_component_is_published_only_as_a_binary_repackage(self):
        self.assertIn("meo-account", publish_aur.BIN_COMPONENTS)
        self.assertNotIn("meo-account", publish_aur.AUR_COMPONENTS)


class ComponentPolicyTest(unittest.TestCase):
    def test_every_aur_component_has_a_public_recipe_and_files(self):
        for name, extras in publish_aur.AUR_COMPONENTS.items():
            package = ROOT / "packages" / name
            self.assertTrue((package / "PKGBUILD").is_file(), name)
            for extra in extras:
                self.assertTrue((package / extra).exists(), f"{name}/{extra}")

    def test_private_source_components_are_never_published_as_source_packages(self):
        self.assertNotIn("meo-account", publish_aur.AUR_COMPONENTS)

    def test_aur_components_exist_in_the_latest_beta_manifest(self):
        latest = sorted((ROOT / "manifests" / "beta").glob("*.json"), key=lambda p: [int(x) for x in re.findall(r"\d+", p.name)])[-1]
        components = json.loads(latest.read_text())["components"]
        for name in publish_aur.AUR_COMPONENTS:
            self.assertIn(name, components)


class WorkflowContractTest(unittest.TestCase):
    def setUp(self):
        workflows = ROOT / ".github" / "workflows"
        self.release = (workflows / "release.yml").read_text()
        self.job = (workflows / "publish-aur.yml").read_text()
        self.caller = self.release.split("  publish-aur:", 1)[1]

    def test_release_calls_the_aur_workflow_only_after_a_full_stable_release(self):
        self.assertIn("needs: [sign-and-publish, remote-pacman-smoke]", self.caller)
        self.assertIn("inputs.channel == 'stable' && inputs.candidate == ''", self.caller)
        self.assertIn("uses: ./.github/workflows/publish-aur.yml", self.caller)

    def test_aur_workflow_runs_in_the_protected_release_environment_and_can_be_dispatched(self):
        self.assertIn("environment: release", self.job)
        self.assertIn("workflow_call:", self.job)
        self.assertIn("workflow_dispatch:", self.job)

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
