"""Small audio-pipeline processors used by the realtime path.

Two responsibilities from the pipeline design live here:

* the noise gate keeps the converter from turning background noise into
  invented speech during pauses;
* the soft limiter guarantees the output cannot clip, whatever the model
  produces.

Both work on one block at a time, matching the converter's block contract.
"""

from __future__ import annotations

import math

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is only needed when processing
    np = None


def require_numpy():
    if np is None:
        raise RuntimeError("音频 DSP 处理需要 numpy，请先安装")
    return np


class SoftLimiter:
    """Smooth saturating limiter.

    Below ``knee`` the signal passes through untouched, so ordinary audio is
    bit-for-bit unchanged. Above it the curve bends continuously toward
    ``ceiling`` (a tangent hyperbolicus), which keeps the transfer function
    monotonic and free of the harsh corner a hard clipper would introduce.
    """

    def __init__(self, ceiling: float = 0.891, knee: float | None = None) -> None:
        if not 0.0 < ceiling <= 1.0:
            raise ValueError("ceiling must be in (0, 1]")
        if knee is None:
            knee = ceiling * 0.7
        if not 0.0 <= knee < ceiling:
            raise ValueError("knee must be in [0, ceiling)")

        self.ceiling = float(ceiling)
        self.knee = float(knee)

    def process_in_place(self, samples) -> None:
        np = require_numpy()
        values = np.asarray(samples, dtype=np.float32)
        magnitude = np.abs(values)
        over = magnitude > self.knee
        if bool(np.any(over)):
            span = self.ceiling - self.knee
            compressed = self.knee + span * np.tanh(
                (magnitude[over] - self.knee) / span
            )
            values[over] = np.sign(values[over]) * compressed

        # np.asarray copies a non-array sequence, so a list would otherwise be
        # left untouched and this would silently do nothing.
        if values is not samples:
            samples[:] = values

    def process(self, samples) -> np.ndarray:
        np = require_numpy()
        output = np.array(samples, dtype=np.float32, copy=True)
        self.process_in_place(output)
        return output


class OutputGain:
    """Apply a fixed decibel gain to one audio block.

    The same primitive is used for input trim and output volume. The output
    limiter runs after the output stage, so a positive output gain cannot push
    the final signal past its ceiling.
    """

    def __init__(self, gain_db: float = 0.0) -> None:
        if not -60.0 <= gain_db <= 24.0:
            raise ValueError("gain_db must be between -60 and 24")
        self.gain_db = float(gain_db)
        self.linear = 10.0 ** (self.gain_db / 20.0)

    def process_in_place(self, samples) -> None:
        np = require_numpy()
        values = np.asarray(samples, dtype=np.float32)
        if self.linear != 1.0:
            values *= self.linear
        if values is not samples:
            samples[:] = values

    def process(self, samples) -> np.ndarray:
        np = require_numpy()
        output = np.array(samples, dtype=np.float32, copy=True)
        self.process_in_place(output)
        return output


class NoiseGate:
    """Attenuates blocks that stay below a level threshold.

    The decision is per block, because that is the unit the converter sees; a
    sample-accurate gate would need lookahead to avoid chopping word onsets.
    Gain is ramped across the block instead of stepping, and opening is faster
    than closing so trailing consonants are not cut off.
    """

    def __init__(
        self,
        threshold_db: float = -45.0,
        *,
        attack: float = 1.0,
        release: float = 0.35,
        floor: float = 0.0,
    ) -> None:
        if not -120.0 <= threshold_db <= 0.0:
            raise ValueError("threshold_db must be between -120 and 0")
        for name, value in (("attack", attack), ("release", release)):
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")
        if not 0.0 <= floor <= 1.0:
            raise ValueError("floor must be in [0, 1]")

        self.threshold_db = float(threshold_db)
        self.attack = float(attack)
        self.release = float(release)
        self.floor = float(floor)
        self.gain = 1.0

    def reset(self) -> None:
        self.gain = 1.0

    @staticmethod
    def level_db(samples) -> float:
        np = require_numpy()
        values = np.asarray(samples, dtype=np.float32)
        if values.size == 0:
            return -140.0
        mean_square = float(np.mean(np.square(values)))
        if mean_square <= 0.0:
            return -140.0
        return 10.0 * math.log10(mean_square)

    def process(self, samples) -> np.ndarray:
        np = require_numpy()
        values = np.asarray(samples, dtype=np.float32)
        target = 1.0 if self.level_db(values) >= self.threshold_db else self.floor

        coefficient = self.attack if target > self.gain else self.release
        new_gain = self.gain + (target - self.gain) * coefficient
        ramp = np.linspace(self.gain, new_gain, values.size, dtype=np.float32)
        self.gain = new_gain
        return values * ramp

    def process_in_place(self, samples) -> None:
        samples[:] = self.process(samples)


def _windowed_sinc_lowpass(taps: int, cutoff: float) -> "np.ndarray":
    """Windowed-sinc low-pass normalised to unit gain at DC.

    ``cutoff`` is in cycles per sample, so 1/6 passes everything below 8 kHz
    when the device runs at 48 kHz.
    """
    np = require_numpy()
    if taps < 3 or taps % 2 == 0:
        raise ValueError("taps must be an odd number >= 3")
    if not 0.0 < cutoff < 0.5:
        raise ValueError("cutoff must be in (0, 0.5)")

    centre = (taps - 1) / 2
    offsets = np.arange(taps, dtype=np.float64) - centre
    kernel = 2.0 * cutoff * np.sinc(2.0 * cutoff * offsets)
    kernel *= np.hamming(taps)
    return (kernel / kernel.sum()).astype(np.float32)


class _PolyphasePath:
    """One direction of an integer-ratio resampler, with retained state."""

    def __init__(self, ratio: int, kernel, upsample_first: bool) -> None:
        self.ratio = ratio
        self.kernel = kernel
        self.upsample_first = upsample_first
        self.state = None

    def reset(self) -> None:
        self.state = None

    def apply(self, values):
        np = require_numpy()
        # Stateful FIR with numpy only. scipy.signal.lfilter pulls in
        # scipy.linalg.blas, whose DLL load hangs in some launch environments
        # (verified stuck in `import scipy.linalg.blas`), so we avoid scipy
        # entirely; numpy is already required for resampling.
        work = values
        if self.upsample_first:
            work = np.zeros(values.size * self.ratio, dtype=np.float32)
            work[:: self.ratio] = values

        taps = len(self.kernel)
        if self.state is None:
            self.state = np.zeros(taps - 1, dtype=np.float32)

        extended = np.concatenate([self.state, work])
        filtered = np.convolve(extended, self.kernel, mode="valid")
        filtered = np.asarray(filtered, dtype=np.float32)
        self.state = extended[-(taps - 1):].copy()

        if self.upsample_first:
            return filtered
        return filtered[:: self.ratio].astype(np.float32)


class StreamResampler:
    """Stateful conversion between a device rate and the engine rate.

    WASAPI shared mode only accepts the device's own mix format, so a 48 kHz
    device cannot be opened at the engine's 16 kHz. Converting block by block
    without state leaves a discontinuity at every boundary, which is audible as
    a periodic click; this keeps the FIR history between calls so the stream is
    filtered as if it were continuous.

    Both directions are needed at once -- capture comes in at the device rate
    and playback goes out at it -- so each direction keeps its own filter state.
    Integer ratios (48 kHz against 16 kHz) use the stateful path; anything else
    falls back to stateless linear interpolation.

    The polyphase path is linear-phase, so it adds a group delay of roughly
    half a filter per direction (about 0.6 ms at 48 kHz with the default 63
    taps). That is inherent to resampling and is far below the block size.
    """

    def __init__(
        self,
        device_rate: int,
        engine_rate: int = 16000,
        *,
        taps: int = 63,
    ) -> None:
        if device_rate <= 0 or engine_rate <= 0:
            raise ValueError("sample rates must be positive")

        self.device_rate = int(device_rate)
        self.engine_rate = int(engine_rate)
        self.exact = self.device_rate == self.engine_rate
        self._down: _PolyphasePath | None = None
        self._up: _PolyphasePath | None = None

        if self.exact:
            return

        if self.device_rate % self.engine_rate == 0:
            # Filter at the device rate, then decimate (or zero-stuff first).
            ratio = self.device_rate // self.engine_rate
            kernel = _windowed_sinc_lowpass(
                taps,
                (self.engine_rate / 2.0) / self.device_rate,
            )
            self._down = _PolyphasePath(ratio, kernel, upsample_first=False)
            self._up = _PolyphasePath(
                ratio,
                kernel * ratio,  # zero-stuffing divides the average by ratio
                upsample_first=True,
            )
        elif self.engine_rate % self.device_rate == 0:
            # Filter at the engine rate instead.
            ratio = self.engine_rate // self.device_rate
            kernel = _windowed_sinc_lowpass(
                taps,
                (self.device_rate / 2.0) / self.engine_rate,
            )
            self._down = _PolyphasePath(
                ratio,
                kernel * ratio,
                upsample_first=True,
            )
            self._up = _PolyphasePath(ratio, kernel, upsample_first=False)

    @property
    def uses_polyphase(self) -> bool:
        return self._down is not None

    def device_frames(self, engine_frames: int) -> int:
        """How many device frames carry ``engine_frames`` of engine audio."""
        if engine_frames <= 0:
            raise ValueError("engine_frames must be positive")
        return int(round(engine_frames * self.device_rate / self.engine_rate))

    def engine_frames(self, device_frames: int) -> int:
        if device_frames <= 0:
            raise ValueError("device_frames must be positive")
        return int(round(device_frames * self.engine_rate / self.device_rate))

    def reset(self) -> None:
        if self._down is not None:
            self._down.reset()
        if self._up is not None:
            self._up.reset()

    def to_engine(self, samples) -> "np.ndarray":
        """Device rate -> engine rate."""
        if self.exact:
            return samples
        np = require_numpy()
        values = np.asarray(samples, dtype=np.float32)
        if self._down is None:
            return self._interpolate(values, self.engine_rate / self.device_rate)
        return self._down.apply(values)

    def from_engine(self, samples) -> "np.ndarray":
        """Engine rate -> device rate."""
        if self.exact:
            return samples
        np = require_numpy()
        values = np.asarray(samples, dtype=np.float32)
        if self._up is None:
            return self._interpolate(values, self.device_rate / self.engine_rate)
        return self._up.apply(values)

    @staticmethod
    def _interpolate(values: "np.ndarray", factor: float) -> "np.ndarray":
        np = require_numpy()
        if values.size == 0 or factor == 1.0:
            return values
        count = int(round(values.size * factor))
        source = np.arange(values.size, dtype=np.float64)
        target = np.linspace(0.0, values.size - 1, count, dtype=np.float64)
        return np.interp(target, source, values).astype(np.float32)
