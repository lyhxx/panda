from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Iterator
from pathlib import Path

from panda_infer.cli import resolve_reference_from_pack
from panda_infer.dsp import (
    NoiseGate,
    OutputGain,
    SoftLimiter,
    StreamResampler,
    require_numpy,
)
from panda_infer.realtime_session import (
    ConversionSession,
    MonitorTap,
    format_metrics_line,
)


def copy_captured(samples) -> "np.ndarray":
    """Copy one captured block into memory the input queue owns.

    PortAudio reuses its capture buffer on every callback, so anything queued
    for the model must not alias it. ConversionSession promises exactly that
    ("samples are copied, so the caller may reuse its buffer immediately"),
    but the copier used before this did not keep the promise: an already
    contiguous float32 view -- which is precisely what the 16 kHz pass-through
    path returns -- came back unchanged from np.ascontiguousarray, and queued
    audio was overwritten mid-flight by the next callback.
    """
    np = require_numpy()
    return np.array(samples, dtype=np.float32, copy=True)

SAMPLE_RATE = 16000
WARMUP_CHUNKS = 3

# Width of one device callback, in milliseconds.
#
# PortAudio/WASAPI charge *two* callbacks of device latency per direction.
# Measured on this host: 160 ms callbacks -> 320 ms in + 320 ms out, 20 ms ->
# 40 + 40, 10 ms -> 22 + 22. The callback width was the single largest term in
# the mouth-to-ear delay, so it is kept at 10 ms, which is also the default
# WASAPI shared-mode period.
#
# The model still gets full 160 ms chunks: process_chunk accumulates whatever
# the callback hands over, and the session reports processing time per
# converted block, so nothing downstream changes meaning. The cost of feeding
# it in 10 ms pieces instead of whole chunks measures ~12.7% more CPU, which
# against the observed 68 ms mean per 160 ms block leaves comfortable room.
#
# The exception is the denoiser, which is block-synchronous at 160 ms and
# raises on any other width -- when it is active the callback stays wide.
DEVICE_BLOCK_MS = 10.0

# Seconds of captured audio the input queue may hold before dropping the
# oldest block. Kept independent of the callback width so shrinking the
# callback cannot silently shrink the queue's time budget.
INPUT_QUEUE_SECONDS = 1.28

# Upper bound on the stop-time drain (input queue + model tail + buffer).
FLUSH_TIMEOUT_SECONDS = 1.5


class LiveControls:
    """Settings the worker can apply without restarting.

    The desktop writes JSON lines to the worker's stdin; a reader thread
    applies them. Gains, the gate and output mute are read by the audio
    callbacks on every block (instant). Device changes bump a revision counter
    that makes the serve loop reopen only the audio streams, so the model is
    never reloaded just because a device changed.
    """

    # Keys that require only the audio streams to be reopened. The model and
    # conversion session are kept; the worker re-enters the serve loop.
    _REOPEN_KEYS = (
        "input_device",
        "output_device",
        "monitor_device",
        "input_device_name",
        "output_device_name",
        "monitor_device_name",
        "voice_pack",
        "denoise",
        "denoise_level",
        "prefill_chunks",
        "max_backlog_chunks",
    )

    def __init__(self, **initial) -> None:
        self._lock = threading.Lock()
        self._values = {
            "output_gain_db": 0.0,
            "input_gain_db": 0.0,
            "monitor_gain_db": 0.0,
            "gate_enabled": False,
            "gate_db": -45.0,
            "output_muted": False,
            "input_device": None,
            "output_device": None,
            "monitor_device": None,
            "input_device_name": None,
            "output_device_name": None,
            "monitor_device_name": None,
            "voice_pack": None,
            "denoise": False,
            "denoise_level": "strong",
            "prefill_chunks": None,
            "max_backlog_chunks": None,
            # One-shot: ask the audio loop to play out everything still in
            # flight before the process exits (see ConversionSession.flush_tail).
            "flush": False,
        }
        self._revision = 0
        self.update(initial)

    def update(self, payload) -> None:
        with self._lock:
            reopen = False
            for key, value in payload.items():
                if key not in self._values:
                    continue
                if key in self._REOPEN_KEYS and self._values[key] != value:
                    reopen = True
                self._values[key] = value
            if reopen:
                self._revision += 1

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._values)


def _read_stdin_controls(controls: LiveControls, stream=None) -> None:
    # Read raw bytes and decode as UTF-8. On Windows the default text encoding
    # is the system code page (GBK here), which mangles the device names in the
    # JSON the desktop writes (always UTF-8).
    if stream is None:
        stream = sys.stdin
    stream = getattr(stream, "buffer", stream)
    for raw in stream:
        line = (
            raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        )
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict):
            controls.update(payload)


def _gain_linear(db: float) -> float:
    return 10.0 ** (db / 20.0)


def warm_up_runner(
    runner,
    warmup_chunks: int = WARMUP_CHUNKS,
    *,
    zeros=None,
) -> None:
    """Pre-run the model on silence so the first real block is not cold.

    Measured on the development host, the very first block costs ~348 ms
    against a 160 ms budget; after warm-up the same block costs ~121 ms.
    The caches are reset afterwards so streaming still starts at sample 0.
    """
    if warmup_chunks <= 0:
        return

    if zeros is None:
        import numpy as np

        zeros = lambda count: np.zeros(count, dtype=np.float32)  # noqa: E731

    silence = zeros(int(runner.CHUNK))
    for _ in range(warmup_chunks):
        runner.process_chunk(silence)
    runner._init_cache()


def load_sounddevice(stream_module=None):
    if stream_module is not None:
        return stream_module
    try:
        import sounddevice as sd
    except ImportError as exception:  # pragma: no cover - environment specific
        raise RuntimeError(
            "缺少 sounddevice，请执行 pip install sounddevice"
        ) from exception
    return sd


def device_default_rate(sd, device) -> int | None:
    """The rate a device runs at natively, or None if it cannot be queried.

    WASAPI shared mode only accepts this rate, so opening a stream at the
    engine's 16 kHz fails outright there while MME/DirectSound quietly
    resample for us.
    """
    try:
        if device is not None and device < 0:
            return None
        info = sd.query_devices(device)
    except Exception:  # noqa: BLE001 - a probe must not break the stream
        return None
    try:
        rate = int(round(float(info["default_samplerate"])))
    except (KeyError, TypeError, ValueError):
        return None
    return rate if rate > 0 else None


def _decoded_name(encoded, plain):
    """Decode a base64 UTF-8 device name.

    Windows mangles non-ASCII command-line arguments, so the desktop sends
    device names base64-encoded and we decode them here.
    """
    if not encoded:
        return plain
    try:
        import base64

        return base64.b64decode(encoded).decode("utf-8")
    except Exception:  # noqa: BLE001 - fall back to the raw value
        return plain


def find_device_index(sd, name, want_input, fallback):
    """Resolve a device friendly name to its current PortAudio index.

    Indices are not stable between processes, so prefer the stable name and only
    fall back to the numeric id. When several host APIs expose the same name,
    prefer WASAPI, which is what the desktop lists.
    """
    if name:
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
        except Exception:  # noqa: BLE001 - fall through to the numeric id
            devices = []
            hostapis = []
        best = None
        for index, info in enumerate(devices):
            if want_input:
                if int(info.get("max_input_channels", 0)) <= 0:
                    continue
            elif int(info.get("max_output_channels", 0)) <= 0:
                continue
            if info.get("name") != name:
                continue
            hostapi = int(info.get("hostapi", -1))
            api_name = (
                hostapis[hostapi].get("name", "")
                if 0 <= hostapi < len(hostapis)
                else ""
            )
            if api_name == "Windows WASAPI":
                return index
            if best is None:
                best = index
        if best is not None:
            return best
    if fallback is not None and fallback >= 0:
        return fallback
    return None


def device_block_frames(
    session: ConversionSession,
    device_block_ms: float,
    denoiser=None,
) -> int:
    """Engine frames one device callback should carry.

    The width is what the backend charges device latency against (measured:
    two callback widths per direction), so it wants to be as small as the
    backend accepts. Two things keep it larger: the denoiser is
    block-synchronous at one model chunk and raises on any other width, and
    a divisor of the model chunk keeps the input queue's time budget aligned
    with callbacks.
    """
    if denoiser is not None:
        return session.chunk_size
    # 5 ms is the floor: below that the callback overhead starts to matter and
    # no backend reports less device latency anyway.
    requested = int(
        round(session.sample_rate * max(float(device_block_ms), 5.0) / 1000.0)
    )
    if requested <= 0:
        return session.chunk_size
    frames = min(requested, session.chunk_size)
    if session.chunk_size % frames:
        for candidate in range(frames, 0, -1):
            if session.chunk_size % candidate == 0:
                frames = candidate
                break
    return frames


def stream_latency_ms(stream) -> float:
    """PortAudio's reported latency for a stream, in milliseconds."""
    if stream is None:
        return 0.0
    latency = getattr(stream, "latency", 0.0)
    if isinstance(latency, (tuple, list)):
        latency = latency[0] if latency else 0.0
    try:
        return round(float(latency) * 1000.0, 3)
    except (TypeError, ValueError):
        return 0.0


def open_metrics_file(path) -> object | None:
    """Open the side-channel metrics log, keeping it bounded.

    The desktop filters ``[panda.metrics]`` lines out of its own log, so the
    full time series needed to diagnose dropouts only exists here. Returns
    ``None`` (and stays silent) when the path cannot be written, because a
    diagnostics sink must never be able to break the audio pipeline.
    """
    if not path:
        return None
    try:
        target = Path(str(path))
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if target.exists() and target.stat().st_size > 8 * 1024 * 1024 else "a"
        return target.open(mode, encoding="utf-8")
    except OSError:
        return None


def run_realtime_session(
    session: ConversionSession,
    *,
    input_device: int | None = None,
    output_device: int | None = None,
    monitor_device: int | None = None,
    sample_rate: int = SAMPLE_RATE,
    stream_module=None,
    poll_seconds: float = 0.5,
    metrics_stream=None,
    emit_metrics: bool = True,
    gate: NoiseGate | None = None,
    limiter: SoftLimiter | None = None,
    gain: OutputGain | None = None,
    input_gain: OutputGain | None = None,
    monitor_gain: OutputGain | None = None,
    denoiser=None,
    no_output: bool = False,
    controls: LiveControls | None = None,
    device_block_ms: float = DEVICE_BLOCK_MS,
    metrics_file=None,
) -> None:
    """Play a conversion session through a real audio device.

    The callback only copies captured audio in and converted audio out; the
    model runs on the session's worker thread.

    While running, a ``[panda.metrics]`` JSON line is written to
    ``metrics_stream`` (stdout by default) whenever a new block has been
    converted, so the desktop UI can display live latency. When
    ``metrics_file`` is set the same line is appended there as well: the
    desktop keeps only a filtered subset in its log, and diagnosing dropouts
    needs the whole series.

    When ``monitor_device`` is set, the converted audio is also fanned out to
    that playback device so the speaker can hear their own converted voice even
    though the main output goes to a virtual cable.
    """
    sd = load_sounddevice(stream_module)
    metrics_out = metrics_stream if metrics_stream is not None else sys.stdout
    last_reported_chunk: int | None = None
    levels = {
        "input_rms": 0.0,
        "input_peak": 0.0,
        "output_rms": 0.0,
        "output_peak": 0.0,
        "input_clipped": False,
        "output_clipped": False,
    }
    metrics_handle = open_metrics_file(metrics_file)
    # Set once the desktop asks to stop: the capture callback then stops
    # feeding the queue so flush_tail can actually drain what is in flight
    # instead of racing against fresh microphone audio.
    flushing = False

    # Live-adjustable settings. Values start from the command line and are then
    # kept up to date by the desktop over stdin.
    if controls is None:
        controls = LiveControls(
            output_gain_db=getattr(gain, "gain_db", 0.0) if gain is not None else 0.0,
            input_gain_db=(
                getattr(input_gain, "gain_db", 0.0)
                if input_gain is not None else 0.0
            ),
            monitor_gain_db=(
                getattr(monitor_gain, "gain_db", 0.0)
                if monitor_gain is not None else 0.0
            ),
            gate_enabled=gate is not None,
            gate_db=(
                getattr(gate, "threshold_db", -45.0)
                if gate is not None else -45.0
            ),
            output_muted=no_output,
        )

    # Devices and latency may have changed since the last call; the caller
    # re-enters this function with the same model and session, so only the
    # streams reopen.
    initial = controls.snapshot()
    if initial.get("input_device") is not None:
        input_device = initial["input_device"]
    if initial.get("output_device") is not None:
        output_device = initial["output_device"]
    if initial.get("monitor_device") is not None:
        monitor_device = initial["monitor_device"]
    # Resolve by name whenever possible. PortAudio's numeric indices are not
    # stable across processes/launches (the desktop and the worker enumerate
    # independently), so the same number can point at a different device. The
    # friendly name is stable, which is what the desktop actually stores.
    input_device = find_device_index(
        sd, initial.get("input_device_name"), True, input_device
    )
    output_device = find_device_index(
        sd, initial.get("output_device_name"), False, output_device
    )
    monitor_device = find_device_index(
        sd, initial.get("monitor_device_name"), False, monitor_device
    )
    # A negative id means "not chosen" (input) or "no output" (output). Never
    # hand a negative index to PortAudio: it raises "Error querying device -1"
    # and the worker exits, which the desktop turns into a reconnect loop.
    if input_device is not None and input_device < 0:
        input_device = None
    if output_device is not None and output_device < 0:
        output_device = None
    if monitor_device is not None and monitor_device < 0:
        monitor_device = None
    # Recompute from the live device on every (re)open so turning the output
    # back on after starting with "不输出" takes effect without a reload.
    no_output = output_device is None or output_device < 0
    if initial.get("prefill_chunks") is not None:
        session.set_latency(
            initial["prefill_chunks"],
            initial.get("max_backlog_chunks"),
        )

    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is required for resampling
        np = None

    # Open at the device's own rate and convert in software: WASAPI shared mode
    # rejects anything else, and relying on the host API to resample is what
    # made the engine work on MME but not on WASAPI.
    device_rate = device_default_rate(sd, input_device)
    if device_rate is None:
        device_rate = device_default_rate(sd, output_device)
    if device_rate is None:
        device_rate = sample_rate
    if device_rate != sample_rate and np is None:
        raise RuntimeError("设备采样率与引擎不一致，转换需要 numpy")
    resampler = StreamResampler(device_rate, sample_rate)
    # One callback carries this much engine audio. The model keeps working in
    # full chunks because process_chunk accumulates short pieces itself, but
    # the callback width is what PortAudio charges device latency against.
    block_frames = device_block_frames(session, device_block_ms, denoiser)
    # Same wall-clock budget for the input queue whatever the callback width:
    # it may hold INPUT_QUEUE_SECONDS of captured audio, no more and no less.
    session.set_input_capacity(
        max(
            8,
            int(
                round(
                    INPUT_QUEUE_SECONDS * session.sample_rate / max(1, block_frames)
                )
            ),
        )
    )
    device_block = resampler.device_frames(block_frames)
    output_rate = device_rate
    if output_device is not None and output_device >= 0:
        output_rate = device_default_rate(sd, output_device) or device_rate
    out_resampler = StreamResampler(output_rate, sample_rate)
    output_block = out_resampler.device_frames(block_frames)
    # Headroom of one extra block: some backends hand over a different width
    # than the one requested, and a callback must never overrun its buffer.
    engine_capacity = block_frames * 2
    engine_block = (
        np.zeros(engine_capacity, dtype=np.float32)
        if np is not None
        else [0.0] * engine_capacity
    )

    # Monitoring to the same device as the main output is redundant and, on
    # WASAPI, opening a second output stream on that endpoint silences the
    # capture stream (verified: input RMS drops to exactly 0). Skip it so the
    # input keeps working; the main output already plays the converted voice.
    monitor = (
        MonitorTap(session.chunk_size, sample_rate)
        if monitor_device is not None and monitor_device != output_device
        else None
    )
    monitor_resampler = None
    monitor_block = 0
    monitor_engine = None
    if monitor is not None:
        monitor_rate = device_default_rate(sd, monitor_device) or device_rate
        monitor_resampler = StreamResampler(monitor_rate, sample_rate)
        monitor_block = monitor_resampler.device_frames(block_frames)
        monitor_engine = (
            np.zeros(engine_capacity, dtype=np.float32)
            if np is not None
            else [0.0] * engine_capacity
        )

    def report_metrics() -> None:
        nonlocal last_reported_chunk
        if not emit_metrics:
            return
        snapshot = session.metrics_snapshot(levels=levels)
        if snapshot["chunk"] == last_reported_chunk:
            return
        last_reported_chunk = snapshot["chunk"]
        line = format_metrics_line(snapshot)
        print(line, file=metrics_out, flush=True)
        if metrics_handle is not None:
            try:
                # Same prefix and payload as stdout, plus a wall-clock stamp:
                # dropouts can only be correlated with what the listener heard
                # if the series has real timestamps.
                payload = json.loads(line.split(" ", 1)[1])
                payload["t"] = round(time.time(), 3)
                metrics_handle.write(
                    "[panda.metrics] " + json.dumps(payload, separators=(",", ":")) + "\n"
                )
                metrics_handle.flush()
            except (OSError, ValueError, IndexError):
                # A diagnostics sink must never be able to stop the audio.
                pass

    def process_input(indata) -> None:
        # While draining for a stop the queue must only receive what is
        # already captured; fresh microphone audio would keep it from ever
        # emptying and the stop would fall back to a kill.
        if flushing:
            return
        live = controls.snapshot()
        captured = resampler.to_engine(indata[:, 0])
        if np is not None:
            input_values = np.asarray(captured, dtype=np.float32)
            input_peak = float(np.max(np.abs(input_values))) if input_values.size else 0.0
            levels["input_rms"] = round(
                float(np.sqrt(np.mean(np.square(input_values)))) if input_values.size else 0.0,
                6,
            )
            levels["input_peak"] = round(input_peak, 6)
            levels["input_clipped"] = input_peak >= 0.99
        if input_gain is not None:
            input_gain.gain_db = live["input_gain_db"]
            input_gain.linear = _gain_linear(input_gain.gain_db)
            input_gain.process_in_place(captured)
        if denoiser is not None:
            # Denoise before the gate so the gate's level decision sees a
            # cleaned signal.
            captured = denoiser.process(captured)
        if gate is not None and live["gate_enabled"]:
            gate.threshold_db = live["gate_db"]
            captured = gate.process(captured)
        session.submit_input(captured)

    def render_output(target) -> None:
        live = controls.snapshot()
        session.read_output_into(target)
        if gain is not None:
            gain.gain_db = live["output_gain_db"]
            gain.linear = _gain_linear(gain.gain_db)
            gain.process_in_place(target)
        if limiter is not None:
            limiter.process_in_place(target)
        if np is not None:
            output_values = np.asarray(target, dtype=np.float32)
            output_peak = float(np.max(np.abs(output_values))) if output_values.size else 0.0
            levels["output_rms"] = round(
                float(np.sqrt(np.mean(np.square(output_values)))) if output_values.size else 0.0,
                6,
            )
            levels["output_peak"] = round(output_peak, 6)
            levels["output_clipped"] = output_peak >= 0.99
        if monitor is not None:
            # Fan out exactly what the main device just played.
            monitor.push(target)

    def slice_target(buffer, frames: int):
        """A view of ``buffer`` wide enough for ``frames`` engine samples."""
        wanted = max(1, int(frames))
        if wanted > len(buffer):
            wanted = len(buffer)
        return buffer[:wanted]

    def write_device(outdata, rendered, frames: int) -> None:
        # Backends may hand over a width other than the one requested; never
        # raise inside a callback, pad the shortfall with silence instead.
        if len(rendered) >= frames:
            outdata[:, 0][:] = rendered[:frames]
            return
        outdata[:, 0][: len(rendered)] = rendered
        outdata[:, 0][len(rendered) :] = 0.0

    def input_callback(indata, frames, time_info, status) -> None:
        if status:
            print(f"[audio] {status}", file=sys.stderr)
        process_input(indata)

    def no_output_callback(indata, frames, time_info, status) -> None:
        # Capture-only: still render so the output gain/limiter run and the
        # monitor tap receives audio even though nothing plays to a device.
        if status:
            print(f"[audio] {status}", file=sys.stderr)
        process_input(indata)
        render_output(slice_target(engine_block, block_frames))

    def output_callback(outdata, frames, time_info, status) -> None:
        if status:
            print(f"[audio] {status}", file=sys.stderr)
        target = slice_target(engine_block, out_resampler.engine_frames(frames))
        render_output(target)
        if controls.snapshot()["output_muted"]:
            outdata[:, 0][:] = [0.0] * frames
        else:
            write_device(outdata, out_resampler.from_engine(target), frames)

    def monitor_callback(outdata, frames, time_info, status) -> None:
        if status:
            print(f"[monitor] {status}", file=sys.stderr)
        target = slice_target(monitor_engine, monitor_resampler.engine_frames(frames))
        monitor.read_into(target)
        if monitor_gain is not None:
            live = controls.snapshot()
            monitor_gain.gain_db = live["monitor_gain_db"]
            monitor_gain.linear = _gain_linear(monitor_gain.gain_db)
            monitor_gain.process_in_place(target)
        write_device(outdata, monitor_resampler.from_engine(target), frames)

    revision = controls.revision

    print(
        f"[audio] opening input={input_device} output={output_device} "
        f"monitor={monitor_device} rate={device_rate} out_rate={output_rate} "
        f"no_output={no_output}",
        file=sys.stderr,
        flush=True,
    )

    with contextlib.ExitStack() as stack:
        if metrics_handle is not None:
            # The serve loop re-enters this function on every device reopen;
            # a handle left open would leak one file per switch. Registered
            # before the streams so LIFO closes it after they stop writing.
            stack.callback(metrics_handle.close)
        input_stream = None
        output_stream = None
        if no_output:
            # Output is disabled: capture only, so monitoring can still play
            # the converted voice without sending it to any output device.
            input_stream = stack.enter_context(
                sd.InputStream(
                    samplerate=device_rate,
                    blocksize=device_block,
                    device=input_device,
                    channels=1,
                    dtype="float32",
                    callback=no_output_callback,
                )
            )
        else:
            # Always open independent input and output streams. A single duplex
            # stream ties both directions to one device pair and, on this
            # hardware, silences capture when the output is the headphones
            # endpoint (verified: input_rms stayed 0.0 while the output was
            # fine). The session already decouples the two directions through
            # its jitter buffer, so separate streams are safe and work for any
            # device pair or host API.
            input_stream = stack.enter_context(
                sd.InputStream(
                    samplerate=device_rate,
                    blocksize=device_block,
                    device=input_device,
                    channels=1,
                    dtype="float32",
                    callback=input_callback,
                )
            )
            output_stream = stack.enter_context(
                sd.OutputStream(
                    samplerate=output_rate,
                    blocksize=output_block,
                    device=output_device,
                    channels=1,
                    dtype="float32",
                    callback=output_callback,
                )
            )
        if monitor is not None:
            stack.enter_context(
                sd.OutputStream(
                    samplerate=monitor_resampler.device_rate,
                    blocksize=monitor_block,
                    device=monitor_device,
                    channels=1,
                    dtype="float32",
                    callback=monitor_callback,
                )
            )

        # What the backend itself holds on to. This is charged on top of our
        # jitter buffer and processing time, so the latency shown to the
        # listener has to include it rather than pretending the pipeline is
        # only as deep as our own queue.
        levels["input_latency_ms"] = stream_latency_ms(input_stream)
        levels["output_latency_ms"] = stream_latency_ms(output_stream)
        levels["device_block_ms"] = round(
            block_frames / session.sample_rate * 1000.0, 3
        )
        print(
            "[audio] latency in={}ms out={}ms block={}ms ({} engine frames)".format(
                levels["input_latency_ms"],
                levels["output_latency_ms"],
                levels["device_block_ms"],
                block_frames,
            ),
            file=sys.stdout,
            flush=True,
        )

        # Tell the desktop that the model and audio stream are ready, so it can
        # stop showing a loading state.
        _progress(100)
        print("[panda.ready]", file=sys.stdout, flush=True)

        try:
            report_metrics()
            while (
                session.last_error is None
                and session.running
                and controls.revision == revision
                and not controls.snapshot()["flush"]
            ):
                sd.sleep(int(poll_seconds * 1000))
                report_metrics()
        finally:
            report_metrics()

        if controls.snapshot()["flush"]:
            # Play out everything still in flight before the streams close.
            # The input queue holds up to ~1.3 s of speech and the model lags
            # its last input by ~260 ms; exiting first discarded both, which
            # is how the end of a sentence went missing.
            flushing = True
            result = session.flush_tail(
                timeout=FLUSH_TIMEOUT_SECONDS,
                drain_playback=True,
            )
            print(
                "[panda.flush] " + json.dumps(result, separators=(",", ":")),
                file=sys.stdout,
                flush=True,
            )
            report_metrics()


def load_meanvc2_runtime(root: Path):
    runtime_path = root / "runtime" / "run_rt.py"
    if not runtime_path.is_file():
        raise FileNotFoundError(f"没有找到官方 MeanVC2 runtime：{runtime_path}")

    runtime_root = str(runtime_path.parent)
    if runtime_root not in sys.path:
        sys.path.insert(0, runtime_root)
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    spec = importlib.util.spec_from_file_location(
        "panda_meanvc2_runtime",
        runtime_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 MeanVC2 runtime")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def pack_embedding_path(wav_path: Path) -> Path:
    """Speaker embedding a pack ships next to its reference audio."""
    return wav_path.parent.parent / "assets" / "spk_emb.npy"


def load_pack_embedding(wav_path) -> object | None:
    """Read the precomputed speaker embedding if it is newer than the audio.

    The pack already stores ``assets/spk_emb.npy`` and it is bit-identical to
    what ``extract_embedding`` recomputes from ``reference.wav`` (verified by
    cosine 1.0 / max diff 0.0), so the WavLM+ECAPA pass can be skipped. The
    mtime check keeps a re-cut reference from silently using a stale feature.
    """
    wav = Path(wav_path)
    if not wav.is_file():
        return None
    cache = pack_embedding_path(wav)
    try:
        if not cache.is_file() or cache.stat().st_mtime < wav.stat().st_mtime:
            return None
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        array = np.load(cache)
        if array.dtype != np.float32:
            array = array.astype(np.float32, copy=False)
        if array.ndim == 1 and array.shape[0] == 256:
            array = array.reshape(1, 256)
        if array.shape != (1, 256):
            return None
        return torch.from_numpy(np.ascontiguousarray(array))
    except Exception:  # noqa: BLE001
        # A corrupt cache must never break loading; fall back to extraction.
        return None


def install_pack_embedding_cache(runtime) -> None:
    """Let the upstream runner pick up a pack's precomputed embedding."""
    original = getattr(runtime, "extract_embedding", None)
    if original is None:
        return

    def fast_extract(model, wav, sample_rate: int = 16000, device="cpu"):
        cached = load_pack_embedding(wav)
        if cached is not None:
            return cached.to(device)
        return original(model, wav, sample_rate=sample_rate, device=device)

    runtime.extract_embedding = fast_extract


def reload_voice(runner, voice_pack: str) -> Path:
    """Swap only the speaker embedding, keeping every loaded model resident.

    ASR, VC, vocoder and the speaker model together take ~20s to load and are
    completely voice independent; only the 256-dim speaker embedding depends on
    the pack. Reading it from the pack takes well under a second, so switching
    voice no longer needs a process restart.
    """
    import torch  # noqa: PLC0415

    target = resolve_reference_from_pack(Path(voice_pack))
    embedding = load_pack_embedding(target)
    if embedding is None:
        # The upstream runtime puts its own package directory on sys.path.
        from src.speaker import extract_embedding  # noqa: PLC0415

        embedding = extract_embedding(
            runner.spk_model, str(target), device=runner.device
        )

    with torch.no_grad():
        runner.vc_spk_emb = embedding.to(runner.device)
        runner.vc_gtm_kv = runner.vc.gtm(runner.vc_spk_emb)

    # Only the speaker-conditioned DiT KV cache belongs to the old voice; drop
    # it exactly the way the periodic 4000-frame reset does. The fBank/ASR/BN
    # caches hold audio history rather than voice state, and clearing them from
    # this thread would race the conversion worker (it reads them while it is
    # inside process_chunk) and glitch playback, so they are left untouched.
    runner.vc_kv_cache = None
    runner.vc_offset = 0
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Panda MeanVC2 realtime worker")
    parser.add_argument("--meanvc2-root", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--target-wav")
    target.add_argument("--voice-pack")
    parser.add_argument("--model", choices=("120ms", "40ms"), default="120ms")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--input-device", type=int)
    parser.add_argument(
        "--output-device",
        type=int,
        help="输出设备 ID；负数表示不输出（仅监听）",
    )
    parser.add_argument(
        "--monitor-device",
        type=int,
        help="监听输出设备 ID；把变声结果同时播给本机扬声器",
    )
    parser.add_argument("--input-name", help="输入设备友好名（不推荐，中文会乱码）")
    parser.add_argument("--output-name", help="输出设备友好名")
    parser.add_argument("--monitor-name", help="监听设备友好名")
    parser.add_argument("--input-name-b64", help=argparse.SUPPRESS)
    parser.add_argument("--output-name-b64", help=argparse.SUPPRESS)
    parser.add_argument("--monitor-name-b64", help=argparse.SUPPRESS)
    parser.add_argument(
        "--noise-gate-db",
        type=float,
        help="静音门阈值（dBFS）；不指定表示关闭，推荐 -45",
    )
    parser.add_argument(
        "--limiter-ceiling",
        type=float,
        default=0.891,
        help="输出软限幅上限（0 表示关闭）",
    )
    parser.add_argument(
        "--output-gain-db",
        type=float,
        default=0.0,
        help="输出音量增益（dB），范围 -60 到 24，默认 0",
    )
    parser.add_argument(
        "--input-gain-db",
        type=float,
        default=0.0,
        help="输入麦克风增益（dB），范围 -60 到 24，默认 0",
    )
    parser.add_argument(
        "--monitor-gain-db",
        type=float,
        default=0.0,
        help="监听输出增益（dB），范围 -60 到 24，默认 0",
    )
    parser.add_argument(
        "--denoise",
        action="store_true",
        help="启用 DeepFilterNet 降噪；会额外增加约 160 ms 延迟",
    )
    parser.add_argument(
        "--denoise-level",
        choices=("strong", "balanced", "gentle"),
        default="strong",
        help="降噪强度：strong 最强，balanced/gentle 保留更多环境声与语音细节",
    )
    parser.add_argument(
        "--prefill-chunks",
        type=int,
        default=1,
        help="播放前预滚的块数；每块 160 ms，直接决定启动延迟与抗抖动余量",
    )
    parser.add_argument(
        "--max-backlog-chunks",
        type=int,
        default=6,
        help="抖动缓冲上限（块）；超出后丢弃最旧音频以避免延迟累积",
    )
    parser.add_argument(
        "--trim-margin-chunks",
        type=float,
        # Measured on the reference host: at 1.0 the buffer sits right on the
        # 320 ms threshold, so a normal processing jitter trims ~18% of the
        # already-converted audio away (audible as dropped syllables). At 4.0
        # trimming never fired and the observed peak depth stayed at 360 ms,
        # because playback drains any surplus at real time anyway.
        default=4.0,
        help="缓冲高于预滚多少块才回收盈余；余量过小会把已转换的语音当盈余丢掉（漏字）",
    )
    parser.add_argument(
        "--warmup-chunks",
        type=int,
        default=WARMUP_CHUNKS,
        help="播放前用静音预热推理的次数",
    )
    parser.add_argument(
        "--device-block-ms",
        type=float,
        default=DEVICE_BLOCK_MS,
        help=(
            "音频回调宽度（毫秒）。后端按回调宽度的两倍计入设备延迟，"
            f"默认 {DEVICE_BLOCK_MS:g} ms；开启降噪时自动回到 160 ms"
            "（降噪器按 160 ms 分块同步）"
        ),
    )
    parser.add_argument(
        "--metrics-file",
        help=(
            "指标时序落盘路径（默认系统临时目录 panda_metrics.jsonl）；"
            "桌面端日志只保留白名单行，完整时序只在这里"
        ),
    )
    return parser


_PROGRESS_LOCK = threading.Lock()
_PROGRESS_VALUE = 0


def _progress(percent: int) -> None:
    """Tell the desktop how far model loading is, so it can show a percent.

    Monotonic: stage boundaries report from the main thread while
    :class:`_SmoothProgress` reports from a background one, and the desktop
    would otherwise watch the bar run backwards.
    """
    global _PROGRESS_VALUE
    with _PROGRESS_LOCK:
        value = int(percent)
        if value <= _PROGRESS_VALUE:
            return
        _PROGRESS_VALUE = value
    print(
        f'[panda.progress] {{"percent": {value}}}',
        file=sys.stdout,
        flush=True,
    )


class _SmoothProgress:
    """Keep the bar moving through a stage that cannot be subdivided.

    The speaker model is one ``torch.load`` of the ~1 GB fine-tuned
    checkpoint: measured at 7.96s out of a 13.2s load, with nothing inside
    it to hook. Rather than let the bar sit still and then jump, advance it
    toward the stage's real end over the measured duration and stop just
    short of it. A machine slower than the measurement therefore pauses at
    79% instead of claiming to be done, and the real report that follows
    still wins because progress only ever moves forward.
    """

    def __init__(self, start: int, target: int, seconds: float, emit) -> None:
        self._start = start
        self._target = target
        self._seconds = max(seconds, 0.1)
        self._emit = emit
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "_SmoothProgress":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        begin = time.monotonic()
        while not self._stopped.wait(0.15):
            fraction = min(1.0, (time.monotonic() - begin) / self._seconds)
            self._emit(self._start + int((self._target - self._start) * fraction))


@contextlib.contextmanager
def progress_hooks(runtime, emit=_progress) -> Iterator[None]:
    """Mark the boundaries *inside* ``VCRunner.__init__``.

    The runner loads all four models in one call, so the desktop's own
    checkpoints can only bracket it — which is what made the bar jump from
    20% to 85% while thirteen seconds went by. Measured split of that call:
    ASR jit 1.45s, VC 0.21s, vocoder 0.06s, speaker 7.96s. Everything is
    restored on exit; a hook left in place would keep reporting through live
    voice swaps.
    """
    import torch  # noqa: PLC0415

    original_jit = torch.jit.load
    original_vc = getattr(runtime, "_load_vc_model", None)
    original_spk = getattr(runtime, "init_speaker_model", None)
    jit_calls = [0]

    def hooked_jit(*args, **kwargs):
        result = original_jit(*args, **kwargs)
        jit_calls[0] += 1
        # 1st = ASR (1.45s), 2nd = vocoder (0.06s).
        emit(30 if jit_calls[0] == 1 else 34)
        return result

    def hooked_vc(*args, **kwargs):
        result = original_vc(*args, **kwargs)
        emit(33)
        return result

    def hooked_spk(*args, **kwargs):
        with _SmoothProgress(34, 79, 8.0, emit):
            result = original_spk(*args, **kwargs)
        emit(80)
        return result

    if original_vc is None or original_spk is None:
        # Older runtime without the symbols: bracketing still works, so just
        # leave the known piece out rather than fail to load at all.
        yield
        return

    torch.jit.load = hooked_jit
    runtime._load_vc_model = hooked_vc
    runtime.init_speaker_model = hooked_spk
    try:
        yield
    finally:
        torch.jit.load = original_jit
        runtime._load_vc_model = original_vc
        runtime.init_speaker_model = original_spk


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.meanvc2_root).expanduser().resolve()
    target = (
        resolve_reference_from_pack(Path(args.voice_pack))
        if args.voice_pack
        else Path(args.target_wav).expanduser().resolve()
    )
    # Full metric time series. The desktop drops [panda.metrics] lines from its
    # own log, so without this side channel a dropout that cannot be replayed
    # can never be diagnosed after the fact.
    metrics_path = args.metrics_file or str(
        Path(tempfile.gettempdir()) / "panda_metrics.jsonl"
    )

    try:
        import numpy as np

        _progress(5)
        # Importing the runtime is a single ~3.5s call with nothing inside it
        # to report; crawl toward 19% while it runs instead of sitting on 5%.
        with _SmoothProgress(5, 19, 3.5, _progress):
            runtime = load_meanvc2_runtime(root)
        install_pack_embedding_cache(runtime)
        _progress(20)
        # The four models load inside one call; report their real boundaries
        # so the bar does not sit at 20% for thirteen seconds.
        with progress_hooks(runtime):
            runner = runtime.VCRunner(
                target_wav=str(target),
                device=args.device,
                model=args.model,
            )
        # ConversionSession runs process_chunk on its own thread, so a live
        # voice swap must not touch VCRunner state from this thread: reading
        # the KV cache before the swap and the RoPE offset after it tears the
        # two apart (52 cached keys vs 16 frequencies) and kills the worker.
        # One lock serialises "convert a chunk" against "revoice".
        swap_lock = threading.Lock()

        def process_locked(samples):
            with swap_lock:
                return runner.process_chunk(samples)

        _progress(85)
        warm_up_runner(runner, args.warmup_chunks)
        _progress(92)
        session = ConversionSession(
            process_locked,
            int(runner.CHUNK),
            sample_rate=SAMPLE_RATE,
            prefill_chunks=args.prefill_chunks,
            max_backlog_chunks=args.max_backlog_chunks,
            trim_margin_chunks=args.trim_margin_chunks,
            copy_input=copy_captured,
        )
        # The gate always exists so it can be switched on live; whether it is
        # active is carried by the live controls.
        gate = NoiseGate(
            threshold_db=(
                args.noise_gate_db
                if args.noise_gate_db is not None
                else -45.0
            )
        )
        limiter = (
            SoftLimiter(ceiling=args.limiter_ceiling)
            if args.limiter_ceiling > 0.0
            else None
        )
        gain = OutputGain(args.output_gain_db)
        input_gain = OutputGain(args.input_gain_db)
        monitor_gain = OutputGain(args.monitor_gain_db)
        denoiser = None
        if args.denoise:
            from panda_infer.denoise import (
                attenuation_limit_db,
                build_deepfilter_denoiser,
            )

            # A packaged build ships the checkpoint and sets the environment
            # variable; the builder also detects the portable layout directly.
            denoiser = build_deepfilter_denoiser(
                atten_lim_db=attenuation_limit_db(args.denoise_level)
            )
        _progress(95)
        with session:
            no_output = (
                args.output_device is not None and args.output_device < 0
            )
            controls = LiveControls(
                output_gain_db=args.output_gain_db,
                input_gain_db=args.input_gain_db,
                monitor_gain_db=args.monitor_gain_db,
                gate_enabled=args.noise_gate_db is not None,
                gate_db=(
                    args.noise_gate_db
                    if args.noise_gate_db is not None
                    else -45.0
                ),
                output_muted=no_output,
                input_device=args.input_device,
                output_device=args.output_device,
                monitor_device=(
                    args.monitor_device
                    if args.monitor_device is not None
                    else -1
                ),
                input_device_name=(
                    _decoded_name(args.input_name_b64, args.input_name) or ""
                ),
                output_device_name=(
                    _decoded_name(args.output_name_b64, args.output_name) or ""
                ),
                monitor_device_name=(
                    _decoded_name(args.monitor_name_b64, args.monitor_name) or ""
                ),
                denoise=args.denoise,
                denoise_level=args.denoise_level,
                prefill_chunks=args.prefill_chunks,
                max_backlog_chunks=args.max_backlog_chunks,
            )
            if sys.stdin is not None:
                # Hand the stream to the thread and take it off sys.stdin.
                # The reader parks inside readline(), which holds that
                # buffer's lock for the duration of the syscall; interpreter
                # shutdown flushes sys.stdin, blocks on the very same lock and
                # dies with "_enter_buffered_busy ... at interpreter shutdown",
                # leaving the process alive with nothing left to do it. With
                # sys.stdin cleared the shutdown path skips it, the thread is a
                # daemon and gets abandoned with the buffer it is parked in.
                control_stream = sys.stdin
                sys.stdin = None  # type: ignore[assignment]
                threading.Thread(
                    target=_read_stdin_controls,
                    args=(controls, control_stream),
                    name="panda-control",
                    daemon=True,
                ).start()
                # Let the control message the desktop sends at launch apply
                # before the first stream open, so we open once instead of
                # opening and immediately reopening (which can leave the mic
                # endpoint half-released and silent).
                time.sleep(0.3)

            # Keep serving while the desktop changes settings. Device, denoise
            # and latency changes reopen the streams (or rebuild the denoiser)
            # but never reload the model, which stays alive in this loop.
            current_denoise = (args.denoise, args.denoise_level)
            current_voice_pack = args.voice_pack or ""
            served = False
            while True:
                live = controls.snapshot()
                wanted = (bool(live["denoise"]), str(live["denoise_level"]))
                if wanted != current_denoise:
                    current_denoise = wanted
                    if wanted[0]:
                        from panda_infer.denoise import (
                            attenuation_limit_db,
                            build_deepfilter_denoiser,
                        )

                        denoiser = build_deepfilter_denoiser(
                            atten_lim_db=attenuation_limit_db(wanted[1])
                        )
                    else:
                        denoiser = None

                # Switching voice recomputes the speaker embedding in place;
                # the models stay loaded, so this is ~1s instead of a ~20s
                # reload. Any failure falls back to the current voice.
                requested_voice = live["voice_pack"] or ""
                if requested_voice and requested_voice != current_voice_pack:
                    try:
                        with swap_lock:
                            reload_voice(runner, requested_voice)
                        current_voice_pack = requested_voice
                        print(
                            "[panda.voice] "
                            + json.dumps({"ok": True}, ensure_ascii=False),
                            file=sys.stdout,
                            flush=True,
                        )
                    except Exception as exception:  # noqa: BLE001
                        current_voice_pack = ""
                        print(
                            f"[audio] 切换音色失败：{exception}",
                            file=sys.stderr,
                            flush=True,
                        )

                try:
                    run_realtime_session(
                        session,
                        input_device=args.input_device,
                        output_device=args.output_device,
                        monitor_device=args.monitor_device,
                        sample_rate=SAMPLE_RATE,
                        gate=gate,
                        limiter=limiter,
                        gain=gain,
                        input_gain=input_gain,
                        monitor_gain=monitor_gain,
                        denoiser=denoiser,
                        no_output=no_output,
                        controls=controls,
                        device_block_ms=args.device_block_ms,
                        metrics_file=metrics_path,
                    )
                except Exception as exception:
                    # A device can be busy or reject the sample rate. Keep the
                    # model and session alive and wait for the next device change
                    # instead of letting the process exit, which would make the
                    # desktop pay for a full model reload.
                    if session.last_error is not None or not session.running:
                        raise
                    if not served:
                        # The very first open failed (device busy or missing):
                        # exit so the desktop shows the error instead of
                        # spinning on "loading model" forever.
                        raise
                    print(
                        f"[audio] 打开音频设备失败：{exception}",
                        file=sys.stderr,
                        flush=True,
                    )
                    revision = controls.revision
                    while controls.revision == revision:
                        time.sleep(0.05)
                    continue
                served = True
                if controls.snapshot().get("flush"):
                    # The listener asked to stop: everything still in flight
                    # has been played out inside run_realtime_session, so the
                    # serve loop must not reopen the streams.
                    break
                if session.last_error is not None or not session.running:
                    break
        if session.last_error is not None:
            # The streaming thread swallows the traceback, so re-emit it here;
            # without this the desktop only ever sees the bare message.
            traceback.print_exception(session.last_error)
            raise session.last_error
        stats = session.stats()
        print(
            "[stats] blocks={processed_chunks} "
            "mean={mean_process_ms:.1f}ms max={max_process_ms:.1f}ms "
            "starved={starved_reads} underrun={buffer_underrun_frames}f "
            "dropped={buffer_dropped_frames}f".format(**stats)
        )
    except KeyboardInterrupt:
        return 0
    except Exception as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

