#!/usr/bin/env python3
"""Create a makepkg context from one immutable manifest component."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
VERSION_ASSIGNMENT = re.compile(r"^pkg(?P<field>ver|rel)=(?P<value>[^\s#]+)$", re.MULTILINE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, expected: str, destination: Path) -> None:
    if not url.startswith("https://"):
        raise ValueError("component source URL must use HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "meo-repo-release/1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    actual = sha256(destination)
    if actual != expected:
        destination.unlink(missing_ok=True)
        raise ValueError(f"source checksum mismatch: expected {expected}, got {actual}")


def safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:*") as bundle:
        members = [member for member in bundle.getmembers() if member.name not in {"", "."}]
        roots = {PurePosixPath(member.name).parts[0] for member in members if PurePosixPath(member.name).parts}
        strip_root = next(iter(roots)) if len(roots) == 1 else None
        for member in members:
            parts = PurePosixPath(member.name).parts
            if PurePosixPath(member.name).is_absolute() or ".." in parts:
                raise ValueError(f"archive path is unsafe: {member.name}")
            relative = parts[1:] if strip_root and parts and parts[0] == strip_root else parts
            if not relative:
                continue
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ValueError(f"unsafe archive member type: {member.name}")
            target = destination.joinpath(*relative)
            if destination.resolve() not in target.resolve().parents:
                raise ValueError(f"archive path escapes destination: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError(f"could not extract archive member: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)


def recipe_version(recipe: str) -> str:
    fields = {match.group("field"): match.group("value").strip("'\"") for match in VERSION_ASSIGNMENT.finditer(recipe)}
    if set(fields) != {"ver", "rel"}:
        raise ValueError("PKGBUILD must define literal pkgver and pkgrel")
    return f"{fields['ver']}-{fields['rel']}"


def stage(manifest_path: Path, package: str, output: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    component = manifest.get("components", {}).get(package)
    if not isinstance(component, dict):
        raise ValueError(f"manifest has no component named {package}")
    recipe_source = ROOT / "packages" / package
    if not recipe_source.is_dir():
        raise ValueError(f"package recipe does not exist: {package}")
    if output.exists():
        raise ValueError(f"refusing to overwrite build context: {output}")
    shutil.copytree(recipe_source, output)
    recipe = (output / "PKGBUILD").read_text(encoding="utf-8")
    if recipe_version(recipe) != component.get("expectedVersion"):
        raise ValueError(f"{package} PKGBUILD version does not match manifest")

    archive = output / "component-source.archive"
    download(component["sourceUrl"], component["sourceSha256"], archive)
    layout = component.get("sourceLayout", "source")
    destination = output / "src" / ("release_bundle" if layout == "release-bundle" else "source")
    destination.mkdir(parents=True)
    safe_extract(archive, destination)
    archive.unlink()

    if package == "omnistore-bin":
        verifier = output / "src" / "verify_release_exporter_contract.py"
        download(component["verifierUrl"], component["verifierSha256"], verifier)
        verifier.chmod(0o755)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("package")
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    stage(arguments.manifest.resolve(), arguments.package, arguments.output.resolve())


if __name__ == "__main__":
    main()
