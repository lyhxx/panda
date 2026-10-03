"""Report whether converted audio can reach other applications.

Recording a voice changer is only half the problem: for Discord, a game, or an
OBS scene to hear it, Panda must render into a virtual audio device and the
other application must capture the matching end of that device. This command
finds those pairs and names both sides, instead of leaving the user to guess.
"""

from __future__ import annotations

import argparse
import sys

from panda_infer.doctor import find_route_pairs
from panda_infer.realtime_cli import query_devices, write_json_utf8


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="检查虚拟声卡路由，并给出两端应选择的设备。",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="安装了 sounddevice 的 Python 解释器",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)

    try:
        payload = query_devices(args.python)
    except RuntimeError as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 2

    pairs = find_route_pairs(
        list(payload.get("devices", [])),
        list(payload.get("hostapis", [])),
    )

    if args.json:
        write_json_utf8({"ok": bool(pairs), "routes": pairs})
        return 0 if pairs else 1

    if not pairs:
        print("[WARNING] 没有可用的虚拟声卡路由。")
        print(
            "          Panda 需要一块可以写入的虚拟声卡（例如 VB-CABLE），"
        )
        print(
            "          其它软件再从同一块声卡的采集端读取。安装后重新运行本命令。"
        )
        return 1

    print(f"[OK] 检测到 {len(pairs)} 条可用路由。")
    for index, pair in enumerate(pairs, start=1):
        print(f"  路由 {index}:")
        print(f"    Panda 的输出设备 → {pair['render']}")
        print(f"    其它软件的麦克风   → {pair['capture']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
