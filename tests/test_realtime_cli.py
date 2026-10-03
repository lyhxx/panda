from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from panda_infer.realtime_cli import (
    build_runtime_command,
    enrich_device_payload,
    write_json_utf8,
)
from panda_infer.realtime_worker import load_meanvc2_runtime


class RealtimeCliTest(unittest.TestCase):
    def test_runtime_loader_adds_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            runtime = root / "runtime" / "run_rt.py"
            package = root / "runtime" / "src"
            runtime.parent.mkdir(parents=True)
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "dit.py").write_text(
                "VALUE = 42\n",
                encoding="utf-8",
            )
            runtime.write_text(
                "from src.dit import VALUE\n",
                encoding="utf-8",
            )

            try:
                module = load_meanvc2_runtime(root)
                self.assertEqual(module.VALUE, 42)
            finally:
                sys.path.remove(str(root))
                sys.path.remove(str(root / "runtime"))
                sys.modules.pop("panda_meanvc2_runtime", None)
                sys.modules.pop("src.dit", None)
                sys.modules.pop("src", None)

    def test_build_realtime_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            pack = root / "pack"
            reference = pack / "reference" / "reference.wav"
            meanvc2 = root / "MeanVC2"
            reference.parent.mkdir(parents=True)
            (meanvc2 / "runtime").mkdir(parents=True)
            reference.write_bytes(b"RIFF")
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

            args = Namespace(
                meanvc2_root=str(meanvc2),
                python=str(Path(__import__("sys").executable)),
                voice_pack=str(pack),
                target_wav=None,
                model="40ms",
                device="cpu",
                input_device=1,
                output_device=4,
            )
            command = build_runtime_command(args)
            self.assertIn("panda_infer.realtime_worker", command)
            self.assertIn("--input-device", command)
            self.assertIn("1", command)
            self.assertIn("--output-device", command)
            self.assertIn("4", command)

    def test_build_realtime_command_passes_latency_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            pack = root / "pack"
            reference = pack / "reference" / "reference.wav"
            meanvc2 = root / "MeanVC2"
            reference.parent.mkdir(parents=True)
            (meanvc2 / "runtime").mkdir(parents=True)
            reference.write_bytes(b"RIFF")
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

            args = Namespace(
                meanvc2_root=str(meanvc2),
                python=str(Path(sys.executable)),
                voice_pack=str(pack),
                target_wav=None,
                model="40ms",
                device="cpu",
                input_device=None,
                output_device=None,
                prefill_chunks=1,
                max_backlog_chunks=4,
                monitor_device=9,
                noise_gate_db=-45.0,
                limiter_ceiling=0.891,
                output_gain_db=3.0,
                input_gain_db=-2.0,
                monitor_gain_db=-4.0,
                denoise=True,
                denoise_level="balanced",
            )
            command = build_runtime_command(args)

            prefill_index = command.index("--prefill-chunks")
            self.assertEqual(command[prefill_index + 1], "1")
            backlog_index = command.index("--max-backlog-chunks")
            self.assertEqual(command[backlog_index + 1], "4")
            monitor_index = command.index("--monitor-device")
            self.assertEqual(command[monitor_index + 1], "9")
            gate_index = command.index("--noise-gate-db")
            self.assertEqual(command[gate_index + 1], "-45.0")
            limiter_index = command.index("--limiter-ceiling")
            self.assertEqual(command[limiter_index + 1], "0.891")
            gain_index = command.index("--output-gain-db")
            self.assertEqual(command[gain_index + 1], "3.0")
            input_gain_index = command.index("--input-gain-db")
            self.assertEqual(command[input_gain_index + 1], "-2.0")
            monitor_gain_index = command.index("--monitor-gain-db")
            self.assertEqual(command[monitor_gain_index + 1], "-4.0")
            self.assertIn("--denoise", command)
            level_index = command.index("--denoise-level")
            self.assertEqual(command[level_index + 1], "balanced")

    def test_device_payload_marks_virtual_devices(self) -> None:
        payload = {
            "devices": [
                {"index": 1, "name": "CABLE Input (VB-Audio Virtual Cable)"},
                {"index": 2, "name": "Speakers (Realtek(R) Audio)"},
                {
                    "index": 3,
                    "name": "BaoMiao Microphone (BaoMiao Virtual Microphone)",
                },
            ]
        }

        enriched = enrich_device_payload(payload)

        self.assertTrue(enriched["devices"][0]["is_virtual"])
        self.assertFalse(enriched["devices"][1]["is_virtual"])
        self.assertTrue(enriched["devices"][2]["is_virtual"])

    def test_device_payload_tolerates_missing_devices(self) -> None:
        self.assertEqual(enrich_device_payload({}), {})

    def test_device_payload_ignores_non_objects(self) -> None:
        payload = {"devices": ["unexpected"]}

        self.assertEqual(enrich_device_payload(payload), payload)

    def test_write_json_utf8_survives_a_cp936_console(self) -> None:
        class FakeStdout:
            def __init__(self) -> None:
                self.buffer = io.BytesIO()

        fake = FakeStdout()
        name = "麦克风阵列 (英特尔® 智音技术)"

        with contextlib.redirect_stdout(fake):
            write_json_utf8({"name": name})

        decoded = json.loads(fake.buffer.getvalue().decode("utf-8"))
        self.assertEqual(decoded["name"], name)

    def test_write_json_utf8_falls_back_to_text_stream(self) -> None:
        stream = io.StringIO()

        with contextlib.redirect_stdout(stream):
            write_json_utf8({"ok": True})

        self.assertEqual(json.loads(stream.getvalue()), {"ok": True})


if __name__ == "__main__":
    unittest.main()

