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
