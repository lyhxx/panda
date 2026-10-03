"""Objective check that conversion actually changes the speaker.

Listening is not available to an automated check, so this compares speaker
embeddings instead: after converting source audio into a target timbre, the
result should sit closer to the target than the source does. A control run
converts the source into its own timbre, which shows whether the measurement
can be trusted at all.

The inputs must be real speech. A pure tone produces meaningless embeddings --
the fixture used by the earlier tests was a 220 Hz sine, which is exactly how
this check came to exist.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


def cosine_similarity(left, right) -> float:
    """Cosine similarity of two vectors, using plain Python sequences."""
    if len(left) != len(right):
        raise ValueError("vectors must have the same length")
    if not left:
        raise ValueError("vectors must not be empty")

    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("vectors must not be zero")
    return dot / ((left_norm ** 0.5) * (right_norm ** 0.5))


def _embedding(extract, model, path: Path) -> list[float]:
    tensor = extract(model, str(path), device="cpu")
    return [float(value) for value in tensor.detach().numpy().reshape(-1)]


def verify_conversion(
    meanvc2_root: Path,
    source: Path,
    target: Path,
    *,
    work_dir: Path | None = None,
    model: str = "120ms",
) -> dict:
    """Convert source into target and report how the speaker moved."""
    from panda_infer.realtime_worker import load_meanvc2_runtime

    if not source.is_file():
        raise FileNotFoundError(f"源音频不存在：{source}")
    if not target.is_file():
        raise FileNotFoundError(f"目标音频不存在：{target}")

    runtime = load_meanvc2_runtime(meanvc2_root)
    # The upstream runtime resolves its own imports relative to its directory.
    from src.speaker import extract_embedding  # noqa: PLC0415

    scratch = Path(work_dir) if work_dir else Path(tempfile.mkdtemp())
    scratch.mkdir(parents=True, exist_ok=True)
    converted_path = scratch / "converted.wav"
    control_path = scratch / "control.wav"

    control_runner = runtime.VCRunner(
        target_wav=str(source),
        device="cpu",
        model=model,
    )
    control_runner.process_file(str(source), str(control_path), seed=42)
    extract = extract_embedding
    model_handle = control_runner.spk_model

    source_embedding = _embedding(extract, model_handle, source)
    control_embedding = _embedding(extract, model_handle, control_path)
    target_embedding = _embedding(extract, model_handle, target)

    runner = runtime.VCRunner(
        target_wav=str(target),
        device="cpu",
        model=model,
    )
    runner.process_file(str(source), str(converted_path), seed=42)
    converted_embedding = _embedding(extract, model_handle, converted_path)

    report = {
        "control_converted_vs_source": cosine_similarity(
            control_embedding,
            source_embedding,
        ),
        "source_vs_target": cosine_similarity(
            source_embedding,
            target_embedding,
        ),
        "converted_vs_target": cosine_similarity(
            converted_embedding,
            target_embedding,
        ),
        "converted_vs_source": cosine_similarity(
            converted_embedding,
            source_embedding,
        ),
        "converted_wav": str(converted_path),
    }
    report["moved_toward_target"] = (
        report["converted_vs_target"] > report["source_vs_target"]
    )
    return report


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="客观验证变声是否把说话人身份换成目标音色。",
    )
    parser.add_argument("--meanvc2-root", required=True, help="官方 MeanVC2 仓库")
    parser.add_argument("--source-wav", required=True, help="源说话人语音")
    parser.add_argument("--target-wav", required=True, help="目标音色参考语音")
    parser.add_argument("--work-dir", help="中间产物目录")
    parser.add_argument("--model", choices=("120ms", "40ms"), default="120ms")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    try:
        report = verify_conversion(
            Path(args.meanvc2_root).expanduser().resolve(),
            Path(args.source_wav).expanduser().resolve(),
            Path(args.target_wav).expanduser().resolve(),
            work_dir=(
                Path(args.work_dir).expanduser().resolve()
                if args.work_dir
                else None
            ),
            model=args.model,
        )
    except Exception as exception:  # noqa: BLE001 - reported to the user
        print(f"error: {exception}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "对照（源→自身）：转换后 vs 源 "
            f"{report['control_converted_vs_source']:+.4f}"
        )
        print(f"源 vs 目标      {report['source_vs_target']:+.4f}")
        print(f"转换后 vs 目标  {report['converted_vs_target']:+.4f}")
        print(f"转换后 vs 源    {report['converted_vs_source']:+.4f}")

    if not report["moved_toward_target"]:
        print("FAIL: 转换没有把说话人推向目标", file=sys.stderr)
        return 1
    if not args.json:
        print("OK: 说话人身份向目标移动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
