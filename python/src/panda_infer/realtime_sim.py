"""Offline simulation of the realtime pipeline.

This drives the exact runtime path used for live conversion -- worker thread,
input queue, jitter buffer, playback cadence -- but replaces the audio device
with a WAV file. It needs no microphone and no virtual cable, so the pipeline
can be verified end to end on any machine.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

from panda_infer.benchmark import load_wav_16k_mono
from panda_infer.cli import resolve_reference_from_pack
from panda_infer.realtime_session import ConversionSession, drive_offline
from panda_infer.realtime_worker import (
    WARMUP_CHUNKS,
    copy_captured,
    load_meanvc2_runtime,
    warm_up_runner,
)


def resolve_target(args: argparse.Namespace) -> Path:
    if args.voice_pack:
        return resolve_reference_from_pack(Path(args.voice_pack))
    target = Path(args.target_wav).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"目标音频不存在：{target}")
    return target


def write_wav_16k_mono(path: Path, samples) -> None:
    import numpy as np

    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(pcm.tobytes())


def wait_for_worker(
    session: ConversionSession,
    *,
    timeout: float = 30.0,
    sleep=time.sleep,
    clock=time.perf_counter,
) -> bool:
    """Block until every submitted block has been converted."""
    deadline = clock() + timeout
    while clock() < deadline:
        if session.pending_input == 0 and session.idle:
            return True
        sleep(0.01)
    return False


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="用 WAV 文件模拟实时音频设备，端到端验证变声管线。",
    )
    parser.add_argument("--meanvc2-root", required=True, help="官方 MeanVC2 仓库")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--voice-pack", help="已安装的 Panda 音色包目录")
    target.add_argument("--target-wav", help="目标说话人参考 WAV")
    parser.add_argument("--source-wav", required=True, help="16 kHz 单声道源 WAV")
    parser.add_argument("--output-wav", required=True, help="转换结果输出路径")
    parser.add_argument("--model", choices=("120ms", "40ms"), default="120ms")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--threads",
        type=int,
        help="torch CPU 线程数；默认沿用运行时设置（官方为 1）",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="源音频重复遍数，用来拉长仿真时间",
    )
    parser.add_argument(
        "--warmup-chunks",
        type=int,
        default=WARMUP_CHUNKS,
        help="播放前用静音预热推理的次数（避免第一块冷启动超时）",
    )
    parser.add_argument(
        "--prefill-chunks",
        type=int,
        default=1,
        help="播放前预滚的块数，直接决定额外启动延迟",
    )
    parser.add_argument(
        "--max-backlog-chunks",
        type=int,
        default=6,
        help="抖动缓冲上限（块），防止延迟无界增长",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="不按实时节奏等待，尽快跑完（用于自动化检查）",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    root = Path(args.meanvc2_root).expanduser().resolve()
    source = Path(args.source_wav).expanduser().resolve()
    if not source.is_file():
        return _error(f"源音频不存在：{source}")
    if args.repeat < 1:
        return _error("--repeat must be at least 1")
    if args.warmup_chunks < 0:
        return _error("--warmup-chunks must not be negative")
    if args.prefill_chunks < 0:
        return _error("--prefill-chunks must not be negative")
    if args.max_backlog_chunks <= args.prefill_chunks:
        return _error("--max-backlog-chunks must exceed --prefill-chunks")
    if args.threads is not None and args.threads <= 0:
        return _error("--threads must be positive")

    try:
        import numpy as np
        import torch

        target = resolve_target(args)
        samples = load_wav_16k_mono(source)
        if args.repeat > 1:
            samples = np.tile(samples, args.repeat)

        runtime = load_meanvc2_runtime(root)
        runner = runtime.VCRunner(
            target_wav=str(target),
            device=args.device,
            model=args.model,
        )
        if args.threads is not None:
            torch.set_num_threads(args.threads)
        threads = int(torch.get_num_threads())

        chunk_size = int(runner.CHUNK)
        warm_up_runner(runner, args.warmup_chunks)

        # Same contract as the live capture path: submit_input promises a
        # copy, and ascontiguousarray returns the input untouched when it
        # already is contiguous float32 (which load_wav_16k_mono guarantees),
        # so the queued block would alias the caller's buffer.
        session = ConversionSession(
            runner.process_chunk,
            chunk_size,
            prefill_chunks=args.prefill_chunks,
            max_backlog_chunks=args.max_backlog_chunks,
            copy_input=copy_captured,
        )

        started = time.perf_counter()
        with session:
            converted = drive_offline(
                session,
                samples,
                realtime=not args.fast,
            )
            waited = wait_for_worker(session)
            converted.extend(session.drain_output())
        elapsed = time.perf_counter() - started
        failure = session.last_error
        if failure is not None:
            raise failure
        if not waited:
            return _error("转换线程在超时前没有处理完所有输入")

        output_path = Path(args.output_wav).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_wav_16k_mono(output_path, converted)
        stats = session.stats()
    except Exception as exception:
        return _error(str(exception))

    source_seconds = len(samples) / 16000.0
    report = {
        **stats,
        "threads": threads,
        "warmup_chunks": args.warmup_chunks,
        "prefill_chunks": args.prefill_chunks,
        "max_backlog_chunks": args.max_backlog_chunks,
        "source_seconds": source_seconds,
        "output_seconds": len(converted) / 16000.0,
        "wall_seconds": elapsed,
        "realtime_factor": elapsed / source_seconds if source_seconds else 0.0,
        "output_wav": str(output_path),
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"source: {report['source_seconds']:.2f} s")
        print(f"output: {report['output_seconds']:.2f} s -> {report['output_wav']}")
        print(f"wall: {report['wall_seconds']:.2f} s")
        print(f"converted blocks: {report['processed_chunks']}"
              f" (empty {report['empty_conversions']})")
        print(f"process time: mean {report['mean_process_ms']:.1f} ms,"
              f" max {report['max_process_ms']:.1f} ms")
        print(f"buffer depth at end: {report['buffer_depth_ms']:.1f} ms")
        print(f"prefill silence: {report['prefill_reads']} reads"
              f" ({report['prefill_frames']} frames)")
        print(f"starved reads: {report['starved_reads']}")
        print(f"underrun: {report['buffer_underrun_frames']} frames")
        print(f"dropped input blocks: {report['input_dropped_chunks']}")
        print(f"dropped buffered frames: {report['buffer_dropped_frames']}")
        print(f"threads: {report['threads']}")
    return 0


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
