import json
import io
import re
import subprocess
import sys
import tempfile
import tarfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from overlay import stable_supersedes_beta
from artifact_manifest import CONTROL_PACKAGES, create as create_artifact_contract, verify as verify_artifact_contract
from stage_component import safe_extract
from render_keyring_recipe import render as render_keyring_recipe
from overlay_cleanup import cleanup_candidates, database_versions
from verify_manifest_sources import verify as verify_manifest_sources
from verify_package_metadata import verify as verify_package_metadata

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
        self.assertIn("meo-account", catalog["packages"])
        self.assertEqual(catalog["channelPackages"]["beta"], "meo-channel-beta")
        self.assertEqual(
            (ROOT / "manifests/package-catalog.json").read_bytes(),
            (ROOT / "packages/meo-release/package-catalog.json").read_bytes(),
        )
        self.assertEqual(
            (ROOT / "manifests/application-catalog.json").read_bytes(),
            (ROOT / "packages/meo-release/application-catalog.json").read_bytes(),
        )

    def test_application_catalog_is_opt_in_and_arch_official_for_installer(self):
        catalog = json.loads((ROOT / "manifests/application-catalog.json").read_text())
        self.assertEqual(catalog["policy"]["thirdPartyDefault"], "opt-in")
        self.assertTrue(catalog["applications"])
        for application in catalog["applications"]:
            self.assertEqual(application["installer"]["source"], "arch-official")
            if application["installer"]["tier"] == "third-party":
                self.assertEqual(application["installer"]["profiles"], [])

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

    def test_static_package_sources_use_real_checksums(self):
        for package in ("meo-channel-stable", "meo-channel-beta", "meo-mirrorlist", "meo-release"):
            recipe = (ROOT / "packages" / package / "PKGBUILD").read_text()
            self.assertNotIn("SKIP", recipe)

    def test_meta_packages_cover_core_apps_and_recommended_profiles(self):
        expected = {
            "meo-core-meta": ("meo-release", "meo-desktop"),
            "meo-apps-meta": ("meo-account", "meo-settings", "omnistore-bin", "flatpak"),
            "meo-recommended-meta": ("meo-core-meta", "meo-apps-meta"),
        }
        for package, dependencies in expected.items():
            recipe = (ROOT / "packages" / package / "PKGBUILD").read_text()
            for dependency in dependencies:
                self.assertIn(f"'{dependency}'", recipe)

    def test_omnistore_package_owns_system_account_and_cold_callback_contract(self):
        recipe = (ROOT / "packages/omnistore-bin/PKGBUILD").read_text()
        manifest = json.loads(
            (ROOT / "packages/omnistore-bin/org.meo.OmniStore.json").read_text()
        )
        desktop = (ROOT / "packages/omnistore-bin/omnistore.desktop").read_text()
        self.assertIn("'libsecret'", recipe)
        self.assertIn("org.meo.OmniStore.json", recipe)
        self.assertEqual(manifest["executables"], ["/opt/omnistore/frontend"])
        self.assertEqual(manifest["redirectUri"], "omnistore://auth/callback")
        self.assertIn("Exec=/usr/bin/omnistore %u", desktop)
        self.assertIn("MimeType=x-scheme-handler/omnistore;", desktop)

    def test_stable_artifact_contract_is_complete_and_hash_bound(self):
        manifest_path = ROOT / "manifests/stable/2026.08.json"
        manifest = json.loads(manifest_path.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packages = root / "packages"
            packages.mkdir()
            for name, metadata in manifest["components"].items():
                (packages / f"{name}-{metadata['expectedVersion']}-x86_64.pkg.tar.zst").write_bytes(name.encode())
            for name in CONTROL_PACKAGES:
                recipe = (ROOT / "packages" / name / "PKGBUILD").read_text()
                version = next(line.split("=", 1)[1] for line in recipe.splitlines() if line.startswith("pkgver="))
                release = next(line.split("=", 1)[1] for line in recipe.splitlines() if line.startswith("pkgrel="))
                (packages / f"{name}-{version}-{release}-any.pkg.tar.zst").write_bytes(name.encode())
            contract = root / "artifacts.json"
            create_artifact_contract(manifest_path, packages, contract, "stable")
            verify_artifact_contract(contract, manifest_path, packages)
            target = next(packages.iterdir())
            target.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                verify_artifact_contract(contract, manifest_path, packages)

    def test_source_extractor_rejects_archive_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            payload = root / "payload"
            payload.write_text("unsafe")
            with tarfile.open(archive, "w:gz") as bundle:
                bundle.add(payload, arcname="../escape")
            with self.assertRaises(ValueError):
                safe_extract(archive, root / "output")

    def test_keyring_build_recipe_is_bound_to_public_payload_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            context = Path(directory)
            (context / "files").mkdir()
            (context / "PKGBUILD").write_text("sha256sums=('SKIP' 'SKIP' 'SKIP')\n")
            for name in ("meo.gpg", "meo-trusted", "meo-revoked"):
                (context / "files" / name).write_bytes(name.encode())
            render_keyring_recipe(context)
            rendered = (context / "PKGBUILD").read_text()
            self.assertNotIn("SKIP", rendered)
            self.assertEqual(rendered.count("'"), 6)

    def test_overlay_cleanup_uses_actual_repository_records(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "repo.db.tar.gz"
            with tarfile.open(database, "w:gz") as bundle:
                payload = b"%NAME%\nmeoui-qml\n\n%VERSION%\n1.7.0-1\n"
                info = tarfile.TarInfo("meoui-qml-1.7.0-1/desc")
                info.size = len(payload)
                bundle.addfile(info, io.BytesIO(payload))
            self.assertEqual(database_versions(database), {"meoui-qml": "1.7.0-1"})
        stable = {"meoui-qml": "1.7.0-1", "meo-settings": "1.4.0-1"}
        beta = {"meoui-qml": "1.7.0beta1-1", "meo-settings": "1.5.0beta1-1"}
        ordering = {
            ("1.7.0-1", "1.7.0beta1-1"): 1,
            ("1.4.0-1", "1.5.0beta1-1"): -1,
        }
        self.assertEqual(cleanup_candidates(stable, beta, lambda left, right: ordering[(left, right)]),
                         ["meoui-qml"])

    def test_manifest_source_tag_and_url_must_match_pinned_commit(self):
        commit = "a" * 40
        manifest = {"components": {"meoui-qml": {
            "repository": "QwQdoge/MeoUI", "tag": "v1.2.3", "commit": commit,
            "sourceUrl": f"https://github.com/QwQdoge/MeoUI/archive/{commit}.tar.gz",
            "sourceLayout": "source",
        }}}
        verify_manifest_sources(manifest, lambda repository, tag: commit)
        with self.assertRaises(ValueError):
            verify_manifest_sources(manifest, lambda repository, tag: "b" * 40)

    def test_protected_publication_is_globally_serialized_and_secrets_are_step_scoped(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("group: meo-repository-publish", workflow)
        sign_job = workflow.split("  sign-and-publish:", 1)[1].split("  remote-pacman-smoke:", 1)[0]
        before_steps = sign_job.split("    steps:", 1)[0]
        self.assertNotIn("AWS_ACCESS_KEY_ID", before_steps)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", before_steps)
        self.assertNotRegex(workflow, r"uses: actions/[^@\s]+@v\d")
        self.assertGreaterEqual(len(re.findall(r"uses: actions/[^@\s]+@[0-9a-f]{40}", workflow)), 5)
        self.assertNotRegex(workflow, r"run:[^\n]*\$\{\{\s*inputs\.")
        self.assertLess(workflow.index("id: publication-preflight"), workflow.index("Import revocable CI signing subkey"))
        self.assertIn("MEO_PUBLICATION_PREFLIGHT_SHA256", workflow)

    def test_beta_cleanup_purges_all_mutable_database_aliases(self):
        cleanup = (ROOT / "ci/cleanup-beta-overlay.sh").read_text()
        self.assertNotIn("mapfile -t removals < <(", cleanup)
        self.assertIn('removal_output="$(python3', cleanup)
        for suffix in ("db", "db.sig", "db.tar.gz", "db.tar.gz.sig",
                       "files", "files.sig", "files.tar.gz", "files.tar.gz.sig"):
            self.assertIn(f"meo-beta.{suffix}", cleanup)

    def test_protected_signer_checks_internal_package_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packages = root / "packages"
            packages.mkdir()
            filename = "meoui-qml-1.0.2-2-x86_64.pkg.tar.gz"
            package = packages / filename
            metadata = b"pkgname = meoui-qml\npkgver = 1.0.2-2\narch = x86_64\n"
            with tarfile.open(package, "w:gz") as bundle:
                info = tarfile.TarInfo(".PKGINFO")
                info.size = len(metadata)
                bundle.addfile(info, io.BytesIO(metadata))
            contract = root / "artifacts.json"
            contract.write_text(json.dumps({"packages": [{
                "name": "meoui-qml", "version": "1.0.2-2", "filename": filename,
            }]}))
            verify_package_metadata(contract, packages)
            contract.write_text(json.dumps({"packages": [{
                "name": "meo-settings", "version": "1.0.2-2", "filename": filename,
            }]}))
            with self.assertRaises(ValueError):
                verify_package_metadata(contract, packages)

if __name__ == "__main__":
    unittest.main()
