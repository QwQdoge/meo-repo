#!/usr/bin/env python3
"""Pure resolver for the versioned input-method capability catalog.

This module performs no package-manager, network, privilege, or filesystem
mutation. Consumers provide stable catalog capability IDs and receive a
bounded package plan which a separate trusted transaction authority may resolve
against the repositories configured on the target.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from pathlib import Path
import re
from typing import Any, Iterable


FRAMEWORK_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9@._+:-]{0,127}$")
MODES = frozenset({"keyboard-only", "meo-managed", "self-managed"})
OPTIONAL_ROLES = frozenset({"toolkit-bridge", "configuration", "integration"})


class CapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class InputMethodPlan:
    schema_version: int
    mode: str
    framework: str | None
    engines: tuple[str, ...]
    packages: tuple[str, ...]
    source_policy: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "mode": self.mode,
            "framework": self.framework,
            "engines": list(self.engines),
            "packages": list(self.packages),
            "sourcePolicy": self.source_policy,
        }


def load_catalog(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: Any) -> None:
    if not isinstance(catalog, dict) or set(catalog) != {"schemaVersion", "frameworks", "engines"}:
        raise CapabilityError("input-method catalog must contain exactly schemaVersion, frameworks, and engines")
    if catalog.get("schemaVersion") != 1:
        raise CapabilityError("unsupported input-method catalog schema")

    frameworks = catalog.get("frameworks")
    engines = catalog.get("engines")
    if not isinstance(frameworks, list) or not frameworks:
        raise CapabilityError("input-method catalog has no frameworks")
    if not isinstance(engines, list):
        raise CapabilityError("input-method engines must be a list")

    framework_ids: set[str] = set()
    for framework in frameworks:
        if not isinstance(framework, dict):
            raise CapabilityError("framework entry must be an object")
        framework_id = framework.get("id")
        if not isinstance(framework_id, str) or not FRAMEWORK_ID.fullmatch(framework_id):
            raise CapabilityError("framework has an invalid id")
        if framework_id in framework_ids:
            raise CapabilityError(f"duplicate framework id: {framework_id}")
        framework_ids.add(framework_id)
        modes = framework.get("modes")
        if not isinstance(modes, list) or not modes or any(mode != "meo-managed" for mode in modes):
            raise CapabilityError(f"framework {framework_id} has invalid modes")
        _validate_packages(framework.get("packages"), framework_id)

    engine_ids: set[str] = set()
    for engine in engines:
        if not isinstance(engine, dict):
            raise CapabilityError("engine entry must be an object")
        engine_id = engine.get("id")
        framework_id = engine.get("framework")
        if not isinstance(engine_id, str) or not FRAMEWORK_ID.fullmatch(engine_id):
            raise CapabilityError("engine has an invalid id")
        if engine_id in engine_ids:
            raise CapabilityError(f"duplicate engine id: {engine_id}")
        engine_ids.add(engine_id)
        if framework_id not in framework_ids:
            raise CapabilityError(f"engine {engine_id} references an unknown framework")
        if engine.get("sourcePolicy") != "configured-signed-repository":
            raise CapabilityError(f"engine {engine_id} has an unsupported source policy")
        _validate_packages(engine.get("packages"), engine_id)


def _validate_packages(packages: Any, owner: str) -> None:
    if not isinstance(packages, list) or not packages:
        raise CapabilityError(f"{owner} has no package mappings")
    seen: set[str] = set()
    for package in packages:
        if not isinstance(package, dict) or set(package) != {"name", "role", "required"}:
            raise CapabilityError(f"{owner} has an invalid package mapping")
        name = package.get("name")
        role = package.get("role")
        required = package.get("required")
        if not isinstance(name, str) or not PACKAGE_NAME.fullmatch(name):
            raise CapabilityError(f"{owner} has an invalid package name")
        if name in seen:
            raise CapabilityError(f"{owner} maps package {name} more than once")
        seen.add(name)
        if role not in {"framework", "toolkit-bridge", "configuration", "engine", "integration"}:
            raise CapabilityError(f"{owner} has an invalid package role")
        if type(required) is not bool:
            raise CapabilityError(f"{owner} package required flag must be boolean")


def resolve(
    catalog: dict[str, Any],
    *,
    mode: str,
    framework: str | None = None,
    engines: Iterable[str] = (),
    include_optional_roles: Iterable[str] = (),
) -> InputMethodPlan:
    validate_catalog(catalog)
    if mode not in MODES:
        raise CapabilityError("input-method mode must be keyboard-only, meo-managed, or self-managed")

    requested_engines = tuple(engines)
    if len(requested_engines) != len(set(requested_engines)):
        raise CapabilityError("input-method engine list contains duplicates")
    if len(requested_engines) > 32:
        raise CapabilityError("too many input-method engines were requested")

    optional_roles = frozenset(include_optional_roles)
    if not optional_roles.issubset(OPTIONAL_ROLES):
        raise CapabilityError("unsupported optional input-method package role")

    # These two modes deliberately create no Meo-owned package request.
    # keyboard-only means no IMF is wanted; self-managed means the user will
    # own framework/engine choices independently. Existing packages are never
    # removed by this pure resolver.
    if mode in {"keyboard-only", "self-managed"}:
        if framework is not None or requested_engines or optional_roles:
            raise CapabilityError(
                f"{mode} mode cannot request a Meo framework, engine, or optional package role"
            )
        return InputMethodPlan(1, mode, None, (), (), "configured-signed-repository")

    if not isinstance(framework, str) or not FRAMEWORK_ID.fullmatch(framework):
        raise CapabilityError("meo-managed input-method mode requires a valid framework id")

    frameworks = {entry["id"]: entry for entry in catalog["frameworks"]}
    framework_entry = frameworks.get(framework)
    if framework_entry is None:
        raise CapabilityError(f"unknown input-method framework: {framework}")
    if mode not in framework_entry["modes"]:
        raise CapabilityError(f"framework {framework} does not support mode {mode}")

    engines_by_id = {entry["id"]: entry for entry in catalog["engines"]}
    packages: set[str] = set()
    for package in framework_entry["packages"]:
        if package["required"] or package["role"] in optional_roles:
            packages.add(package["name"])

    for engine_id in requested_engines:
        engine = engines_by_id.get(engine_id)
        if engine is None:
            raise CapabilityError(f"unknown input-method engine: {engine_id}")
        if engine["framework"] != framework:
            raise CapabilityError(f"input-method engine {engine_id} belongs to a different framework")
        for package in engine["packages"]:
            if package["required"] or package["role"] in optional_roles:
                packages.add(package["name"])

    return InputMethodPlan(
        1,
        mode,
        framework,
        tuple(requested_engines),
        tuple(sorted(packages)),
        "configured-signed-repository",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve a MeoArch input-method capability plan")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=sorted(MODES))
    parser.add_argument("--framework")
    parser.add_argument("--engine", action="append", default=[])
    parser.add_argument("--include-role", action="append", default=[], choices=sorted(OPTIONAL_ROLES))
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        plan = resolve(
            load_catalog(args.catalog),
            mode=args.mode,
            framework=args.framework,
            engines=args.engine,
            include_optional_roles=args.include_role,
        )
    except (CapabilityError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"input-method capability resolution failed: {error}") from error
    print(json.dumps(plan.as_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
