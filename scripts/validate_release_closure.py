#!/usr/bin/env python3
"""Fail closed when a release manifest cannot reproduce the requested package train."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^pkg(?P<field>ver|rel)=(?P<value>[^\s#]+)$", re.MULTILINE)


def fail(message: str) -> None:
    raise ValueError(message)


def recipe_version(package: str, recipe_root: Path = ROOT / "packages") -> str:
    path = recipe_root / package / "PKGBUILD"
    if not path.is_file():
        fail(f"release component has no package recipe: {package}")
    source = path.read_text(encoding="utf-8")
    fields = {
        match.group("field"): match.group("value").strip("'\"")
        for match in VERSION.finditer(source)
    }
    if set(fields) != {"ver", "rel"}:
        fail(f"{package} recipe has no literal pkgver/pkgrel")
    return f"{fields['ver']}-{fields['rel']}"


def profile_closure(catalog: dict, profile: str) -> set[str]:
    packages = catalog.get("packages")
    if not isinstance(packages, dict):
        fail("package catalog has no package map")
    selected = {
        name for name, metadata in packages.items()
        if profile in metadata.get("profiles", [])
    }
    pending = list(selected)
    while pending:
        name = pending.pop()
        metadata = packages.get(name)
        if not isinstance(metadata, dict):
            fail(f"package catalog references unknown package: {name}")
        requires = metadata.get("requires", [])
        if not isinstance(requires, list) or any(not isinstance(item, str) for item in requires):
            fail(f"package catalog has invalid dependencies for {name}")
        for dependency in requires:
            if dependency not in packages:
                fail(f"package catalog dependency is missing: {name} -> {dependency}")
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    return selected


def validate(
    manifest: dict,
    catalog: dict,
    recipe_root: Path = ROOT / "packages",
    candidate: str | None = None,
) -> None:
    components = manifest.get("components")
    if not isinstance(components, dict) or not components:
        fail("manifest has no component set")

    if candidate:
        component = components.get(candidate)
        if not isinstance(component, dict):
            fail(f"manifest has no selected candidate: {candidate}")
        expected = str(component.get("expectedVersion", ""))
        actual = recipe_version(candidate, recipe_root)
        if expected != actual:
            fail(f"{candidate} recipe is {actual}, manifest expects {expected}")
        return

    profile = str(manifest.get("profile", "recommended"))
    if profile not in {"minimal", "recommended"}:
        fail("full release closure requires a minimal or recommended profile")
    if manifest.get("generation") != catalog.get("generation"):
        fail(
            "release manifest generation does not match package catalog: "
            f"{manifest.get('generation')} != {catalog.get('generation')}"
        )

    selected = profile_closure(catalog, profile)
    package_map = catalog["packages"]
    required_components = {
        name for name in selected
        if package_map[name].get("kind") != "meta"
    }
    missing = sorted(required_components - set(components))
    if missing:
        fail("release manifest does not cover package catalog closure: " + ", ".join(missing))
    extra = sorted(set(components) - required_components)
    if extra:
        fail("release manifest contains components outside the package catalog closure: " + ", ".join(extra))

    for name, component in sorted(components.items()):
        expected = str(component.get("expectedVersion", ""))
        actual = recipe_version(name, recipe_root)
        if expected != actual:
            fail(f"{name} recipe is {actual}, manifest expects {expected}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--catalog", type=Path, default=ROOT / "manifests/package-catalog.json")
    parser.add_argument("--candidate")
    args = parser.parse_args()
    try:
        validate(
            json.loads(args.manifest.read_text(encoding="utf-8")),
            json.loads(args.catalog.read_text(encoding="utf-8")),
            candidate=args.candidate or None,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"release closure validation failed: {error}") from error
    print("release closure validation passed")


if __name__ == "__main__":
    main()
