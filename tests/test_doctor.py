from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from panda_infer.doctor import (
    check_deepfilter,
    check_meanvc2,
    check_voice_pack,
    counterpart_name,
    describe_virtual_routing,
    find_route_pairs,
    find_virtual_inputs,
    find_virtual_outputs,
    is_virtual_audio_device,
)


class DoctorTest(unittest.TestCase):
    def test_deepfilter_required_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "config.ini").write_text("test", encoding="utf-8")
            checkpoint = root / "checkpoints" / "model_120.ckpt.best"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b"test")

            checks = check_deepfilter(root)

            self.assertEqual(len(checks), 2)
            self.assertTrue(all(check.status == "ok" for check in checks))

    def test_meanvc2_required_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            files = [
                "runtime/run_rt.py",
                "ckpts/vocos/vocos.pt",
                "preprocess/ckpts/wavlm_large_finetune.pth",
                "preprocess/ckpts/wavlm_large_cfg.pt",
                "preprocess/ckpts/fastu2pp_160ms.pt",
                "preprocess/ckpts/fastu2pp_80ms.pt",
                "ckpts/pretrained_models/meanvc2_120ms_40ms.safetensors",
                "ckpts/pretrained_models/meanvc2_40ms_40ms.safetensors",
            ]
            for relative in files:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test")

            checks = check_meanvc2(root)
            self.assertTrue(checks)
            self.assertTrue(all(check.status == "ok" for check in checks))

    def test_invalid_voice_pack_reports_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            pack = Path(temp_name) / "pack"
            pack.mkdir()
            (pack / "manifest.json").write_text(
                json.dumps(
                    {
                        "format": "panda.voice-pack",
                        "engine": "meanvc2",
                        "files": [],
                    }
                ),
                encoding="utf-8",
            )

            checks = check_voice_pack(pack)
            self.assertEqual(checks[0].status, "error")

    def test_virtual_output_detection(self) -> None:
        devices = [
            {
                "index": 1,
                "name": "CABLE Input (VB-Audio Virtual Cable)",
                "hostapi": 0,
                "max_output_channels": 2,
            },
            {
                "index": 2,
                "name": "BaoMiao Microphone (BaoMiao Virtual Microphone)",
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
            },
            {
                "index": 3,
                "name": "Speakers (Realtek Audio)",
                "hostapi": 0,
                "max_output_channels": 2,
            },
        ]

        outputs = find_virtual_outputs(devices, ["Windows WASAPI"])
        self.assertEqual(len(outputs), 1)
        self.assertIn("CABLE Input", outputs[0])

        inputs = find_virtual_inputs(devices, ["Windows WASAPI"])
        self.assertEqual(len(inputs), 1)
        self.assertIn("BaoMiao", inputs[0])

        self.assertTrue(is_virtual_audio_device("VoiceMeeter Input"))
        self.assertFalse(is_virtual_audio_device("Realtek Speakers"))

    def test_routing_message_prefers_a_writable_device(self) -> None:
        message = describe_virtual_routing(
            ["#1 CABLE Input · WASAPI"],
            ["#2 BaoMiao Microphone · WASAPI"],
        )

        self.assertIn("CABLE Input", message)
        self.assertNotIn("无法写入", message)

    def test_routing_message_explains_a_capture_only_device(self) -> None:
        # This is the observed development-host situation: a virtual
        # microphone exists, but nothing writable to feed it.
        message = describe_virtual_routing(
            [],
            ["#2 BaoMiao Microphone · WASAPI"],
        )

        self.assertIn("只提供采集端", message)
        self.assertIn("VB-CABLE", message)

    def test_routing_message_when_nothing_is_detected(self) -> None:
        message = describe_virtual_routing([], [])

        self.assertIn("未检测到虚拟播放设备", message)

    def test_counterpart_name_swaps_the_role_token(self) -> None:
        self.assertEqual(
            counterpart_name("CABLE Input (VB-Audio Virtual Cable)"),
            "CABLE Output (VB-Audio Virtual Cable)",
        )
        self.assertEqual(
            counterpart_name("CABLE Output (VB-Audio Virtual Cable)"),
            "CABLE Input (VB-Audio Virtual Cable)",
        )
        self.assertEqual(
            counterpart_name("VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)"),
            "VoiceMeeter Output (VB-Audio VoiceMeeter VAIO)",
        )

    def test_counterpart_name_needs_a_standalone_role_token(self) -> None:
        self.assertIsNone(
            counterpart_name(
                "BaoMiao Microphone (BaoMiao Virtual Microphone)"
            )
        )
        self.assertIsNone(counterpart_name("Speakers (Realtek(R) Audio)"))
        # "InputDevice" is one word; it is not the Input/Output role token.
        self.assertIsNone(counterpart_name("Virtual InputDevice"))

    def test_find_route_pairs_matches_both_ends(self) -> None:
        devices = [
            {
                "index": 3,
                "name": "CABLE Input (VB-Audio Virtual Cable)",
                "hostapi": 0,
                "max_output_channels": 2,
                "max_input_channels": 0,
            },
            {
                "index": 4,
                "name": "CABLE Output (VB-Audio Virtual Cable)",
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
            },
            {
                "index": 5,
                "name": "Speakers (Realtek(R) Audio)",
                "hostapi": 0,
                "max_output_channels": 2,
            },
        ]

        pairs = find_route_pairs(devices, ["Windows WASAPI"])

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["render_index"], 3)
        self.assertEqual(pairs[0]["capture_index"], 4)
        self.assertIn("CABLE Input", pairs[0]["render"])
        self.assertIn("CABLE Output", pairs[0]["capture"])
        self.assertIn("Windows WASAPI", pairs[0]["render"])

    def test_find_route_pairs_requires_both_ends(self) -> None:
        # The observed development host has a capture-only virtual microphone.
        devices = [
            {
                "index": 2,
                "name": "BaoMiao Microphone (BaoMiao Virtual Microphone)",
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
            }
        ]

        self.assertEqual(find_route_pairs(devices, ["MME"]), [])


if __name__ == "__main__":
    unittest.main()
