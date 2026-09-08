import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ResponsivenessPackageTests(unittest.TestCase):
    def test_meo_desktop_selects_supported_default_stack(self):
        recipe = (ROOT / "packages/meo-desktop/PKGBUILD").read_text(encoding="utf-8")
        for package in (
            "system76-scheduler", "zram-generator", "dbus-broker-units",
            "power-profiles-daemon", "gamemode",
        ):
            self.assertIn(f"'{package}'", recipe)
        self.assertNotIn("'ananicy-cpp'", recipe)
        for payload in (
            "zram-generator.conf", "gamemode.ini", "cachyos-ananicy.kdl",
            "preload-ng-meo.toml", "prelockd-meo.conf",
            "50-meo-responsiveness.preset",
        ):
            self.assertIn(payload, recipe)


if __name__ == "__main__":
    unittest.main()
