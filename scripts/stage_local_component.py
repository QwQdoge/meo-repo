#!/usr/bin/env python3
"""Render a conventional, checksum-pinned makepkg context from a local commit.

This creates local candidates only. It neither installs nor signs nor publishes.
Commit component changes first: dirty source trees are rejected, not silently
included or discarded. All package recipes remain owned by meo-repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {"meoui-qml", "meo-icons", "meo-desktop", "meo-kde-runtime",
             "meo-plasma-login-manager", "meo-settings", "meo-icon-studio"}


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def stage(package: str, source: Path, output: Path) -> None:
    if package not in SUPPORTED:
        raise ValueError("unsupported source package")
    if output.exists():
        raise ValueError(f"refusing to overwrite context: {output}")
    if git(source, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("commit source changes before staging a package")
    commit = git(source, "rev-parse", "HEAD")
    epoch = int(git(source, "show", "-s", "--format=%ct", "HEAD"))
    recipe_dir = ROOT / "packages" / package
    recipe = (recipe_dir / "PKGBUILD").read_text()
    if recipe.count("source=()") != 1 or recipe.count("sha256sums=()") != 1:
        raise ValueError("recipe does not have the reviewed source placeholders")
    shutil.copytree(recipe_dir, output)
    name = f"{package}-{commit}.tar"
    archive = output / name
    subprocess.run(["git", "-C", str(source), "archive", "--format=tar",
                    "--prefix=source/", f"--output={archive}", commit], check=True)
    with archive.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    recipe = recipe.replace("source=()", f"source=('{name}')")
    recipe = recipe.replace("sha256sums=()", f"sha256sums=('{digest}')")
    (output / "PKGBUILD").write_text(recipe)
    (output / "source-provenance.json").write_text(json.dumps({
        "package": package, "commit": commit, "sourceDateEpoch": epoch,
        "sourceSha256": digest, "recipeSha256": hashlib.sha256(recipe.encode()).hexdigest(),
        "publication": "unsigned-local-candidate",
    }, indent=2) + "\n")
    with (output / ".SRCINFO").open("w") as handle:
        subprocess.run(["makepkg", "--printsrcinfo"], cwd=output, stdout=handle, check=True)
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=sorted(SUPPORTED))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    stage(args.package, args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
