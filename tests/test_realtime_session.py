from __future__ import annotations

import json
import time
import unittest

from panda_infer.realtime_session import (
    METRICS_PREFIX,
    ConversionSession,
    MonitorTap,
    drive_offline,
    format_metrics_line,
)
from panda_infer.realtime_sim import build_parser as build_sim_parser
from panda_infer.realtime_sim import wait_for_worker


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class FakeSession:
    """Minimal stand-in for drive_offline that needs no threads."""

    def __init__(self, chunk_size: int, sample_rate: int = 16000) -> None:
        self.chunk_size = chunk_size
        self.sample_rate = sample_rate
        self.submitted: list[list[float]] = []
        self.reads = 0

    def submit_input(self, samples) -> None:
        self.submitted.append(list(samples))

    def read_output_into(self, target) -> int:
        self.reads += 1
        for index in range(len(target)):
            target[index] = 0.0
        return 0


class ConversionSessionTest(unittest.TestCase):
    def test_worker_converts_into_the_jitter_buffer(self) -> None:
        session = ConversionSession(
            lambda chunk: [value * 2 for value in chunk],
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
            input_queue_chunks=4,
        )
        session.start()
        try:
            session.submit_input([1.0, 2.0, 3.0, 4.0])
            self.assertTrue(wait_until(lambda: session.buffer_depth >= 4))

            target = [0.0] * 4
            written = session.read_output_into(target)

            self.assertEqual(written, 4)
            self.assertEqual(target, [2.0, 4.0, 6.0, 8.0])
            self.assertTrue(session.idle)
        finally:
            session.stop()

    def test_submit_input_drops_oldest_when_queue_is_full(self) -> None:
        # The session is never started, so nothing drains the queue.
        session = ConversionSession(
            lambda chunk: chunk,
            1,
            prefill_chunks=0,
            max_backlog_chunks=2,
            input_queue_chunks=2,
        )

        for value in (1.0, 2.0, 3.0):
            session.submit_input([value])

        self.assertEqual(session.pending_input, 2)
        self.assertEqual(session.input_dropped_chunks, 1)
        # Only the blocks that actually entered the queue count as submitted,
        # otherwise the idle check could never succeed after a drop.
        self.assertEqual(session.submitted_chunks, 2)
        self.assertEqual(session.input_capacity, 2)

    def test_input_capacity_can_be_rescaled_for_the_callback_width(self) -> None:
        # "8 blocks" means 1.3 s at one callback width and 160 ms at another;
        # the width is what must stay fixed, not the block count.
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            input_queue_chunks=8,
        )

        session.set_input_capacity(64)

        self.assertEqual(session.input_capacity, 64)
        self.assertEqual(session._input.maxsize, 64)
        with self.assertRaises(ValueError):
            session.set_input_capacity(0)

    def test_a_resized_capacity_really_bounds_the_queue(self) -> None:
        # A reported value the queue ignores would let every width keep the
        # constructor's budget, which is what dropped captured speech when the
        # callbacks were narrowed to 10 ms.
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            input_queue_chunks=8,
        )

        session.set_input_capacity(2)
        for value in (1.0, 2.0, 3.0):
            session.submit_input([value] * 4)

        self.assertEqual(session.submitted_chunks, 2)
        self.assertEqual(session.input_dropped_chunks, 1)

    def test_flush_tail_drains_the_queue_and_pushes_the_model_lag(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=8,
            input_queue_chunks=8,
        )
        session.start()
        try:
            for _ in range(3):
                session.submit_input([1.0, 2.0, 3.0, 4.0])

            result = session.flush_tail(
                silence_blocks=2,
                timeout=5.0,
                drain_playback=False,
            )

            self.assertTrue(result["queue_drained"])
            self.assertEqual(result["tail_blocks"], 2)
            # Three captured blocks plus the two silence blocks that flushed
            # the model: nothing is left when the streams close.
            self.assertEqual(session.submitted_chunks, 5)
            self.assertTrue(session.idle)
        finally:
            session.stop()

    def test_flush_tail_is_bounded_when_nothing_drains(self) -> None:
        # The desktop waits for this before it kills the worker, so a wedged
        # converter must never be able to hang the stop button.
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            input_queue_chunks=8,
        )
        # Never started: the queued block can never be converted.
        session.submit_input([1.0] * 4)
        started = time.monotonic()
        result = session.flush_tail(timeout=0.2, drain_playback=False)
        elapsed = time.monotonic() - started

        self.assertFalse(result["queue_drained"])
        self.assertEqual(result["tail_blocks"], 0)
        self.assertLess(elapsed, 1.5)
        self.assertGreaterEqual(result["elapsed_ms"], 200.0)

    def test_processing_time_is_charged_to_the_block_it_produces(self) -> None:
        # The device may hand over 20 ms pieces while the model still works in
        # 160 ms blocks; "processing_ms" has to stay per converted block rather
        # than per callback, or the latency display becomes meaningless.
        calls = {"count": 0}

        def convert(chunk):
            calls["count"] += 1
            time.sleep(0.004)
            if calls["count"] == 1:
                return None  # priming call: its time belongs to the next block
            return chunk

        session = ConversionSession(
            convert,
            4,
            prefill_chunks=1,
            max_backlog_chunks=8,
        )
        session.start()
        try:
            session.submit_input([1.0] * 4)  # converted by the priming call
            session.submit_input([1.0] * 4)  # produced by the second call
            self.assertTrue(wait_until(lambda: session.converted_chunks >= 1))

            self.assertEqual(session.processed_chunks, 2)
            self.assertEqual(session.converted_chunks, 1)
            # Both calls' time landed on the single block they produced.
            self.assertGreaterEqual(session.last_process_ms, 4.0)
            self.assertGreaterEqual(session.stats()["mean_process_ms"], 4.0)
        finally:
            session.stop()

    def test_converter_failure_is_recorded(self) -> None:
        def convert(chunk):
            raise RuntimeError("boom")

        session = ConversionSession(
            convert,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        session.start()
        try:
            session.submit_input([0.0] * 4)
            self.assertTrue(
                wait_until(
                    lambda: session.last_error is not None and not session.running
                )
            )
            self.assertIsInstance(session.last_error, RuntimeError)
            self.assertFalse(session.running)
        finally:
            session.stop()

    def test_empty_conversions_are_counted(self) -> None:
        calls = {"count": 0}

        def convert(chunk):
            calls["count"] += 1
            return None if calls["count"] == 1 else chunk

        session = ConversionSession(
            convert,
            2,
            prefill_chunks=1,
            max_backlog_chunks=4,
            input_queue_chunks=4,
        )
        session.start()
        try:
            session.submit_input([1.0, 1.0])
            session.submit_input([2.0, 2.0])
            self.assertTrue(wait_until(lambda: session.buffer_depth >= 2))

            self.assertEqual(session.empty_conversions, 1)
            self.assertEqual(session.processed_chunks, 2)
            self.assertAlmostEqual(session.stats()["buffer_depth_ms"], 0.125)
        finally:
            session.stop()

    def test_stats_expose_the_documented_keys(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        stats = session.stats()

        for key in (
            "processed_chunks",
            "empty_conversions",
            "input_dropped_chunks",
            "mean_process_ms",
            "max_process_ms",
            "buffer_depth_ms",
            "buffer_underrun_frames",
            "starved_reads",
            "buffer_dropped_frames",
            "last_error",
        ):
            self.assertIn(key, stats)
        self.assertIsNone(stats["last_error"])

    def test_invalid_arguments_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ConversionSession(lambda chunk: chunk, 0)
        with self.assertRaises(ValueError):
            ConversionSession(lambda chunk: chunk, 4, prefill_chunks=-1)
        with self.assertRaises(ValueError):
            ConversionSession(
                lambda chunk: chunk,
                4,
                prefill_chunks=4,
                max_backlog_chunks=4,
            )
        with self.assertRaises(ValueError):
            ConversionSession(lambda chunk: chunk, 4, input_queue_chunks=0)
        with self.assertRaises(ValueError):
            ConversionSession(lambda chunk: chunk, 4, sample_rate=0)

    def test_start_twice_is_rejected(self) -> None:
        session = ConversionSession(lambda chunk: chunk, 4)
        session.start()
        try:
            with self.assertRaises(RuntimeError):
                session.start()
        finally:
            session.stop()

    def test_startup_surplus_is_trimmed(self) -> None:
        # Mimics the real catch-up: the converter returns nothing first, then
        # several blocks in one call, briefly outrunning playback.
        calls = {"count": 0}

        def convert(chunk):
            calls["count"] += 1
            if calls["count"] == 1:
                return None
            if calls["count"] <= 4:
                return [1.0] * (len(chunk) * 3)
            return [1.0] * len(chunk)

        session = ConversionSession(
            convert,
            4,
            prefill_chunks=1,
            max_backlog_chunks=8,
            input_queue_chunks=8,
        )
        session.start()
        try:
            for _ in range(8):
                session.submit_input([0.0] * 4)
            self.assertTrue(wait_until(lambda: session.processed_chunks >= 8))
            stats = session.stats()
        finally:
            session.stop()

        self.assertGreater(stats["trimmed_frames"], 0)
        # However big the burst, the backlog comes back near the pre-roll.
        self.assertLessEqual(stats["buffer_depth_ms"], 2.0)

    def test_trim_margin_must_not_be_negative(self) -> None:
        with self.assertRaises(ValueError):
            ConversionSession(lambda chunk: chunk, 4, trim_margin_chunks=-1)

    def test_a_smaller_trim_margin_trims_sooner(self) -> None:
        # Measured live: a margin of half a block let the backlog oscillate down
        # to zero and trimmed repeatedly, so the default of one block is kept.
        def measure(margin: float) -> int:
            def convert(chunk):
                # One push of two blocks: exactly the case the margin governs.
                return [1.0] * (len(chunk) * 2)

            session = ConversionSession(
                convert,
                4,
                prefill_chunks=1,
                max_backlog_chunks=8,
                input_queue_chunks=8,
                trim_margin_chunks=margin,
            )
            session.start()
            try:
                session.submit_input([0.0] * 4)
                self.assertTrue(
                    wait_until(lambda: session.processed_chunks >= 1)
                )
                return session.stats()["trimmed_frames"]
            finally:
                session.stop()

        self.assertGreater(measure(0.0), measure(1.0))


class MetricsContractTest(unittest.TestCase):
    def test_metrics_snapshot_matches_the_contract(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            2560,
            sample_rate=16000,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        session.last_process_ms = 190.5

        snapshot = session.metrics_snapshot()

        self.assertEqual(snapshot["chunk"], 0)
        self.assertAlmostEqual(snapshot["processing_ms"], 190.5)
        self.assertAlmostEqual(snapshot["chunk_ms"], 160.0)
        self.assertTrue(snapshot["overrun"])
        for key in (
            "buffer_ms",
            "mean_ms",
            "max_ms",
            "starved_reads",
            "underrun_frames",
            "dropped_frames",
            "input_dropped",
        ):
            self.assertIn(key, snapshot)

    def test_metrics_line_is_prefixed_json(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            2560,
            sample_rate=16000,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )

        line = format_metrics_line(session.metrics_snapshot())

        self.assertTrue(line.startswith(METRICS_PREFIX + " "))
        payload = json.loads(line[len(METRICS_PREFIX):])
        self.assertEqual(payload["chunk_ms"], 160.0)
        self.assertIs(payload["overrun"], False)
        # Pin the field set: the C++ core parses these keys by name.
        self.assertEqual(
            set(payload),
            {
                "chunk",
                "processing_ms",
                "chunk_ms",
                "buffer_ms",
                "overrun",
                "mean_ms",
                "max_ms",
                "starved_reads",
                "underrun_frames",
                "dropped_frames",
                "input_dropped",
                "trimmed_frames",
                # What the listener actually heard as silence: start-up priming
                # plus any re-prime an underrun forced.
                "prefill_frames",
                "prefill_reads",
                "resume_reads",
            },
        )

    def test_metrics_line_carries_device_latency(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            2560,
            sample_rate=16000,
            prefill_chunks=1,
        )

        snapshot = session.metrics_snapshot(
            levels={
                "input_latency_ms": 40.0,
                "output_latency_ms": 40.0,
                "device_block_ms": 20.0,
            }
        )

        # The backend's own buffering is charged on top of our queue, so the
        # latency shown to the listener has to include it.
        self.assertEqual(snapshot["input_latency_ms"], 40.0)
        self.assertEqual(snapshot["output_latency_ms"], 40.0)
        self.assertEqual(snapshot["device_block_ms"], 20.0)

    def test_metrics_snapshot_carries_audio_levels(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            2560,
            sample_rate=16000,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )

        snapshot = session.metrics_snapshot(
            levels={
                "input_rms": 0.021,
                "input_peak": 0.18,
                "output_rms": 0.04,
                "output_peak": 0.72,
                "input_clipped": False,
                "output_clipped": False,
            }
        )

        self.assertAlmostEqual(snapshot["input_rms"], 0.021)
        self.assertAlmostEqual(snapshot["input_peak"], 0.18)
        self.assertAlmostEqual(snapshot["output_rms"], 0.04)
        self.assertAlmostEqual(snapshot["output_peak"], 0.72)
        self.assertFalse(snapshot["input_clipped"])
        self.assertFalse(snapshot["output_clipped"])


class MonitorTapTest(unittest.TestCase):
    def test_reproduces_pushed_audio(self) -> None:
        tap = MonitorTap(chunk_size=4, sample_rate=16000, prefill_chunks=1)

        tap.push([1.0, 2.0, 3.0, 4.0])
        target = [0.0] * 4
        written = tap.read_into(target)

        self.assertEqual(written, 4)
        self.assertEqual(target, [1.0, 2.0, 3.0, 4.0])

    def test_starts_with_silence_until_the_pre_roll_is_filled(self) -> None:
        tap = MonitorTap(chunk_size=4, sample_rate=16000, prefill_chunks=2)

        target = [9.0] * 4
        written = tap.read_into(target)

        self.assertEqual(written, 0)
        self.assertEqual(target, [0.0, 0.0, 0.0, 0.0])
        self.assertEqual(tap.stats()["prefill_reads"], 1)

    def test_stats_report_backlog(self) -> None:
        tap = MonitorTap(chunk_size=4, sample_rate=16000, prefill_chunks=1)

        tap.push([1.0] * 4)
        tap.push([2.0] * 4)

        stats = tap.stats()
        self.assertEqual(stats["depth_frames"], 8)
        self.assertEqual(stats["underrun_frames"], 0)

    def test_invalid_arguments_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MonitorTap(chunk_size=0, sample_rate=16000)
        with self.assertRaises(ValueError):
            MonitorTap(chunk_size=4, sample_rate=0)


class DriveOfflineTest(unittest.TestCase):
    def test_submits_fixed_size_blocks(self) -> None:
        session = FakeSession(chunk_size=4)

        output = drive_offline(
            session,
            [1.0] * 14,
            realtime=False,
        )

        self.assertEqual(len(session.submitted), 4)
        self.assertEqual(session.submitted[0], [1.0] * 4)
        self.assertEqual(len(session.submitted[-1]), 2)
        self.assertEqual(len(output), 16)

    def test_realtime_pacing_waits_for_the_next_deadline(self) -> None:
        session = FakeSession(chunk_size=16, sample_rate=16000)
        sleeps: list[float] = []
        current = {"value": 0.0}

        def clock() -> float:
            return current["value"]

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            current["value"] += seconds

        drive_offline(
            session,
            [0.0] * 32,
            realtime=True,
            sleep=sleep,
            clock=clock,
        )

        self.assertEqual(len(sleeps), 2)
        for value in sleeps:
            self.assertAlmostEqual(value, 0.001)


class WaitForWorkerTest(unittest.TestCase):
    def test_returns_true_once_the_worker_is_idle(self) -> None:
        class Fake:
            pending_input = 0
            idle = True

        self.assertTrue(wait_for_worker(Fake(), timeout=0.1))

    def test_times_out_when_the_worker_stays_busy(self) -> None:
        class Fake:
            pending_input = 1
            idle = False

        current = {"value": 0.0}

        def clock() -> float:
            return current["value"]

        def sleep(seconds: float) -> None:
            current["value"] += seconds

        self.assertFalse(
            wait_for_worker(Fake(), timeout=0.05, sleep=sleep, clock=clock)
        )


class SimulateParserTest(unittest.TestCase):
    def test_parses_simulation_options(self) -> None:
        args = build_sim_parser().parse_args(
            [
                "--meanvc2-root",
                "MeanVC2",
                "--target-wav",
                "ref.wav",
                "--source-wav",
                "src.wav",
                "--output-wav",
                "out.wav",
                "--repeat",
                "3",
                "--threads",
                "1",
                "--fast",
                "--json",
            ]
        )

        self.assertEqual(args.repeat, 3)
        self.assertEqual(args.threads, 1)
        self.assertTrue(args.fast)
        self.assertTrue(args.json)

    def test_parses_latency_controls(self) -> None:
        args = build_sim_parser().parse_args(
            [
                "--meanvc2-root",
                "MeanVC2",
                "--target-wav",
                "ref.wav",
                "--source-wav",
                "src.wav",
                "--output-wav",
                "out.wav",
                "--prefill-chunks",
                "1",
                "--max-backlog-chunks",
                "4",
            ]
        )

        self.assertEqual(args.prefill_chunks, 1)
        self.assertEqual(args.max_backlog_chunks, 4)


class SimulationCopierTest(unittest.TestCase):
    def test_simulation_feeds_the_session_the_shared_copier(self) -> None:
        # realtime_sim used to define its own copy_input on top of
        # np.ascontiguousarray, which returns the input untouched when it
        # already is contiguous float32 (which load_wav_16k_mono guarantees) --
        # aliasing the caller's buffer and breaking the copy contract
        # submit_input documents. It now reuses the tested worker copier;
        # CopyCapturedTest pins that copier's semantics.
        from panda_infer import realtime_sim, realtime_worker

        self.assertIs(
            realtime_sim.copy_captured, realtime_worker.copy_captured
        )


if __name__ == "__main__":
    unittest.main()
