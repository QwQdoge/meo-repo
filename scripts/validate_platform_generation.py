#!/usr/bin/env python3
"""Fail closed on an incomplete or unsafe Meo platform-generation manifest."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


CORE_PACKAGES = {
    "meoui-qml",
    "meo-lockscreen",
    "meo-login-manager",
    "meo-desktop",
    "meo-settings",
    "meo-core-meta",
}
PRESERVED_PACKAGES = {"kscreenlocker", "plasma-workspace", "plasma-desktop", "kwin"}
PLATFORM_ROOTS = PRESERVED_PACKAGES | {"qt6-base", "qt6-declarative", "kf6-kconfig"}
PACKAGE_NAME = re.compile(r"^[A-Za-z0-9@._+:-]+$")
VERSION = re.compile(r"^[A-Za-z0-9._+:-]+-[0-9][A-Za-z0-9._+]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GENERATION = re.compile(r"^meo-plasma-[0-9]+\.[0-9]+$")
TRAIN = re.compile(r"^[0-9]{4}\.[0-9]{2}(?:-beta\.[0-9]+)?$")


class ManifestError(ValueError):
    """The manifest does not safely describe an atomic platform train."""


def fail(message: str) -> None:
    raise ManifestError(message)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def require_artifact(value: Any, label: str) -> dict[str, Any]:
    artifact = require_object(value, label)
    if set(artifact) != {"name", "version", "origin", "sourceUrl", "archiveSha256"}:
        fail(f"{label} has unsupported or missing artifact fields")
    if not PACKAGE_NAME.fullmatch(str(artifact["name"])):
        fail(f"{label} name is invalid")
    if not VERSION.fullmatch(str(artifact["version"])):
        fail(f"{label} version is not exact")
    if artifact["origin"] not in {"meo", "arch-snapshot"}:
        fail(f"{label} origin is invalid")
    if not isinstance(artifact["sourceUrl"], str) or not artifact["sourceUrl"].startswith("https://"):
        fail(f"{label} sourceUrl must use HTTPS")
    if not SHA256.fullmatch(str(artifact["archiveSha256"])):
        fail(f"{label} archiveSha256 is not pinned")
    return artifact


def require_artifacts(value: Any, label: str, expected: set[str], origin: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        fail(f"{label} must be an array")
    artifacts = [require_artifact(item, f"{label}[{index}]") for index, item in enumerate(value)]
    names = [str(item["name"]) for item in artifacts]
    if len(set(names)) != len(names) or set(names) != expected:
        fail(f"{label} must contain exactly: {', '.join(sorted(expected))}")
    if any(item["origin"] != origin for item in artifacts):
        fail(f"{label} must use {origin} artifacts")
    return artifacts


def validate(payload: Any) -> None:
    manifest = require_object(payload, "manifest")
    expected_fields = {
        "schemaVersion", "platformGeneration", "architecture", "train", "entryPackage",
        "sessionPackages", "preservedPackages", "replacedPackages", "platformRoots",
        "dependencyClosure", "upgradePolicy",
    }
    if set(manifest) != expected_fields:
        fail("manifest has unsupported or missing top-level fields")
    if manifest["schemaVersion"] != 1:
        fail("unsupported schemaVersion")
    if not GENERATION.fullmatch(str(manifest["platformGeneration"])):
        fail("platformGeneration is invalid")
    if manifest["architecture"] != "x86_64":
        fail("unsupported architecture")
    if manifest["entryPackage"] != "meo-core-meta":
        fail("meo-core-meta must remain the only core entry package")

    train = require_object(manifest["train"], "train")
    if set(train) != {"channel", "id"} or train["channel"] not in {"beta", "stable"} or not TRAIN.fullmatch(str(train["id"])):
        fail("train must have a supported channel and immutable train id")

    require_artifacts(manifest["sessionPackages"], "sessionPackages", CORE_PACKAGES, "meo")
    preserved = manifest["preservedPackages"]
    if not isinstance(preserved, list) or set(preserved) != PRESERVED_PACKAGES or len(set(preserved)) != len(preserved):
        fail("preservedPackages must retain the complete Plasma security/runtime set")

    replacements = manifest["replacedPackages"]
    if not isinstance(replacements, list):
        fail("replacedPackages must be an array")
    replacement_map: dict[str, str] = {}
    for index, replacement in enumerate(replacements):
        item = require_object(replacement, f"replacedPackages[{index}]")
        if set(item) != {"name", "replacedBy"} or not PACKAGE_NAME.fullmatch(str(item.get("name", ""))) or not PACKAGE_NAME.fullmatch(str(item.get("replacedBy", ""))):
            fail(f"replacedPackages[{index}] is invalid")
        if item["name"] in replacement_map:
            fail("replacedPackages has duplicate names")
        replacement_map[str(item["name"])] = str(item["replacedBy"])
    if replacement_map.get("plasma-login-manager") != "meo-login-manager":
        fail("plasma-login-manager must be replaced by meo-login-manager")
    if PRESERVED_PACKAGES & set(replacement_map):
        fail("a preserved Plasma security/runtime package may not be replaced")

    roots = require_artifacts(manifest["platformRoots"], "platformRoots", PLATFORM_ROOTS, "arch-snapshot")
    closure = manifest["dependencyClosure"]
    if not isinstance(closure, list):
        fail("dependencyClosure must be an array")
    closure_names: set[str] = set()
    closure_dependencies: set[str] = set()
    for index, value in enumerate(closure):
        item = require_object(value, f"dependencyClosure[{index}]")
        if set(item) != {"name", "version", "origin", "sourceUrl", "archiveSha256", "depends"}:
            fail(f"dependencyClosure[{index}] has unsupported or missing fields")
        artifact = require_artifact({key: item[key] for key in ("name", "version", "origin", "sourceUrl", "archiveSha256")}, f"dependencyClosure[{index}]")
        if artifact["name"] in closure_names:
            fail("dependencyClosure has duplicate package names")
        closure_names.add(str(artifact["name"]))
        depends = item["depends"]
        if not isinstance(depends, list) or len(set(depends)) != len(depends) or any(not PACKAGE_NAME.fullmatch(str(name)) for name in depends):
            fail(f"dependencyClosure[{index}] has invalid dependencies")
        closure_dependencies.update(str(name) for name in depends)
    required_closure = CORE_PACKAGES | PLATFORM_ROOTS
    if not required_closure <= closure_names:
        fail("dependencyClosure is missing a core package or compatibility root")
    if any(root["name"] not in closure_names for root in roots):
        fail("each platform root must appear in dependencyClosure")
    if not closure_dependencies <= closure_names:
        fail("dependencyClosure refers to a package outside the resolved closure")

    policy = require_object(manifest["upgradePolicy"], "upgradePolicy")
    if policy != {
        "atomicCoreUpdate": True,
        "allowIgnorePkg": False,
        "allowPartialCoreUpgrade": False,
    }:
        fail("upgradePolicy must require atomic updates without IgnorePkg or partial core upgrades")


def main(path: str) -> None:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        validate(payload)
    except (OSError, json.JSONDecodeError, ManifestError) as error:
        raise SystemExit(f"platform-generation validation failed: {error}") from error


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_platform_generation.py MANIFEST.json")
    main(sys.argv[1])
