#!/usr/bin/env python3
"""Fail-closed validation for immutable MeoArch release manifests."""
import json
import re
import sys
from pathlib import Path

REQUIRED = {"meoui-qml", "meo-icons", "meo-desktop", "meo-settings", "omnistore-bin"}
COMMIT = re.compile(r"^[0-9a-f]{40}$")
VERSION = re.compile(r"^[A-Za-z0-9._+:-]+-[0-9][A-Za-z0-9._+]*$")

def fail(message: str) -> None:
    raise SystemExit(f"manifest validation failed: {message}")

def main(path: str) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or payload.get("architecture") != "x86_64":
        fail("unsupported schema or architecture")
    components = payload.get("components")
    if not isinstance(components, dict) or set(components) != REQUIRED:
        fail("components must be exactly the core Meo package set")
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

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_manifest.py MANIFEST.json")
    main(sys.argv[1])
