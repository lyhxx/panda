from __future__ import annotations

import io
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from panda_infer.realtime_session import METRICS_PREFIX, ConversionSession
from panda_infer.realtime_worker import (
    LiveControls,
    device_block_frames,
    device_default_rate,
    find_device_index,
    open_metrics_file,
    run_realtime_session,
    stream_latency_ms,
    warm_up_runner,
)

try:
    import numpy  # noqa: F401

    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False


class FakeArray:
    """Minimal stand-in for a 2-D audio buffer supporting ``buffer[:, 0]``."""

    def __init__(self, frames: int, value: float = 0.0) -> None:
        self.column = [value] * frames

    def __getitem__(self, key):
        if key != (slice(None), 0):
            raise AssertionError(f"unexpected index: {key}")
        return self.column


class FakeSoundDevice:
    """Runs the audio callback synchronously for a fixed number of ticks."""

    def __init__(self, ticks: int = 6, device_rate: int = 16000) -> None:
        self.ticks = ticks
        self.device_rate = device_rate
        self.stream_kwargs: dict = {}
        self.input_stream_kwargs: dict = {}
        self.sleeps: list[int] = []
        self.captured: list[list[float]] = []
        self.on_sleep = None
        self.max_sleeps = 50
        self.output_stream_kwargs: dict = {}
        self.output_stream_count = 0
        self.monitor_ticks = ticks
        self.monitor_reads = 0

    def Stream(self, **kwargs):  # noqa: N802 - mirrors the sounddevice API
        self.stream_kwargs = kwargs
        outer = self

        class _Stream:
            def __enter__(self_inner):
                callback = kwargs["callback"]
                frames = kwargs["blocksize"]
                for _ in range(outer.ticks):
                    indata = FakeArray(frames, 0.5)
                    outdata = FakeArray(frames)
                    outer.captured.append(list(indata.column))
                    callback(indata, outdata, frames, None, None)
                return self_inner

            def __exit__(self_inner, exc_type, exc, traceback):
                return False

        return _Stream()

    def InputStream(self, **kwargs):  # noqa: N802 - mirrors sounddevice API
        self.input_stream_kwargs = kwargs
        outer = self

        class _Stream:
            def __enter__(self_inner):
                callback = kwargs["callback"]
                frames = kwargs["blocksize"]
                for _ in range(outer.ticks):
                    indata = FakeArray(frames, 0.5)
                    outer.captured.append(list(indata.column))
                    callback(indata, frames, None, None)
                return self_inner

            def __exit__(self_inner, exc_type, exc, traceback):
                return False

        return _Stream()

    def OutputStream(self, **kwargs):  # noqa: N802 - mirrors sounddevice API
        self.output_stream_kwargs = kwargs
        self.output_stream_count += 1
        outer = self

        class _Stream:
            def __enter__(self_inner):
                callback = kwargs["callback"]
                frames = kwargs["blocksize"]
                for _ in range(outer.monitor_ticks):
                    outdata = FakeArray(frames)
                    callback(outdata, frames, None, None)
                    outer.monitor_reads += 1
                return self_inner

            def __exit__(self_inner, exc_type, exc, traceback):
                return False

        return _Stream()

    def sleep(self, milliseconds: int) -> None:
        self.sleeps.append(milliseconds)
        # Yield the GIL like the real sd.sleep would, otherwise a tight loop
        # can starve the conversion worker and make these tests flaky.
        time.sleep(min(milliseconds, 5) / 1000.0)
        if self.on_sleep is not None:
            self.on_sleep()
        if len(self.sleeps) >= self.max_sleeps:
            raise AssertionError("run_realtime_session did not exit")

    def query_devices(self, device=None):  # noqa: N802 - mirrors sounddevice
        return {"default_samplerate": float(self.device_rate)}


class DuplexFailingSoundDevice(FakeSoundDevice):
    """Simulates PortAudio rejecting a mixed-host-API duplex pair."""

    def Stream(self, **kwargs):  # noqa: N802 - mirrors the sounddevice API
        raise RuntimeError("Illegal combination of I/O devices")


class FakeRunner:
    CHUNK = 4

    def __init__(self) -> None:
        self.processed = 0
        self.cache_resets = 0
        self.received: list[list[float]] = []

    def process_chunk(self, chunk):
        self.processed += 1
        self.received.append(list(chunk))
        return list(chunk)

    def _init_cache(self) -> None:
        self.cache_resets += 1


class LiveControlsTest(unittest.TestCase):
    def test_updates_only_known_keys(self) -> None:
        controls = LiveControls(output_gain_db=1.0)

        controls.update({"output_gain_db": -3.0, "unknown": 9})
        snapshot = controls.snapshot()

        self.assertEqual(snapshot["output_gain_db"], -3.0)
        self.assertNotIn("unknown", snapshot)
        # A snapshot is a copy, so later updates do not mutate it.
        controls.update({"output_gain_db": 2.0})
        self.assertEqual(snapshot["output_gain_db"], -3.0)


class WarmUpRunnerTest(unittest.TestCase):
    def test_runs_silence_then_resets_caches(self) -> None:
        runner = FakeRunner()

        warm_up_runner(runner, 3, zeros=lambda count: [0.0] * count)

        self.assertEqual(runner.processed, 3)
        self.assertEqual(runner.cache_resets, 1)
        self.assertEqual(runner.received[0], [0.0] * FakeRunner.CHUNK)

    def test_zero_warmup_is_a_no_op(self) -> None:
        runner = FakeRunner()

        warm_up_runner(runner, 0, zeros=lambda count: [0.0] * count)

        self.assertEqual(runner.processed, 0)
        self.assertEqual(runner.cache_resets, 0)


class RunRealtimeSessionTest(unittest.TestCase):
    def test_opens_a_stream_and_drives_the_callback(self) -> None:
        session = ConversionSession(
            lambda chunk: [value * 2 for value in chunk],
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
            input_queue_chunks=4,
        )
        fake = FakeSoundDevice(ticks=6)
        session.start()
        # The serve loop runs until the session stops, so let the fake device
        # end it deterministically instead of spinning.
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                input_device=1,
                output_device=2,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        self.assertEqual(fake.input_stream_kwargs["samplerate"], 16000)
        self.assertEqual(fake.input_stream_kwargs["blocksize"], 4)
        self.assertEqual(fake.input_stream_kwargs["device"], 1)
        self.assertEqual(fake.input_stream_kwargs["channels"], 1)
        self.assertEqual(fake.input_stream_kwargs["dtype"], "float32")
        self.assertEqual(fake.output_stream_kwargs["device"], 2)
        self.assertEqual(len(fake.captured), 6)
        self.assertEqual(fake.captured[0], [0.5] * 4)
        # The callback must not run inference, so the worker may lag; give it
        # a moment and then confirm the session actually converted audio.
        deadline = time.monotonic() + 2.0
        while session.processed_chunks == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertGreaterEqual(session.processed_chunks, 1)
        self.assertIsNone(session.last_error)

    def test_loop_exits_when_the_worker_fails(self) -> None:
        def convert(chunk):
            raise RuntimeError("boom")

        session = ConversionSession(
            convert,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=4)
        session.start()
        try:
            run_realtime_session(
                session,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        self.assertIsInstance(session.last_error, RuntimeError)

    def test_emits_parseable_metrics_lines(self) -> None:
        session = ConversionSession(
            lambda chunk: [value * 2 for value in chunk],
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
            input_queue_chunks=4,
        )
        fake = FakeSoundDevice(ticks=6)
        stream = io.StringIO()
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=stream,
            )
        finally:
            session.stop()

        lines = [
            line
            for line in stream.getvalue().splitlines()
            if line.startswith(METRICS_PREFIX)
        ]
        self.assertGreaterEqual(len(lines), 1)

        payload = json.loads(lines[-1][len(METRICS_PREFIX):])
        # 4 frames at 16 kHz is a 0.25 ms block.
        self.assertEqual(payload["chunk_ms"], 0.25)
        self.assertIn("processing_ms", payload)
        self.assertIn("buffer_ms", payload)
        self.assertIn("overrun", payload)

    def test_metrics_can_be_disabled(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=2)
        stream = io.StringIO()
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=stream,
                emit_metrics=False,
            )
        finally:
            session.stop()

        self.assertEqual(stream.getvalue(), "")

    def test_no_output_captures_without_an_output_stream(self) -> None:
        session = ConversionSession(
            lambda chunk: [value * 2 for value in chunk],
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
            input_queue_chunks=4,
        )
        fake = FakeSoundDevice(ticks=4)
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                input_device=1,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                no_output=True,
                monitor_device=3,
            )
        finally:
            session.stop()

        # No duplex stream: capture only, plus the monitor output.
        self.assertEqual(fake.stream_kwargs, {})
        self.assertEqual(fake.input_stream_kwargs["device"], 1)
        self.assertEqual(fake.output_stream_kwargs["device"], 3)
        self.assertEqual(len(fake.captured), 4)

    def test_reopen_uses_the_live_device_values(self) -> None:
        controls = LiveControls(input_device=1, output_device=2)

        first = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        first_fake = FakeSoundDevice(ticks=2)
        first.start()
        first_fake.on_sleep = lambda: controls.update({"input_device": 5})
        try:
            run_realtime_session(
                first,
                input_device=1,
                output_device=2,
                stream_module=first_fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                controls=controls,
            )
        finally:
            first.stop()

        self.assertEqual(first_fake.input_stream_kwargs["device"], 1)
        self.assertEqual(first_fake.output_stream_kwargs["device"], 2)

        # The serve loop re-enters run_realtime_session after a revision bump;
        # the new input device must be used without rebuilding the session.
        second = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        second_fake = FakeSoundDevice(ticks=2)
        second.start()
        second_fake.on_sleep = second.stop
        try:
            run_realtime_session(
                second,
                input_device=1,
                output_device=2,
                stream_module=second_fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                controls=controls,
            )
        finally:
            second.stop()

        self.assertEqual(second_fake.input_stream_kwargs["device"], 5)
        self.assertEqual(second_fake.output_stream_kwargs["device"], 2)

    def test_output_can_be_enabled_after_starting_disabled(self) -> None:
        controls = LiveControls(input_device=1, output_device=-1)

        first = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        first_fake = FakeSoundDevice(ticks=2)
        first.start()
        first_fake.on_sleep = first.stop
        try:
            run_realtime_session(
                first,
                input_device=1,
                stream_module=first_fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                no_output=True,
                controls=controls,
            )
        finally:
            first.stop()

        self.assertEqual(first_fake.stream_kwargs, {})
        self.assertEqual(first_fake.input_stream_kwargs["device"], 1)

        controls.update({"output_device": 7})

        second = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        second_fake = FakeSoundDevice(ticks=2)
        second.start()
        second_fake.on_sleep = second.stop
        try:
            run_realtime_session(
                second,
                input_device=1,
                stream_module=second_fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                no_output=True,
                controls=controls,
            )
        finally:
            second.stop()

        # Enabling the output after starting with "不输出" must open a duplex
        # stream instead of staying capture-only.
        self.assertEqual(second_fake.input_stream_kwargs["device"], 1)
        self.assertEqual(second_fake.output_stream_kwargs["device"], 7)

    def test_falls_back_to_separate_streams_when_duplex_is_rejected(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = DuplexFailingSoundDevice(ticks=3)
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                input_device=1,
                output_device=2,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        # A mixed input/output pair cannot share one duplex stream, so the
        # worker must fall back to independent streams instead of crashing.
        self.assertEqual(fake.stream_kwargs, {})
        self.assertEqual(fake.input_stream_kwargs["device"], 1)
        self.assertEqual(fake.output_stream_kwargs["device"], 2)

    def test_negative_input_device_falls_back_to_the_default(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=2)
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                input_device=-1,
                output_device=2,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        # -1 means "not chosen". PortAudio must receive None, not -1, which
        # raises "Error querying device -1" and used to crash the worker.
        self.assertIsNone(fake.input_stream_kwargs["device"])
        self.assertEqual(fake.output_stream_kwargs["device"], 2)

    def test_monitor_device_opens_a_second_output_stream(self) -> None:
        session = ConversionSession(
            lambda chunk: [value * 2 for value in chunk],
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
            input_queue_chunks=4,
        )
        fake = FakeSoundDevice(ticks=4)
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                input_device=1,
                output_device=4,
                monitor_device=9,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        self.assertEqual(fake.output_stream_kwargs["device"], 9)
        self.assertEqual(fake.output_stream_kwargs["samplerate"], 16000)
        self.assertEqual(fake.output_stream_kwargs["blocksize"], 4)
        self.assertEqual(fake.output_stream_kwargs["channels"], 1)
        # Main output + monitor output.
        self.assertEqual(fake.output_stream_count, 2)
        self.assertGreaterEqual(fake.monitor_reads, fake.monitor_ticks)

    def test_monitor_on_the_output_device_is_skipped(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=4)
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                input_device=1,
                output_device=4,
                monitor_device=4,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        # Opening a second output stream on the main output device silences the
        # capture stream on WASAPI, so the redundant monitor must be skipped.
        self.assertEqual(fake.input_stream_kwargs["device"], 1)
        self.assertEqual(fake.output_stream_kwargs["device"], 4)
        # Only the main output stream, no monitor.
        self.assertEqual(fake.output_stream_count, 1)

    def test_no_monitor_stream_is_opened_without_a_monitor_device(self) -> None:
        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=2)
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        self.assertEqual(fake.output_stream_count, 0)
        self.assertEqual(fake.monitor_reads, 0)

    @unittest.skipUnless(HAVE_NUMPY, "resampling needs numpy")
    def test_stream_opens_at_the_device_rate(self) -> None:
        # WASAPI shared mode only accepts the device's own rate, so the engine
        # must open there and resample in software.
        session = ConversionSession(
            lambda chunk: [value * 2 for value in chunk],
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
            input_queue_chunks=4,
        )
        fake = FakeSoundDevice(ticks=4, device_rate=48000)
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                input_device=1,
                output_device=4,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        self.assertEqual(fake.input_stream_kwargs["samplerate"], 48000)
        # 4 engine frames are 12 device frames at three times the rate.
        self.assertEqual(fake.input_stream_kwargs["blocksize"], 12)

    @unittest.skipUnless(HAVE_NUMPY, "resampling needs numpy")
    def test_monitor_stream_uses_its_own_rate(self) -> None:
        class SplitRateDevice(FakeSoundDevice):
            def query_devices(self, device=None):  # noqa: N802
                return {
                    "default_samplerate": 48000.0 if device == 9 else 16000.0
                }

        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = SplitRateDevice(ticks=2)
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                input_device=1,
                output_device=4,
                monitor_device=9,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
            )
        finally:
            session.stop()

        self.assertEqual(fake.output_stream_kwargs["samplerate"], 48000)
        self.assertEqual(fake.output_stream_kwargs["blocksize"], 12)

    def test_denoiser_runs_on_every_captured_block(self) -> None:
        class RecordingDenoiser:
            def __init__(self) -> None:
                self.blocks = 0

            def process(self, block):
                self.blocks += 1
                return block

        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=3)
        denoiser = RecordingDenoiser()
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                denoiser=denoiser,
            )
        finally:
            session.stop()

        self.assertGreaterEqual(denoiser.blocks, 1)

    def test_output_gain_runs_on_every_played_block(self) -> None:
        class RecordingGain:
            def __init__(self) -> None:
                self.blocks = 0

            def process_in_place(self, block):
                self.blocks += 1

        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=3)
        gain = RecordingGain()
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                gain=gain,
            )
        finally:
            session.stop()

        self.assertGreaterEqual(gain.blocks, 1)

    def test_input_gain_runs_before_submission(self) -> None:
        class RecordingGain:
            def __init__(self) -> None:
                self.blocks = 0

            def process_in_place(self, block):
                self.blocks += 1

        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=3)
        gain = RecordingGain()
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                input_gain=gain,
            )
        finally:
            session.stop()

        self.assertGreaterEqual(gain.blocks, 1)

    def test_monitor_gain_runs_on_the_monitor_path(self) -> None:
        class RecordingGain:
            def __init__(self) -> None:
                self.blocks = 0

            def process_in_place(self, block):
                self.blocks += 1

        session = ConversionSession(
            lambda chunk: chunk,
            4,
            prefill_chunks=1,
            max_backlog_chunks=4,
        )
        fake = FakeSoundDevice(ticks=3)
        gain = RecordingGain()
        session.start()
        fake.on_sleep = session.stop
        try:
            run_realtime_session(
                session,
                output_device=4,
                monitor_device=9,
                stream_module=fake,
                poll_seconds=0.01,
                metrics_stream=io.StringIO(),
                monitor_gain=gain,
            )
        finally:
            session.stop()

        self.assertGreaterEqual(gain.blocks, 1)


class FindDeviceIndexTest(unittest.TestCase):
    class Stub:
        def query_devices(self, device=None):
            if device is not None:
                return {"default_samplerate": 16000.0}
            return [
                {"name": "Mic", "max_input_channels": 2, "max_output_channels": 0, "hostapi": 1},
                {"name": "Mic", "max_input_channels": 2, "max_output_channels": 0, "hostapi": 0},
                {"name": "Spk", "max_input_channels": 0, "max_output_channels": 2, "hostapi": 0},
            ]

        def query_hostapis(self):
            return [{"name": "Windows WASAPI"}, {"name": "MME"}]

    def test_prefers_wasapi_and_respects_direction(self) -> None:
        stub = self.Stub()
        # The WASAPI "Mic" (index 1) wins over the MME one (index 0).
        self.assertEqual(find_device_index(stub, "Mic", True, 7), 1)
        self.assertEqual(find_device_index(stub, "Spk", False, 0), 2)

    def test_falls_back_to_the_numeric_id(self) -> None:
        stub = self.Stub()
        self.assertEqual(find_device_index(stub, "Missing", True, 7), 7)
        self.assertIsNone(find_device_index(stub, None, True, -1))


class DeviceRateTest(unittest.TestCase):
    def test_reads_the_default_rate(self) -> None:
        class Device:
            def query_devices(self, device=None):
                return {"default_samplerate": 48000.0}

        self.assertEqual(device_default_rate(Device(), 3), 48000)

    def test_returns_none_when_the_probe_fails(self) -> None:
        class Device:
            def query_devices(self, device=None):
                raise RuntimeError("no such device")

        self.assertIsNone(device_default_rate(Device(), 3))

    def test_returns_none_for_a_bad_payload(self) -> None:
        class Device:
            def query_devices(self, device=None):
                return {"default_samplerate": "not a number"}

        self.assertIsNone(device_default_rate(Device(), 3))


class DeviceBlockFramesTest(unittest.TestCase):
    def test_defaults_to_a_small_fraction_of_the_chunk(self) -> None:
        session = ConversionSession(lambda chunk: chunk, 2560, sample_rate=16000)
        self.assertEqual(device_block_frames(session, 20.0), 320)
        self.assertEqual(device_block_frames(session, 40.0), 640)

    def test_denoiser_pins_the_width_to_a_whole_chunk(self) -> None:
        # DeepFilterNet is block-synchronous at 160 ms and raises on any other
        # width, so an active denoiser must keep callbacks chunk-wide.
        session = ConversionSession(lambda chunk: chunk, 2560, sample_rate=16000)
        self.assertEqual(device_block_frames(session, 20.0, denoiser=object()), 2560)

    def test_width_never_exceeds_the_chunk_and_stays_a_divisor(self) -> None:
        session = ConversionSession(lambda chunk: chunk, 2560, sample_rate=16000)
        self.assertEqual(device_block_frames(session, 1600.0), 2560)
        # 7 ms is 112 frames, not a divisor of 2560: round down to one that is.
        self.assertEqual(device_block_frames(session, 7.0), 80)
        # A pathological value must not turn into thousands of callbacks a
        # second on the audio thread.
        self.assertEqual(device_block_frames(session, 0.0), 80)


class StreamLatencyTest(unittest.TestCase):
    def test_reads_scalars_tuples_and_missing_values(self) -> None:
        class Single:
            latency = 0.04

        class Duplex:
            latency = (0.08, 0.12)

        class Missing:
            pass

        class Broken:
            latency = "not a number"

        self.assertEqual(stream_latency_ms(Single()), 40.0)
        # Duplex streams report both directions; we only want the input side
        # here because each stream is asked separately.
        self.assertEqual(stream_latency_ms(Duplex()), 80.0)
        self.assertEqual(stream_latency_ms(Missing()), 0.0)
        self.assertEqual(stream_latency_ms(Broken()), 0.0)
        self.assertEqual(stream_latency_ms(None), 0.0)


class MetricsFileTest(unittest.TestCase):
    def test_appends_to_the_series_across_restarts(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="panda-metrics-"))
        path = directory / "metrics.jsonl"
        try:
            first = open_metrics_file(str(path))
            self.assertIsNotNone(first)
            first.write('[panda.metrics] {"chunk":1}\n')
            first.close()

            second = open_metrics_file(str(path))
            second.write('[panda.metrics] {"chunk":2}\n')
            second.close()

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(all(line.startswith("[panda.metrics]") for line in lines))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_returns_none_when_the_sink_cannot_be_written(self) -> None:
        blocker = Path(tempfile.mkdtemp(prefix="panda-metrics-")) / "blocker"
        blocker.write_text("x", encoding="utf-8")
        try:
            # A parent that is a regular file: the sink must fail soft rather
            # than take the audio pipeline down with it.
            self.assertIsNone(open_metrics_file(str(blocker / "nested" / "x.jsonl")))
            self.assertIsNone(open_metrics_file(""))
        finally:
            shutil.rmtree(blocker.parent, ignore_errors=True)


class FlushDrainTest(unittest.TestCase):
    def test_flush_converts_what_is_in_flight_before_returning(self) -> None:
        # Returning None keeps the output buffer empty, so the drain step only
        # has to wait for the converter instead of for real playback.
        session = ConversionSession(
            lambda chunk: None,
            4,
            prefill_chunks=1,
            max_backlog_chunks=8,
            input_queue_chunks=8,
        )
        fake = FakeSoundDevice(ticks=1)
        controls = LiveControls()
        controls.update({"flush": True})
        session.start()
        try:
            session.submit_input([1.0] * 4)
            started = time.monotonic()
            run_realtime_session(
                session,
                stream_module=fake,
                controls=controls,
                metrics_stream=io.StringIO(),
                poll_seconds=0.01,
            )
            elapsed = time.monotonic() - started
        finally:
            session.stop()

        # One captured block, one explicitly queued block and the silence that
        # pulled the model's own lag out, all converted before the streams close.
        self.assertGreaterEqual(session.submitted_chunks, 4)
        self.assertTrue(session.idle)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
