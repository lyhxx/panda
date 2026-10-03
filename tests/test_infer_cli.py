from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from panda_infer.cli import build_runtime_command, resolve_reference_from_pack


class InferCliTest(unittest.TestCase):
    def test_resolve_reference_and_build_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            pack = root / "pack"
            reference = pack / "reference" / "reference.wav"
            source = root / "source.wav"
            output = root / "output.wav"
            meanvc2 = root / "MeanVC2"

            reference.parent.mkdir(parents=True)
            (meanvc2 / "runtime").mkdir(parents=True)
            reference.write_bytes(b"RIFF")
            source.write_bytes(b"RIFF")
            (meanvc2 / "runtime" / "run_rt.py").write_text(
                "print('runtime')\n",
                encoding="utf-8",
            )
            (pack / "manifest.json").write_text(
                json.dumps(
                    {
                        "format": "panda.voice-pack",
                        "engine": "meanvc2",
                        "files": [{"path": "reference/reference.wav"}],
                    }
                ),
                encoding="utf-8",
            )

            resolved = resolve_reference_from_pack(pack)
            self.assertEqual(resolved, reference.resolve())

            args = Namespace(
                meanvc2_root=str(meanvc2),
                python=str(Path(__import__("sys").executable)),
                source_wav=str(source),
                voice_pack=str(pack),
                target_wav=None,
                output_wav=str(output),
                model="120ms",
                device="cpu",
                seed=666,
            )
            command = build_runtime_command(args)
            self.assertIn("--target-spk", command)
            self.assertIn(str(reference.resolve()), command)


if __name__ == "__main__":
    unittest.main()

