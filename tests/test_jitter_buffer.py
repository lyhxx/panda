from __future__ import annotations

import unittest

from panda_infer.jitter_buffer import JitterBuffer

BLOCK = 2560  # 160 ms at 16 kHz


class JitterBufferTest(unittest.TestCase):
    def test_prefill_returns_silence_until_primed(self) -> None:
        buffer = JitterBuffer(target_depth=BLOCK)

        self.assertFalse(buffer.primed)
        self.assertEqual(buffer.read(BLOCK), [0.0] * BLOCK)
        # Pre-roll silence is intentional and must not be reported as a
        # genuine underrun.
        self.assertEqual(buffer.prefill_reads, 1)
        self.assertEqual(buffer.prefill_frames, BLOCK)
        self.assertEqual(buffer.starved_reads, 0)
        self.assertEqual(buffer.underrun_frames, 0)

        buffer.push([1.0] * BLOCK)

        self.assertTrue(buffer.primed)
        self.assertEqual(buffer.read(BLOCK), [1.0] * BLOCK)
        self.assertEqual(buffer.starved_reads, 0)

    def test_zero_target_is_primed_immediately(self) -> None:
        buffer = JitterBuffer(target_depth=0)

        self.assertTrue(buffer.primed)
        self.assertEqual(buffer.read(BLOCK), [0.0] * BLOCK)
        self.assertEqual(buffer.starved_reads, 1)

    def test_backlog_absorbs_a_slow_block(self) -> None:
        # A two-block pre-roll lets the consumer keep reading while the
        # converter is stalled on a single slow block.
        buffer = JitterBuffer(target_depth=2 * BLOCK)
        buffer.push([1.0] * BLOCK)
        buffer.push([2.0] * BLOCK)

        self.assertEqual(buffer.read(BLOCK), [1.0] * BLOCK)
        self.assertEqual(buffer.read(BLOCK), [2.0] * BLOCK)
        self.assertEqual(buffer.starved_reads, 0)
        self.assertEqual(buffer.underrun_frames, 0)
        self.assertEqual(buffer.depth, 0)

    def test_drained_buffer_resumes_below_the_full_preroll(self) -> None:
        # After a total drain the listener must not wait for another full
        # pre-roll: the converter hands audio over in 120-240 ms bursts, so
        # demanding the whole target added a fixed block of silence to every
        # underrun on top of its shortfall.
        buffer = JitterBuffer(target_depth=2 * BLOCK)
        buffer.push([1.0] * BLOCK)
        buffer.push([2.0] * BLOCK)
        buffer.read(BLOCK)
        buffer.read(BLOCK)

        self.assertFalse(buffer.primed)
        self.assertEqual(buffer.read(BLOCK), [0.0] * BLOCK)
        self.assertEqual(buffer.prefill_reads, 1)
        # One silent read was forced by the underrun, not by start-up.
        self.assertEqual(buffer.resume_reads, 1)

        buffer.push([3.0] * BLOCK)
        self.assertTrue(buffer.primed)
        self.assertEqual(buffer.read(BLOCK), [3.0] * BLOCK)

    def test_first_start_still_waits_for_the_full_preroll(self) -> None:
        buffer = JitterBuffer(target_depth=2 * BLOCK)
        buffer.push([1.0] * BLOCK)
        self.assertFalse(buffer.primed)
        self.assertEqual(buffer.resume_reads, 0)

        buffer.push([2.0] * BLOCK)
        self.assertTrue(buffer.primed)

    def test_resume_depth_follows_the_preroll_and_ratio(self) -> None:
        buffer = JitterBuffer(target_depth=4 * BLOCK, resume_ratio=0.5)
        self.assertEqual(buffer.resume_depth, 2 * BLOCK)
        # Until playback has started once, the full pre-roll gates it.
        self.assertEqual(buffer.prime_threshold, 4 * BLOCK)

        buffer.set_target_depth(6 * BLOCK)
        self.assertEqual(buffer.resume_depth, 3 * BLOCK)

        buffer.push([1.0] * 6 * BLOCK)
        self.assertTrue(buffer.primed)
        # From here on a drain only needs the half-depth to resume.
        self.assertEqual(buffer.prime_threshold, 3 * BLOCK)

    def test_shortfall_is_zero_filled_and_counted(self) -> None:
        buffer = JitterBuffer(target_depth=0)
        buffer.push([1.0] * (BLOCK // 2))

        output = buffer.read(BLOCK)

        self.assertEqual(output[: BLOCK // 2], [1.0] * (BLOCK // 2))
        self.assertEqual(output[BLOCK // 2:], [0.0] * (BLOCK // 2))
        self.assertEqual(buffer.underrun_frames, BLOCK // 2)
        self.assertEqual(buffer.starved_reads, 1)

    def test_overflow_drops_oldest_frames(self) -> None:
        buffer = JitterBuffer(target_depth=0, max_depth=BLOCK)
        buffer.push([1.0] * BLOCK)
        buffer.push([2.0] * BLOCK)

        self.assertEqual(buffer.depth, BLOCK)
        self.assertEqual(buffer.dropped_frames, BLOCK)
        self.assertEqual(buffer.read(BLOCK), [2.0] * BLOCK)

    def test_order_is_preserved_across_many_small_pushes(self) -> None:
        buffer = JitterBuffer(target_depth=0, max_depth=8 * BLOCK)
        pushed: list[float] = []
        for index in range(200):
            piece = [float(index)] * 32
            pushed.extend(piece)
            buffer.push(piece)

        output: list[float] = []
        while len(output) < len(pushed):
            output.extend(buffer.read(256))

        self.assertEqual(output[: len(pushed)], pushed)
        self.assertEqual(buffer.depth, 0)

    def test_depth_ms(self) -> None:
        buffer = JitterBuffer(target_depth=0)
        buffer.push([1.0] * 8000)

        self.assertAlmostEqual(buffer.depth_ms(16000), 500.0)

    def test_trim_discards_the_oldest_frames(self) -> None:
        buffer = JitterBuffer(target_depth=0, max_depth=8 * BLOCK)
        buffer.push([1.0] * BLOCK)
        buffer.push([2.0] * BLOCK)
        buffer.push([3.0] * BLOCK)

        removed = buffer.trim_to(BLOCK)

        self.assertEqual(removed, 2 * BLOCK)
        self.assertEqual(buffer.depth, BLOCK)
        self.assertEqual(buffer.trimmed_frames, 2 * BLOCK)
        # The newest audio is what survives.
        self.assertEqual(buffer.read(BLOCK), [3.0] * BLOCK)

    def test_trim_is_a_no_op_below_the_target(self) -> None:
        buffer = JitterBuffer(target_depth=0)
        buffer.push([1.0] * BLOCK)

        self.assertEqual(buffer.trim_to(4 * BLOCK), 0)
        self.assertEqual(buffer.depth, BLOCK)
        self.assertEqual(buffer.trimmed_frames, 0)

    def test_trim_rejects_a_negative_target(self) -> None:
        buffer = JitterBuffer(target_depth=0)
        with self.assertRaises(ValueError):
            buffer.trim_to(-1)

    def test_default_bounds(self) -> None:
        bounded = JitterBuffer(target_depth=BLOCK)
        self.assertEqual(bounded.max_depth, 3 * BLOCK)

        # Without a pre-roll there is nothing to protect, so no bound is set
        # by default. Callers that stream must pass max_depth explicitly.
        unbounded = JitterBuffer(target_depth=0)
        self.assertIsNone(unbounded.max_depth)

    def test_reset_clears_state(self) -> None:
        buffer = JitterBuffer(target_depth=BLOCK)
        buffer.push([1.0] * BLOCK)
        buffer.read(BLOCK)

        buffer.reset()

        self.assertEqual(buffer.depth, 0)
        self.assertFalse(buffer.primed)
        self.assertEqual(buffer.pushed_frames, 0)
        self.assertEqual(buffer.starved_reads, 0)
        self.assertEqual(buffer.prefill_reads, 0)
        self.assertEqual(buffer.prefill_frames, 0)

    def test_invalid_arguments_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            JitterBuffer(target_depth=-1)
        with self.assertRaises(ValueError):
            JitterBuffer(target_depth=10, max_depth=5)

        buffer = JitterBuffer(target_depth=0)
        with self.assertRaises(ValueError):
            buffer.read(0)
        with self.assertRaises(ValueError):
            buffer.depth_ms(0)


if __name__ == "__main__":
    unittest.main()
