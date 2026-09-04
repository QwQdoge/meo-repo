#!/usr/bin/env python3
"""Validate the public pacman-key payload before protected publication."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("packages/meo-keyring/files")
missing = [name for name in ("meo.gpg", "meo-trusted", "meo-revoked")
           if not (root / name).is_file() or not (root / name).stat().st_size]
if missing:
    raise SystemExit("keyring payload validation failed: missing/non-empty " + ", ".join(missing))

with tempfile.TemporaryDirectory() as gpg_home:
    listing = subprocess.run(
        ["gpg", "--homedir", gpg_home, "--batch", "--no-default-keyring",
         "--keyring", root / "meo.gpg", "--with-colons", "--list-keys"],
        check=False,
        text=True,
        capture_output=True,
    )
fingerprints = {line.split(":")[9].upper() for line in listing.stdout.splitlines()
                if line.startswith("fpr:")}
if listing.returncode or not fingerprints:
    raise SystemExit("keyring payload validation failed: meo.gpg has no readable public keys")

def metadata_lines(name: str) -> list[str]:
    return [line.strip() for line in (root / name).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]

trusted = metadata_lines("meo-trusted")
if not trusted or any(not re.fullmatch(r"[0-9A-Fa-f]{40}:[56]:", line) for line in trusted):
    raise SystemExit("keyring payload validation failed: meo-trusted must contain public full ownertrust fingerprints")
if any(line[:40].upper() not in fingerprints for line in trusted):
    raise SystemExit("keyring payload validation failed: meo-trusted references a key absent from meo.gpg")

revoked = metadata_lines("meo-revoked")
if not revoked or any(not re.fullmatch(r"[0-9A-Fa-f]{40}", line) for line in revoked):
    raise SystemExit("keyring payload validation failed: meo-revoked must contain public full fingerprints")
if any(line.upper() not in fingerprints for line in revoked):
    raise SystemExit("keyring payload validation failed: meo-revoked references a key absent from meo.gpg")
