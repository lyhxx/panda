"""A bounded jitter buffer for the realtime voice-conversion pipeline.

Measured on the development host, roughly one 160 ms block in 250 exceeds the
block budget. A plain queue cannot hide that: it drains to zero and the next
read starves, which is audible as a click or a dropout. This buffer pre-fills
to a small target depth before it starts producing output, so a single slow
block only consumes backlog instead of interrupting playback.

Backlog is bounded by ``max_depth``. If inference falls behind for long enough
that the backlog would exceed the bound, the oldest samples are dropped so
latency cannot grow without limit.

The implementation uses ``array('f')`` so it has no third-party dependency and
is safe to import in minimal environments.
"""

from __future__ import annotations

import array


class JitterBuffer:
    """Accumulate converted audio and emit it at a steady rate."""

    def __init__(
        self,
        target_depth: int,
        max_depth: int | None = None,
        *,
        resume_ratio: float = 0.5,
    ) -> None:
        if target_depth < 0:
            raise ValueError("target_depth must not be negative")
        if max_depth is None and target_depth > 0:
            max_depth = target_depth * 3
        if max_depth is not None and max_depth < target_depth:
            raise ValueError("max_depth must be at least target_depth")
        if not 0.0 < resume_ratio <= 1.0:
            raise ValueError("resume_ratio must be in (0, 1]")

        self._target_depth = target_depth
        self._max_depth = max_depth
        # Re-priming after a dry read must not cost another full pre-roll: the
        # converter hands over 120-240 ms bursts, so a half-depth threshold
        # resumes on the very next burst. Requiring the full target would add
        # a fixed 160 ms of silence on top of every underrun, which is what
        # turned a 40 ms shortfall into a missing syllable.
        self._resume_ratio = resume_ratio
        self._resume_depth = self._depth_ratio(target_depth)
        self._data: array.array[float] = array.array("f")
        self._read_position = 0
        self._primed = target_depth == 0
        self._ever_primed = self._primed

        self.pushed_frames = 0
        self.emitted_frames = 0
        self.dropped_frames = 0
        self.underrun_frames = 0
        self.starved_reads = 0
        self.prefill_frames = 0
        self.prefill_reads = 0
        self.resume_reads = 0
        self.trimmed_frames = 0

    def _depth_ratio(self, target_depth: int) -> int:
        """Depth at which playback may resume after a total drain."""
        if target_depth <= 0:
            return 0
        return max(1, int(target_depth * self._resume_ratio))

    @property
    def resume_depth(self) -> int:
        """Frames needed to resume playback after the buffer ran dry."""
        return self._resume_depth

    @property
    def prime_threshold(self) -> int:
        """Frames needed to start producing output.

        The very first start-up uses the full pre-roll; every later start
        after a drain only needs ``resume_depth``, so a single underrun costs
        one converter burst instead of another full pre-roll of silence.
        """
        return self._target_depth if not self._ever_primed else self._resume_depth

    @property
    def target_depth(self) -> int:
        return self._target_depth

    @property
    def max_depth(self) -> int | None:
        """Backlog bound in frames, or ``None`` when unbounded."""
        return self._max_depth

    @property
    def depth(self) -> int:
        """Frames currently buffered and not yet read."""
        return len(self._data) - self._read_position

    @property
    def primed(self) -> bool:
        """True once enough audio has accumulated to start playback."""
        return self._primed

    def depth_ms(self, sample_rate: int) -> float:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        return self.depth / sample_rate * 1000.0

    def push(self, samples) -> None:
        """Append converted audio to the backlog."""
        count = len(samples)
        if count:
            self._data.extend(samples)
            self.pushed_frames += count
        self._drop_overflow()
        if not self._primed and self.depth >= self.prime_threshold:
            self._primed = True
            self._ever_primed = True

    def read(self, frames: int) -> list[float]:
        """Return exactly ``frames`` samples, zero-filling any shortfall."""
        output = [0.0] * frames
        self.read_into(output)
        return output

    def read_into(self, target) -> int:
        """Fill ``target`` with audio, zero-filling any shortfall.

        Returns the number of real (non-padding) frames written. This is the
        allocation-free read path used by the audio callback.
        """
        frames = len(target)
        if frames <= 0:
            raise ValueError("frames must be positive")

        if not self._primed:
            # Still filling the pre-roll. This silence is intentional, so it
            # is counted separately from a genuine underrun. Reads that happen
            # *after* playback already started are the expensive ones: they are
            # the extra silence an underrun costs on top of its shortfall.
            if self._ever_primed:
                self.resume_reads += 1
            for index in range(frames):
                target[index] = 0.0
            self.emitted_frames += frames
            self.prefill_frames += frames
            self.prefill_reads += 1
            return 0

        available = self.depth
        take = min(available, frames)
        start = self._read_position
        target[0:take] = self._data[start:start + take]
        self._read_position += take
        self._compact()

        for index in range(take, frames):
            target[index] = 0.0

        shortfall = frames - take
        if shortfall:
            self.underrun_frames += shortfall
            self.starved_reads += 1

        self.emitted_frames += frames
        if self.depth == 0:
            # Refill before producing more audio after a total drain.
            self._primed = self._target_depth == 0
        return take

    def read_available(self) -> list[float]:
        """Return every buffered frame without zero-padding.

        Used to flush a finished stream, where padding silence would be
        appended as if it were converted audio.
        """
        available = self.depth
        if available == 0:
            return []
        start = self._read_position
        output = list(self._data[start:start + available])
        self._read_position += available
        self._compact()
        self.emitted_frames += available
        if self.depth == 0:
            self._primed = self._target_depth == 0
        return output

    def set_target_depth(self, target_depth: int) -> None:
        """Adjust the pre-roll target while the session is running."""
        if target_depth < 0:
            raise ValueError("target_depth must not be negative")
        if self._max_depth is not None and target_depth > self._max_depth:
            target_depth = self._max_depth
        self._target_depth = target_depth
        self._resume_depth = self._depth_ratio(target_depth)
        if not self._primed and self.depth >= self.prime_threshold:
            self._primed = True
            self._ever_primed = True

    def set_max_depth(self, max_depth: int | None) -> None:
        """Adjust the backlog bound while the session is running."""
        if max_depth is not None and max_depth < 0:
            raise ValueError("max_depth must not be negative")
        self._max_depth = max_depth
        self._drop_overflow()

    def trim_to(self, target_depth: int) -> int:
        """Discard the oldest frames until at most ``target_depth`` remain.

        A startup catch-up leaves the buffer deeper than its pre-roll: the
        converter returns nothing for the first blocks, then emits several
        blocks in one call to catch up, pushing faster than playback drains.
        Production and playback are balanced afterwards, so that surplus is
        never given back and stays as pure added latency.
        """
        if target_depth < 0:
            raise ValueError("target_depth must not be negative")

        excess = self.depth - target_depth
        if excess <= 0:
            return 0

        self._read_position += excess
        self.trimmed_frames += excess
        self._compact()
        return excess

    def reset(self) -> None:
        self._data = array.array("f")
        self._read_position = 0
        self._primed = self._target_depth == 0
        self._ever_primed = self._primed
        self.pushed_frames = 0
        self.emitted_frames = 0
        self.dropped_frames = 0
        self.underrun_frames = 0
        self.starved_reads = 0
        self.prefill_frames = 0
        self.prefill_reads = 0
        self.resume_reads = 0
        self.trimmed_frames = 0

    def _drop_overflow(self) -> None:
        if self._max_depth is None:
            return
        excess = self.depth - self._max_depth
        if excess > 0:
            self._read_position += excess
            self.dropped_frames += excess
            self._compact()

    def _compact(self) -> None:
        if self._read_position and (
            self._read_position >= 4096
            or self._read_position * 2 >= len(self._data)
        ):
            del self._data[: self._read_position]
            self._read_position = 0
