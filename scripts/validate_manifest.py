#!/usr/bin/env python3
"""Fail-closed validation for immutable MeoArch release manifests."""
import json
import re
import sys
from pathlib import Path

REQUIRED = {"meoui-qml", "meo-icons", "meo-desktop", "meo-kde-runtime", "meo-account", "meo-settings", "omnistore-bin"}
MINIMAL = {"meoui-qml", "meo-icons", "meo-desktop"}
LEGACY_RECOMMENDED = REQUIRED - {"meo-kde-runtime"}
COMMIT = re.compile(r"^[0-9a-f]{40}$")
VERSION = re.compile(r"^[A-Za-z0-9._+:-]+-[0-9][A-Za-z0-9._+]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

def fail(message: str) -> None:
    raise SystemExit(f"manifest validation failed: {message}")

def main(path: str) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or payload.get("architecture") != "x86_64":
        fail("unsupported schema or architecture")
    components = payload.get("components")
    profile = payload.get("profile", "recommended")
    if profile not in {"minimal", "recommended"}:
        fail("unsupported release profile")
    selected = set(components) if isinstance(components, dict) else set()
    valid_sets = {frozenset(MINIMAL)} if profile == "minimal" else {
        frozenset(REQUIRED), frozenset(LEGACY_RECOMMENDED),
    }
    if not isinstance(components, dict) or frozenset(selected) not in valid_sets:
        fail("components must be exactly the selected Meo release profile")
    for name, component in components.items():
        if not isinstance(component, dict):
            fail(f"{name} is not an object")
        if not isinstance(component.get("repository"), str) or "/" not in component["repository"]:
            fail(f"{name} has no GitHub repository")
        if not isinstance(component.get("tag"), str) or not component["tag"].startswith("v"):
            fail(f"{name} has no immutable release tag")
        if not COMMIT.fullmatch(str(component.get("commit", ""))):
            fail(f"{name} commit must be a pinned 40-character SHA")
        if not VERSION.fullmatch(str(component.get("expectedVersion", ""))):
            fail(f"{name} expectedVersion is invalid")
        source_url = component.get("sourceUrl")
        transport = component.get("sourceTransport", "https")
        if transport == "git-ssh":
            expected_url = f"ssh://git@github.com/{component['repository']}.git"
            if name != "meo-account" or source_url != expected_url:
                fail(f"{name} git-ssh source must be the private Account repository")
        elif transport != "https" or not isinstance(source_url, str) or not source_url.startswith("https://"):
            fail(f"{name} sourceUrl must use HTTPS or the reviewed private git-ssh transport")
        if not SHA256.fullmatch(str(component.get("sourceSha256", ""))):
            fail(f"{name} sourceSha256 must be a pinned SHA-256")
        layout = component.get("sourceLayout", "source")
        if layout not in {"source", "release-bundle"}:
            fail(f"{name} sourceLayout is unsupported")
        if name == "omnistore-bin":
            if layout != "release-bundle":
                fail("omnistore-bin must use the release-bundle layout")
            if not isinstance(component.get("verifierUrl"), str) or not component["verifierUrl"].startswith("https://"):
                fail("omnistore-bin verifierUrl must use HTTPS")
            if not SHA256.fullmatch(str(component.get("verifierSha256", ""))):
                fail("omnistore-bin verifierSha256 must be pinned")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_manifest.py MANIFEST.json")
    main(sys.argv[1])
