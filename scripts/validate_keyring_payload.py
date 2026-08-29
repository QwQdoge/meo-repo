#!/usr/bin/env python3
"""Ensure protected publishing cannot accidentally ship an empty trust root."""
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("packages/meo-keyring/files")
missing = [name for name in ("meo.gpg", "meo-trusted", "meo-revoked")
           if not (root / name).is_file() or not (root / name).stat().st_size]
if missing:
    raise SystemExit("keyring payload validation failed: missing/non-empty " + ", ".join(missing))
