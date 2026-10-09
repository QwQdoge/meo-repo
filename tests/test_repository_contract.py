import json
from pathlib import Path

import repository_contract_suite as _suite


ROOT = Path(__file__).parents[1]


class RepositoryContractTests(_suite.RepositoryContractTests):
    """Discovery wrapper for the shared repository contract suite.

    Keep the large stable suite byte-for-byte in repository_contract_suite.py;
    this wrapper owns contracts that intentionally changed with the native-only
    OmniStore migration.
    """

    def test_omnistore_package_owns_system_account_and_cold_callback_contract(self):
        recipe = (ROOT / "packages/omnistore-bin/PKGBUILD").read_text()
        manifest = json.loads(
            (ROOT / "packages/omnistore-bin/org.meo.OmniStore.json").read_text()
        )
        desktop = (ROOT / "packages/omnistore-bin/omnistore.desktop").read_text()

        self.assertIn("'libsecret'", recipe)
        self.assertIn("org.meo.OmniStore.json", recipe)
        self.assertEqual(
            manifest["executables"],
            ["/usr/lib/omnistore/omnistore-native"],
        )
        self.assertEqual(manifest["redirectUri"], "omnistore://auth/callback")
        self.assertEqual(manifest["capabilities"], ["local_ai"])
        self.assertIn("Exec=/usr/bin/omnistore %u", desktop)
        self.assertIn("Icon=org.meo.OmniStore", desktop)
        self.assertIn("MimeType=x-scheme-handler/omnistore;", desktop)
        self.assertIn("license=('GPL-3.0-only')", recipe)
        self.assertIn("release_bundle/LICENSE", recipe)
        self.assertIn("usr/share/licenses/$pkgname/LICENSE", recipe)
        self.assertIn("release_bundle/omnistore-native", recipe)
        self.assertIn("omnistore-task.service", recipe)
        self.assertIn("org.meo.OmniStore.desktop", recipe)
        self.assertNotIn("patchelf --remove-rpath", recipe)
        self.assertNotIn("exec /usr/lib/omnistore/frontend", recipe)
        self.assertNotIn("/opt/omnistore", recipe)


if __name__ == "__main__":
    import unittest
    unittest.main()
