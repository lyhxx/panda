"""Optional streaming wrapper around an offline denoiser.

DeepFilterNet's Python API processes whole signals: it resets the model's
recurrent state on every call, so calling it per block leaves a transient at
each boundary. Measured against whole-signal processing, the worst-case
difference is 0.235 for naive block-wise use, and 0.60 if the state is simply
kept -- the STFT state does not carry across Python calls either.

Running it on overlapping windows and cross-fading the results brings that down
to 0.060. The price is one hop of added latency and about 1.6x the CPU, so the
denoiser is opt-in and off by default.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - only needed when denoising
    np = None

from panda_infer.dsp import StreamResampler

ENGINE_RATE = 16000
DENOISER_RATE = 48000
DENOISE_ATTEN_LIM_DB = {
    "strong": 0.0,
    "balanced": 12.0,
    "gentle": 6.0,
}


def require_numpy():
    if np is None:
        raise RuntimeError("降噪需要 numpy，请先安装")
    return np


def resolve_model_base_dir(model_base_dir=None) -> str | None:
    """Resolve a DeepFilterNet checkpoint directory.

    An explicit path wins.  Otherwise, the environment variable used by the
    portable package is honoured, followed by the layout written by
    ``scripts/package_windows.ps1`` next to a bundled Python runtime.
    """
    if model_base_dir:
        return str(Path(model_base_dir).expanduser())

    configured = os.environ.get("PANDA_DEEPFILTER_ROOT")
    if configured:
        return str(Path(configured).expanduser())

    executable = Path(sys.executable).resolve()
    if executable.name.casefold() == "python.exe":
        portable_root = executable.parent.parent
        candidate = portable_root / "DeepFilterNet" / "DeepFilterNet3"
        if (candidate / "config.ini").is_file():
            return str(candidate)

    return None


def attenuation_limit_db(level: str) -> float:
    """Map a user-facing denoise level to DeepFilterNet's attenuation limit."""
    try:
        return DENOISE_ATTEN_LIM_DB[level]
    except KeyError as exception:
        raise ValueError(f"unknown denoise level: {level}") from exception


class Denoiser:
    """Feed it engine blocks, get denoised engine blocks back.

    ``denoise_48k`` takes and returns 48 kHz float32 audio for one window; it is
    injected so the buffering logic can be tested without the model.
    """

    def __init__(
        self,
        denoise_48k,
        *,
        engine_rate: int = ENGINE_RATE,
        denoiser_rate: int = DENOISER_RATE,
        window_blocks: int = 2,
        hop_blocks: int = 1,
    ) -> None:
        if window_blocks < 1 or hop_blocks < 1:
            raise ValueError("window_blocks and hop_blocks must be positive")
        if hop_blocks > window_blocks:
            raise ValueError("hop_blocks must not exceed window_blocks")
        require_numpy()

        self._denoise = denoise_48k
        self._engine_rate = engine_rate
        self._rate = denoiser_rate
        self._window_blocks = window_blocks
        self._hop_blocks = hop_blocks

        # One engine block, expressed at both rates.
        self._engine_block = max(1, int(round(engine_rate * 0.160)))
        self._device_block = self._engine_block * denoiser_rate // engine_rate

        # The window and hop are kept in device samples: the cross-fade has to
        # happen at the denoiser's rate. Resampling each window down before the
        # cross-fade gave every window its own resampler edge and made the
        # result measurably worse.
        self._window_device = self._device_block * window_blocks
        self._hop_device = self._device_block * hop_blocks

        self._up = StreamResampler(denoiser_rate, engine_rate)
        self._down = StreamResampler(denoiser_rate, engine_rate)

        self._pending = np.zeros(0, dtype=np.float32)
        self._accumulate = np.zeros(
            self._window_device * 2,
            dtype=np.float32,
        )
        self._weights = np.zeros(self._window_device * 2, dtype=np.float32)
        self._output = np.zeros(0, dtype=np.float32)

        # A Hann window sums to a constant under 50% overlap, so the cross-fade
        # is level-correct without extra normalisation.
        self._taper = np.hanning(self._window_device).astype(np.float32)
        self._consumed = 0

    @property
    def latency_blocks(self) -> int:
        return self._window_blocks - self._hop_blocks

    @property
    def latency_ms(self) -> float:
        return self.latency_blocks * self._engine_block / self._engine_rate * 1000

    def reset(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)
        self._accumulate = np.zeros(
            self._window_device * 2,
            dtype=np.float32,
        )
        self._weights = np.zeros(self._window_device * 2, dtype=np.float32)
        self._output = np.zeros(0, dtype=np.float32)
        self._consumed = 0
        self._up.reset()
        self._down.reset()

    def process(self, block) -> np.ndarray:
        """Denoise one engine block, returning exactly that many samples."""
        values = np.asarray(block, dtype=np.float32)
        expected = self._engine_block
        if values.size != expected:
            raise ValueError(
                f"expected {expected} samples per block, got {values.size}"
            )

        # Engine block -> denoiser rate, buffered until a full window is ready.
        self._pending = np.concatenate([self._pending, self._up.from_engine(values)])
        while self._pending.size >= self._window_device:
            piece = self._pending[: self._window_device]
            self._pending = self._pending[self._hop_device:]
            self._render(piece)

        if self._output.size >= expected:
            out = self._output[:expected]
            self._output = self._output[expected:]
            return out

        # Still filling the first window: emit silence, which the jitter buffer
        # and the converter's own pre-roll already handle.
        return np.zeros(expected, dtype=np.float32)

    def _render(self, piece: np.ndarray) -> None:
        denoised = np.asarray(self._denoise(piece), dtype=np.float32)
        if denoised.size < self._window_device:
            denoised = np.pad(
                denoised,
                (0, self._window_device - denoised.size),
            )
        denoised = denoised[: self._window_device]

        start = self._consumed
        stop = start + self._window_device
        self._accumulate[start:stop] += denoised * self._taper
        self._weights[start:stop] += self._taper
        self._consumed += self._hop_device

        ready = self._consumed
        if ready > 0:
            weights = np.maximum(self._weights[:ready], 1e-6)
            mixed = self._accumulate[:ready] / weights
            self._accumulate[:ready] = 0.0
            self._weights[:ready] = 0.0
            self._accumulate = np.roll(self._accumulate, -ready)
            self._weights = np.roll(self._weights, -ready)
            self._consumed = 0

            # One resampling step for the whole stream, not one per window.
            self._output = np.concatenate(
                [self._output, self._down.to_engine(mixed)]
            )


def build_deepfilter_denoiser(
    model_base_dir=None,
    *,
    atten_lim_db: float = 0.0,
    **kwargs,
) -> Denoiser:
    """Build a :class:`Denoiser` backed by DeepFilterNet.

    DeepFilterNet is an optional dependency, so a missing install reports that
    instead of failing somewhere deep inside the pipeline.

    ``model_base_dir`` points at a bundled checkpoint; without it DeepFilterNet
    uses (and may download into) its per-user cache.
    """
    try:
        from df.enhance import enhance, init_df
    except ImportError as exception:  # pragma: no cover - env specific
        raise RuntimeError(
            "降噪需要 deepfilternet，请先安装：pip install deepfilternet"
        ) from exception

    import torch

    require_numpy()
    resolved = resolve_model_base_dir(model_base_dir)
    model, state, _ = init_df(model_base_dir=resolved)

    def denoise_48k(window: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            out = enhance(
                model,
                state,
                torch.from_numpy(window).unsqueeze(0),
                atten_lim_db=atten_lim_db,
            )
        return out.squeeze(0).numpy()

    return Denoiser(denoise_48k, **kwargs)
