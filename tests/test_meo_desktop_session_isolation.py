from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PKGBUILD = ROOT / "packages" / "meo-desktop" / "PKGBUILD"


class MeoDesktopSessionIsolationTests(unittest.TestCase):
    def setUp(self):
        self.source = PKGBUILD.read_text(encoding="utf-8")

    def test_package_installs_a_distinct_wayland_session(self):
        self.assertIn('tools/session/startmeo-wayland', self.source)
        self.assertIn('usr/bin/startmeo-wayland', self.source)
        self.assertIn('data/wayland-sessions/meo.desktop', self.source)
        self.assertIn('usr/share/wayland-sessions/meo.desktop', self.source)

    def test_package_includes_current_shell_and_default_layout_applets(self):
        self.assertIn('themes/shells/org.meo.shell', self.source)
        self.assertIn('usr/share/plasma/shells/org.meo.shell/contents/lockscreen/config.xml', self.source)
        for path in ('etc/gamemode.ini', 'etc/system76-scheduler/process-scheduler/meo-cachyos.kdl', 'usr/lib/systemd/zram-generator.conf.d/50-meo-desktop.conf', 'usr/lib/systemd/system-preset/50-meo-responsiveness.preset'):
            self.assertIn(path, self.source)
        for plugin in ('org.meo.time', 'org.meo.widgetexplorer', 'org.meo.widget.clock', 'org.meo.widget.media', 'org.meo.widget.performance'):
            self.assertIn(plugin, self.source)

    def test_package_includes_upstream_wallet_login_integration(self):
        depends_block = self.source.split("makedepends=", 1)[0]
        self.assertIn("'kwallet-pam'", depends_block)

    def test_package_does_not_force_a_display_manager(self):
        depends_block = self.source.split("makedepends=", 1)[0]
        self.assertNotIn("'meo-plasma-login-manager'", depends_block)
        self.assertNotIn("'plasma-login-manager'", depends_block)
        self.assertNotIn("'sddm'", depends_block)

    def test_plasma_defaults_are_session_seed_files_not_global_xdg_overrides(self):
        for relative in (
            'session-defaults/kdeglobals',
            'session-defaults/kwinrc',
            'session-defaults/plasmarc',
            'session-defaults/meo-shellrc',
            'session-defaults/fcitx5/conf/classicui.conf',
        ):
            with self.subTest(relative=relative):
                self.assertIn(relative, self.source)

        for forbidden in (
            '$pkgdir/etc/xdg/kdeglobals',
            '$pkgdir/etc/xdg/kwinrc',
            '$pkgdir/etc/xdg/plasmarc',
            '$pkgdir/etc/xdg/meo-shellrc',
            '$pkgdir/etc/environment.d/90-meo-applications.conf',
            '$pkgdir/etc/xdg/fcitx5/conf/classicui.conf',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_session_color_units_are_enabled_only_for_the_meo_session(self):
        self.assertIn('meo-session-dynamic-colors.path meo-session-dynamic-colors.service', self.source)
        self.assertIn('usr/lib/systemd/user/graphical-session.target.wants', self.source)
        self.assertIn('MEO_DESKTOP_SESSION=1', self.source)
        # Only the session-conditioned pair may be enabled; the unconditioned
        # units must stay disabled.
        self.assertNotIn('graphical-session.target.wants/meo-dynamic-colors', self.source)
        self.assertNotIn('graphical-session.target.wants/meo-weather-refresh', self.source)

    def test_font_alias_config_is_enabled(self):
        self.assertIn('etc/fonts/conf.d/50-meo-fonts.conf', self.source)

    def test_install_does_not_globally_enable_meo_user_units(self):
        self.assertNotIn(
            'usr/lib/systemd/user/default.target.wants/meo-dynamic-colors.path',
            self.source,
        )
        self.assertNotIn(
            'usr/lib/systemd/user/default.target.wants/meo-weather-refresh.timer',
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
