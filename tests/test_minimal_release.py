import io
import json
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
