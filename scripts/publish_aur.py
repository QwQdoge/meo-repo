#!/usr/bin/env python3
"""Render and publish AUR packages from a reviewed MeoArch release manifest.

The Meo pacman repository recipes under ``packages/`` are rendered by the
protected release job, which stages the pinned source as ``$srcdir/source``.
The AUR needs self-contained recipes, so this script rewrites a package recipe
to download the same pinned GitHub tarball (commit and SHA-256 come from the
manifest) and writes ``.SRCINFO``.  Only components that build from public
sources belong here.

    publish_aur.py render  MANIFEST OUTPUT_DIR [--component NAME]
    publish_aur.py publish MANIFEST WORK_DIR   [--component NAME] [--push]

``publish`` needs the SSH key in ``AUR_SSH_KEY_FILE`` (a path the caller wrote
from a protected secret); it never prints or stores key material.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# component -> files that must travel with the recipe (relative to packages/<name>/).
# The AUR forbids subdirectories, so directory entries are flattened into the repository root and
# the recipe refers to them as ordinary sources.
AUR_COMPONENTS = {
    "meoui-qml": ("licenses",),
    "meo-plasma-login-manager": ("meo-session.conf",),
}

MAINTAINER = "# Maintainer: MeoArch <https://github.com/QwQdoge>"


class AurError(Exception):
    pass


def load_component(manifest_path: Path, name: str) -> dict:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    component = payload.get("components", {}).get(name)
    if not component:
        raise AurError(f"{name} is not in {manifest_path}")
    return component


def split_version(expected: str) -> tuple[str, str]:
    match = re.fullmatch(r"(.+)-([0-9][0-9A-Za-z._+]*)", expected)
    if not match:
        raise AurError(f"unsupported expectedVersion: {expected}")
    return match.group(1), match.group(2)


def source_dir_name(component: dict) -> str:
    return f"{component['repository'].split('/')[-1]}-{component['commit']}"


def _array(text: str, key: str) -> re.Match | None:
    return re.search(rf"^{key}=\((.*?)\)\n", text, re.M | re.S)


def render_recipe(recipe: str, component: dict, flattened: dict[str, str] | None = None) -> str:
    """Return the AUR PKGBUILD text for ``recipe`` pinned to ``component``.

    ``flattened`` maps file names moved from a package subdirectory into the repository root to
    their SHA-256; they are appended to the source arrays.
    """
    pkgver, pkgrel = split_version(component["expectedVersion"])
    directory = source_dir_name(component)
    tarball = f"{component['repository'].split('/')[-1]}-{component['commit']}.tar.gz"
    url = component["sourceUrl"]
    digest = component["sourceSha256"]

    text = "\n".join(
        line for line in recipe.splitlines()
        if not line.startswith("# Rendered by the protected release job")
    ) + "\n"
    text = re.sub(r"^pkgver=.*$", f"pkgver={pkgver}", text, count=1, flags=re.M)
    text = re.sub(r"^pkgrel=.*$", f"pkgrel={pkgrel}", text, count=1, flags=re.M)

    sources = _array(text, "source")
    sums = _array(text, "sha256sums")
    if sources is None or sums is None:
        raise AurError("recipe must define source and sha256sums arrays")
    existing_sources = re.findall(r"'([^']+)'", sources.group(1))
    existing_sums = re.findall(r"'([^']+)'", sums.group(1))
    if len(existing_sources) != len(existing_sums):
        raise AurError("source and sha256sums length mismatch")
    extra = {name: sha for name, sha in (flattened or {}).items() if name not in existing_sources}
    new_sources = [f"{tarball}::{url}", *existing_sources, *extra]
    new_sums = [digest, *existing_sums, *extra.values()]
    joined_sources = "\n        ".join(f"'{item}'" for item in new_sources)
    joined_sums = "\n            ".join(f"'{item}'" for item in new_sums)
    text = text.replace(sources.group(0), f"source=({joined_sources})\n", 1)
    text = text.replace(_array(text, "sha256sums").group(0), f"sha256sums=({joined_sums})\n", 1)

    if "$srcdir/source" not in text:
        raise AurError("recipe does not use $srcdir/source")
    text = text.replace('"$startdir/licenses/', '"$srcdir/')
    text = text.replace('"$srcdir/source', '"$srcdir/$_srcdir')
    text = text.replace("$srcdir/source", "$srcdir/$_srcdir")
    # `_srcdir` is declared before pkgname so every function sees it.
    header = f"{MAINTAINER}\n_srcdir={directory}\n"
    return header + text


def render_package(manifest_path: Path, name: str, out_dir: Path) -> Path:
    if name not in AUR_COMPONENTS:
        raise AurError(f"{name} is not an AUR component")
    component = load_component(manifest_path, name)
    package_dir = ROOT / "packages" / name
    recipe = (package_dir / "PKGBUILD").read_text(encoding="utf-8")
    target = out_dir / name
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    flattened: dict[str, str] = {}
    for extra in AUR_COMPONENTS[name]:
        source = package_dir / extra
        if source.is_dir():
            for item in sorted(source.iterdir()):
                if item.is_file():
                    shutil.copy2(item, target / item.name)
                    flattened[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
        else:
            shutil.copy2(source, target / extra)
    (target / "PKGBUILD").write_text(render_recipe(recipe, component, flattened), encoding="utf-8")
    srcinfo = subprocess.run(
        ["makepkg", "--printsrcinfo"], cwd=target, check=True, capture_output=True, text=True,
    ).stdout
    (target / ".SRCINFO").write_text(srcinfo, encoding="utf-8")
    return target


def publish_package(rendered: Path, work_dir: Path, push: bool) -> bool:
    name = rendered.name
    key_file = os.environ.get("AUR_SSH_KEY_FILE", "")
    env = dict(os.environ)
    if key_file:
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {key_file} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
        )
    repo = work_dir / name
    if not repo.exists():
        subprocess.run(["git", "clone", f"ssh://aur@aur.archlinux.org/{name}.git", str(repo)],
                       check=True, env=env)
    for child in repo.iterdir():
        if child.name != ".git":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    for child in rendered.iterdir():
        destination = repo / child.name
        shutil.copytree(child, destination) if child.is_dir() else shutil.copy2(child, destination)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo, env=env).returncode == 0:
        print(f"{name}: AUR already up to date")
        return False
    version = re.search(r"^\s*pkgver = (.+)$", (repo / ".SRCINFO").read_text(), re.M).group(1)
    release = re.search(r"^\s*pkgrel = (.+)$", (repo / ".SRCINFO").read_text(), re.M).group(1)
    subprocess.run(["git", "-c", "user.name=MeoArch", "-c", "user.email=packages@meoarch.org",
                    "commit", "-q", "-m", f"Update to {version}-{release}"], cwd=repo, check=True, env=env)
    if push:
        subprocess.run(["git", "push", "origin", "HEAD:master"], cwd=repo, check=True, env=env)
        print(f"{name}: pushed {version}-{release} to the AUR")
    else:
        print(f"{name}: committed {version}-{release} locally (no --push)")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("render", "publish"):
        item = sub.add_parser(command)
        item.add_argument("manifest", type=Path)
        item.add_argument("directory", type=Path)
        item.add_argument("--component", action="append", choices=sorted(AUR_COMPONENTS))
        if command == "publish":
            item.add_argument("--push", action="store_true")
    args = parser.parse_args(argv)
    manifest = args.manifest.resolve()
    names = args.component or [
        name for name in AUR_COMPONENTS
        if name in json.loads(manifest.read_text(encoding="utf-8")).get("components", {})
    ]
    if not names:
        print("no AUR components in this manifest")
        return 0
    try:
        for name in names:
            if args.command == "render":
                print(render_package(manifest, name, args.directory.resolve()))
            else:
                with_tmp = args.directory.resolve() / "_rendered"
                rendered = render_package(manifest, name, with_tmp)
                publish_package(rendered, args.directory.resolve(), args.push)
    except (AurError, subprocess.CalledProcessError) as error:
        print(f"publish_aur: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
