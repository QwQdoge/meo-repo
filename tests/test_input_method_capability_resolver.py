import sys
import copy
import tempfile
from itertools import repeat
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from input_method_capabilities import CapabilityError, load_catalog, resolve, validate_catalog


CATALOG = ROOT / "manifests" / "input-method-capabilities.json"


class InputMethodCapabilityResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(CATALOG)

    def test_malformed_request_values_fail_with_capability_error(self):
        for kwargs in (
            {"mode": []}, {"engines": "fcitx5.rime"}, {"engines": [None]},
            {"engines": [["fcitx5.rime"]]}, {"engines": None},
            {"include_optional_roles": [["configuration"]]},
            {"include_optional_roles": "configuration"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(CapabilityError):
                resolve(self.catalog, **({"mode": "meo-managed", "framework": "fcitx5"} | kwargs))

    def test_request_iterators_are_consumed_only_to_the_limit(self):
        consumed = []
        def too_many():
            for index in range(1000):
                consumed.append(index)
                yield f"fcitx5.engine{index}"
        with self.assertRaises(CapabilityError):
            resolve(self.catalog, mode="meo-managed", framework="fcitx5", engines=too_many())
        self.assertEqual(len(consumed), 33)
        with self.assertRaises(CapabilityError):
            resolve(self.catalog, mode="meo-managed", framework="fcitx5",
                    include_optional_roles=repeat("configuration"))

    def test_catalog_schema_and_nested_types_are_enforced(self):
        paths = (
            (("schemaVersion",), True), (("schemaVersion",), 1.0),
            (("frameworks", 0, "unexpected"), "value"),
            (("frameworks", 0, "sessionModel"), "system-root"),
            (("frameworks", 0, "name"), ""),
            (("frameworks", 0, "modes"), ["meo-managed", "meo-managed"]),
            (("frameworks", 0, "packages", 0, "role"), []),
            (("engines", 0, "framework"), []),
            (("engines", 0, "languages"), [[]]),
            (("engines", 0, "languages"), ["zh", "zh"]),
        )
        for path, value in paths:
            catalog = copy.deepcopy(self.catalog)
            parent = catalog
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(CapabilityError):
                validate_catalog(catalog)

    def test_catalog_file_has_a_size_and_encoding_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_bytes(b" " * 262145)
            with self.assertRaises(CapabilityError):
                load_catalog(path)
            path.write_bytes(b"\xff")
            with self.assertRaises(CapabilityError):
                load_catalog(path)

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
