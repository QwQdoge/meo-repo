import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from input_method_capabilities import CapabilityError, load_catalog, resolve


CATALOG = ROOT / "manifests" / "input-method-capabilities.json"


class InputMethodCapabilityResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(CATALOG)

    def test_meo_managed_resolves_framework_engine_and_requested_bridges(self):
        plan = resolve(
            self.catalog,
            mode="meo-managed",
            framework="fcitx5",
            engines=["fcitx5.pinyin", "fcitx5.rime"],
            include_optional_roles=["toolkit-bridge"],
        )
        self.assertEqual(plan.framework, "fcitx5")
        self.assertEqual(plan.engines, ("fcitx5.pinyin", "fcitx5.rime"))
        self.assertIn("fcitx5", plan.packages)
        self.assertIn("fcitx5-qt", plan.packages)
        self.assertIn("fcitx5-gtk", plan.packages)
        self.assertIn("fcitx5-chinese-addons", plan.packages)
        self.assertIn("fcitx5-rime", plan.packages)
        self.assertNotIn("fcitx5-configtool", plan.packages)

    def test_self_managed_creates_no_meo_package_request(self):
        plan = resolve(self.catalog, mode="self-managed")
        self.assertIsNone(plan.framework)
        self.assertEqual(plan.engines, ())
        self.assertEqual(plan.packages, ())

    def test_self_managed_rejects_smuggled_framework_engine_or_optional_role(self):
        cases = (
            {"framework": "fcitx5"},
            {"engines": ["fcitx5.rime"]},
            {"include_optional_roles": ["configuration"]},
        )
        for extra in cases:
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(CapabilityError, "cannot request a Meo framework"):
                    resolve(self.catalog, mode="self-managed", **extra)

    def test_keyboard_only_also_stays_package_free(self):
        plan = resolve(self.catalog, mode="keyboard-only")
        self.assertIsNone(plan.framework)
        self.assertEqual(plan.packages, ())

    def test_meo_managed_requires_known_framework_and_engine(self):
        with self.assertRaisesRegex(CapabilityError, "requires a valid framework"):
            resolve(self.catalog, mode="meo-managed")
        with self.assertRaisesRegex(CapabilityError, "unknown input-method engine"):
            resolve(
                self.catalog,
                mode="meo-managed",
                framework="fcitx5",
                engines=["fcitx5.not-real"],
            )


if __name__ == "__main__":
    unittest.main()
