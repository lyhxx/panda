from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from panda_pack.cli import main


class ExportVoicePackTest(unittest.TestCase):
    def make_wav(self, path: Path) -> None:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * 1600)

    def test_export_with_existing_feature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            wav_path = root / "original-take.wav"
            feature_path = root / "spk_emb.npy"
            output = root / "pack"
            self.make_wav(wav_path)
            feature_path.write_bytes(b"\x93NUMPYtest-feature")

            code = main(
                [
                    "--name",
                    "曼波",
                    "--id",
                    "manbo",
                    "--audio",
                    str(wav_path),
                    "--feature-file",
                    str(feature_path),
                    "--output",
                    str(output),
                    "--overwrite",
                ]
            )

            self.assertEqual(code, 0)
            self.assertTrue((output / "manifest.json").is_file())
            self.assertTrue((output / "assets" / "spk_emb.npy").is_file())
            self.assertTrue((output / "assets" / "register.json").is_file())
            self.assertTrue(output.with_suffix(".zip").is_file())

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["id"], "manbo")
            self.assertEqual(manifest["format"], "panda.voice-pack")
            self.assertEqual(manifest["engine"], "meanvc2")

            # The pack is distributed as-is: the original recording's file
            # name is local context the recipient has no business seeing,
            # so it must not ride along in any shipped metadata.
            register_text = (
                output / "assets" / "register.json"
            ).read_text(encoding="utf-8")
            self.assertNotIn("source_name", register_text)
            self.assertNotIn("original-take", register_text)
            self.assertNotIn("original-take", json.dumps(manifest))

            with zipfile.ZipFile(output.with_suffix(".zip")) as archive:
                names = archive.namelist()
                self.assertIn("manifest.json", names)
                self.assertIn("assets/spk_emb.npy", names)

    def test_export_converts_non_16k_audio(self) -> None:
        try:
            import numpy as np
            import soundfile as sf
        except ImportError:
            self.skipTest("soundfile and numpy are needed for audio conversion")

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "reference-24k.wav"
            feature_path = root / "spk_emb.npy"
            output = root / "pack"
            tone = np.sin(
                2.0 * np.pi * 220.0 * np.arange(24000, dtype=np.float32) / 24000.0
            )
            sf.write(str(source), tone, 24000, subtype="PCM_16")
            feature_path.write_bytes(b"\x93NUMPYtest-feature")

            code = main(
                [
                    "--name",
                    "转换测试",
                    "--id",
                    "converted-test",
                    "--audio",
                    str(source),
                    "--feature-file",
                    str(feature_path),
                    "--output",
                    str(output),
                    "--overwrite",
                    "--no-zip",
                ]
            )

            self.assertEqual(code, 0)
            converted = output / "reference" / "reference.wav"
            self.assertTrue(converted.is_file())
            info = sf.info(str(converted))
            self.assertEqual(info.samplerate, 16000)
            self.assertEqual(info.channels, 1)


    def test_failed_overwrite_keeps_previous_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            wav_path = root / "reference.wav"
            feature_path = root / "spk_emb.npy"
            output = root / "pack"
            self.make_wav(wav_path)
            feature_path.write_bytes(b"\x93NUMPYtest-feature")

            args = [
                "--name",
                "覆盖测试",
                "--id",
                "overwrite-test",
                "--audio",
                str(wav_path),
                "--feature-file",
                str(feature_path),
                "--output",
                str(output),
                "--overwrite",
            ]
            self.assertEqual(main(args), 0)
            manifest_before = (output / "manifest.json").read_bytes()
            zip_before = output.with_suffix(".zip").read_bytes()

            # The icon is validated mid-build; failing there used to leave
            # neither the old pack nor a new one.
            with self.assertRaises(FileNotFoundError):
                main(args + ["--icon", str(root / "missing.png")])

            self.assertEqual(
                (output / "manifest.json").read_bytes(), manifest_before
            )
            self.assertEqual(
                output.with_suffix(".zip").read_bytes(), zip_before
            )
            self.assertFalse((root / "pack.partial").exists())


if __name__ == "__main__":
    unittest.main()

