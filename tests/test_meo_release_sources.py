import hashlib
import re
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "packages" / "meo-release"


class MeoReleaseSourceChecksumTest(unittest.TestCase):
    def test_pkgbuild_checksums_match_packaged_catalogs(self):
        text = (PACKAGE / "PKGBUILD").read_text(encoding="utf-8")
        sources = re.search(r"^source=\((.*?)\)", text, re.M | re.S).group(1)
        sums = re.search(r"^sha256sums=\((.*?)\)", text, re.M | re.S).group(1)
        names = re.findall(r"'([^']+)'", sources)
        digests = re.findall(r"'([0-9a-f]{64})'", sums)
        self.assertEqual(len(names), len(digests))
        for name, digest in zip(names, digests):
            actual = hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest()
            self.assertEqual(digest, actual, f"{name} changed without updating sha256sums and pkgrel")



class AllRecipesLocalSourceChecksumTest(unittest.TestCase):
    # meo-keyring's payload files are rendered by the release job, so they are not tracked here.
    RENDERED_AT_RELEASE = {"meo-keyring"}

    def test_local_source_checksums_match_tracked_files(self):
        for recipe in sorted(PACKAGE.parent.glob("*/PKGBUILD")):
            if recipe.parent.name in self.RENDERED_AT_RELEASE:
                continue
            text = recipe.read_text(encoding="utf-8")
            sources = re.search(r"^source=\((.*?)\)\n", text, re.M | re.S)
            sums = re.search(r"^sha256sums=\((.*?)\)\n", text, re.M | re.S)
            if not sources or not sums:
                continue
            names = re.findall(r"'([^']+)'", sources.group(1))
            digests = re.findall(r"'([^']+)'", sums.group(1))
            for name, digest in zip(names, digests):
                if "://" in name or "::" in name or digest == "SKIP":
                    continue
                actual = hashlib.sha256((recipe.parent / name).read_bytes()).hexdigest()
                self.assertEqual(digest, actual, f"{recipe.parent.name}/{name} changed without updating sha256sums")


if __name__ == "__main__":
    unittest.main()
