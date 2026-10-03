from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from panda_infer import denoise

HAVE_NUMPY = denoise.np is not None


@unittest.skipUnless(HAVE_NUMPY, "denoising needs numpy")
class DenoiserTest(unittest.TestCase):
    BLOCK = 2560  # 160 ms at 16 kHz

    def make(self, calls: list[int] | None = None, **kwargs):
        def fake(window):
            if calls is not None:
                calls.append(len(window))
            return window

        return denoise.Denoiser(fake, **kwargs)

    def test_returns_exactly_one_block_every_time(self) -> None:
        denoiser = self.make()

        for _ in range(6):
            out = denoiser.process(denoise.np.zeros(self.BLOCK, dtype="float32"))
            self.assertEqual(out.size, self.BLOCK)

    def test_reports_one_block_of_latency(self) -> None:
        denoiser = self.make(window_blocks=2, hop_blocks=1)

        self.assertEqual(denoiser.latency_blocks, 1)
        self.assertAlmostEqual(denoiser.latency_ms, 160.0)

    def test_the_first_block_is_silence_while_the_window_fills(self) -> None:
        denoiser = self.make()
        loud = denoise.np.ones(self.BLOCK, dtype="float32")

        first = denoiser.process(loud)

        # One window of input is needed before anything can be emitted.
        self.assertEqual(float(denoise.np.max(denoise.np.abs(first))), 0.0)

    def test_audio_flows_once_the_window_is_full(self) -> None:
        denoiser = self.make()
        loud = denoise.np.ones(self.BLOCK, dtype="float32")

        outputs = [denoiser.process(loud) for _ in range(4)]

        self.assertTrue(
            any(float(denoise.np.max(denoise.np.abs(out))) > 0.5 for out in outputs)
        )

    def test_the_denoiser_sees_full_windows(self) -> None:
        calls: list[int] = []
        denoiser = self.make(calls, window_blocks=2, hop_blocks=1)

        for _ in range(4):
            denoiser.process(denoise.np.zeros(self.BLOCK, dtype="float32"))

        # Two engine blocks at three times the rate.
        self.assertTrue(calls)
        self.assertTrue(all(size == self.BLOCK * 3 * 2 for size in calls))

    def test_wrong_block_size_is_rejected(self) -> None:
        denoiser = self.make()

        with self.assertRaises(ValueError):
            denoiser.process(denoise.np.zeros(10, dtype="float32"))

    def test_invalid_window_settings_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.make(window_blocks=0)
        with self.assertRaises(ValueError):
            self.make(window_blocks=1, hop_blocks=2)

    def test_reset_clears_the_buffers(self) -> None:
        denoiser = self.make()
        loud = denoise.np.ones(self.BLOCK, dtype="float32")
        for _ in range(3):
            denoiser.process(loud)

        denoiser.reset()

        out = denoiser.process(loud)
        self.assertEqual(float(denoise.np.max(denoise.np.abs(out))), 0.0)

    def test_explicit_model_directory_wins(self) -> None:
        with TemporaryDirectory() as temp_name:
            explicit = Path(temp_name) / "explicit"
            self.assertEqual(
                denoise.resolve_model_base_dir(explicit),
                str(explicit),
            )

    def test_packaged_model_directory_is_discovered_from_environment(self) -> None:
        with TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "DeepFilterNet3"
            root.mkdir()
            (root / "config.ini").write_text("test", encoding="utf-8")

            with patch.dict(
                "os.environ",
                {"PANDA_DEEPFILTER_ROOT": str(root)},
                clear=False,
            ):
                self.assertEqual(
                    denoise.resolve_model_base_dir(),
                    str(root),
                )

    def test_denoise_levels_map_to_attenuation_limits(self) -> None:
        self.assertEqual(denoise.attenuation_limit_db("strong"), 0.0)
        self.assertEqual(denoise.attenuation_limit_db("balanced"), 12.0)
        self.assertEqual(denoise.attenuation_limit_db("gentle"), 6.0)
        with self.assertRaises(ValueError):
            denoise.attenuation_limit_db("unknown")


if __name__ == "__main__":
    unittest.main()
