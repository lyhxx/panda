"""The product version must stay identical across the two language ecosystems.

core/include/panda/version.hpp is the single source of truth for C++ (the root
CMakeLists parses it for project(VERSION) and the packaging script reads it
for the package manifest). python/src/panda_version.py is the single source of
truth for Python (pyproject reads it through setuptools dynamic version).

A release bumps both files, and this test is what stops them from drifting
apart -- which is exactly what happened while they were at 0.1.0.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_HEADER = REPO_ROOT / "core" / "include" / "panda" / "version.hpp"


class VersionConsistencyTest(unittest.TestCase):
    def test_cpp_header_has_a_version_triple(self) -> None:
        header = VERSION_HEADER.read_text(encoding="utf-8")
        match = re.search(r"Version\{\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", header)
        self.assertIsNotNone(
            match,
            f"no Version{{major, minor, patch}} literal found in {VERSION_HEADER}",
        )

    def test_python_version_matches_cpp_version(self) -> None:
        from panda_version import __version__

        header = VERSION_HEADER.read_text(encoding="utf-8")
        match = re.search(r"Version\{\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", header)
        assert match is not None
        cpp_version = ".".join(match.groups())
        self.assertEqual(
            __version__,
            cpp_version,
            "version.hpp and panda_version.py disagree; bump both to the same "
            "value",
        )

    def test_python_version_is_a_release_triple(self) -> None:
        from panda_version import __version__

        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
