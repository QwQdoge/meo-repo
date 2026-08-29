#!/usr/bin/env python3
"""Small, testable beta-overlay policy helpers; publication owns DB mutation."""
from __future__ import annotations
import re

def split_version(value: str) -> tuple[tuple[int | str, ...], bool]:
    """Conservative comparator for policy tests; release job also calls vercmp."""
    base, _, _rel = value.partition("-")
    tokens = tuple(int(x) if x.isdigit() else x.lower()
                   for x in re.findall(r"\d+|[A-Za-z]+", base))
    return tokens, bool(re.search(r"(?:alpha|beta|rc|pre)", base, re.I))

def stable_supersedes_beta(stable: str, beta: str, vercmp: int) -> bool:
    """Only remove a beta package when pacman's own comparison says stable wins.

    ``stable`` and ``beta`` remain inputs for audit logging.  Do not recreate
    pacman's nuanced epoch/pkgver/pkgrel ordering in Python: publication passes
    the result of the Arch ``vercmp`` binary and this policy trusts only it.
    """
    del stable, beta
    return vercmp >= 0
