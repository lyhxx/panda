from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from panda_infer.cli import resolve_reference_from_pack


VIRTUAL_AUDIO_MARKERS = (
    "vb-audio",
    "voicemeeter",
    "virtual audio",
    "virtual cable",
    "cable input",
    "vac ",
    "baomiao",
    "bao miao",
    "virtual microphone",
    "虚拟声卡",
    "虚拟麦克风",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def is_virtual_audio_device(name: str) -> bool:
    normalized = name.casefold()
    return any(marker in normalized for marker in VIRTUAL_AUDIO_MARKERS)


def _find_virtual_devices(
    devices: list[dict],
    hostapis: list[str],
    channel_key: str,
) -> list[str]:
    results = []
    for device in devices:
        if int(device.get(channel_key, 0)) <= 0:
            continue
        name = str(device.get("name", ""))
        if not is_virtual_audio_device(name):
            continue
        hostapi_index = int(device.get("hostapi", -1))
        hostapi = (
            hostapis[hostapi_index]
            if 0 <= hostapi_index < len(hostapis)
            else "unknown"
        )
        results.append(f"#{device.get('index', '?')} {name} · {hostapi}")
    return results


def find_virtual_outputs(
    devices: list[dict],
    hostapis: list[str],
) -> list[str]:
    """Virtual devices a converter can render into (the writable side)."""
    return _find_virtual_devices(devices, hostapis, "max_output_channels")


def find_virtual_inputs(
    devices: list[dict],
    hostapis: list[str],
) -> list[str]:
    """Virtual capture devices other applications can read from.

    A device like the BaoMiao Virtual Microphone appears here. Such a device
    only proves that *something* publishes a microphone; without a matching
    writable endpoint Panda cannot feed it.
    """
    return _find_virtual_devices(devices, hostapis, "max_input_channels")


def describe_virtual_routing(
    virtual_outputs: list[str],
    virtual_inputs: list[str],
) -> str:
    """Explain what the detected virtual devices can and cannot do."""
    if virtual_outputs:
        return "; ".join(virtual_outputs)
    if virtual_inputs:
        return (
            "检测到虚拟采集设备（"
            + "; ".join(virtual_inputs)
            + "），但它只提供采集端，无法写入。"
            "要像商业变声器那样把变声结果送进其它软件，"
            "需要先安装 VB-CABLE 等虚拟声卡，或由 Panda 自带驱动提供。"
        )
    return (
        "未检测到虚拟播放设备；安装 VB-CABLE 等虚拟声卡后才能把"
        "变声结果路由给其它软件。"
    )


def counterpart_name(name: str) -> str | None:
    """Swap the Input/Output role token of a virtual device name.

    VB-CABLE and VoiceMeeter each expose a render endpoint named ``... Input``
    and a capture endpoint named ``... Output``. A converter renders into the
    Input end, and other applications then select the Output end as their
    microphone, so the two names differ by exactly that token.
    """
    lowered = name.casefold()
    for source, target in (("input", "output"), ("output", "input")):
        index = lowered.find(source)
        if index < 0:
            continue

        before = lowered[index - 1] if index > 0 else " "
        end = index + len(source)
        after = lowered[end] if end < len(lowered) else " "
        if before.isalnum() or after.isalnum():
            continue

        token = name[index:end]
        replacement = target.capitalize() if token[:1].isupper() else target
        return name[:index] + replacement + name[end:]
    return None


def _describe_device(device: dict, hostapis: list[str]) -> str:
    hostapi_index = int(device.get("hostapi", -1))
    hostapi = (
        hostapis[hostapi_index]
        if 0 <= hostapi_index < len(hostapis)
        else "unknown"
    )
    return f"#{device.get('index', '?')} {device.get('name', '')} · {hostapi}"


def find_route_pairs(
    devices: list[dict],
    hostapis: list[str],
) -> list[dict]:
    """Pair every writable virtual endpoint with its capture counterpart.

    Returns one entry per usable route, naming the device Panda should
    render into and the device other applications should select as a
    microphone.
    """
    captures: dict[str, dict] = {}
    for device in devices:
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        name = str(device.get("name", ""))
        if not is_virtual_audio_device(name):
            continue
        captures.setdefault(name.casefold(), device)

    pairs = []
    for device in devices:
        if int(device.get("max_output_channels", 0)) <= 0:
            continue
        name = str(device.get("name", ""))
        if not is_virtual_audio_device(name):
            continue

        counterpart = counterpart_name(name)
        if counterpart is None:
            continue
        capture = captures.get(counterpart.casefold())
        if capture is None:
            continue

        pairs.append(
            {
                "render_index": int(device.get("index", -1)),
                "render": _describe_device(device, hostapis),
                "capture_index": int(capture.get("index", -1)),
                "capture": _describe_device(capture, hostapis),
            }
        )
    return pairs


def check_meanvc2(root: Path) -> list[CheckResult]:
    resolved = root.expanduser().resolve()
    required = {
        "runtime": Path("runtime/run_rt.py"),
        "vocoder": Path("ckpts/vocos/vocos.pt"),
        "speaker model": Path("preprocess/ckpts/wavlm_large_finetune.pth"),
        "speaker config": Path("preprocess/ckpts/wavlm_large_cfg.pt"),
        # Both variants: 120ms is the default and 40ms stays selectable.
        "120ms ASR": Path("preprocess/ckpts/fastu2pp_160ms.pt"),
        "120ms voice model": Path(
            "ckpts/pretrained_models/meanvc2_120ms_40ms.safetensors"
        ),
        "40ms ASR": Path("preprocess/ckpts/fastu2pp_80ms.pt"),
        "40ms voice model": Path(
            "ckpts/pretrained_models/meanvc2_40ms_40ms.safetensors"
        ),
    }

    results = []
    for name, relative in required.items():
        path = resolved / relative
        results.append(
            CheckResult(
                name=f"meanvc2:{name}",
                status="ok" if path.is_file() else "error",
                detail=str(path),
            )
        )
    return results


def check_deepfilter(root: Path) -> list[CheckResult]:
    """Check the optional DeepFilterNet checkpoint shipped in a package."""
    resolved = root.expanduser().resolve()
    required = {
        "config": Path("config.ini"),
        "checkpoint": Path("checkpoints/model_120.ckpt.best"),
    }
    results = []
    for name, relative in required.items():
        path = resolved / relative
        results.append(
            CheckResult(
                name=f"deepfilter:{name}",
                status="ok" if path.is_file() else "error",
                detail=str(path),
            )
        )
    return results


def check_voice_pack(pack: Path) -> list[CheckResult]:
    try:
        reference = resolve_reference_from_pack(pack)
    except Exception as exception:
        return [
            CheckResult(
                name="voice-pack",
                status="error",
                detail=str(exception),
            )
        ]
    return [
        CheckResult(
            name="voice-pack",
            status="ok",
            detail=str(reference),
        )
    ]


def check_python(python_executable: str) -> list[CheckResult]:
    script = """
import importlib.util
import json

modules = ["numpy", "torch", "torchaudio", "sounddevice", "safetensors"]
result = {"modules": {name: importlib.util.find_spec(name) is not None
                      for name in modules}}
try:
    import sounddevice as sd
    devices = list(sd.query_devices())
    result["devices"] = [
        {
            "index": index,
            "name": device["name"],
            "hostapi": device["hostapi"],
            "max_input_channels": device["max_input_channels"],
            "max_output_channels": device["max_output_channels"],
        }
        for index, device in enumerate(devices)
    ]
    result["hostapis"] = [api["name"] for api in sd.query_hostapis()]
    result["device_count"] = len(devices)
except Exception as exception:
    result["error"] = str(exception)
print(json.dumps(result))
"""
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [
            str(Path(python_executable).expanduser().resolve()),
            "-c",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit code {completed.returncode}"
        return [CheckResult(name="python", status="error", detail=detail)]

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exception:
        return [
            CheckResult(
                name="python",
                status="error",
                detail=f"invalid probe output: {exception}",
            )
        ]

    results = []
    for name, available in payload.get("modules", {}).items():
        results.append(
            CheckResult(
                name=f"python:{name}",
                status="ok" if available else "error",
                detail="available" if available else "missing",
            )
        )
    if "error" in payload:
        results.append(
            CheckResult(
                name="audio-devices",
                status="error",
                detail=str(payload["error"]),
            )
        )
    else:
        device_count = int(payload.get("device_count", 0))
        results.append(
            CheckResult(
                name="audio-devices",
                status="ok" if device_count > 0 else "warning",
                detail=f"{device_count} device(s)",
            )
        )
        virtual_outputs = find_virtual_outputs(
            list(payload.get("devices", [])),
            list(payload.get("hostapis", [])),
        )
        virtual_inputs = find_virtual_inputs(
            list(payload.get("devices", [])),
            list(payload.get("hostapis", [])),
        )
        virtual_detail = describe_virtual_routing(virtual_outputs, virtual_inputs)
        results.append(
            CheckResult(
                name="virtual-output",
                status="ok" if virtual_outputs else "warning",
                detail=virtual_detail,
            )
        )
    return results


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="检查 Panda 运行环境、模型资产和音色包。",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="需要检查的 Python 解释器",
    )
    parser.add_argument("--meanvc2-root", help="官方 MeanVC2 仓库")
    parser.add_argument("--deepfilter-root", help="DeepFilterNet 检查点目录")
    parser.add_argument("--voice-pack", help="已安装的 Panda 音色包")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    checks = check_python(args.python)
    if args.meanvc2_root:
        checks += check_meanvc2(Path(args.meanvc2_root))
    if args.deepfilter_root:
        checks += check_deepfilter(Path(args.deepfilter_root))
    if args.voice_pack:
        checks += check_voice_pack(Path(args.voice_pack))

    ok = not any(check.status == "error" for check in checks)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "checks": [asdict(check) for check in checks],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for check in checks:
            print(f"[{check.status.upper()}] {check.name}: {check.detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
