#!/usr/bin/env python3
"""Create or verify the hash-bound unsigned package artifact contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

PACKAGE_FILE = re.compile(r"^[A-Za-z0-9@._+:-]+\.pkg\.tar\.(?:zst|xz|gz)$")
ROOT = Path(__file__).resolve().parents[1]
CONTROL_PACKAGES = (
    "meo-keyring", "meo-mirrorlist", "meo-channel-stable", "meo-channel-beta",
    "meo-release", "meo-core-meta", "meo-apps-meta", "meo-recommended-meta",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def package_files(directory: Path) -> list[Path]:
    files = sorted(path for path in directory.iterdir() if path.is_file() and PACKAGE_FILE.fullmatch(path.name))
    if not files or any(path.is_symlink() for path in files):
        raise ValueError("artifact directory must contain regular package files")
    return files


def literal_recipe_version(package: str) -> str:
    recipe = (ROOT / "packages" / package / "PKGBUILD").read_text(encoding="utf-8")
    version = re.search(r"^pkgver=([^\s#]+)$", recipe, re.MULTILINE)
    release = re.search(r"^pkgrel=([^\s#]+)$", recipe, re.MULTILINE)
    if not version or not release:
        raise ValueError(f"{package} recipe has no literal version")
    return f"{version.group(1).strip(chr(39) + chr(34))}-{release.group(1).strip(chr(39) + chr(34))}"


def expected_versions(manifest: dict) -> dict[str, str]:
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise ValueError("manifest has no component set")
    expected = {name: str(metadata.get("expectedVersion", "")) for name, metadata in components.items()}
    expected.update({name: literal_recipe_version(name) for name in CONTROL_PACKAGES})
    return expected


def identify(filename: str, versions: dict[str, str]) -> tuple[str, str]:
    matches = [(name, version) for name, version in versions.items() if filename.startswith(f"{name}-{version}-")]
    if len(matches) != 1:
        raise ValueError(f"package filename does not match exactly one expected version: {filename}")
    return matches[0]


def create(manifest_path: Path, package_dir: Path, output: Path, channel: str, candidate: str | None = None) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    versions = expected_versions(manifest)
    entries = []
    for path in package_files(package_dir):
        name, version = identify(path.name, versions)
        entries.append({"name": name, "version": version, "filename": path.name,
                        "sha256": digest(path), "size": path.stat().st_size})
    names = {entry["name"] for entry in entries}
    core = set(manifest["components"])
    if channel == "stable" and names != core | set(CONTROL_PACKAGES):
        raise ValueError("Stable artifact must contain the complete release train and control packages")
    if channel == "beta" and (candidate not in core or names != {candidate}):
        raise ValueError("Beta artifact must contain exactly the reviewed candidate")
    payload = {
        "schemaVersion": 1,
        "channel": channel,
        "release": manifest.get("release"),
        "candidate": candidate if channel == "beta" else None,
        "manifestSha256": digest(manifest_path),
        "packages": entries,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify(contract_path: Path, manifest_path: Path, package_dir: Path) -> None:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schemaVersion") != 1 or contract.get("channel") not in {"stable", "beta"}:
        raise ValueError("unsupported artifact contract")
    if contract.get("manifestSha256") != digest(manifest_path):
        raise ValueError("artifact contract references a different release manifest")
    files = {path.name: path for path in package_files(package_dir)}
    entries = contract.get("packages")
    if not isinstance(entries, list) or {entry.get("filename") for entry in entries} != set(files):
        raise ValueError("artifact contract package set does not match directory")
    for entry in entries:
        path = files[entry["filename"]]
        if entry.get("size") != path.stat().st_size or entry.get("sha256") != digest(path):
            raise ValueError(f"artifact verification failed: {path.name}")
    versions = expected_versions(json.loads(manifest_path.read_text(encoding="utf-8")))
    for entry in entries:
        name, version = identify(entry["filename"], versions)
        if entry.get("name") != name or entry.get("version") != version:
            raise ValueError("artifact package identity does not match its filename")
    names = {entry["name"] for entry in entries}
    core = set(json.loads(manifest_path.read_text(encoding="utf-8"))["components"])
    if contract["channel"] == "stable" and names != core | set(CONTROL_PACKAGES):
        raise ValueError("Stable artifact package set is incomplete")
    if contract["channel"] == "beta" and names != {contract.get("candidate")}:
        raise ValueError("Beta artifact package set is not sparse")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--manifest", required=True, type=Path)
    create_parser.add_argument("--packages", required=True, type=Path)
    create_parser.add_argument("--output", required=True, type=Path)
    create_parser.add_argument("--channel", choices=("stable", "beta"), required=True)
    create_parser.add_argument("--candidate")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--contract", required=True, type=Path)
    verify_parser.add_argument("--manifest", required=True, type=Path)
    verify_parser.add_argument("--packages", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.command == "create":
        create(arguments.manifest.resolve(), arguments.packages.resolve(), arguments.output.resolve(),
               arguments.channel, arguments.candidate)
    else:
        verify(arguments.contract.resolve(), arguments.manifest.resolve(), arguments.packages.resolve())


if __name__ == "__main__":
    main()
