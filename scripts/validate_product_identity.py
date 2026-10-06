#!/usr/bin/env python3
"""Validate release-facing pacman metadata against the frozen Meo identity."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "packages/meo-desktop/PKGBUILD": 'pkgdesc="Meo Desktop integration for MeoArch, powered by KDE Plasma"',
    "packages/meo-plasma-login-manager/PKGBUILD": 'pkgdesc="Meo Login display manager for MeoArch"',
    "packages/meo-settings/PKGBUILD": 'pkgdesc="Meo Settings application for MeoArch"',
    "packages/meo-account/PKGBUILD": 'pkgdesc="Meo Account broker and authentication dialog for MeoArch"',
    "packages/omnistore-bin/PKGBUILD": 'pkgdesc="OmniStore software manager for MeoArch"',
    "packages/meo-core-meta/PKGBUILD": 'pkgdesc="Meo Desktop core package for MeoArch"',
    "packages/meo-apps-meta/PKGBUILD": 'pkgdesc="Meo first-party application bundle for MeoArch"',
    "packages/meo-recommended-meta/PKGBUILD": 'pkgdesc="Complete recommended Meo experience for MeoArch"',
    "packages/meo-keyring/PKGBUILD": 'pkgdesc="Meo package signing keyring for MeoArch"',
    "packages/meo-release/PKGBUILD": 'pkgdesc="MeoArch release metadata"',
}

FORBIDDEN = (
    'pkgdesc="MeoArch core desktop profile"',
    'pkgdesc="MeoArch official apps integration meta package"',
    'pkgdesc="Complete supported MeoArch application experience"',
    'pkgdesc="Native Qt 6 MeoArch system settings application"',
    'pkgdesc="MeoArch system account broker and authentication dialog"',
)


def fail(message: str) -> None:
    print(f"product identity validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    for relative, expected in EXPECTED.items():
        path = ROOT / relative
        if not path.is_file():
            fail(f"missing package recipe: {relative}")
        text = path.read_text(encoding="utf-8")
        if expected not in text:
            fail(f"{relative} does not contain canonical metadata {expected!r}")
        for forbidden in FORBIDDEN:
            if forbidden in text:
                fail(f"{relative} still contains legacy public metadata {forbidden!r}")

    key_doc = (ROOT / "docs/KEY_MANAGEMENT.md").read_text(encoding="utf-8")
    if "MeoArch Package Archive <packages@meoarch.org>" not in key_doc:
        fail("package signing identity is not frozen in docs/KEY_MANAGEMENT.md")
    if "ACCF 58C0 05D4 67A0 C863 3806 F302 FD51 C406 16AA" not in key_doc:
        fail("trusted package-archive fingerprint is missing from the key-management runbook")

    print("product identity validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
