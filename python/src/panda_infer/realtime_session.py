"""Decoupled realtime conversion session.

The audio callback must never run the model. Measured MeanVC2 CPU inference
takes ~121 ms for a 160 ms block, and about one block in 250 exceeds the
budget. Running that inside the device callback makes every slow block an
audible dropout.

This module owns the boundary instead:

* the audio callback submits captured audio and reads converted audio,
* a worker thread runs inference and pushes finished audio into a
  :class:`~panda_infer.jitter_buffer.JitterBuffer`.

The buffer pre-roll absorbs occasional slow blocks, and its bound keeps
latency from growing when inference falls behind for a long stretch.
"""

from __future__ import annotations

import json
import queue
import threading
import time

from panda_infer.jitter_buffer import JitterBuffer

_STOP = object()

# Prefix for the machine-readable metrics line consumed by the desktop UI.
# Keeping the prefix separate from the payload lets the reader pick these
# lines out of ordinary log output without parsing every line as JSON.
METRICS_PREFIX = "[panda.metrics]"


def format_metrics_line(snapshot: dict) -> str:
    """Render a metrics snapshot as one line the C++ core can parse."""
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return f"{METRICS_PREFIX} {payload}"


class MonitorTap:
    """Fan converted audio out to a second playback device.

    Routing the converted voice into a virtual cable makes it inaudible to the
    person speaking. This tap keeps a separate short backlog so a monitor
    output can play the same audio without stealing samples from the main
    output, and without the monitor's own timing affecting the conversion.
    """

    def __init__(
        self,
        chunk_size: int,
        sample_rate: int,
        *,
        prefill_chunks: int = 2,
        max_backlog_chunks: int = 6,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        self._buffer = JitterBuffer(
            prefill_chunks * chunk_size,
            max_depth=max_backlog_chunks * chunk_size,
        )
        self._lock = threading.Lock()

    def push(self, samples) -> None:
        with self._lock:
            self._buffer.push(samples)

    def read_into(self, target) -> int:
        with self._lock:
            return self._buffer.read_into(target)

    def stats(self) -> dict:
        with self._lock:
            return {
                "depth_frames": self._buffer.depth,
                "starved_reads": self._buffer.starved_reads,
                "underrun_frames": self._buffer.underrun_frames,
                "dropped_frames": self._buffer.dropped_frames,
                "prefill_reads": self._buffer.prefill_reads,
            }


class ConversionSession:
    """Run conversion on a worker thread behind a jitter buffer."""

    def __init__(
        self,
        convert,
        chunk_size: int,
        *,
        sample_rate: int = 16000,
        # One block is enough in practice: measured on the development host,
        # one block of pre-roll held zero underruns across 113 live WASAPI
        # blocks while halving the buffer latency (320 ms -> 160 ms).
        prefill_chunks: int = 1,
        max_backlog_chunks: int = 6,
        input_queue_chunks: int = 8,
        # How far above the pre-roll the backlog may drift before the surplus
        # is given back. Anything above the pre-roll is pure added latency, but
        # a margin avoids trimming a transient burst.
        trim_margin_chunks: float = 1.0,
        # After the buffer runs dry, playback resumes at this fraction of the
        # pre-roll instead of the full pre-roll. The converter hands audio over
        # in 120-240 ms bursts, so a half-depth threshold resumes on the next
        # burst; requiring the full pre-roll added a fixed block of silence to
        # every underrun (audible as a missing syllable).
        resume_ratio: float = 0.5,
        copy_input=None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if prefill_chunks < 0:
            raise ValueError("prefill_chunks must not be negative")
        if max_backlog_chunks <= prefill_chunks:
            raise ValueError("max_backlog_chunks must exceed prefill_chunks")
        if input_queue_chunks <= 0:
            raise ValueError("input_queue_chunks must be positive")
        if trim_margin_chunks < 0:
            raise ValueError("trim_margin_chunks must not be negative")

        self._convert = convert
        self._chunk_size = chunk_size
        self._sample_rate = sample_rate
        # The default copier gives the session ownership of the samples using
        # only the standard library; callers working with numpy pass their own.
        self._copy_input = copy_input if copy_input is not None else list
        self._trim_margin_frames = int(round(chunk_size * trim_margin_chunks))

        self._buffer = JitterBuffer(
            prefill_chunks * chunk_size,
            max_depth=max_backlog_chunks * chunk_size,
            resume_ratio=resume_ratio,
        )
        self._buffer_lock = threading.Lock()
        self._input: queue.Queue = queue.Queue(maxsize=input_queue_chunks)
        self._input_capacity = input_queue_chunks
        self._prefill_chunks = prefill_chunks
        self._max_backlog_chunks = max_backlog_chunks
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error: BaseException | None = None

        self.processed_chunks = 0
        self.converted_chunks = 0
        self.empty_conversions = 0
        self.submitted_chunks = 0
        self.input_dropped_chunks = 0
        self.total_process_ms = 0.0
        self.max_process_ms = 0.0
        self.last_process_ms = 0.0
        # Calls that have not produced output yet; their time is charged to the
        # block they eventually produce, so ``processing_ms`` keeps meaning
        # "time spent converting one block of audio" even when the device
        # hands over smaller pieces than the model's own chunk.
        self._pending_process_ms = 0.0

    @property
    def chunk_size(self) -> int:
        return self._chunk_size

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def last_error(self) -> BaseException | None:
        return self._last_error

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def pending_input(self) -> int:
        """Blocks queued but not yet picked up by the worker."""
        return self._input.qsize()

    @property
    def input_capacity(self) -> int:
        """Maximum number of queued input blocks before the oldest is dropped."""
        return self._input_capacity

    def set_input_capacity(self, blocks: int) -> None:
        """Resize the input queue, expressed in the *current* callback width.

        The device callbacks can shrink from a whole model chunk to a few
        milliseconds of audio. Keeping the capacity a fixed block count would
        then mean 1.3 s of queued speech at one width and 80 ms at another, and
        the narrow setting would start dropping captured audio on the first
        processing hiccup.
        """
        if blocks < 1:
            raise ValueError("blocks must be positive")
        self._input_capacity = int(blocks)
        # The bound that actually limits submissions is the queue's own
        # maxsize; the field above is only what gets reported. Resizing one
        # without the other would silently keep the old budget.
        self._input.maxsize = int(blocks)

    @property
    def buffer_depth(self) -> int:
        """Converted frames waiting to be played."""
        with self._buffer_lock:
            return self._buffer.depth

    @property
    def idle(self) -> bool:
        """True when every submitted block has been converted."""
        return self.processed_chunks >= self.submitted_chunks

    def start(self) -> "ConversionSession":
        if self._thread is not None:
            raise RuntimeError("session already started")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker,
            name="panda-convert",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> BaseException | None:
        """Signal the worker to finish and wait for it. Returns any failure."""
        self._stop_event.set()
        try:
            self._input.put_nowait(_STOP)
        except queue.Full:
            pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            self._thread = None
        return self._last_error

    def submit_input(self, samples) -> None:
        """Queue one captured block. Never blocks the calling audio thread.

        When the queue is full the oldest pending block is discarded so that
        latency stays bounded. Samples are copied, so the caller may reuse its
        buffer immediately.
        """
        chunk = self._copy_input(samples)
        if self._try_enqueue(chunk):
            return

        # Make room by discarding the oldest block still waiting to run.
        try:
            self._input.get_nowait()
            self.input_dropped_chunks += 1
            # That block was counted when it was enqueued but will never be
            # converted, so it must not keep the session looking busy.
            self.submitted_chunks -= 1
        except queue.Empty:
            pass

        if not self._try_enqueue(chunk):
            self.input_dropped_chunks += 1

    def _try_enqueue(self, chunk) -> bool:
        try:
            self._input.put_nowait(chunk)
        except queue.Full:
            return False
        self.submitted_chunks += 1
        return True

    def set_latency(
        self,
        prefill_chunks: int,
        max_backlog_chunks: int | None = None,
    ) -> None:
        """Apply new pre-roll / backlog bounds to the running buffer."""
        if prefill_chunks is None:
            return
        prefill_chunks = int(prefill_chunks)
        if prefill_chunks < 0:
            raise ValueError("prefill_chunks must not be negative")
        if max_backlog_chunks is None:
            max_backlog_chunks = prefill_chunks + 1
        else:
            max_backlog_chunks = int(max_backlog_chunks)
        if max_backlog_chunks <= prefill_chunks:
            max_backlog_chunks = prefill_chunks + 1

        self._prefill_chunks = prefill_chunks
        self._max_backlog_chunks = max_backlog_chunks
        with self._buffer_lock:
            self._buffer.set_max_depth(max_backlog_chunks * self._chunk_size)
            self._buffer.set_target_depth(prefill_chunks * self._chunk_size)

    def read_output_into(self, target) -> int:
        """Fill ``target`` with converted audio from the buffer."""
        with self._buffer_lock:
            return self._buffer.read_into(target)

    def drain_output(self) -> list[float]:
        """Return all buffered converted audio without padding."""
        with self._buffer_lock:
            return self._buffer.read_available()

    def flush_tail(
        self,
        *,
        silence_blocks: int = 3,
        timeout: float = 1.5,
        drain_playback: bool = True,
    ) -> dict:
        """Convert the captured tail so stopping cannot cut off the last word.

        Three things are still in flight when the listener presses stop: the
        input queue (up to ~1.3 s of speech), the model's own lag behind its
        last input (measured: 260 ms), and the converted audio waiting in the
        buffer. Draining the queue and pushing a little silence through the
        model turns that tail into audio the listener actually hears instead
        of discarding it with the process.

        Every wait is bounded by ``timeout`` so a wedged worker can never hang
        the desktop's stop button.
        """
        started = time.monotonic()
        deadline = started + timeout

        def wait_until(predicate) -> bool:
            while time.monotonic() < deadline:
                if predicate():
                    return True
                time.sleep(0.01)
            return False

        # 1. Finish converting what the microphone already handed over.
        drained = wait_until(
            lambda: self._input.empty()
            and self.processed_chunks >= self.submitted_chunks
        )

        # 2. Push the model's own lag out. Feeding silence makes process_chunk
        #    emit the audio still sitting in its ASR/VC caches.
        tail_blocks = 0
        if time.monotonic() < deadline:
            silence = self._copy_input([0.0] * self._chunk_size)
            for _ in range(max(0, silence_blocks)):
                self.submit_input(silence)
                tail_blocks += 1
            wait_until(lambda: self.processed_chunks >= self.submitted_chunks)

        # 3. Let playback consume the backlog before the streams close.
        drained_playback = True
        if drain_playback:
            drained_playback = wait_until(lambda: self.buffer_depth <= 0)

        return {
            "queue_drained": drained,
            "tail_blocks": tail_blocks,
            "playback_drained": drained_playback,
            "depth_frames": self.buffer_depth,
            "elapsed_ms": (time.monotonic() - started) * 1000.0,
        }

    def stats(self) -> dict:
        with self._buffer_lock:
            depth = self._buffer.depth
            buffer_underruns = self._buffer.underrun_frames
            starved_reads = self._buffer.starved_reads
            buffer_dropped = self._buffer.dropped_frames
            prefill_frames = self._buffer.prefill_frames
            prefill_reads = self._buffer.prefill_reads
            resume_reads = self._buffer.resume_reads
            trimmed_frames = self._buffer.trimmed_frames
        mean_process_ms = (
            self.total_process_ms / self.converted_chunks
            if self.converted_chunks
            else 0.0
        )
        return {
            "processed_chunks": self.processed_chunks,
            "converted_chunks": self.converted_chunks,
            "empty_conversions": self.empty_conversions,
            "input_dropped_chunks": self.input_dropped_chunks,
            "mean_process_ms": mean_process_ms,
            "max_process_ms": self.max_process_ms,
            "buffer_depth_ms": depth / self._sample_rate * 1000.0,
            "buffer_underrun_frames": buffer_underruns,
            "starved_reads": starved_reads,
            "buffer_dropped_frames": buffer_dropped,
            "prefill_frames": prefill_frames,
            "prefill_reads": prefill_reads,
            "resume_reads": resume_reads,
            "trimmed_frames": trimmed_frames,
            "last_error": repr(self._last_error) if self._last_error else None,
        }

    def metrics_snapshot(self, levels: dict | None = None) -> dict:
        """Live metrics for the desktop UI.

        ``processing_ms`` is the most recent block so the display tracks
        current load; ``mean_ms``/``max_ms`` provide the session context.
        """
        stats = self.stats()
        chunk_ms = self._chunk_size / self._sample_rate * 1000.0
        processing_ms = self.last_process_ms
        snapshot = {
            "chunk": stats["converted_chunks"],
            "processing_ms": round(processing_ms, 3),
            "chunk_ms": round(chunk_ms, 3),
            "buffer_ms": round(stats["buffer_depth_ms"], 3),
            "overrun": processing_ms > chunk_ms,
            "mean_ms": round(stats["mean_process_ms"], 3),
            "max_ms": round(stats["max_process_ms"], 3),
            "starved_reads": stats["starved_reads"],
            "underrun_frames": stats["buffer_underrun_frames"],
            "dropped_frames": stats["buffer_dropped_frames"],
            "input_dropped": stats["input_dropped_chunks"],
            "trimmed_frames": stats["trimmed_frames"],
            # Frames the listener heard as silence because playback had to
            # (re)prime: at start-up this is expected, after an underrun it is
            # the extra cost the listener pays on top of the shortfall.
            "prefill_frames": stats["prefill_frames"],
            "prefill_reads": stats["prefill_reads"],
            "resume_reads": stats["resume_reads"],
        }
        if levels:
            snapshot.update(levels)
        return snapshot

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._input.get(timeout=0.1)
            except queue.Empty:
                continue
            if chunk is _STOP:
                break

            started = time.perf_counter()
            try:
                output = self._convert(chunk)
            except BaseException as exception:  # noqa: BLE001 - surfaced via stats
                self._last_error = exception
                self._stop_event.set()
                break
            elapsed_ms = (time.perf_counter() - started) * 1000.0

            self.processed_chunks += 1
            self._pending_process_ms += elapsed_ms

            if output is None or len(output) == 0:
                self.empty_conversions += 1
                continue

            # One block of audio is out: charge every call that led to it, so
            # the reported processing time tracks real per-block work even
            # when the device feeds smaller pieces than the model chunk.
            self.converted_chunks += 1
            block_ms = self._pending_process_ms
            self._pending_process_ms = 0.0
            self.last_process_ms = block_ms
            self.total_process_ms += block_ms
            if block_ms > self.max_process_ms:
                self.max_process_ms = block_ms

            with self._buffer_lock:
                self._buffer.push(output)
                # Give back the surplus that a startup catch-up leaves behind;
                # otherwise it stays as permanent added latency.
                limit = (
                    self._buffer.target_depth + self._trim_margin_frames
                )
                if self._buffer.depth > limit:
                    self._buffer.trim_to(self._buffer.target_depth)

    def __enter__(self) -> "ConversionSession":
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.stop()


def drive_offline(
    session: ConversionSession,
    samples,
    *,
    realtime: bool = True,
    sleep=time.sleep,
    clock=time.perf_counter,
) -> list[float]:
    """Push ``samples`` through ``session`` as if a device were feeding it.

    Emulates a capture device that hands over one fixed-size block per tick
    and a playback device that consumes one block per tick. With
    ``realtime=True`` the loop paces itself against a monotonic deadline so
    the timing matches a live device; ``realtime=False`` runs flat out.
    """
    chunk_size = session.chunk_size
    if chunk_size <= 0:
        raise ValueError("session chunk_size must be positive")

    block_ms = chunk_size / session.sample_rate * 1000.0
    total = len(samples)
    output: list[float] = []
    position = 0
    started = clock()
    blocks = 0

    while position < total:
        if not realtime:
            # Offline conversion must not lose audio, so apply back pressure
            # instead of letting the queue discard the oldest block.
            capacity = getattr(session, "input_capacity", 0)
            if capacity:
                while session.pending_input >= capacity:
                    sleep(0.001)

        chunk = samples[position:position + chunk_size]
        position += chunk_size
        session.submit_input(chunk)

        target = [0.0] * chunk_size
        session.read_output_into(target)
        output.extend(target)
        blocks += 1

        if realtime:
            deadline = started + blocks * block_ms / 1000.0
            remaining = deadline - clock()
            if remaining > 0:
                sleep(remaining)

    return output
