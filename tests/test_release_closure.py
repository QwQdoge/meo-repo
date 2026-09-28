import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_closure", ROOT / "scripts/validate_release_closure.py"
)
closure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closure)


class ReleaseClosureTests(unittest.TestCase):
    def write_recipe(self, root: Path, name: str, version: str, release: str) -> None:
        package = root / name
        package.mkdir(parents=True)
        (package / "PKGBUILD").write_text(
            f"pkgname={name}\npkgver={version}\npkgrel={release}\n",
            encoding="utf-8",
        )

    def fixture(self, root: Path):
        self.write_recipe(root, "core", "1.0", "2")
        self.write_recipe(root, "helper", "2.0", "1")
        catalog = {
            "generation": "next",
            "packages": {
                "core": {"profiles": ["recommended"], "requires": ["helper"]},
                "helper": {"profiles": []},
                "meta": {"profiles": ["recommended"], "requires": ["core"], "kind": "meta"},
            },
        }
        manifest = {
            "generation": "next",
            "profile": "recommended",
            "components": {
                "core": {"expectedVersion": "1.0-2"},
                "helper": {"expectedVersion": "2.0-1"},
            },
        }
        return manifest, catalog

    def test_full_release_requires_the_complete_catalog_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            recipes = Path(directory)
            manifest, catalog = self.fixture(recipes)
            closure.validate(manifest, catalog, recipes)
            del manifest["components"]["helper"]
            with self.assertRaisesRegex(ValueError, "helper"):
                closure.validate(manifest, catalog, recipes)

    def test_full_release_rejects_generation_and_recipe_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            recipes = Path(directory)
            manifest, catalog = self.fixture(recipes)
            manifest["generation"] = "old"
            with self.assertRaisesRegex(ValueError, "generation"):
                closure.validate(manifest, catalog, recipes)
            manifest["generation"] = "next"
            manifest["components"]["core"]["expectedVersion"] = "1.0-1"
            with self.assertRaisesRegex(ValueError, "recipe is 1.0-2"):
                closure.validate(manifest, catalog, recipes)

    def test_sparse_candidate_checks_only_the_package_being_built(self):
        with tempfile.TemporaryDirectory() as directory:
            recipes = Path(directory)
            manifest, catalog = self.fixture(recipes)
            manifest["components"]["helper"]["expectedVersion"] = "stale"
            closure.validate(manifest, catalog, recipes, candidate="core")
            manifest["components"]["core"]["expectedVersion"] = "stale"
            with self.assertRaisesRegex(ValueError, "core recipe"):
                closure.validate(manifest, catalog, recipes, candidate="core")

    def test_historical_stable_manifest_is_not_implicitly_releasable_from_current_main(self):
        result = subprocess.run(
            [
                sys.executable,
                ROOT / "scripts/validate_release_closure.py",
                ROOT / "manifests/stable/2026.09.3.json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release closure validation failed", result.stderr)

    def test_full_train_gets_private_account_source_only_when_required(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("id: source-requirements", workflow)
        self.assertIn('not candidate and "meo-account" in manifest.get("components", {})', workflow)
        self.assertIn("steps.source-requirements.outputs.needs_account == 'true'", workflow)
        self.assertIn(
            "MEO_ACCOUNT_SOURCE_SSH: ${{ steps.source-requirements.outputs.needs_account == 'true' && '1' || '0' }}",
            workflow,
        )
        self.assertNotIn("if: inputs.candidate == 'meo-account'", workflow)

    def test_workflow_requires_explicit_manifest_and_preflights_closure_twice(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        build = (ROOT / "ci/build-release.sh").read_text()
        publication = (ROOT / "ci/preflight-publication.sh").read_text()
        manifest_block = workflow.split("manifest:", 1)[1].split("candidate:", 1)[0]
        self.assertNotIn("default:", manifest_block)
        self.assertIn("validate_release_closure.py", build)
        self.assertIn("validate_release_closure.py", publication)


if __name__ == "__main__":
    unittest.main()
