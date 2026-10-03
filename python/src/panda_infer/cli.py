from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def resolve_reference_from_pack(pack_path: Path) -> Path:
    pack = pack_path.expanduser().resolve()
    manifest_path = pack / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"音色包缺少 manifest.json：{pack}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("format") != "panda.voice-pack":
        raise ValueError("不是 Panda 音色包")
    if manifest.get("engine") != "meanvc2":
        raise ValueError("当前推理工具只支持 MeanVC2 音色包")

    references = []
    for item in manifest.get("files", []):
        relative = str(item.get("path", ""))
        if relative.lower().endswith(".wav") and relative.startswith("reference/"):
            candidate = (pack / relative).resolve()
            if pack not in candidate.parents:
                raise ValueError("音色包包含越界参考路径")
            references.append(candidate)

    if not references:
        raise FileNotFoundError(
            "音色包没有 reference/*.wav，请使用 --target-wav 指定目标音频"
        )
    if not references[0].is_file():
        raise FileNotFoundError(f"参考音频不存在：{references[0]}")
    return references[0]


def build_runtime_command(args: argparse.Namespace) -> list[str]:
    root = Path(args.meanvc2_root).expanduser().resolve()
    runtime = root / "runtime" / "run_rt.py"
    if not runtime.is_file():
        raise FileNotFoundError(f"没有找到官方 MeanVC2 runtime：{runtime}")

    if args.voice_pack:
        target_wav = resolve_reference_from_pack(Path(args.voice_pack))
    else:
        target_wav = Path(args.target_wav).expanduser().resolve()
        if not target_wav.is_file():
            raise FileNotFoundError(f"目标音频不存在：{target_wav}")

    source_wav = Path(args.source_wav).expanduser().resolve()
    if not source_wav.is_file():
        raise FileNotFoundError(f"源音频不存在：{source_wav}")

    output_wav = Path(args.output_wav).expanduser().resolve()
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    return [
        str(Path(args.python).expanduser().resolve()),
        str(runtime),
        "--mode",
        "file",
        "--input",
        str(source_wav),
        "--target-spk",
        str(target_wav),
        "--output",
        str(output_wav),
        "--model",
        args.model,
        "--device",
        args.device,
        "--seed",
        str(args.seed),
    ]


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="使用官方 MeanVC2 runtime 对 WAV 执行离线变声。"
    )
    parser.add_argument("--meanvc2-root", required=True, help="官方 MeanVC2 仓库")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="安装了 MeanVC2 依赖的 Python 解释器",
    )
    parser.add_argument("--source-wav", required=True, help="待转换的源 WAV")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--voice-pack", help="已安装的 Panda 音色包目录")
    target.add_argument("--target-wav", help="目标说话人参考 WAV")
    parser.add_argument("--output-wav", required=True, help="输出 WAV")
    parser.add_argument("--model", choices=("120ms", "40ms"), default="120ms")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--seed", type=int, default=666)
    parser.add_argument("--dry-run", action="store_true", help="只打印命令，不执行")
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    try:
        command = build_runtime_command(args)
    except Exception as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(subprocess.list2cmdline(command))
        return 0

    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

