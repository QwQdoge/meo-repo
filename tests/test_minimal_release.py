import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from artifact_manifest import control_packages, create, verify, literal_recipe_version
from stage_component import safe_extract


class MinimalReleaseTests(unittest.TestCase):
    def test_namcap_errors_block_even_when_command_returns_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "candidate.pkg.tar.zst").touch()
            command = root / "namcap"
            command.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_REPORT"\nexit "$TEST_STATUS"\n')
            command.chmod(0o755)
            archive = root / "bsdtar"
            archive.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_BSDTAR_REPORT"\nexit "$TEST_BSDTAR_STATUS"\n')
            archive.chmod(0o755)
            for report, status, valid in (("candidate E: missing dependency", 0, False),
                                          ("candidate W: redundant dependency", 0, True),
                                          ("", 1, False)):
                with self.subTest(report=report, status=status):
                    result = subprocess.run(["bash", ROOT / "ci/check-package-metadata.sh", root],
                                            env=dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                                                     TEST_REPORT=report, TEST_STATUS=str(status),
                                                     TEST_BSDTAR_REPORT="-rw-r--r-- 0 0 0 1 fixture",
                                                     TEST_BSDTAR_STATUS="0"), capture_output=True)
                    self.assertEqual(result.returncode == 0, valid, result.stderr)

    def test_non_root_package_ownership_blocks_signing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "candidate.pkg.tar.zst").touch()
            namcap = root / "namcap"
            namcap.write_text("#!/bin/sh\nexit 0\n")
            namcap.chmod(0o755)
            bsdtar = root / "bsdtar"
            bsdtar.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_BSDTAR_REPORT"\n')
            bsdtar.chmod(0o755)
            for report, valid in (
                ("-rw-r--r-- 0 0 0 1 usr/share/root-owned", True),
                ("drwxr-xr-x 0 1000 1000 0 usr/", False),
                ("-rw-r--r-- 0 0 1000 1 etc/group-owned", False),
            ):
                with self.subTest(report=report):
                    result = subprocess.run(
                        ["bash", ROOT / "ci/check-package-metadata.sh", root],
                        env=dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                                 TEST_BSDTAR_REPORT=report),
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode == 0, valid, result.stderr)
                    if not valid:
                        self.assertIn("non-root ownership", result.stderr)

    def test_minimal_control_packages_ship_declared_mit_license(self):
        for package in control_packages(self.manifest()):
            license_text = (ROOT / "packages" / package / "LICENSE").read_text()
            self.assertIn("Permission is hereby granted", license_text)
            recipe = (ROOT / "packages" / package / "PKGBUILD").read_text()
            self.assertIn('"$pkgdir/usr/share/licenses/$pkgname/LICENSE"', recipe)

    def test_minimal_native_recipes_do_not_emit_unreviewed_debug_packages(self):
        for package in ("meoui-qml", "meo-desktop"):
            recipe = (ROOT / "packages" / package / "PKGBUILD").read_text()
            self.assertIn("options=('!debug'", recipe)
        meoui_recipe = (ROOT / "packages/meoui-qml/PKGBUILD").read_text()
        self.assertIn("'staticlibs'", meoui_recipe)
        self.assertIn("'qt6-shadertools'", meoui_recipe)
        build_script = (ROOT / "ci/build-release.sh").read_text()
        self.assertIn('makepkg --config "$output/makepkg.conf" --syncdeps', build_script)
        self.assertIn('makepkg --config "$output/makepkg.conf" --packagelist', build_script)
        self.assertIn('SOURCE_DATE_EPOCH="$source_date_epoch" makepkg', build_script)
        self.assertIn('sparse candidate requires a positive sourceDateEpoch', build_script)

    def test_runtime_packages_ship_complete_license_sets(self):
        meoui = (ROOT / "packages/meoui-qml/PKGBUILD").read_text()
        self.assertIn("license=('MIT' 'Apache-2.0' 'OFL-1.1')", meoui)
        for required in (
            "THIRD_PARTY_NOTICES.md",
            "Apache-2.0.txt",
            "DankMaterialShell-MIT.txt",
            "OFL-Roboto.txt",
            "OFL-Comfortaa.txt",
        ):
            self.assertIn(required, meoui)

        desktop = (ROOT / "packages/meo-desktop/PKGBUILD").read_text()
        for declared in (
            "GPL-3.0-or-later",
            "GPL-2.0-or-later",
            "MIT",
            "Apache-2.0",
            "OFL-1.1",
        ):
            self.assertIn(declared, desktop)
        for required in (
            "THIRD_PARTY_NOTICES.md",
            "Material-Symbols-Apache-2.0.txt",
            "Material-Color-Utilities-Apache-2.0.txt",
            "DankMaterialShell-MIT.txt",
            "OFL-Roboto.txt",
            "OFL-Comfortaa.txt",
        ):
            self.assertIn(required, desktop)

        runtime = (ROOT / "packages/meo-kde-runtime/PKGBUILD").read_text()
        self.assertIn("GPL-2.0-or-later", runtime)
        self.assertIn("Apache-2.0", runtime)
        self.assertIn("DankMaterialShell-MIT.txt", runtime)
        self.assertIn("Material-Color-Utilities-Apache-2.0.txt", runtime)

        settings = (ROOT / "packages/meo-settings/PKGBUILD").read_text()
        self.assertIn("source/LICENSE", settings)
        self.assertIn("usr/share/licenses/$pkgname/LICENSE", settings)

    def test_desktop_recipe_uses_plasma_login_manager_without_sddm_payload(self):
        recipe = (ROOT / "packages/meo-desktop/PKGBUILD").read_text()
        self.assertIn("'plasma-login-manager'", recipe)
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

    def test_repository_order_checks_exact_set_and_parser_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = root / "pacman-conf"
            command.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_REPOS"\nexit "$TEST_STATUS"\n')
            command.chmod(0o755)
            for channel, repos, status, valid in (
                ("stable", "core\nextra\nmeo", 0, True),
                ("beta", "core\nextra\nmeo-beta\nmeo", 0, True),
                ("stable", "core\nextra", 0, False),
                ("stable", "meo\nmeo-beta", 0, False),
                ("stable", "meo\nmeo", 0, False),
                ("beta", "meo\nmeo-beta", 0, False),
                ("beta", "meo-beta\nmeo\nmeo-unknown", 0, False),
                ("stable", "meo", 42, False),
            ):
                with self.subTest(channel=channel, repos=repos, status=status):
                    env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                               TEST_REPOS=repos, TEST_STATUS=str(status))
                    result = subprocess.run(["bash", ROOT / "ci/check-repository-order.sh", "/unused", channel],
                                            env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, valid, result.stderr)

    def test_package_listing_checks_consume_large_output(self):
        script = (ROOT / "ci/smoke-installed.sh").read_text()
        commands = [line for line in script.splitlines() if line.startswith("pacman -Qlq ")]
        self.assertEqual(len(commands), 3)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = root / "pacman"
            command.write_text(f'#!{sys.executable}\nimport sys\n'
                               'print("/MeoUI/qmldir\\n/icons/MeoSymbols/index.theme\\n/plasma/look-and-feel/test")\n'
                               'sys.stdout.write("/unrelated/file\\n" * 100000)\n')
            command.chmod(0o755)
            result = subprocess.run(["bash", "-euo", "pipefail", "-c", "\n".join(commands)],
                                    env=dict(os.environ, PATH=f"{root}:{os.environ['PATH']}"), capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def manifest(self):
        return {"schemaVersion": 1, "architecture": "x86_64", "profile": "minimal", "components": {
            name: {"repository": "QwQdoge/source", "tag": "v1.0.0", "commit": "a" * 40,
                   "sourceUrl": "https://example.invalid/" + "a" * 40 + ".tar.gz",
                   "sourceSha256": "b" * 64, "expectedVersion": literal_recipe_version(name)}
            for name in ("meoui-qml", "meo-icons", "meo-desktop")}}

    def test_minimal_manifest_and_artifacts_require_the_whole_minimal_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            data = self.manifest()
            manifest.write_text(json.dumps(data))
            result = subprocess.run([sys.executable, ROOT / "scripts/validate_manifest.py", manifest], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            packages = root / "packages"
            packages.mkdir()
            for name in [*data["components"], *control_packages(data)]:
                (packages / f"{name}-{literal_recipe_version(name)}-any.pkg.tar.zst").write_bytes(name.encode())
            contract = root / "artifacts.json"
            create(manifest, packages, contract, "stable")
            verify(contract, manifest, packages)
            self.assertNotIn("meo-apps-meta", control_packages(data))
            next(packages.glob("meo-desktop-*.pkg.tar.zst")).unlink()
            with self.assertRaises(ValueError):
                create(manifest, packages, contract, "stable")
            del data["components"]["meo-desktop"]
            manifest.write_text(json.dumps(data))
            result = subprocess.run([sys.executable, ROOT / "scripts/validate_manifest.py", manifest], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_source_symlink_is_allowed_only_inside_extraction_root(self):
        for link, allowed in (("real.svg", True), ("../../escape", False), ("/etc/passwd", False)):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "source.tar.gz"
                with tarfile.open(archive, "w:gz") as bundle:
                    file = tarfile.TarInfo("source/icons/real.svg")
                    file.size = 4
                    bundle.addfile(file, io.BytesIO(b"icon"))
                    symlink = tarfile.TarInfo("source/icons/alias.svg")
                    symlink.type, symlink.linkname = tarfile.SYMTYPE, link
                    bundle.addfile(symlink)
                if allowed:
                    safe_extract(archive, root / "out")
                    self.assertEqual((root / "out/icons/alias.svg").read_bytes(), b"icon")
                else:
                    with self.assertRaises(ValueError):
                        safe_extract(archive, root / "out")

    def test_reviewed_source_allowlist_excludes_unused_vendor_symlink_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                file = tarfile.TarInfo("source/native/CMakeLists.txt")
                file.size = 5
                bundle.addfile(file, io.BytesIO(b"cmake"))
                link = tarfile.TarInfo("source/vendor/cycle")
                link.type, link.linkname = tarfile.SYMTYPE, "cycle"
                bundle.addfile(link)
            safe_extract(archive, root / "out", ["native"])
            self.assertEqual((root / "out/native/CMakeLists.txt").read_bytes(), b"cmake")
            self.assertFalse((root / "out/vendor").exists())
            with self.assertRaises(ValueError):
                safe_extract(archive, root / "bad", ["../outside"])
