from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]


@unittest.skipUnless(shutil.which("gpg"), "requires GnuPG")
class PublicKeyringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="meo-keyring-test-")
        self.root = Path(self.temporary.name)
        self.payload = self.root / "payload"
        shutil.copytree(ROOT / "packages/meo-keyring/files", self.payload)

    def tearDown(self):
        self.temporary.cleanup()

    def validate(self):
        return subprocess.run([sys.executable, ROOT / "scripts/validate_keyring_payload.py", self.payload],
                              text=True, capture_output=True)

    def test_real_public_payload_passes(self):
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_symlinked_payload_fails(self):
        path = self.payload / "meo.gpg"
        path.unlink()
        path.symlink_to(ROOT / "packages/meo-keyring/files/meo.gpg")
        self.assertNotEqual(self.validate().returncode, 0)

    def test_trusted_and_revoked_overlap_fails(self):
        fingerprint = next(line[:40] for line in (self.payload / "meo-trusted").read_text().splitlines()
                           if line and not line.startswith("#"))
        (self.payload / "meo-revoked").write_text(fingerprint + "\n")
        self.assertIn("overlap", self.validate().stderr)

    def test_private_packet_cannot_be_published(self):
        home = self.root / "gnupg"
        home.mkdir(mode=0o700)
        command = ["gpg", "--homedir", str(home), "--batch", "--pinentry-mode", "loopback", "--passphrase", ""]
        subprocess.run([*command, "--quick-generate-key", "Disposable key <test@example.invalid>",
                        "ed25519", "sign", "1d"], check=True, capture_output=True)
        secret = subprocess.run([*command, "--export-secret-keys"], check=True, capture_output=True).stdout
        self.assertTrue(secret)
        # The test key exists only in an automatically removed /tmp fixture.
        (self.payload / "meo.gpg").write_bytes(secret)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("public keys only", result.stderr)
        subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"], check=False, capture_output=True)
