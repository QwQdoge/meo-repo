#!/usr/bin/env python3
"""Bind the reviewed public keyring payload to an exact build recipe."""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

FILES = ("meo.gpg", "meo-trusted", "meo-revoked")


def render(context: Path) -> None:
    hashes = []
    for name in FILES:
        path = context / "files" / name
        if not path.is_file() or path.stat().st_size == 0 or path.is_symlink():
            raise ValueError(f"invalid public keyring payload: {name}")
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    recipe_path = context / "PKGBUILD"
    recipe = recipe_path.read_text(encoding="utf-8")
    replacement = "sha256sums=(" + " ".join(f"'{value}'" for value in hashes) + ")"
    rendered, count = re.subn(r"^sha256sums=\([^\n]*\)$", replacement, recipe, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("meo-keyring recipe has no single-line sha256sums declaration")
    recipe_path.write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("context", type=Path)
    arguments = parser.parse_args()
    render(arguments.context.resolve())


if __name__ == "__main__":
    main()
