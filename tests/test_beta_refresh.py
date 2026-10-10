import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage_component
import validate_manifest


class BetaRefreshTests(unittest.TestCase):
    def test_login_preextracted_context_contains_session_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            version = stage_component.recipe_version(
                (ROOT / "packages/meo-plasma-login-manager/PKGBUILD").read_text())
            manifest.write_text(json.dumps({"components": {
                "meo-plasma-login-manager": {
                    "expectedVersion": version, "sourceUrl": "https://example.test/source",
                    "sourceSha256": "0" * 64}}}))

            def download(url, checksum, destination):
                with tarfile.open(destination, "w"):
                    pass

            context = root / "context"
            with patch.object(stage_component, "download", download):
                stage_component.stage(manifest, "meo-plasma-login-manager", context)
            self.assertEqual((context / "src/meo-session.conf").read_bytes(),
                             (ROOT / "packages/meo-plasma-login-manager/meo-session.conf").read_bytes())

    def test_optional_applications_keep_unknown_components_fail_closed(self):
        payload = json.loads((ROOT / "manifests/beta/2026.10-beta.1.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload))
            validate_manifest.main(str(path))
            payload["components"]["unreviewed-app"] = payload["components"]["meo-ai"]
            path.write_text(json.dumps(payload))
            with self.assertRaises(SystemExit):
                validate_manifest.main(str(path))


if __name__ == "__main__":
    unittest.main()
