import json
import re
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG = REPO_ROOT / "manifests/input-method-capabilities.json"
SCHEMA = REPO_ROOT / "manifests/input-method-capabilities.schema.json"


ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9@._+:-]{0,127}$")
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")


class InputMethodCapabilityCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_version_and_top_level_shape(self):
        self.assertEqual(self.catalog["schemaVersion"], 1)
        self.assertEqual(set(self.catalog), {"schemaVersion", "frameworks", "engines"})
        self.assertEqual(
            self.schema["$id"],
            "https://meoarch.org/schemas/input-method-capabilities/v1",
        )
        self.assertFalse(self.schema["additionalProperties"])

    def test_framework_ids_and_packages_are_unambiguous(self):
        frameworks = self.catalog["frameworks"]
        ids = [framework["id"] for framework in frameworks]
        self.assertEqual(len(ids), len(set(ids)))

        for framework in frameworks:
            with self.subTest(framework=framework["id"]):
                self.assertRegex(framework["id"], ID_RE)
                self.assertEqual(framework["sessionModel"], "wayland-user-session")
                self.assertTrue(framework["packages"])
                self.assertIn("meo-managed", framework["modes"])
                self.assertIn("self-managed", framework["modes"])

                package_names = [entry["name"] for entry in framework["packages"]]
                self.assertEqual(len(package_names), len(set(package_names)))
                for package in framework["packages"]:
                    self.assertRegex(package["name"], PACKAGE_RE)
                    self.assertNotIn("=", package["name"], "catalog must not pin package versions")
                    self.assertIn(
                        package["role"],
                        {"framework", "toolkit-bridge", "configuration", "engine", "integration"},
                    )
                    self.assertIs(type(package["required"]), bool)

    def test_engines_reference_known_frameworks_and_trusted_sources(self):
        framework_ids = {framework["id"] for framework in self.catalog["frameworks"]}
        engine_ids = [engine["id"] for engine in self.catalog["engines"]]
        self.assertEqual(len(engine_ids), len(set(engine_ids)))

        for engine in self.catalog["engines"]:
            with self.subTest(engine=engine["id"]):
                self.assertRegex(engine["id"], ID_RE)
                self.assertIn(engine["framework"], framework_ids)
                self.assertEqual(engine["sourcePolicy"], "configured-signed-repository")
                self.assertTrue(engine["languages"])
                self.assertEqual(len(engine["languages"]), len(set(engine["languages"])))
                for language in engine["languages"]:
                    self.assertRegex(language, LANGUAGE_RE)

                package_names = [entry["name"] for entry in engine["packages"]]
                self.assertEqual(len(package_names), len(set(package_names)))
                self.assertTrue(any(entry["required"] for entry in engine["packages"]))
                for package in engine["packages"]:
                    self.assertRegex(package["name"], PACKAGE_RE)
                    self.assertEqual(package["role"], "engine")
                    self.assertNotIn("=", package["name"], "catalog must not pin package versions")

    def test_fcitx5_baseline_and_supported_engines_are_explicit(self):
        fcitx = next(framework for framework in self.catalog["frameworks"] if framework["id"] == "fcitx5")
        packages = {entry["name"]: entry for entry in fcitx["packages"]}
        self.assertTrue(packages["fcitx5"]["required"])
        self.assertFalse(packages["fcitx5-qt"]["required"])
        self.assertFalse(packages["fcitx5-gtk"]["required"])
        self.assertFalse(packages["fcitx5-configtool"]["required"])

        engines = {engine["id"]: engine for engine in self.catalog["engines"]}
        expected = {
            "fcitx5.pinyin": "fcitx5-chinese-addons",
            "fcitx5.rime": "fcitx5-rime",
            "fcitx5.mozc": "fcitx5-mozc",
            "fcitx5.hangul": "fcitx5-hangul",
            "fcitx5.m17n": "fcitx5-m17n",
        }
        self.assertEqual(set(engines), set(expected))
        for engine_id, package_name in expected.items():
            self.assertIn(package_name, {entry["name"] for entry in engines[engine_id]["packages"]})

    def test_catalog_contains_no_urls_commands_or_local_paths(self):
        serialized = CATALOG.read_text(encoding="utf-8")
        for forbidden in (
            "http://",
            "https://",
            "sudo ",
            "pacman ",
            "pkexec ",
            "/usr/",
            "/home/",
            "curl ",
            "wget ",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
