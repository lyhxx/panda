from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import wave
from pathlib import Path

from panda_infer.cli import resolve_reference_from_pack
from panda_infer.realtime_worker import load_meanvc2_runtime


def summarize_latencies(
    durations_ms: list[float],
    chunk_ms: float,
) -> dict[str, float | int]:
    if not durations_ms:
        raise ValueError("at least one latency sample is required")
    if chunk_ms <= 0:
        raise ValueError("chunk_ms must be positive")

    ordered = sorted(durations_ms)
    def percentile(ratio: float) -> float:
        index = min(
            len(ordered) - 1,
            max(0, math.ceil(len(ordered) * ratio) - 1),
        )
        return ordered[index]

    mean_ms = statistics.fmean(ordered)
    return {
        "samples": len(ordered),
        "mean_ms": mean_ms,
        "p50_ms": statistics.median(ordered),
        "p90_ms": percentile(0.90),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "max_ms": ordered[-1],
        "chunk_ms": chunk_ms,
        "realtime_factor": mean_ms / chunk_ms,
        "overruns": sum(value > chunk_ms for value in ordered),
    }


def load_wav_16k_mono(path: Path):
    import numpy as np

    with wave.open(str(path), "rb") as audio:
        if audio.getframerate() != 16000:
            raise ValueError("benchmark input must be 16 kHz")
        if audio.getnchannels() != 1:
            raise ValueError("benchmark input must be mono")
        if audio.getsampwidth() != 2:
            raise ValueError("benchmark input must be 16-bit PCM")
        frames = audio.readframes(audio.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    return samples


def resolve_target(args: argparse.Namespace) -> Path:
    if args.voice_pack:
        return resolve_reference_from_pack(Path(args.voice_pack))
    target = Path(args.target_wav).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"目标音频不存在：{target}")
    return target


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="用预录音频测量 MeanVC2 实时分块处理性能。",
    )
    parser.add_argument("--meanvc2-root", required=True, help="官方 MeanVC2 仓库")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--voice-pack", help="已安装的 Panda 音色包目录")
    target.add_argument("--target-wav", help="目标说话人参考 WAV")
    parser.add_argument("--source-wav", required=True, help="16 kHz 单声道源 WAV")
    parser.add_argument("--model", choices=("120ms", "40ms"), default="120ms")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--threads",
        type=int,
        help="torch CPU 线程数；默认沿用运行时设置（官方为 1，实测单线程最快）",
    )
    parser.add_argument("--warmup-chunks", type=int, default=3)
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    root = Path(args.meanvc2_root).expanduser().resolve()
    target = resolve_target(args)
    source = Path(args.source_wav).expanduser().resolve()
    if not source.is_file():
        return _error(f"源音频不存在：{source}")
    if args.warmup_chunks < 0:
        return _error("--warmup-chunks must not be negative")
    if args.max_chunks is not None and args.max_chunks <= 0:
        return _error("--max-chunks must be positive")
    if args.threads is not None and args.threads <= 0:
        return _error("--threads must be positive")

    try:
        import numpy as np
        import torch

        samples = load_wav_16k_mono(source)
        runtime = load_meanvc2_runtime(root)
        init_started = time.perf_counter()
        runner = runtime.VCRunner(
            target_wav=str(target),
            device=args.device,
            model=args.model,
        )
        init_seconds = time.perf_counter() - init_started
        if args.threads is not None:
            torch.set_num_threads(args.threads)
        threads = int(torch.get_num_threads())

        chunk_size = int(runner.CHUNK)
        warmup = np.zeros(chunk_size, dtype=np.float32)
        for _ in range(args.warmup_chunks):
            runner.process_chunk(warmup)
        runner._init_cache()

        durations_ms = []
        chunk_count = math.ceil(len(samples) / chunk_size)
        if args.max_chunks is not None:
            chunk_count = min(chunk_count, args.max_chunks)
        for index in range(chunk_count):
            start = index * chunk_size
            chunk = samples[start:start + chunk_size]
            if len(chunk) < chunk_size:
                chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
            started = time.perf_counter()
            runner.process_chunk(chunk)
            durations_ms.append((time.perf_counter() - started) * 1000.0)

        summary = summarize_latencies(
            durations_ms,
            chunk_size / 16.0,
        )
        summary["init_seconds"] = init_seconds
        summary["threads"] = threads
    except Exception as exception:
        return _error(str(exception))

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"samples: {summary['samples']}")
        print(f"chunk: {summary['chunk_ms']:.1f} ms")
        print(f"mean: {summary['mean_ms']:.1f} ms")
        print(f"p50: {summary['p50_ms']:.1f} ms")
        print(f"p90: {summary['p90_ms']:.1f} ms")
        print(f"p95: {summary['p95_ms']:.1f} ms")
        print(f"p99: {summary['p99_ms']:.1f} ms")
        print(f"max: {summary['max_ms']:.1f} ms")
        print(f"RTF: {summary['realtime_factor']:.3f}")
        print(f"overruns: {summary['overruns']}/{summary['samples']}")
        print(f"threads: {summary['threads']}")
        print(f"init: {summary['init_seconds']:.2f} s")
    return 0


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
