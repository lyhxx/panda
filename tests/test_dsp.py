from __future__ import annotations

import unittest

from panda_infer import dsp

HAVE_NUMPY = dsp.np is not None


@unittest.skipUnless(HAVE_NUMPY, "DSP processing needs numpy")
class SoftLimiterTest(unittest.TestCase):
    def test_passes_audio_below_the_knee_unchanged(self) -> None:
        limiter = dsp.SoftLimiter(ceiling=0.9)
        samples = dsp.np.array(
            [-0.5, -0.1, 0.0, 0.1, 0.5],
            dtype=dsp.np.float32,
        )

        output = limiter.process(samples)

        self.assertEqual(output.tolist(), samples.tolist())

    def test_bounds_peaks_at_the_ceiling(self) -> None:
        limiter = dsp.SoftLimiter(ceiling=0.9)
        samples = dsp.np.array(
            [-10.0, -1.0, 0.0, 1.0, 10.0],
            dtype=dsp.np.float32,
        )

        output = limiter.process(samples)

        self.assertLessEqual(
            float(dsp.np.max(dsp.np.abs(output))),
            limiter.ceiling,
        )
        self.assertGreater(float(output[3]), limiter.knee)

    def test_transfer_function_is_monotonic(self) -> None:
        limiter = dsp.SoftLimiter(ceiling=0.9)
        inputs = dsp.np.linspace(0.0, 4.0, 256, dtype=dsp.np.float32)

        output = limiter.process(inputs)

        self.assertTrue(bool(dsp.np.all(dsp.np.diff(output) >= 0.0)))

    def test_preserves_sign(self) -> None:
        limiter = dsp.SoftLimiter(ceiling=0.9)
        samples = dsp.np.array([-3.0, 3.0], dtype=dsp.np.float32)

        output = limiter.process(samples)

        self.assertLess(float(output[0]), 0.0)
        self.assertGreater(float(output[1]), 0.0)

    def test_in_place_matches_the_copying_form(self) -> None:
        limiter = dsp.SoftLimiter(ceiling=0.9)
        samples = dsp.np.array([0.1, 0.8, 2.0], dtype=dsp.np.float32)
        expected = limiter.process(samples)

        limiter.process_in_place(samples)

        self.assertEqual(samples.tolist(), expected.tolist())

    def test_in_place_also_works_on_a_plain_list(self) -> None:
        # np.asarray copies a list, so a naive implementation would silently
        # leave the caller's buffer untouched.
        limiter = dsp.SoftLimiter(ceiling=0.2)
        samples = [0.05, 0.5, -0.5]
        expected = limiter.process(samples).tolist()

        limiter.process_in_place(samples)

        self.assertEqual([float(value) for value in samples], expected)
        self.assertLess(abs(float(samples[1])), 0.2)

    def test_rejects_invalid_settings(self) -> None:
        with self.assertRaises(ValueError):
            dsp.SoftLimiter(ceiling=0.0)
        with self.assertRaises(ValueError):
            dsp.SoftLimiter(ceiling=1.5)
        with self.assertRaises(ValueError):
            dsp.SoftLimiter(ceiling=0.9, knee=0.9)


@unittest.skipUnless(HAVE_NUMPY, "DSP processing needs numpy")
class OutputGainTest(unittest.TestCase):
    def test_zero_db_is_transparent(self) -> None:
        gain = dsp.OutputGain(0.0)
        values = dsp.np.array([0.25, -0.5], dtype=dsp.np.float32)

        output = gain.process(values)

        self.assertTrue(dsp.np.array_equal(output, values))

    def test_positive_gain_scales_the_block(self) -> None:
        gain = dsp.OutputGain(6.0)
        values = dsp.np.array([0.25, -0.5], dtype=dsp.np.float32)

        output = gain.process(values)

        self.assertAlmostEqual(float(output[0]), 0.25 * 10.0 ** (6.0 / 20.0))
        self.assertAlmostEqual(float(output[1]), -0.5 * 10.0 ** (6.0 / 20.0))

    def test_in_place_works_on_a_plain_list(self) -> None:
        gain = dsp.OutputGain(-6.0)
        values = [0.25, -0.5]

        gain.process_in_place(values)

        self.assertAlmostEqual(values[0], 0.25 * 10.0 ** (-6.0 / 20.0))
        self.assertAlmostEqual(values[1], -0.5 * 10.0 ** (-6.0 / 20.0))

    def test_rejects_out_of_range_gain(self) -> None:
        with self.assertRaises(ValueError):
            dsp.OutputGain(-61.0)
        with self.assertRaises(ValueError):
            dsp.OutputGain(25.0)


@unittest.skipUnless(HAVE_NUMPY, "DSP processing needs numpy")
class NoiseGateTest(unittest.TestCase):
    def test_loud_block_passes_through(self) -> None:
        gate = dsp.NoiseGate(threshold_db=-45.0)
        samples = dsp.np.full(64, 0.5, dtype=dsp.np.float32)

        output = gate.process(samples)

        self.assertEqual(output.tolist(), samples.tolist())
        self.assertAlmostEqual(gate.gain, 1.0, places=6)

    def test_quiet_blocks_keep_fading(self) -> None:
        gate = dsp.NoiseGate(threshold_db=-45.0, release=0.5)
        quiet = dsp.np.full(64, 0.0001, dtype=dsp.np.float32)

        first = gate.process(quiet)
        second = gate.process(quiet)
        third = gate.process(quiet)

        peak = lambda block: float(dsp.np.max(dsp.np.abs(block)))
        self.assertLess(peak(second), peak(first))
        self.assertLess(peak(third), peak(second))

    def test_gate_reopens_on_a_loud_block(self) -> None:
        gate = dsp.NoiseGate(threshold_db=-45.0, attack=1.0)
        quiet = dsp.np.full(64, 0.0001, dtype=dsp.np.float32)
        for _ in range(5):
            gate.process(quiet)
        self.assertLess(gate.gain, 0.2)

        output = gate.process(dsp.np.full(64, 0.5, dtype=dsp.np.float32))

        self.assertAlmostEqual(gate.gain, 1.0, places=6)
        self.assertAlmostEqual(float(output[-1]), 0.5, places=6)

    def test_level_of_silence_is_very_low(self) -> None:
        self.assertLess(
            dsp.NoiseGate.level_db(dsp.np.zeros(32, dtype=dsp.np.float32)),
            -100.0,
        )
        self.assertLess(dsp.NoiseGate.level_db([]), -100.0)

    def test_level_of_a_known_block(self) -> None:
        # Full-scale square wave: RMS 1.0, so 0 dBFS.
        samples = dsp.np.ones(64, dtype=dsp.np.float32)
        self.assertAlmostEqual(dsp.NoiseGate.level_db(samples), 0.0, places=5)

    def test_reset_reopens_the_gate(self) -> None:
        gate = dsp.NoiseGate(threshold_db=-45.0)
        for _ in range(10):
            gate.process(dsp.np.full(32, 0.0001, dtype=dsp.np.float32))
        self.assertLess(gate.gain, 0.5)

        gate.reset()

        self.assertEqual(gate.gain, 1.0)

    def test_rejects_invalid_settings(self) -> None:
        with self.assertRaises(ValueError):
            dsp.NoiseGate(threshold_db=10.0)
        with self.assertRaises(ValueError):
            dsp.NoiseGate(threshold_db=-200.0)
        with self.assertRaises(ValueError):
            dsp.NoiseGate(attack=0.0)
        with self.assertRaises(ValueError):
            dsp.NoiseGate(release=1.5)
        with self.assertRaises(ValueError):
            dsp.NoiseGate(floor=2.0)


@unittest.skipUnless(HAVE_NUMPY, "resampling needs numpy")
class StreamResamplerTest(unittest.TestCase):
    def test_equal_rates_pass_through(self) -> None:
        resampler = dsp.StreamResampler(16000)
        samples = dsp.np.linspace(-0.5, 0.5, 32, dtype=dsp.np.float32)

        self.assertTrue(resampler.exact)
        self.assertEqual(resampler.to_engine(samples).tolist(), samples.tolist())
        self.assertEqual(
            resampler.from_engine(samples).tolist(),
            samples.tolist(),
        )

    def test_device_frames_track_the_ratio(self) -> None:
        resampler = dsp.StreamResampler(48000)

        # One 160 ms engine block is 2560 frames at 16 kHz and 7680 at 48 kHz.
        self.assertEqual(resampler.device_frames(2560), 7680)
        self.assertEqual(resampler.engine_frames(7680), 2560)
        self.assertTrue(resampler.uses_polyphase)

    def test_downsampling_preserves_a_low_tone(self) -> None:
        device_rate, engine_rate = 48000, 16000
        resampler = dsp.StreamResampler(device_rate, engine_rate)
        t = dsp.np.arange(device_rate, dtype=dsp.np.float64) / device_rate
        tone = (0.5 * dsp.np.sin(2 * dsp.np.pi * 440 * t)).astype(dsp.np.float32)

        converted = resampler.to_engine(tone)

        self.assertEqual(converted.size, engine_rate)
        # Ignore the filter's start-up transient.
        settled = converted[2000:]
        self.assertAlmostEqual(float(dsp.np.max(dsp.np.abs(settled))), 0.5, places=2)

    def test_dc_is_preserved(self) -> None:
        resampler = dsp.StreamResampler(48000, 16000)
        constant = dsp.np.full(48000, 0.25, dtype=dsp.np.float32)

        converted = resampler.to_engine(constant)

        self.assertAlmostEqual(float(converted[-1]), 0.25, places=5)

    def test_block_processing_matches_one_shot(self) -> None:
        # This is the statefulness guarantee: a stream filtered in 160 ms blocks
        # must come out the same as one continuous pass, otherwise every block
        # boundary becomes a click.
        device_rate, engine_rate = 48000, 16000
        block = 7680
        rng = dsp.np.random.default_rng(7)
        signal = rng.standard_normal(block * 4).astype(dsp.np.float32) * 0.2

        one_shot = dsp.StreamResampler(device_rate, engine_rate).to_engine(signal)

        blocked_resampler = dsp.StreamResampler(device_rate, engine_rate)
        parts = [
            blocked_resampler.to_engine(signal[start:start + block])
            for start in range(0, signal.size, block)
        ]
        blocked = dsp.np.concatenate(parts)

        self.assertEqual(blocked.shape, one_shot.shape)
        self.assertTrue(
            bool(dsp.np.allclose(blocked, one_shot, atol=1e-6)),
            "block-wise resampling drifted from the one-shot result",
        )

    def test_upsampling_preserves_a_low_tone(self) -> None:
        resampler = dsp.StreamResampler(48000, 16000)
        t = dsp.np.arange(16000, dtype=dsp.np.float64) / 16000
        tone = (0.5 * dsp.np.sin(2 * dsp.np.pi * 440 * t)).astype(dsp.np.float32)

        converted = resampler.from_engine(tone)

        self.assertEqual(converted.size, 48000)
        settled = converted[6000:]
        self.assertAlmostEqual(float(dsp.np.max(dsp.np.abs(settled))), 0.5, places=2)

    def test_round_trip_keeps_the_signal(self) -> None:
        device_rate, engine_rate = 48000, 16000
        down = dsp.StreamResampler(device_rate, engine_rate)
        up = dsp.StreamResampler(device_rate, engine_rate)
        t = dsp.np.arange(device_rate, dtype=dsp.np.float64) / device_rate
        tone = (0.4 * dsp.np.sin(2 * dsp.np.pi * 300 * t)).astype(dsp.np.float32)

        round_tripped = up.from_engine(down.to_engine(tone))

        self.assertEqual(round_tripped.size, tone.size)
        inner = slice(12000, 36000)
        # The polyphase filters add a group delay of a few hundred microseconds
        # per direction, so compare the level rather than sample alignment.
        self.assertAlmostEqual(
            float(dsp.np.max(dsp.np.abs(round_tripped[inner]))),
            0.4,
            places=2,
        )

    def test_non_integer_ratio_falls_back_to_interpolation(self) -> None:
        resampler = dsp.StreamResampler(22050, 16000)
        samples = dsp.np.ones(2205, dtype=dsp.np.float32)

        converted = resampler.to_engine(samples)

        self.assertFalse(resampler.uses_polyphase)
        self.assertEqual(converted.size, 1600)
        self.assertAlmostEqual(float(converted[-1]), 1.0, places=5)

    def test_one_instance_handles_both_directions(self) -> None:
        # Capture comes in at the device rate and playback goes out at it, so a
        # single resampler has to serve both.
        resampler = dsp.StreamResampler(48000, 16000)

        down = resampler.to_engine(dsp.np.ones(7680, dtype=dsp.np.float32))
        up = resampler.from_engine(dsp.np.ones(2560, dtype=dsp.np.float32))

        self.assertEqual(down.size, 2560)
        self.assertEqual(up.size, 7680)
        self.assertAlmostEqual(float(down[-1]), 1.0, places=5)
        self.assertAlmostEqual(float(up[-1]), 1.0, places=4)

    def test_invalid_arguments_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dsp.StreamResampler(0)
        with self.assertRaises(ValueError):
            dsp.StreamResampler(48000, 0)
        with self.assertRaises(ValueError):
            dsp.StreamResampler(48000).device_frames(0)


if __name__ == "__main__":
    unittest.main()
