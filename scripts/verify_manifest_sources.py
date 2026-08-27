#!/usr/bin/env python3
"""Verify that every reviewed source tag still resolves to its pinned commit."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG = re.compile(r"^v[A-Za-z0-9._+-]+$")


def remote_tag_commit(repository: str, tag: str) -> str:
    if not REPOSITORY.fullmatch(repository) or not TAG.fullmatch(tag):
        raise ValueError("invalid GitHub repository or tag")
    result = subprocess.run(
        ["git", "ls-remote", f"https://github.com/{repository}.git", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
        check=True, capture_output=True, text=True, timeout=30,
    )
    records = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if not records:
        raise ValueError(f"release tag does not exist: {repository}@{tag}")
    peeled = next((sha for sha, reference in records if reference.endswith("^{}")), None)
    return peeled or records[0][0]


def verify(manifest: dict, resolver=remote_tag_commit) -> None:
    for name, component in manifest["components"].items():
        actual = resolver(component["repository"], component["tag"])
        if actual != component["commit"]:
            raise ValueError(f"{name} tag resolves to {actual}, not pinned commit {component['commit']}")
        if component.get("sourceLayout", "source") == "source" and component["commit"] not in component["sourceUrl"]:
            raise ValueError(f"{name} source URL is not bound to its pinned commit")
        if name == "omnistore-bin" and component["commit"] not in component["verifierUrl"]:
            raise ValueError("OmniStore verifier URL is not bound to its pinned commit")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    arguments = parser.parse_args()
    verify(json.loads(arguments.manifest.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
