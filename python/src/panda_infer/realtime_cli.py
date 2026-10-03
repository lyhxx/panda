from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from panda_infer.cli import resolve_reference_from_pack
from panda_infer.doctor import is_virtual_audio_device


def resolve_target(args: argparse.Namespace) -> Path:
    if args.voice_pack:
        return resolve_reference_from_pack(Path(args.voice_pack))
    target = Path(args.target_wav).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"目标音频不存在：{target}")
    return target


def build_runtime_command(args: argparse.Namespace) -> list[str]:
    root = Path(args.meanvc2_root).expanduser().resolve()
    target_wav = resolve_target(args)
    command = [
        str(Path(args.python).expanduser().resolve()),
        "-m",
        "panda_infer.realtime_worker",
        "--meanvc2-root",
        str(root),
        "--target-wav",
        str(target_wav),
        "--model",
        args.model,
        "--device",
        args.device,
    ]
    if args.input_device is not None:
        command += ["--input-device", str(args.input_device)]
    if args.output_device is not None:
        command += ["--output-device", str(args.output_device)]
    monitor_device = getattr(args, "monitor_device", None)
    if monitor_device is not None:
        command += ["--monitor-device", str(monitor_device)]
    noise_gate_db = getattr(args, "noise_gate_db", None)
    if noise_gate_db is not None:
        command += ["--noise-gate-db", str(noise_gate_db)]
    limiter_ceiling = getattr(args, "limiter_ceiling", None)
    if limiter_ceiling is not None:
        command += ["--limiter-ceiling", str(limiter_ceiling)]
    output_gain_db = getattr(args, "output_gain_db", None)
    if output_gain_db is not None:
        command += ["--output-gain-db", str(output_gain_db)]
    input_gain_db = getattr(args, "input_gain_db", None)
    if input_gain_db is not None:
        command += ["--input-gain-db", str(input_gain_db)]
    monitor_gain_db = getattr(args, "monitor_gain_db", None)
    if monitor_gain_db is not None:
        command += ["--monitor-gain-db", str(monitor_gain_db)]
    if getattr(args, "denoise", False):
        command.append("--denoise")
        command += [
            "--denoise-level",
            getattr(args, "denoise_level", "strong"),
        ]
    prefill_chunks = getattr(args, "prefill_chunks", None)
    if prefill_chunks is not None:
        command += ["--prefill-chunks", str(prefill_chunks)]
    max_backlog_chunks = getattr(args, "max_backlog_chunks", None)
    if max_backlog_chunks is not None:
        command += ["--max-backlog-chunks", str(max_backlog_chunks)]
    return command


def enrich_device_payload(payload: dict) -> dict:
    """Tag every device with whether it looks like a virtual audio device.

    The desktop UI uses this to warn when the chosen output is a plain
    speaker: converted audio played there is inaudible to other applications.
    """
    for device in payload.get("devices", []):
        if isinstance(device, dict):
            device["is_virtual"] = is_virtual_audio_device(
                str(device.get("name", ""))
            )
    return payload


def write_json_utf8(payload: dict) -> None:
    """Write JSON as UTF-8 bytes regardless of the console code page.

    Device names routinely contain characters such as ``®`` that the default
    Windows code page cannot encode. Consumers (the desktop app) parse UTF-8,
    so emit bytes instead of going through the locale-encoded text stream.
    """
    text = json.dumps(payload, ensure_ascii=False)
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        print(text)
        return
    stream.write(text.encode("utf-8"))
    stream.write(b"\n")
    stream.flush()


DEVICE_QUERY_SCRIPT = (
    "import json, sounddevice as sd; "
    "print(json.dumps({"
    "'default': list(sd.default.device), "
    "'hostapis': [api['name'] for api in sd.query_hostapis()], "
    "'devices': list(sd.query_devices())"
    "}, ensure_ascii=False))"
)


def query_devices(python_executable: str) -> dict:
    """Probe sounddevice in the target interpreter and enrich the payload."""
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    executable = str(Path(python_executable).expanduser().resolve())
    completed = subprocess.run(
        [executable, "-c", DEVICE_QUERY_SCRIPT],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"退出码 {completed.returncode}"
        raise RuntimeError(f"设备查询失败：{detail}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exception:
        raise RuntimeError(
            f"设备查询没有返回有效 JSON：{exception}"
        ) from exception

    return enrich_device_payload(payload)


def print_devices(python_executable: str, *, as_json: bool = False) -> int:
    if not as_json:
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        executable = str(Path(python_executable).expanduser().resolve())
        completed = subprocess.run(
            [
                executable,
                "-c",
                "import sounddevice as sd; print(sd.query_devices())",
            ],
            check=False,
            env=environment,
        )
        return completed.returncode

    try:
        payload = query_devices(python_executable)
    except RuntimeError as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 2

    write_json_utf8(payload)
    return 0


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="启动官方 MeanVC2 实时变声 runtime。"
    )
    parser.add_argument("--meanvc2-root", help="官方 MeanVC2 仓库")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="安装了 MeanVC2 依赖的 Python 解释器",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--voice-pack", help="已安装的 Panda 音色包目录")
    target.add_argument("--target-wav", help="目标说话人参考 WAV")
    parser.add_argument("--model", choices=("120ms", "40ms"), default="120ms")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--input-device", type=int, help="sounddevice 输入设备 ID")
    parser.add_argument("--output-device", type=int, help="sounddevice 输出设备 ID")
    parser.add_argument(
        "--monitor-device",
        type=int,
        help="监听输出设备 ID；变声结果同时播给本机扬声器",
    )
    parser.add_argument(
        "--noise-gate-db",
        type=float,
        help="静音门阈值（dBFS）；不指定表示关闭，推荐 -45",
    )
    parser.add_argument(
        "--limiter-ceiling",
        type=float,
        help="输出软限幅上限；0 表示关闭",
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
        help="播放前预滚的块数（每块 160 ms），越小启动越快、抗抖动越弱",
    )
    parser.add_argument(
        "--max-backlog-chunks",
        type=int,
        help="抖动缓冲上限（块），超出后丢弃最旧音频",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印命令，不执行")
    parser.add_argument("--list-devices", action="store_true", help="列出音频设备")
    parser.add_argument(
        "--json",
        action="store_true",
        help="与 --list-devices 一起使用时输出 JSON",
    )
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    if args.list_devices:
        return print_devices(args.python, as_json=args.json)
    if args.json:
        print("error: --json requires --list-devices", file=sys.stderr)
        return 2
    if not args.meanvc2_root:
        print("error: --meanvc2-root is required", file=sys.stderr)
        return 2
    if not args.voice_pack and not args.target_wav:
        print("error: --voice-pack or --target-wav is required", file=sys.stderr)
        return 2

    try:
        command = build_runtime_command(args)
    except Exception as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(subprocess.list2cmdline(command))
        return 0

    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

