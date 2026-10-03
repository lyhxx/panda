"""Show a live microphone level without running the voice converter.

The settings page needs a live input meter even when no conversion session is
running; starting the whole model just to check the microphone would be far too
heavy. This opens the capture device alone and prints one level line per
interval for the desktop to read.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

LEVEL_PREFIX = "[panda.level]"


def format_level_line(rms: float, peak: float, clipped: bool) -> str:
    payload = json.dumps(
        {
            "rms": round(float(rms), 6),
            "peak": round(float(peak), 6),
            "clipped": bool(clipped),
        },
        separators=(",", ":"),
    )
    return f"{LEVEL_PREFIX} {payload}"


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="实时显示指定麦克风的电平，用于设置页的输入指示。",
    )
    parser.add_argument("--input-device", type=int, default=-1)
    parser.add_argument("--interval", type=float, default=0.08)
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)

    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exception:
        print(
            f"error: 麦克风电平需要 numpy 和 sounddevice：{exception}",
            file=sys.stderr,
        )
        return 2

    device = None if args.input_device < 0 else args.input_device
    try:
        info = (
            sd.query_devices(device)
            if device is not None
            else sd.query_devices(kind="input")
        )
        if int(info.get("max_input_channels", 0)) <= 0:
            raise RuntimeError(
                f"设备不是输入设备：{info.get('name', device)}"
            )
        rate = int(round(float(info["default_samplerate"])))
    except Exception as exception:  # noqa: BLE001 - reported to the user
        print(f"error: {exception}", file=sys.stderr)
        return 1

    state = {"rms": 0.0, "peak": 0.0}

    def callback(indata, frames, time_info, status) -> None:
        mono = np.asarray(indata[:, 0], dtype=np.float32)
        if mono.size:
            state["rms"] = float(np.sqrt(np.mean(np.square(mono))))
            state["peak"] = float(np.max(np.abs(mono)))

    try:
        stream = sd.InputStream(
            samplerate=rate,
            channels=1,
            dtype="float32",
            device=device,
            callback=callback,
        )
        with stream:
            while True:
                time.sleep(max(0.02, args.interval))
                print(
                    format_level_line(
                        state["rms"],
                        state["peak"],
                        state["peak"] >= 0.99,
                    ),
                    flush=True,
                )
    except KeyboardInterrupt:
        return 0
    except Exception as exception:  # noqa: BLE001 - reported to the user
        print(f"error: {exception}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
