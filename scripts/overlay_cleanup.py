#!/usr/bin/env python3
"""Find beta DB entries superseded by the current Stable DB using vercmp."""
from __future__ import annotations

import argparse
import subprocess
import tarfile
from pathlib import Path


def database_versions(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    with tarfile.open(path, "r:*") as database:
        for member in database.getmembers():
            if not member.isfile() or not member.name.endswith("/desc"):
                continue
            extracted = database.extractfile(member)
            if extracted is None:
                raise ValueError(f"could not read {member.name}")
            lines = extracted.read().decode("utf-8", errors="strict").splitlines()
            fields: dict[str, str] = {}
            for index, line in enumerate(lines[:-1]):
                if line in {"%NAME%", "%VERSION%"}:
                    fields[line] = lines[index + 1]
            if set(fields) != {"%NAME%", "%VERSION%"}:
                raise ValueError(f"invalid repository record: {member.name}")
            packages[fields["%NAME%"]] = fields["%VERSION%"]
    return packages


def comparison(left: str, right: str) -> int:
    result = subprocess.run(["vercmp", left, right], check=True, capture_output=True, text=True)
    value = int(result.stdout.strip())
    if value not in {-1, 0, 1}:
        raise ValueError("vercmp returned an invalid result")
    return value


def cleanup_candidates(stable: dict[str, str], beta: dict[str, str], compare=comparison) -> list[str]:
    return sorted(name for name, beta_version in beta.items()
                  if name in stable and compare(stable[name], beta_version) >= 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stable", type=Path)
    parser.add_argument("beta", type=Path)
    arguments = parser.parse_args()
    for name in cleanup_candidates(database_versions(arguments.stable), database_versions(arguments.beta)):
        print(name)


if __name__ == "__main__":
    main()
