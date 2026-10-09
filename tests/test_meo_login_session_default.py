from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PKGBUILD = ROOT / "packages" / "meo-plasma-login-manager" / "PKGBUILD"
SESSION_DEFAULT = ROOT / "packages" / "meo-plasma-login-manager" / "meo-session.conf"


class MeoLoginSessionDefaultTests(unittest.TestCase):
    def test_login_manager_preselects_meo_without_autologin(self):
        recipe = PKGBUILD.read_text(encoding="utf-8")
        config = SESSION_DEFAULT.read_text(encoding="utf-8")

        self.assertIn("meo-session.conf", recipe)
        self.assertIn("etc/plasmalogin.conf.d/20-meo-session.conf", recipe)
        self.assertIn("[Greeter]", config)
        self.assertIn(
            "PreselectedSession=/usr/share/wayland-sessions/meo.desktop",
            config,
        )
        self.assertNotIn("[Autologin]", config)
        self.assertNotIn("User=", config)


if __name__ == "__main__":
    unittest.main()
