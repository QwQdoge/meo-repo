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
    "meo-icons": (),
    "meo-icon-studio": (),
    "meo-kde-runtime": (),
    "meo-desktop": (),
    "meo-settings": (),
    "meo-repair": (),
    "omnistore-bin": ("omnistore.desktop", "org.meo.OmniStore.json"),
}

MAINTAINER = "# Maintainer: MeoArch <https://github.com/QwQdoge>"

# Components whose source is private: the AUR package repackages the signed binary package that the
# Meo repository already publishes. component -> AUR package name.
BIN_COMPONENTS = {"meo-account": "meo-account-bin"}
REPO_BASE = "https://packages.meoarch.org"


class AurError(Exception):
    pass


def load_component(manifest_path: Path, name: str, fallbacks: tuple[Path, ...] = ()) -> dict:
    """Return the component entry from the first manifest that contains it."""
    for candidate in (manifest_path, *fallbacks):
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        component = payload.get("components", {}).get(name)
        if component:
            return component
    raise AurError(f"{name} is not in {manifest_path}" + (" or its fallbacks" if fallbacks else ""))


def split_version(expected: str) -> tuple[str, str]:
    match = re.fullmatch(r"(.+)-([0-9][0-9A-Za-z._+]*)", expected)
    if not match:
        raise AurError(f"unsupported expectedVersion: {expected}")
    return match.group(1), match.group(2)


def source_dir_name(component: dict) -> str:
    return f"{component['repository'].split('/')[-1]}-{component['commit']}"


def _array(text: str, key: str) -> re.Match | None:
    return re.search(rf"^{key}=\((.*?)\)\n", text, re.M | re.S)


def url_basename(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def render_recipe(recipe: str, component: dict, flattened: dict[str, str] | None = None) -> str:
    """Return the AUR PKGBUILD text for ``recipe`` pinned to ``component``.

    ``flattened`` maps file names moved from a package subdirectory into the repository root to
    their SHA-256; they are appended to the source arrays.
    """
    pkgver, pkgrel = split_version(component["expectedVersion"])
    directory = source_dir_name(component)
    bundle = component.get("sourceLayout") == "release-bundle"
    tarball = (url_basename(component["sourceUrl"]) if bundle
               else f"{component['repository'].split('/')[-1]}-{component['commit']}.tar.gz")
    url = component["sourceUrl"]
    digest = component["sourceSha256"]

    internal = ("# Rendered by the protected release job", "# The protected renderer", "# the immutable manifest")
    text = "\n".join(line for line in recipe.splitlines() if not line.startswith(internal)) + "\n"
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
    if bundle:
        # The prebuilt release bundle has no top-level directory, so it is extracted by prepare().
        new_sources.append(f"{url_basename(component['verifierUrl'])}::{component['verifierUrl']}")
        new_sums.append(component["verifierSha256"])
    joined_sources = "\n        ".join(f"'{item}'" for item in new_sources)
    joined_sums = "\n            ".join(f"'{item}'" for item in new_sums)
    text = text.replace(sources.group(0), f"source=({joined_sources})\n", 1)
    text = text.replace(_array(text, "sha256sums").group(0), f"sha256sums=({joined_sums})\n", 1)

    if bundle:
        sums_now = _array(text, "sha256sums")
        text = text.replace(sums_now.group(0), sums_now.group(0) + f"noextract=('{tarball}')\n", 1)
        text = text.replace("prepare() {\n", "prepare() {\n  mkdir -p \"$srcdir/release_bundle\"\n  bsdtar -xf \"$srcdir/" + tarball + "\" -C \"$srcdir/release_bundle\"\n", 1)
        if "bsdtar -xf" not in text:
            raise AurError("release-bundle recipe has no prepare() to extend")
        return f"{MAINTAINER}\n" + text
    if "$srcdir/source" not in text:
        raise AurError("recipe does not use $srcdir/source")
    text = text.replace('"$startdir/licenses/', '"$srcdir/')
    text = text.replace('"$srcdir/source', '"$srcdir/$_srcdir')
    text = text.replace("$srcdir/source", "$srcdir/$_srcdir")
    # `_srcdir` is declared before pkgname so every function sees it.
    header = f"{MAINTAINER}\n_srcdir={directory}\n"
    return header + text


def render_package(manifest_path: Path, name: str, out_dir: Path, fallbacks: tuple[Path, ...] = ()) -> Path:
    if name not in AUR_COMPONENTS:
        raise AurError(f"{name} is not an AUR component")
    component = load_component(manifest_path, name, fallbacks)
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
    for install_file in sorted(package_dir.glob("*.install")):
        shutil.copy2(install_file, target / install_file.name)
    (target / "PKGBUILD").write_text(render_recipe(recipe, component, flattened), encoding="utf-8")
    srcinfo = subprocess.run(
        ["makepkg", "--printsrcinfo"], cwd=target, check=True, capture_output=True, text=True,
    ).stdout
    (target / ".SRCINFO").write_text(srcinfo, encoding="utf-8")
    return target


def parse_pkginfo(text: str) -> dict[str, list[str]]:
    info: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("#") or " = " not in line:
            continue
        key, value = line.split(" = ", 1)
        info.setdefault(key.strip(), []).append(value.strip())
    return info


def _quote(items: list[str]) -> str:
    return " ".join("'" + item.replace("'", "'\\''") + "'" for item in items)


def render_bin_recipe(name: str, component: dict, info: dict[str, list[str]], filename: str, url: str, digest: str) -> str:
    """AUR PKGBUILD that repackages a published Meo repository package (``name`` is the component)."""
    pkgver, pkgrel = split_version(component["expectedVersion"])
    one = lambda key, default="": (info.get(key) or [default])[0]
    lines = [
        MAINTAINER,
        f"pkgname={BIN_COMPONENTS[name]}",
        f"_pkgname={name}",
        f"pkgver={pkgver}",
        f"pkgrel={pkgrel}",
        f'pkgdesc="{one("pkgdesc")} (prebuilt)"',
        f"arch=({_quote(info.get('arch', ['x86_64']))})",
        f"url='{one('url')}'",
        f"license=({_quote(info.get('license', []))})",
        f"depends=({_quote(info.get('depend', []))})",
    ]
    if info.get("optdepend"):
        lines.append(f"optdepends=({_quote(info['optdepend'])})")
    lines += [
        f"provides=('{name}={pkgver}-{pkgrel}')",
        f"conflicts=('{name}')",
    ]
    if info.get("backup"):
        lines.append(f"backup=({_quote(info['backup'])})")
    lines += [
        "options=('!strip' '!debug')",
        f"source=('{filename}::{url}')",
        f"noextract=('{filename}')",
        f"sha256sums=('{digest}')",
        "",
        "package() {",
        f'  bsdtar -xf "$srcdir/{filename}" -C "$pkgdir" --exclude=.PKGINFO --exclude=.BUILDINFO --exclude=.MTREE --exclude=.INSTALL --exclude=.CHANGELOG',
        "}",
        "",
    ]
    return "\n".join(lines)


def render_bin_package(manifest_path: Path, name: str, out_dir: Path, fallbacks: tuple[Path, ...] = (),
                       package_file: Path | None = None) -> Path:
    """Render the -bin AUR package for ``name``; downloads the published package unless ``package_file`` is given."""
    import hashlib as _hashlib
    import urllib.request

    component = load_component(manifest_path, name, fallbacks)
    pkgver, pkgrel = split_version(component["expectedVersion"])
    filename = f"{name}-{pkgver}-{pkgrel}-x86_64.pkg.tar.zst"
    target = out_dir / BIN_COMPONENTS[name]
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    url = ""
    if package_file is None:
        package_file = target / ".download"
        for channel in ("meo", "meo-beta"):
            candidate = f"{REPO_BASE}/{channel}/os/x86_64/{filename}"
            # Cloudflare in front of the repository rejects urllib's default User-Agent with 403.
            request = urllib.request.Request(candidate, headers={"User-Agent": "MeoArch-AUR-publisher/1.0 (+https://meoarch.org)"})
            try:
                with urllib.request.urlopen(request, timeout=120) as response, package_file.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
                url = candidate
                break
            except OSError:
                package_file.unlink(missing_ok=True)
        if not url:
            raise AurError(f"{filename} is not published in the Meo repository")
    else:
        url = f"{REPO_BASE}/meo/os/x86_64/{filename}"
    data = package_file.read_bytes()
    digest = _hashlib.sha256(data).hexdigest()
    info_text = subprocess.run(["bsdtar", "-xOf", str(package_file), ".PKGINFO"], check=True,
                               capture_output=True, text=True).stdout
    if package_file.name == ".download":
        package_file.unlink()
    (target / "PKGBUILD").write_text(
        render_bin_recipe(name, component, parse_pkginfo(info_text), filename, url, digest), encoding="utf-8")
    srcinfo = subprocess.run(["makepkg", "--printsrcinfo"], cwd=target, check=True, capture_output=True, text=True).stdout
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
        item.add_argument("--component", action="append", choices=sorted([*AUR_COMPONENTS, *BIN_COMPONENTS]))
        item.add_argument("--also", action="append", type=Path, default=[],
                          help="fallback manifest consulted for components missing from MANIFEST")
        if command == "publish":
            item.add_argument("--push", action="store_true")
    args = parser.parse_args(argv)
    manifest = args.manifest.resolve()
    fallbacks = tuple(path.resolve() for path in args.also)
    known: set[str] = set()
    for source in (manifest, *fallbacks):
        known |= set(json.loads(source.read_text(encoding="utf-8")).get("components", {}))
    names = args.component or [name for name in (*AUR_COMPONENTS, *BIN_COMPONENTS) if name in known]
    if not names:
        print("no AUR components in this manifest")
        return 0
    try:
        for name in names:
            if args.command == "render":
                print((render_bin_package if name in BIN_COMPONENTS else render_package)(manifest, name, args.directory.resolve(), fallbacks))
            else:
                with_tmp = args.directory.resolve() / "_rendered"
                rendered = (render_bin_package if name in BIN_COMPONENTS else render_package)(manifest, name, with_tmp, fallbacks)
                publish_package(rendered, args.directory.resolve(), args.push)
    except (AurError, subprocess.CalledProcessError) as error:
        print(f"publish_aur: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
