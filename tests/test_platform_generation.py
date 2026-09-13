import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_platform_generation import ManifestError, validate


CORE = [
    "meoui-qml",
    "meo-lockscreen",
    "meo-login-manager",
    "meo-desktop",
    "meo-settings",
    "meo-core-meta",
]
ROOTS = [
    "kscreenlocker",
    "plasma-workspace",
    "plasma-desktop",
    "kwin",
    "qt6-base",
    "qt6-declarative",
    "kf6-kconfig",
]


def artifact(name, origin):
    return {
        "name": name,
        "version": "6.7.5-1",
        "origin": origin,
        "sourceUrl": f"https://packages.example.invalid/{origin}/{name}",
        "archiveSha256": "a" * 64,
    }


def valid_manifest():
    packages = [artifact(name, "meo") for name in CORE]
    roots = [artifact(name, "arch-snapshot") for name in ROOTS]
    return {
        "schemaVersion": 1,
        "platformGeneration": "meo-plasma-6.7",
        "architecture": "x86_64",
        "train": {"channel": "beta", "id": "2026.09-beta.7"},
        "entryPackage": "meo-core-meta",
        "sessionPackages": packages,
        "preservedPackages": ["kscreenlocker", "plasma-workspace", "plasma-desktop", "kwin"],
        "replacedPackages": [{"name": "plasma-login-manager", "replacedBy": "meo-login-manager"}],
        "platformRoots": roots,
        "dependencyClosure": [
            {**item, "depends": []}
            for item in [*packages, *roots]
        ],
        "upgradePolicy": {
            "atomicCoreUpdate": True,
            "allowIgnorePkg": False,
            "allowPartialCoreUpgrade": False,
        },
    }


class PlatformGenerationTests(unittest.TestCase):
    def test_complete_generation_is_accepted(self):
        validate(valid_manifest())

    def test_all_core_packages_must_travel_together(self):
        manifest = valid_manifest()
        manifest["sessionPackages"] = manifest["sessionPackages"][:-1]
        with self.assertRaisesRegex(ManifestError, "sessionPackages"):
            validate(manifest)

    def test_platform_security_core_cannot_be_replaced(self):
        manifest = valid_manifest()
        manifest["replacedPackages"].append({"name": "kscreenlocker", "replacedBy": "meo-lockscreen"})
        with self.assertRaisesRegex(ManifestError, "preserved"):
            validate(manifest)

    def test_closure_and_policy_are_fail_closed(self):
        manifest = valid_manifest()
        manifest["dependencyClosure"] = [
            item for item in manifest["dependencyClosure"] if item["name"] != "kwin"
        ]
        with self.assertRaisesRegex(ManifestError, "dependencyClosure"):
            validate(manifest)

        manifest = valid_manifest()
        manifest["upgradePolicy"]["allowIgnorePkg"] = True
        with self.assertRaisesRegex(ManifestError, "atomic"):
            validate(manifest)

    def test_schema_matches_the_validator_surface(self):
        import json

        schema = json.loads((ROOT / "manifests/platform-generation.schema.json").read_text())
        self.assertEqual(schema["$id"], "https://meoarch.org/schemas/platform-generation/v1")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["entryPackage"], {"const": "meo-core-meta"})
        self.assertEqual(
            schema["properties"]["upgradePolicy"]["properties"]["allowPartialCoreUpgrade"],
            {"const": False},
        )

    def test_validator_does_not_mutate_the_manifest(self):
        manifest = valid_manifest()
        before = copy.deepcopy(manifest)
        validate(manifest)
        self.assertEqual(manifest, before)


if __name__ == "__main__":
    unittest.main()
