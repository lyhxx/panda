from __future__ import annotations

import argparse
import sys

from panda_infer import cli as infer_cli
from panda_infer import benchmark
from panda_infer import doctor
from panda_infer import realtime_cli
from panda_infer import realtime_sim
from panda_infer import route_check
from panda_infer import voice_check
from panda_infer import preview
from panda_infer import mic_test
from panda_infer import mic_level
from panda_pack import cli as pack_cli

from panda_cli import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="panda",
        description="Panda 开放音色包、离线推理和实时变声入口。",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{pack,infer,realtime,simulate,benchmark,devices,route-check,voice-check,preview,mic-test,mic-level,doctor}",
    )
    commands.add_parser("pack", add_help=False, help="生成开放音色包")
    commands.add_parser("infer", add_help=False, help="执行离线 WAV 变声")
    commands.add_parser("realtime", add_help=False, help="启动实时变声")
    commands.add_parser("simulate", add_help=False, help="用 WAV 仿真实时管线")
    commands.add_parser("benchmark", add_help=False, help="测量实时分块性能")
    commands.add_parser("devices", add_help=False, help="列出音频设备")
    commands.add_parser("route-check", add_help=False, help="检查虚拟声卡路由")
    commands.add_parser("voice-check", add_help=False, help="客观验证变声效果")
    commands.add_parser("preview", add_help=False, help="试听音色包参考音频")
    commands.add_parser("mic-test", add_help=False, help="测试麦克风输入和回放")
    commands.add_parser("mic-level", add_help=False, help="实时显示麦克风电平")
    commands.add_parser("doctor", add_help=False, help="检查运行环境")
    return parser


def build_device_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="列出 sounddevice 可见的音频设备。",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="安装了 sounddevice 的 Python 解释器",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args, remainder = build_parser().parse_known_args(argv)

    if args.command == "pack":
        return pack_cli.main(remainder, prog="panda pack")
    if args.command == "infer":
        return infer_cli.main(remainder, prog="panda infer")
    if args.command == "realtime":
        return realtime_cli.main(remainder, prog="panda realtime")
    if args.command == "simulate":
        return realtime_sim.main(remainder, prog="panda simulate")
    if args.command == "benchmark":
        return benchmark.main(remainder, prog="panda benchmark")
    if args.command == "devices":
        device_args = build_device_parser("panda devices").parse_args(remainder)
        return realtime_cli.print_devices(
            device_args.python,
            as_json=device_args.json,
        )
    if args.command == "route-check":
        return route_check.main(remainder, prog="panda route-check")
    if args.command == "voice-check":
        return voice_check.main(remainder, prog="panda voice-check")
    if args.command == "preview":
        return preview.main(remainder, prog="panda preview")
    if args.command == "mic-test":
        return mic_test.main(remainder, prog="panda mic-test")
    if args.command == "mic-level":
        return mic_level.main(remainder, prog="panda mic-level")
    if args.command == "doctor":
        return doctor.main(remainder, prog="panda doctor")

    raise AssertionError(f"unhandled command: {args.command}")
