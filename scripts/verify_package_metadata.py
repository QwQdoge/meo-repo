#!/usr/bin/env python3
"""Verify package-internal identity before protected signing."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from artifact_manifest import PACKAGE_FILE


def package_info(path: Path) -> dict[str, str]:
    listing = subprocess.run(
        ["bsdtar", "-tf", str(path)], check=True, capture_output=True, text=True, timeout=30,
    )
    members = [name for name in listing.stdout.splitlines() if name.lstrip("./") == "PKGINFO"]
    if len(members) != 1:
        raise ValueError(f"{path.name} must contain exactly one .PKGINFO")
    extracted = subprocess.run(
        ["bsdtar", "-xOf", str(path), members[0]],
        check=True, capture_output=True, text=True, timeout=30,
    )
    metadata: dict[str, str] = {}
    for line in extracted.stdout.splitlines():
        if " = " not in line:
            continue
        key, value = line.split(" = ", 1)
        if key in {"pkgname", "pkgver", "arch"}:
            if key in metadata:
                raise ValueError(f"{path.name} has duplicate {key} metadata")
            metadata[key] = value
    if set(metadata) != {"pkgname", "pkgver", "arch"}:
        raise ValueError(f"{path.name} has incomplete package identity metadata")
    return metadata


def verify(contract_path: Path, package_dir: Path) -> None:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    entries = contract.get("packages")
    if not isinstance(entries, list):
        raise ValueError("artifact contract has no package list")
    for entry in entries:
        filename = entry.get("filename")
        if not isinstance(filename, str) or not PACKAGE_FILE.fullmatch(filename):
            raise ValueError("artifact contract contains an invalid package filename")
        path = package_dir / filename
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"package file is unavailable: {filename}")
        metadata = package_info(path)
        if metadata["pkgname"] != entry.get("name") or metadata["pkgver"] != entry.get("version"):
            raise ValueError(f"package-internal identity does not match artifact contract: {filename}")
        if metadata["arch"] not in {"any", "x86_64"}:
            raise ValueError(f"package architecture is unsupported: {filename}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--packages", required=True, type=Path)
    arguments = parser.parse_args()
    verify(arguments.contract.resolve(), arguments.packages.resolve())


if __name__ == "__main__":
    main()
