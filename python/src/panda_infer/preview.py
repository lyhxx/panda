"""Play a voice pack's reference audio through an output device."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from panda_infer.cli import resolve_reference_from_pack


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="试听音色包的参考音频。",
    )
    parser.add_argument("--voice-pack", required=True, help="已安装的音色包目录")
    parser.add_argument(
        "--output-device",
        type=int,
        default=-1,
        help="sounddevice 输出设备 ID；-1 表示系统默认",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=8.0,
        help="最多试听时长（秒），默认 8 秒",
    )
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        from scipy.signal import resample_poly
    except ImportError as exception:
        print(f"error: 试听需要 numpy、soundfile、sounddevice 和 scipy", file=sys.stderr)
        return 2

    try:
        reference = resolve_reference_from_pack(Path(args.voice_pack))
        samples, sample_rate = sf.read(
            str(reference),
            always_2d=True,
            dtype="float32",
        )
        mono = samples.mean(axis=1)
        if args.max_seconds > 0:
            mono = mono[: int(sample_rate * args.max_seconds)]
        output_device = None if args.output_device < 0 else args.output_device
        device_info = (
            sd.query_devices(output_device)
            if output_device is not None
            else sd.query_devices(kind="output")
        )
        if int(device_info.get("max_output_channels", 0)) <= 0:
            raise RuntimeError(f"设备不是输出设备：{device_info.get('name', output_device)}")
        device_rate = int(round(float(device_info["default_samplerate"])))
        if sample_rate != device_rate:
            from math import gcd

            divisor = gcd(int(sample_rate), device_rate)
            mono = resample_poly(
                mono,
                device_rate // divisor,
                int(sample_rate) // divisor,
            ).astype(np.float32)
        sd.play(mono, samplerate=device_rate, device=output_device, blocking=True)
        return 0
    except Exception as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
