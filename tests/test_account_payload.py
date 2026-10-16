"""Regression coverage for the migrated desktop broker package contract."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "ci/check-account-payload.sh"


class AccountPayloadTests(unittest.TestCase):
    def fixture(self, root):
        files = {
            "usr/bin/meo-accountd": "#!/bin/sh\nexit 0\n",
            "usr/bin/meo-account-auth-dialog": "#!/bin/sh\nexit 0\n",
            "usr/lib/systemd/user/meo-accountd.service":
                "[Service]\nType=dbus\nBusName=org.meo.Accounts1\n[Install]\nWantedBy=graphical-session.target\n",
            "usr/share/dbus-1/services/org.meo.Accounts1.service":
                "[D-BUS Service]\nName=org.meo.Accounts1\nSystemdService=meo-accountd.service\n",
            "usr/share/dbus-1/interfaces/org.meo.Accounts1.xml": "<node/>\n",
            "etc/meo-account/broker.conf":
                "[OAuth]\nClientId=public-client\nRedirectUri=http://127.0.0.1:43887/callback\n"
                "[Account]\nBaseUrl=https://account.meoarch.org\nApiUrl=https://api.meoarch.org\n",
        }
        for name, contents in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
            if name.startswith("usr/bin/"):
                path.chmod(0o755)
        link = root / "usr/lib/systemd/user/graphical-session.target.wants/meo-accountd.service"
        link.parent.mkdir()
        link.symlink_to("../meo-accountd.service")
        return link

    def run_check(self, root):
        return subprocess.run(["bash", CHECK, str(root)], text=True, capture_output=True)

    def test_migrated_meo_api_payload_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            result = self.run_check(root)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_retired_supabase_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            config = root / "etc/meo-account/broker.conf"
            with config.open("a") as stream:
                stream.write("SupabaseUrl=https://retired.invalid\n")
            self.assertNotEqual(self.run_check(root).returncode, 0)

    def test_missing_graphical_broker_activation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root).unlink()
            self.assertNotEqual(self.run_check(root).returncode, 0)

    def test_missing_public_api_endpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            config = root / "etc/meo-account/broker.conf"
            config.write_text(config.read_text().replace("ApiUrl=https://api.meoarch.org\n", ""))
            self.assertNotEqual(self.run_check(root).returncode, 0)
