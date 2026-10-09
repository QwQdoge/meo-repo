import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class OmniStoreNativeContractTests(unittest.TestCase):
    def setUp(self):
        self.recipe = (ROOT / "packages/omnistore-bin/PKGBUILD").read_text()
        self.desktop = (ROOT / "packages/omnistore-bin/omnistore.desktop").read_text()
        self.account = json.loads(
            (ROOT / "packages/omnistore-bin/org.meo.OmniStore.json").read_text()
        )

    def test_release_is_native_only(self):
        self.assertIn("release_bundle/omnistore-native", self.recipe)
        self.assertIn("/usr/lib/omnistore/omnistore-native", self.recipe)
        self.assertIn("omnistore-task.service", self.recipe)
        self.assertIn("/usr/bin/omnistore-daemon", self.recipe)
        self.assertIn("retired Flutter frontend", self.recipe)
        self.assertNotIn("patchelf --remove-rpath", self.recipe)
        self.assertNotIn("exec /usr/lib/omnistore/frontend", self.recipe)

    def test_canonical_desktop_identity_is_used(self):
        self.assertIn("Icon=org.meo.OmniStore", self.desktop)
        self.assertIn("Exec=/usr/bin/omnistore %u", self.desktop)
        self.assertIn("MimeType=x-scheme-handler/omnistore;", self.desktop)
        self.assertIn("org.meo.OmniStore.desktop", self.recipe)
        self.assertIn("org.meo.OmniStore.svg", self.recipe)

    def test_account_client_targets_native_binary_with_system_ai_capability(self):
        self.assertEqual(self.account["id"], "org.meo.OmniStore")
        self.assertEqual(
            self.account["executables"],
            ["/usr/lib/omnistore/omnistore-native"],
        )
        self.assertEqual(self.account["redirectUri"], "omnistore://auth/callback")
        self.assertEqual(self.account["capabilities"], ["local_ai"])

    def test_runtime_dependencies_follow_qml_stack(self):
        for dependency in (
            "qt6-base",
            "qt6-declarative",
            "meoui-qml>=1.0.4beta1",
            "meo-kde-runtime>=0.4.0beta3",
            "pyalpm",
        ):
            self.assertIn(f"'{dependency}'", self.recipe)
        for retired in ("gtk3", "libdbusmenu-gtk3", "libayatana-appindicator"):
            self.assertNotIn(f"'{retired}'", self.recipe)


if __name__ == "__main__":
    unittest.main()
