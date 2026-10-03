"""Measure DeepFilterNet on real speech mixed with environmental noise.

This is an integration probe, not a unit test: it loads the actual model and
reports what happens while the speaker is talking and during pauses.  It
exists because flat noise-only checks cannot show whether speech survives.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, correlate, sosfilt

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from panda_infer.denoise import (
    attenuation_limit_db,
    build_deepfilter_denoiser,
)

ENGINE_RATE = 16000
BLOCK = 2560


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as stream:
        if (
            stream.getframerate() != ENGINE_RATE
            or stream.getnchannels() != 1
            or stream.getsampwidth() != 2
        ):
            raise ValueError("speech must be mono 16 kHz 16-bit PCM")
        return (
            np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")
            .astype(np.float32)
            / 32768.0
        )


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values, dtype=np.float64)) + 1e-20))


def db(value: float) -> float:
    return 20.0 * math.log10(max(value, 1e-12))


def active_frames(speech: np.ndarray) -> np.ndarray:
    starts = np.arange(0, max(1, speech.size - 320 + 1), 160)
    levels = np.array([rms(speech[start : start + 320]) for start in starts])
    threshold = max(float(np.percentile(levels, 95)) * 0.04, 1e-4)
    return starts, levels > threshold


def make_noise(kind: str, size: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    white = rng.normal(0.0, 1.0, size).astype(np.float32)
    if kind == "white":
        return white
    if kind == "fan":
        low = sosfilt(
            butter(3, 500, btype="lowpass", fs=ENGINE_RATE, output="sos"),
            white,
        ).astype(np.float32)
        return low / (rms(low) + 1e-12)
    if kind == "keyboard":
        clicks = 0.08 * white
        for _ in range(max(1, size // 3200)):
            start = int(rng.integers(0, size))
            length = min(int(rng.integers(120, 500)), size - start)
            envelope = np.exp(-np.arange(length) / 80.0).astype(np.float32)
            clicks[start : start + length] += (
                rng.normal(0.0, 1.0, length).astype(np.float32) * envelope
            )
        return clicks / (rms(clicks) + 1e-12)
    raise ValueError(f"unsupported noise kind: {kind}")


def si_sdr(estimate: np.ndarray, reference: np.ndarray) -> float:
    reference = reference - reference.mean()
    estimate = estimate - estimate.mean()
    scale = float(
        np.dot(estimate, reference) / (np.dot(estimate, estimate) + 1e-20)
    )
    target = scale * estimate
    return 10.0 * math.log10(
        (float(np.sum(reference * reference)) + 1e-20)
        / (float(np.sum((target - reference) ** 2)) + 1e-20)
    )


def estimate_lag(
    output: np.ndarray,
    reference: np.ndarray,
    block: int,
) -> int:
    probe = min(output.size, reference.size, ENGINE_RATE * 8)
    correlation = correlate(
        output[:probe],
        reference[:probe],
        mode="full",
        method="fft",
    )
    lag = int(np.argmax(np.abs(correlation)) - (probe - 1))
    if abs(lag) > block * 3:
        return block
    return lag


def measure(
    speech: np.ndarray,
    noise_kind: str,
    snr_db: float,
    denoise_level: str,
    denoiser,
) -> dict:
    usable = (speech.size // BLOCK) * BLOCK
    speech = speech[:usable]
    starts, active = active_frames(speech)
    speech_only = np.concatenate(
        [speech[start : start + 320] for start, voiced in zip(starts, active) if voiced]
    )
    noise = make_noise(noise_kind, speech.size)
    gain = rms(speech_only) / (rms(noise) * 10.0 ** (snr_db / 20.0))
    mixture = speech + gain * noise

    output = np.concatenate(
        [
            denoiser.process(mixture[start : start + BLOCK])
            for start in range(0, speech.size, BLOCK)
        ]
    )
    lag = estimate_lag(output, speech, BLOCK)
    if lag <= 0:
        raise RuntimeError(f"unexpected denoiser lag: {lag}")

    reference = speech[: speech.size - lag]
    input_part = mixture[: speech.size - lag]
    output_part = output[lag:speech.size]
    mask = np.zeros(reference.size, dtype=bool)
    for start, voiced in zip(starts, active):
        stop = min(start + 320, reference.size)
        if voiced and stop > start:
            mask[start:stop] = True
    pauses = ~mask

    return {
        "noise": noise_kind,
        "snr_db": snr_db,
        "denoise_level": denoise_level,
        "latency_ms": lag / ENGINE_RATE * 1000.0,
        "input_si_sdr_db": si_sdr(input_part[mask], reference[mask]),
        "output_si_sdr_db": si_sdr(output_part[mask], reference[mask]),
        "si_sdr_delta_db": (
            si_sdr(output_part[mask], reference[mask])
            - si_sdr(input_part[mask], reference[mask])
        ),
        "pause_noise_suppression_db": (
            db(rms(input_part[pauses] - reference[pauses]))
            - db(rms(output_part[pauses]))
        ),
        "active_level_change_db": (
            db(rms(output_part[mask])) - db(rms(input_part[mask]))
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech", required=True, type=Path)
    parser.add_argument("--model-base-dir", type=Path)
    parser.add_argument(
        "--noise",
        action="append",
        choices=("white", "fan", "keyboard"),
        default=None,
    )
    parser.add_argument(
        "--snr-db",
        action="append",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--denoise-level",
        action="append",
        choices=("strong", "balanced", "gentle"),
        default=None,
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    speech = read_wav(args.speech)
    noises = args.noise or ["white", "fan", "keyboard"]
    snrs = args.snr_db or [10.0]
    levels = args.denoise_level or ["strong"]
    results = []
    for level in levels:
        denoiser = build_deepfilter_denoiser(
            model_base_dir=args.model_base_dir,
            atten_lim_db=attenuation_limit_db(level),
        )
        results.extend(
            measure(speech, noise, snr, level, denoiser)
            for noise in noises
            for snr in snrs
        )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(
            "level     noise     SNR   SI-SDR in/out     delta"
            "   pause noise   active level"
        )
        for result in results:
            print(
                "{denoise_level:8s} {noise:8s} {snr_db:4.1f} "
                "{input_si_sdr_db:6.2f}/{output_si_sdr_db:6.2f} dB "
                "{si_sdr_delta_db:+6.2f} dB "
                "{pause_noise_suppression_db:6.2f} dB "
                "{active_level_change_db:+6.2f} dB".format(**result)
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
