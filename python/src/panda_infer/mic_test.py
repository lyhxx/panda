"""Record a short microphone sample and play it back through an output."""

from __future__ import annotations

import argparse
import sys


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="录制短麦克风样本并回放，用于检查输入和输出设备。",
    )
    parser.add_argument("--input-device", type=int, default=-1)
    parser.add_argument("--output-device", type=int, default=-1)
    parser.add_argument("--seconds", type=float, default=3.0)
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    try:
        import numpy as np
        import sounddevice as sd
        from scipy.signal import resample_poly
    except ImportError:
        print(
            "error: 麦克风测试需要 numpy、sounddevice 和 scipy",
            file=sys.stderr,
        )
        return 2

    try:
        input_device = None if args.input_device < 0 else args.input_device
        output_device = None if args.output_device < 0 else args.output_device
        input_info = (
            sd.query_devices(input_device)
            if input_device is not None
            else sd.query_devices(kind="input")
        )
        output_info = (
            sd.query_devices(output_device)
            if output_device is not None
            else sd.query_devices(kind="output")
        )
        if int(input_info.get("max_input_channels", 0)) <= 0:
            raise RuntimeError(f"设备不是输入设备：{input_info.get('name', input_device)}")
        if int(output_info.get("max_output_channels", 0)) <= 0:
            raise RuntimeError(f"设备不是输出设备：{output_info.get('name', output_device)}")

        input_rate = int(round(float(input_info["default_samplerate"])))
        output_rate = int(round(float(output_info["default_samplerate"])))
        frames = max(1, int(round(input_rate * max(0.5, args.seconds))))
        print("recording...", file=sys.stderr)
        recording = sd.rec(
            frames,
            samplerate=input_rate,
            device=input_device,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        mono = np.asarray(recording[:, 0], dtype=np.float32)
        peak = float(np.max(np.abs(mono))) if mono.size else 0.0
        if peak < 0.001:
            raise RuntimeError("没有检测到麦克风声音，请检查输入设备和系统权限")
        if input_rate != output_rate:
            from math import gcd

            divisor = gcd(input_rate, output_rate)
            mono = resample_poly(
                mono,
                output_rate // divisor,
                input_rate // divisor,
            ).astype(np.float32)
        print(f"playing back (peak={peak:.3f})...", file=sys.stderr)
        sd.play(mono, samplerate=output_rate, device=output_device, blocking=True)
        return 0
    except Exception as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
