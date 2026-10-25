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


if __name__ == "__main__":
    unittest.main()
