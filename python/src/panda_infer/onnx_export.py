"""Export MeanVC2 stages to ONNX.

Two stages are supported so far, and they need opposite exporters:

* the **vocoder** needs the dynamo exporter, because the legacy one cannot
  translate the complex tensors its iSTFT uses (``aten::complex``). Dynamo then
  emits ``ScatterND`` with int32 indices that ONNX Runtime rejects, so those are
  cast to int64 afterwards.
* the **ASR** needs the legacy exporter, because dynamo trips over the model's
  symbolic shape handling. The legacy path needs no graph surgery at all.

Both entry points are ``decode``/``forward`` mismatches that need a scripted
wrapper. Every export is verified against PyTorch before the command reports
success.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import onnx
    from onnx import TensorProto, helper
except ImportError:  # pragma: no cover - only needed when exporting
    onnx = None
    TensorProto = None
    helper = None

DEFAULT_OPSET = 17
DEFAULT_FRAMES = 32

# Mirrors MODEL_PATHS in the upstream run_rt.py.
ASR_VARIANTS = {
    "40ms": {
        "checkpoint": "preprocess/ckpts/fastu2pp_80ms.pt",
        "bn_window": 11,
        "required_cache_size": 4,
        "offset_init": 4,
    },
    "120ms": {
        "checkpoint": "preprocess/ckpts/fastu2pp_160ms.pt",
        "bn_window": 19,
        "required_cache_size": 8,
        "offset_init": 8,
    },
}

# Cache tensor shapes used by VCRunner._init_cache().
ATT_CACHE_SHAPE = (6, 4, 128)
CNN_CACHE_SHAPE = (6, 1, 256, 8)


def require_onnx():
    if onnx is None:
        raise RuntimeError("导出 ONNX 需要安装 onnx（pip install onnx onnxscript）")
    return onnx


def patch_scatter_indices(model) -> int:
    """Cast every ``ScatterND`` index input to int64, in topological order.

    ONNX Runtime requires int64 indices for ``ScatterND`` while the dynamo
    exporter emits int32. The cast node is inserted directly before its
    consumer: placing it anywhere else can break the graph's topological
    ordering, which made ONNX Runtime allocate tens of gigabytes before it
    gave up. Already-patched inputs are left alone, so this is idempotent.
    """
    require_onnx()

    graph = model.graph
    producers = {}
    for node in graph.node:
        for output in node.output:
            producers[output] = node

    rebuilt = []
    patched = 0
    for node in graph.node:
        if node.op_type != "ScatterND":
            rebuilt.append(node)
            continue

        indices = node.input[1]
        producer = producers.get(indices)
        if producer is not None and casts_to_int64(producer):
            # Already an int64 cast (for example from an earlier run).
            rebuilt.append(node)
            continue

        cast_name = f"{indices}_as_int64"
        cast = helper.make_node(
            "Cast",
            [indices],
            [cast_name],
            to=TensorProto.INT64,
        )
        rebuilt.append(cast)
        producers[cast_name] = cast
        patched += 1
        node.input[1] = cast_name
        rebuilt.append(node)

    del graph.node[:]
    graph.node.extend(rebuilt)
    return patched


def casts_to_int64(node) -> bool:
    if node.op_type != "Cast":
        return False
    for attribute in node.attribute:
        if attribute.name == "to":
            return attribute.i == TensorProto.INT64
    return False


def build_wrapper(vocoder):
    """Wrap a TorchScript vocoder so it exposes ``forward``."""
    import torch

    class _VocoderWrapper(torch.nn.Module):
        def __init__(self, inner):
            super().__init__()
            self.inner = inner

        def forward(self, mel):
            return self.inner.decode(mel)

    return torch.jit.script(_VocoderWrapper(vocoder).eval())


def build_asr_wrapper(asr):
    """Wrap the streaming ASR so it exposes ``forward`` with named inputs."""
    import torch

    class _AsrWrapper(torch.nn.Module):
        def __init__(self, inner):
            super().__init__()
            self.inner = inner

        def forward(self, fbank, offset, cache_size, att_cache, cnn_cache):
            output, new_att, new_cnn = self.inner(
                fbank, offset, cache_size, att_cache, cnn_cache
            )
            return output, new_att, new_cnn

    return torch.jit.script(_AsrWrapper(asr).eval())


def asr_inputs(variant: str):
    """Build the dummy inputs the streaming loop actually produces."""
    import torch

    if variant not in ASR_VARIANTS:
        raise ValueError(f"unknown ASR variant: {variant}")
    settings = ASR_VARIANTS[variant]
    window = settings["bn_window"]
    cache_size = settings["required_cache_size"]
    att_shape = ATT_CACHE_SHAPE[:2] + (cache_size,) + ATT_CACHE_SHAPE[2:]

    return {
        "fbank": torch.rand(1, window, 80),
        # The offset must be at least the cache size: the model slices the
        # attention cache by it, and a smaller value yields an empty slice.
        "offset": torch.tensor(settings["offset_init"], dtype=torch.int64),
        "cache_size": torch.tensor(cache_size, dtype=torch.int64),
        "att_cache": torch.zeros(*att_shape),
        "cnn_cache": torch.zeros(*CNN_CACHE_SHAPE),
    }


def export_asr(
    meanvc2_root: Path,
    output_path: Path,
    *,
    variant: str = "40ms",
    opset: int = DEFAULT_OPSET,
) -> dict:
    """Export the streaming ASR and verify it against TorchScript.

    The legacy exporter is used on purpose: the dynamo exporter fails on this
    model's symbolic shape handling, while the legacy one handles it cleanly.
    That is the opposite of the vocoder, which needs dynamo.
    """
    require_onnx()
    import numpy as np
    import torch

    settings = ASR_VARIANTS[variant]
    checkpoint = meanvc2_root / settings["checkpoint"]
    if not checkpoint.is_file():
        raise FileNotFoundError(f"没有找到 ASR 检查点：{checkpoint}")

    asr = torch.jit.load(str(checkpoint)).eval()
    wrapper = build_asr_wrapper(asr)
    inputs = asr_inputs(variant)
    args = (
        inputs["fbank"],
        inputs["offset"],
        inputs["cache_size"],
        inputs["att_cache"],
        inputs["cnn_cache"],
    )
    with torch.no_grad():
        reference = wrapper(*args)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        wrapper,
        args,
        str(output_path),
        input_names=["fbank", "offset", "cache_size", "att_cache", "cnn_cache"],
        output_names=["bn", "new_att_cache", "new_cnn_cache"],
        opset_version=opset,
        dynamo=False,
    )

    model = onnx.load(str(output_path))
    patched = patch_scatter_indices(model)
    if patched:
        onnx.save(model, str(output_path))

    import onnxruntime as ort

    ort.set_default_logger_severity(3)
    session = ort.InferenceSession(
        str(output_path),
        providers=["CPUExecutionProvider"],
    )
    feeds = {name: value.numpy() for name, value in inputs.items()}
    produced = session.run(None, feeds)

    worst = 0.0
    for index, (got, expected) in enumerate(zip(produced, reference)):
        expected_np = expected.detach().numpy()
        if got.shape != expected_np.shape:
            raise RuntimeError(
                f"输出 {index} 形状不一致：{got.shape} vs {expected_np.shape}"
            )
        peak = max(float(np.max(np.abs(expected_np))), 1e-9)
        worst = max(
            worst,
            float(np.max(np.abs(got - expected_np))) / peak,
        )

    if worst > 1e-3:
        raise RuntimeError(f"ONNX 输出与 PyTorch 偏差过大：{worst:.3e}")

    return {
        "stage": "asr",
        "output": str(output_path),
        "variant": variant,
        "opset": opset,
        "nodes": len(model.graph.node),
        "patched_scatter_nodes": patched,
        "relative_difference": worst,
    }


def export_vocoder(
    vocoder_path: Path,
    output_path: Path,
    *,
    opset: int = DEFAULT_OPSET,
    frames: int = DEFAULT_FRAMES,
) -> dict:
    """Export and verify; returns a report dict."""
    require_onnx()
    import numpy as np
    import torch

    vocoder = torch.jit.load(str(vocoder_path)).eval()
    wrapper = build_wrapper(vocoder)

    # run_rt.py feeds [1, 80, T] mel frames already mapped into [0, 1].
    dummy = torch.rand(1, 80, frames)
    with torch.no_grad():
        reference = wrapper(dummy).detach().numpy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        wrapper,
        (dummy,),
        str(output_path),
        input_names=["mel"],
        output_names=["wav"],
        dynamic_axes={"mel": {2: "frames"}, "wav": {2: "samples"}},
        opset_version=opset,
        dynamo=True,
    )

    model = onnx.load(str(output_path))
    patched = patch_scatter_indices(model)
    onnx.save(model, str(output_path))

    try:
        import onnxruntime as ort
    except ImportError as exception:
        raise RuntimeError(
            "校验导出结果需要 onnxruntime（pip install onnxruntime）"
        ) from exception

    ort.set_default_logger_severity(3)
    session = ort.InferenceSession(
        str(output_path),
        providers=["CPUExecutionProvider"],
    )
    produced = session.run(["wav"], {"mel": dummy.numpy()})[0]

    if produced.shape != reference.shape:
        raise RuntimeError(
            f"ONNX 输出形状不一致：{produced.shape} vs {reference.shape}"
        )

    difference = float(np.max(np.abs(produced - reference)))
    peak = max(float(np.max(np.abs(reference))), 1e-9)
    relative = difference / peak
    if relative > 1e-3:
        raise RuntimeError(f"ONNX 输出与 PyTorch 偏差过大：{relative:.3e}")

    return {
        "output": str(output_path),
        "opset": opset,
        "frames": frames,
        "nodes": len(model.graph.node),
        "patched_scatter_nodes": patched,
        "output_samples": int(produced.shape[-1]),
        "max_abs_difference": difference,
        "relative_difference": relative,
    }


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="把 MeanVC2 的声码器导出成 ONNX 并校验数值一致性。",
    )
    parser.add_argument("--meanvc2-root", required=True, help="官方 MeanVC2 仓库")
    parser.add_argument("--output", required=True, help="输出 .onnx 路径")
    parser.add_argument(
        "--stage",
        choices=("vocoder", "asr"),
        default="vocoder",
        help="要导出的阶段",
    )
    parser.add_argument(
        "--model",
        choices=tuple(ASR_VARIANTS),
        default="40ms",
        help="ASR 变体，仅 --stage asr 有效",
    )
    parser.add_argument("--opset", type=int, default=DEFAULT_OPSET)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    root = Path(args.meanvc2_root).expanduser().resolve()
    if args.frames <= 0:
        print("error: --frames must be positive", file=sys.stderr)
        return 2

    try:
        output = Path(args.output).expanduser().resolve()
        if args.stage == "asr":
            report = export_asr(
                root,
                output,
                variant=args.model,
                opset=args.opset,
            )
        else:
            vocoder_path = root / "ckpts" / "vocos" / "vocos.pt"
            if not vocoder_path.is_file():
                print(
                    f"error: 没有找到声码器：{vocoder_path}",
                    file=sys.stderr,
                )
                return 2
            report = export_vocoder(
                vocoder_path,
                output,
                opset=args.opset,
                frames=args.frames,
            )
    except Exception as exception:  # noqa: BLE001 - reported to the user
        print(f"error: {exception}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"导出完成：{report['output']}")
        print(f"opset {report['opset']}，{report['nodes']} 个节点"
              f"（修正 {report['patched_scatter_nodes']} 处 ScatterND 索引）")
        print(f"与 PyTorch 相对偏差 {report['relative_difference']:.3e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
