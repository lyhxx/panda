"""End-to-end tests for the Windows install scripts.

These run the real PowerShell scripts against a fake package, so they cover
the upgrade and integrity behaviour that unit tests cannot reach.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_windows.ps1"


def powershell_executable() -> str | None:
    for candidate in ("powershell", "pwsh"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 256), b""):
            digest.update(block)
    return digest.hexdigest()


def write_package_manifest(package: Path, version: str = "0.1.0") -> None:
    files = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.name == "package-manifest.json":
            continue
        files.append(
            {
                "path": path.relative_to(package).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_of(path),
            }
        )
    manifest = {
        "format": "panda.package",
        "schema_version": 1,
        "version": version,
        "created_at": "2026-10-02T00:00:00Z",
        "files": files,
    }
    (package / "package-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_fake_package(root: Path) -> Path:
    package = root / "package"
    (package / "share" / "python" / "panda_cli").mkdir(parents=True)
    (package / "panda_desktop.exe").write_bytes(b"MZ fake executable")
    (package / "portable").write_bytes(b"")
    (package / "launch.cmd").write_text("@echo off\n", encoding="ascii")
    (package / "share" / "python" / "panda_cli" / "__init__.py").write_text(
        "__version__ = '0.1.0'\n",
        encoding="utf-8",
    )
    write_package_manifest(package)
    return package


@unittest.skipUnless(os.name == "nt", "Windows installer scripts")
class WindowsInstallerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.powershell = powershell_executable()
        if cls.powershell is None:
            raise unittest.SkipTest("PowerShell was not found")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_installer(self, source: Path, install: Path, *extra: str):
        # This host's inherited PSModulePath lists PowerShell 7 and Codex
        # runtime module directories ahead of the Windows PowerShell ones, so
        # Windows PowerShell finds a Security module it cannot load. Point the
        # child at its own module directories instead.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key != "PSModulePath"
        }
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        environment["PSModulePath"] = os.pathsep.join(
            str(path)
            for path in (
                Path(system_root)
                / "system32"
                / "WindowsPowerShell"
                / "v1.0"
                / "Modules",
                Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
                / "WindowsPowerShell"
                / "Modules",
                Path(os.environ.get("USERPROFILE", ""))
                / "Documents"
                / "WindowsPowerShell"
                / "Modules",
            )
        )
        return subprocess.run(
            [
                self.powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(INSTALL_SCRIPT),
                "-SourceDirectory",
                str(source),
                "-InstallDirectory",
                str(install),
                "-NoShortcut",
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )

    def read_install_info(self, install: Path) -> dict:
        info = install / "install.json"
        self.assertTrue(info.is_file(), f"missing {info}")
        return json.loads(info.read_text(encoding="utf-8-sig"))

    def test_fresh_install_copies_the_package(self) -> None:
        package = build_fake_package(self.root)
        install = self.root / "install"

        completed = self.run_installer(package, install)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        app = install / "app"
        self.assertTrue((app / "panda_desktop.exe").is_file())
        self.assertTrue(
            (app / "share" / "python" / "panda_cli" / "__init__.py").is_file()
        )
        # The portable marker must be stripped from an installed copy.
        self.assertFalse((app / "portable").exists())
        # The manifest travels with the package so the install can be audited.
        self.assertTrue((app / "package-manifest.json").is_file())

        info = self.read_install_info(install)
        self.assertEqual(info["version"], "0.1.0")
        self.assertIsNone(info["previous_version"])
        self.assertTrue(Path(info["voice_directory"]).is_dir())

    def test_upgrade_preserves_voice_packs(self) -> None:
        package = build_fake_package(self.root)
        install = self.root / "install"
        self.assertEqual(self.run_installer(package, install).returncode, 0)

        # A user voice pack lives next to the application by default.
        voice = install / "voices" / "my-pack" / "manifest.json"
        voice.parent.mkdir(parents=True, exist_ok=True)
        voice.write_text('{"id": "my-pack"}', encoding="utf-8")

        # Ship a newer build and upgrade in place.
        (package / "panda_desktop.exe").write_bytes(b"MZ fake executable v2")
        write_package_manifest(package, version="0.2.0")

        completed = self.run_installer(package, install, "-Force")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(voice.is_file(), "voice packs must survive an upgrade")
        self.assertEqual(
            (install / "app" / "panda_desktop.exe").read_bytes(),
            b"MZ fake executable v2",
        )

        info = self.read_install_info(install)
        self.assertEqual(info["version"], "0.2.0")
        self.assertEqual(info["previous_version"], "0.1.0")

    def test_tampered_package_is_rejected(self) -> None:
        package = build_fake_package(self.root)
        install = self.root / "install"
        target = package / "panda_desktop.exe"
        original = target.read_bytes()
        # Same length, different content: only the checksum can catch this.
        target.write_bytes(b"MZ" + b"x" * (len(original) - 2))

        completed = self.run_installer(package, install)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("checksum mismatch", completed.stderr + completed.stdout)
        self.assertFalse((install / "app").exists())
        self.assertFalse((install / "install.json").exists())

    def test_truncated_package_is_rejected(self) -> None:
        package = build_fake_package(self.root)
        install = self.root / "install"
        target = package / "panda_desktop.exe"
        target.write_bytes(target.read_bytes()[:5])

        completed = self.run_installer(package, install)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("size mismatch", completed.stderr + completed.stdout)
        self.assertFalse((install / "app").exists())

    def test_missing_manifest_is_rejected_unless_skipped(self) -> None:
        package = build_fake_package(self.root)
        install = self.root / "install"
        (package / "package-manifest.json").unlink()

        rejected = self.run_installer(package, install)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse((install / "app").exists())

        skipped = self.run_installer(package, install, "-SkipVerify")
        self.assertEqual(skipped.returncode, 0, skipped.stderr)
        self.assertTrue((install / "app" / "panda_desktop.exe").is_file())

    def test_existing_directory_is_refused_without_force(self) -> None:
        package = build_fake_package(self.root)
        install = self.root / "install"
        self.assertEqual(self.run_installer(package, install).returncode, 0)

        refused = self.run_installer(package, install)

        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("-Force", refused.stderr + refused.stdout)

    def test_require_signature_refuses_an_unsigned_package(self) -> None:
        # Checksums prove the package was not altered; only a signature says
        # who packed it, so a caller can demand one.
        package = build_fake_package(self.root)
        install = self.root / "install"

        refused = self.run_installer(package, install, "-RequireSignature")

        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(
            "not validly signed",
            refused.stderr + refused.stdout,
        )
        self.assertFalse((install / "app").exists())


if __name__ == "__main__":
    unittest.main()
