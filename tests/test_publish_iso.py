"""ci/publish-iso.sh uploads first, verifies, then keeps exactly one ISO."""
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ci" / "publish-iso.sh"

FAKE_AWS = r"""#!/usr/bin/env bash
# Stand-in for aws-cli backed by a directory (the "bucket").
store="$FAKE_BUCKET"
args=("$@"); [ "${args[0]}" = --endpoint-url ] && args=("${args[@]:2}")
log() { echo "${args[*]}" >>"$FAKE_LOG"; }
log
case "${args[0]} ${args[1]}" in
  "s3 cp") src="${args[2]}"; dst="${args[3]#s3://*/}"
           [ -n "${FAKE_FAIL_UPLOAD:-}" ] && exit 1
           cp "$src" "$store/$dst" ;;
  "s3api head-object") key=""; for i in "${!args[@]}"; do [ "${args[$i]}" = --key ] && key="${args[$((i+1))]}"; done
           stat -c %s "$store/$key" ;;
  "s3api list-objects-v2") ls "$store" | jq -R . | jq -s . ;;
  "s3api delete-object") key=""; for i in "${!args[@]}"; do [ "${args[$i]}" = --key ] && key="${args[$((i+1))]}"; done
           rm -f "$store/$key" ;;
  *) exit 2 ;;
esac
"""


class PublishIso(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bucket = self.tmp / "bucket"
        self.bucket.mkdir()
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        aws = bin_dir / "aws"
        aws.write_text(FAKE_AWS)
        aws.chmod(aws.stat().st_mode | stat.S_IXUSR)
        self.log = self.tmp / "log"
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_BUCKET": str(self.bucket),
            "FAKE_LOG": str(self.log),
            "R2_ENDPOINT": "https://example.invalid",
        }

    def iso(self, stamp: str, body: bytes) -> Path:
        path = self.tmp / f"meoarch-os-2026.10.{stamp}-x86_64.iso"
        path.write_bytes(body)
        return path

    def run_script(self, iso: Path, **extra):
        return subprocess.run([str(SCRIPT), str(iso)], env={**self.env, **extra}, capture_output=True, text=True)

    def test_new_iso_replaces_the_old_one_and_only_one_stays(self):
        old = self.iso("25-070252", b"old")
        self.assertEqual(self.run_script(old).returncode, 0)
        new = self.iso("26-101010", b"newer iso")
        result = self.run_script(new)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            sorted(p.name for p in self.bucket.iterdir()),
            ["latest.json", f"{new.name}", f"{new.name}.sha256"],
        )
        latest = json.loads((self.bucket / "latest.json").read_text())
        self.assertEqual(latest["name"], new.name)
        self.assertEqual(latest["size"], len(b"newer iso"))

    def test_a_failed_upload_keeps_the_previous_iso(self):
        old = self.iso("25-070252", b"old")
        self.assertEqual(self.run_script(old).returncode, 0)
        new = self.iso("26-101010", b"newer")
        self.assertNotEqual(self.run_script(new, FAKE_FAIL_UPLOAD="1").returncode, 0)
        self.assertIn(old.name, [p.name for p in self.bucket.iterdir()])

    def test_a_wrong_checksum_file_is_refused_before_any_upload(self):
        iso = self.iso("26-101010", b"data")
        Path(f"{iso}.sha256").write_text("0" * 64 + f"  {iso.name}\n")
        self.assertNotEqual(self.run_script(iso).returncode, 0)
        self.assertFalse(self.log.exists())

    def test_names_that_are_not_meoarch_isos_are_refused(self):
        other = self.tmp / "windows.iso"
        other.write_bytes(b"x")
        self.assertEqual(self.run_script(other).returncode, 2)


if __name__ == "__main__":
    unittest.main()
