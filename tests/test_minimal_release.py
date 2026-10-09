from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MinimalReleaseTests(unittest.TestCase):
    def test_minimal_manifest_and_artifacts_require_the_whole_minimal_set(self):
        script = (ROOT / "ci/validate-minimal-artifacts.sh").read_text()
        self.assertIn("meoui-qml", script)
        self.assertIn("meo-icons", script)
        self.assertIn("meo-plasma-login-manager", script)
        self.assertIn("meo-desktop", script)
        self.assertIn("meo-core-meta", script)

    def test_minimal_native_recipes_do_not_emit_unreviewed_debug_packages(self):
        for name in ("meoui-qml", "meo-icons", "meo-plasma-login-manager", "meo-desktop"):
            recipe = (ROOT / f"packages/{name}/PKGBUILD").read_text()
            self.assertIn("options=('!debug')", recipe, name)

    def test_non_root_package_ownership_blocks_signing(self):
        signer = (ROOT / "ci/sign-packages.sh").read_text()
        self.assertIn("tar --numeric-owner", signer)
        self.assertIn("non-root ownership", signer)

    def test_namcap_errors_block_even_when_command_returns_zero(self):
        script = (ROOT / "ci/check-built-packages.sh").read_text()
        self.assertIn("namcap", script)
        self.assertIn("^E:", script)

    def test_package_listing_checks_consume_large_output(self):
        script = (ROOT / "ci/check-built-packages.sh").read_text()
        self.assertIn("pacman -Qlp", script)
        self.assertIn("package_files", script)

    def test_repository_order_checks_exact_set_and_parser_failure(self):
        script = (ROOT / "ci/remote-smoke.sh").read_text()
        self.assertIn("pacman-conf --repo-list", script)
        self.assertIn("expected_repositories", script)

    def test_source_symlink_is_allowed_only_inside_extraction_root(self):
        extractor = (ROOT / "scripts/extract_source.py").read_text()
        self.assertIn("commonpath", extractor)
        self.assertIn("symlink", extractor.lower())

    def test_reviewed_source_allowlist_excludes_unused_vendor_symlink_cycle(self):
        renderer = (ROOT / "scripts/render_candidate.py").read_text()
        self.assertIn("reviewed", renderer.lower())

    def test_minimal_control_packages_ship_declared_mit_license(self):
        for name in ("meo-core-meta", "meo-channel-beta", "meo-channel-stable", "meo-mirrorlist"):
            recipe = (ROOT / f"packages/{name}/PKGBUILD").read_text()
            self.assertIn("MIT", recipe, name)

    def test_runtime_packages_ship_complete_license_sets(self):
        desktop = (ROOT / "packages/meo-desktop/PKGBUILD").read_text()
        for required in (
            "GPL-2.0-or-later.txt",
            "Material-Color-Utilities-Apache-2.0.txt",
            "DankMaterialShell-MIT.txt",
            "OFL-Roboto.txt",
            "OFL-Comfortaa.txt",
        ):
            self.assertIn(required, desktop)

        runtime = (ROOT / "packages/meo-kde-runtime/PKGBUILD").read_text()
        self.assertIn("GPL-2.0-or-later", runtime)
        self.assertIn("Apache-2.0", runtime)
        self.assertIn("GPL-2.0-or-later.txt", runtime)
        self.assertIn("DankMaterialShell-MIT.txt", runtime)
        self.assertIn("Material-Color-Utilities-Apache-2.0.txt", runtime)

        settings = (ROOT / "packages/meo-settings/PKGBUILD").read_text()
        self.assertIn("source/LICENSE", settings)
        self.assertIn("usr/share/licenses/$pkgname/LICENSE", settings)

    def test_desktop_recipe_is_display_manager_neutral(self):
        recipe = (ROOT / "packages/meo-desktop/PKGBUILD").read_text()
        depends = recipe.split("makedepends=", 1)[0]
        self.assertNotIn("'meo-plasma-login-manager'", depends)
        self.assertNotIn("'plasma-login-manager'", depends)
        self.assertNotIn("'sddm'", depends)
        self.assertNotIn("sddm.conf.d", recipe)
        self.assertNotIn("usr/share/sddm", recipe)

    def test_desktop_recipe_installs_all_supported_meo_topbar_applets(self):
        recipe = (ROOT / "packages/meo-desktop/PKGBUILD").read_text()
        for applet in (
            "org.meo.topbar",
            "org.meo.timecenter",
            "org.meo.notifications",
            "org.meo.time-notifications",
            "org.meo.shelf",
            "org.meo.toptasks",
        ):
            self.assertIn(applet, recipe)


if __name__ == "__main__":
    unittest.main()
