from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PKGBUILD = ROOT / "packages" / "meo-desktop" / "PKGBUILD"


class MeoDesktopInputMethodRuntimeTests(unittest.TestCase):
    def test_desktop_package_closes_the_fcitx_runtime_dependency(self):
        source = PKGBUILD.read_text(encoding="utf-8")
        depends_match = re.search(r"depends=\((.*?)\)\nmakedepends=", source, re.S)
        self.assertIsNotNone(depends_match)
        depends = depends_match.group(1)
        for package in ("fcitx5", "fcitx5-qt", "fcitx5-gtk"):
            with self.subTest(package=package):
                self.assertRegex(depends, rf"'{re.escape(package)}'")

    def test_input_engines_remain_optional_capabilities(self):
        source = PKGBUILD.read_text(encoding="utf-8")
        depends_match = re.search(r"depends=\((.*?)\)\nmakedepends=", source, re.S)
        self.assertIsNotNone(depends_match)
        depends = depends_match.group(1)
        for engine in (
            "fcitx5-chinese-addons",
            "fcitx5-rime",
            "fcitx5-mozc",
            "fcitx5-hangul",
            "fcitx5-m17n",
        ):
            with self.subTest(engine=engine):
                self.assertNotIn(engine, depends)

    def test_recipe_does_not_create_a_second_fcitx_lifecycle_owner(self):
        source = PKGBUILD.read_text(encoding="utf-8")
        self.assertNotIn("org.fcitx.Fcitx5.desktop", source)
        self.assertNotIn("fcitx5.service", source)
        self.assertNotIn("autostart", source.lower())


if __name__ == "__main__":
    unittest.main()
