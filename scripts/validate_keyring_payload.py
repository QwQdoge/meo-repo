#!/usr/bin/env python3
"""Validate the public pacman-key payload before protected publication."""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

root = (Path(sys.argv[1]) if len(sys.argv) == 2 else Path("packages/meo-keyring/files")).resolve()
missing = [name for name in ("meo.gpg", "meo-trusted", "meo-revoked")
           if (root / name).is_symlink() or not (root / name).is_file() or not (root / name).stat().st_size]
if missing:
    raise SystemExit("keyring payload validation failed: missing/non-empty " + ", ".join(missing))

with tempfile.TemporaryDirectory() as gpg_home:
    packets = subprocess.run(
        ["gpg", "--homedir", gpg_home, "--batch", "--no-options", "--list-packets", root / "meo.gpg"],
        capture_output=True, text=True, env=dict(os.environ, LC_ALL="C"),
    )
    if packets.returncode or any(marker in packets.stdout for marker in (":secret key packet:", ":secret sub key packet:")):
        raise SystemExit("keyring payload validation failed: meo.gpg must contain public keys only")
    listing = subprocess.run(
        ["gpg", "--homedir", gpg_home, "--batch", "--no-default-keyring",
         "--keyring", root / "meo.gpg", "--with-colons", "--list-keys"],
        check=False,
        text=True,
        capture_output=True,
    )
fingerprints = set()
invalid_roots = set()
primary = False
validity = ""
for line in listing.stdout.splitlines():
    fields = line.split(":")
    if fields[0] in {"pub", "sub"}:
        primary = fields[0] == "pub"
        validity = fields[1]
    elif fields[0] == "fpr" and primary:
        fingerprints.add(fields[9].upper())
        if validity in {"r", "e", "d", "i"}:
            invalid_roots.add(fields[9].upper())
        primary = False
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
if any(line[:40].upper() in invalid_roots for line in trusted):
    raise SystemExit("keyring payload validation failed: trusted primary key is revoked, expired or invalid")

revoked = metadata_lines("meo-revoked")
if not revoked or any(not re.fullmatch(r"[0-9A-Fa-f]{40}", line) for line in revoked):
    raise SystemExit("keyring payload validation failed: meo-revoked must contain public full fingerprints")
if any(line.upper() not in fingerprints for line in revoked):
    raise SystemExit("keyring payload validation failed: meo-revoked references a key absent from meo.gpg")
if {line[:40].upper() for line in trusted} & {line.upper() for line in revoked}:
    raise SystemExit("keyring payload validation failed: trusted and revoked metadata overlap")
