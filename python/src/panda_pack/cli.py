from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 1
PACK_FORMAT = "panda.voice-pack"
DEFAULT_VERSION = "1.0.0"
REFERENCE_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_id(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if not value:
        raise ValueError("id 不能为空，且必须包含小写字母或数字")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wav_metadata(path: Path) -> dict[str, object]:
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return {
                "channels": wav.getnchannels(),
                "sample_width": wav.getsampwidth(),
                "sample_rate": rate,
                "frames": frames,
                "duration_sec": round(frames / rate, 6) if rate else None,
            }
    except Exception:
        return {"format": "unknown"}


def ensure_empty_or_overwrite(path: Path, overwrite: bool) -> None:
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"输出目录已存在：{path}；如需覆盖请添加 --overwrite")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_references(audio_paths: Iterable[Path], root: Path) -> list[dict[str, object]]:
    ref_dir = root / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    used: set[str] = set()
    for index, audio in enumerate(audio_paths, 1):
        audio = audio.expanduser().resolve()
        if not audio.is_file():
            raise FileNotFoundError(f"参考音频不存在：{audio}")
        suffix = audio.suffix.lower()
        if suffix not in REFERENCE_SUFFIXES:
            raise ValueError(
                f"不支持的参考音频格式：{audio}；"
                "请使用 WAV、MP3、FLAC、OGG、M4A、AAC 或 WMA"
            )
        name = "reference.wav" if index == 1 else f"reference-{index}.wav"
        target = ref_dir / name
        if target.name in used:
            raise ValueError(f"重复文件名：{target.name}")
        used.add(target.name)
        write_reference_wav(audio, target)
        record: dict[str, object] = {
            "path": target.relative_to(root).as_posix(),
            "sha256": sha256_file(target),
            "source_name": audio.name,
        }
        record.update(wav_metadata(target))
        records.append(record)
    return records


def write_reference_wav(source: Path, target: Path) -> None:
    """Decode a common audio file and write the canonical 16 kHz mono WAV."""
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exception:
        raise RuntimeError(
            "转换 MP3/FLAC 等参考音频需要 soundfile 和 numpy"
        ) from exception

    try:
        samples, sample_rate = sf.read(
            str(source),
            always_2d=True,
            dtype="float32",
        )
    except Exception as exception:
        raise ValueError(f"无法解码参考音频：{source}") from exception

    if samples.size == 0:
        raise ValueError(f"参考音频没有采样：{source}")
    mono = samples.mean(axis=1)
    if sample_rate != 16000:
        try:
            from math import gcd

            from scipy.signal import resample_poly
        except ImportError as exception:
            raise RuntimeError(
                "参考音频需要重采样到 16 kHz，请安装 scipy"
            ) from exception
        divisor = gcd(int(sample_rate), 16000)
        mono = resample_poly(
            mono,
            16000 // divisor,
            int(sample_rate) // divisor,
        ).astype(np.float32)

    peak = float(np.max(np.abs(mono)))
    if peak > 0.99:
        mono = mono * (0.99 / peak)
    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(target), mono, 16000, subtype="PCM_16")


def run_meanvc2_extract(
    meanvc2_root: Path,
    python_exe: Path,
    audio_files: list[Path],
    destination: Path,
    device: str,
) -> None:
    root = meanvc2_root.expanduser().resolve()
    script = root / "preprocess" / "extract_spk_emb.py"
    if not script.is_file():
        raise FileNotFoundError(
            f"没有找到 MeanVC2 特征提取脚本：{script}。"
            "请用 --meanvc2-root 指向官方 MeanVC2 仓库。"
        )

    with tempfile.TemporaryDirectory(prefix="panda-spk-") as temp_name:
        temp = Path(temp_name)
        input_dir = temp / "input"
        output_dir = temp / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Extract from a canonical 16 kHz mono WAV, not the original file:
        # stereo or odd bit-depth inputs otherwise reach the model with the
        # wrong shape (its conv1d expects mono), which fails extraction.
        for index, audio in enumerate(audio_files, 1):
            write_reference_wav(
                Path(audio),
                input_dir / f"reference-{index:04d}.wav",
            )

        command = [
            str(python_exe),
            str(script),
            "--input_dir",
            str(input_dir),
            "--output_dir",
            str(output_dir),
            "--device",
            device,
        ]
        subprocess.run(command, cwd=str(root), check=True)

        features = sorted(output_dir.glob("*.npy"))
        if not features:
            raise RuntimeError("MeanVC2 没有生成 .npy 特征文件")

        destination.parent.mkdir(parents=True, exist_ok=True)
        if len(features) == 1:
            shutil.copy2(features[0], destination)
            return

        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("多段参考音频求平均需要 numpy，请安装 numpy") from exc

        arrays = [np.load(path) for path in features]
        first_shape = arrays[0].shape
        if any(item.shape != first_shape for item in arrays):
            raise RuntimeError("MeanVC2 生成的特征维度不一致，无法自动平均")
        merged = np.mean(np.stack(arrays, axis=0), axis=0)
        np.save(destination, merged)


def write_yaml(path: Path, pack_id: str, kind: str, has_local_dit: bool) -> None:
    dit = "assets/dit.safetensors" if has_local_dit else "common/mvc2/dit_base_vanilla.onnx"
    text = f"""schema_version: 1
name: mvc2_{pack_id}_rt
engine: meanvc2
kind: {kind}

mvc2:
  enabled: true
  encoder: common/mvc2/asr_160ms.onnx
  dit: {dit}
  vocoder: common/mvc2/vocos.onnx
  pitch: common/mvc2/fcpe.onnx
  assets_dir: assets
  coeff_dir: common/meanvc
  dit_vanilla: true
  vocoder_type: vocos
  mode: speech
  nfe: 3
"""
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_files(root: Path, exclude: set[Path]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path in exclude:
            continue
        items.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return items


def build_zip(root: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())


def normalize_icon(source: Path, target: Path, size: int = 256) -> None:
    """Convert any image into a circular PNG used as the gallery avatar.

    Qt cannot load WebP without an extra plugin, so the pack stores a plain
    PNG; baking the circular mask here keeps the client rendering trivial.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exception:
        raise RuntimeError(
            "生成图标需要 Pillow，请先安装：pip install pillow"
        ) from exception

    image = Image.open(source).convert("RGBA")
    width, height = image.size
    side = min(width, height)
    image = image.crop(
        (
            (width - side) // 2,
            (height - side) // 2,
            (width + side) // 2,
            (height + side) // 2,
        )
    ).resize((size, size), Image.LANCZOS)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(image, (0, 0), mask)
    target.parent.mkdir(parents=True, exist_ok=True)
    output.save(target, "PNG")


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="从参考音频或现有 spk_emb 生成 Panda 开放音色包。"
    )
    parser.add_argument("--name", required=True, help="展示名称，例如“曼波”")
    parser.add_argument(
        "--id",
        required=True,
        help="稳定 ID，只允许小写字母、数字和短横线",
    )
    parser.add_argument("--version", default=DEFAULT_VERSION, help="音色包版本")
    parser.add_argument(
        "--audio",
        action="append",
        required=True,
        help="参考音频（WAV/MP3/FLAC/OGG/M4A/AAC/WMA），可重复传入",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--feature-file", help="已有的 spk_emb.npy")
    source.add_argument("--meanvc2-root", help="官方 MeanVC2 仓库根目录")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="运行 MeanVC2 特征提取脚本的 Python 解释器",
    )
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"), help="特征提取设备")
    parser.add_argument("--output", help="输出目录；默认 dist/<id>")
    parser.add_argument(
        "--icon",
        help="可选头像图片（任意常见格式）；会转成圆形 PNG 存入 assets/icon.png",
    )
    parser.add_argument("--overwrite", action="store_true", help="覆盖现有输出目录")
    parser.add_argument("--no-zip", action="store_true", help="不生成 ZIP")
    parser.add_argument(
        "--license",
        default="No license metadata supplied.",
        help="写入 LICENSES.json 的资源说明",
    )
    return parser


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(argv)
    pack_id = safe_id(args.id)
    output = Path(args.output or Path("dist") / pack_id).expanduser().resolve()
    audio_paths = [Path(item) for item in args.audio]

    ensure_empty_or_overwrite(output, args.overwrite)
    references = copy_references(audio_paths, output)

    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    feature_destination = assets / "spk_emb.npy"

    if args.feature_file:
        feature_source = Path(args.feature_file).expanduser().resolve()
        if not feature_source.is_file():
            raise FileNotFoundError(f"特征文件不存在：{feature_source}")
        shutil.copy2(feature_source, feature_destination)
    else:
        run_meanvc2_extract(
            Path(args.meanvc2_root),
            Path(args.python),
            [path.expanduser().resolve() for path in audio_paths],
            feature_destination,
            args.device,
        )

    kind = "zero-shot"
    has_local_dit = False
    entry_name = f"mvc2_{pack_id}_rt.yaml"
    entry = output / entry_name
    write_yaml(entry, pack_id, kind, has_local_dit)

    register = {
        "schema_version": SCHEMA_VERSION,
        "id": pack_id,
        "name": args.name,
        "engine": "meanvc2",
        "kind": kind,
        "feature_type": "spk_emb",
        "feature_file": "spk_emb.npy",
        "references": references,
        "notes": "",
    }
    write_json(assets / "register.json", register)

    icon_rel = ""
    if args.icon:
        icon_source = Path(args.icon).expanduser().resolve()
        if not icon_source.is_file():
            raise FileNotFoundError(f"图标不存在：{icon_source}")
        normalize_icon(icon_source, assets / "icon.png")
        icon_rel = "assets/icon.png"

    write_json(
        output / "LICENSES.json",
        {
            "schema_version": 1,
            "voice_resources": args.license,
            "upstream": [
                {
                    "name": "MeanVC2",
                    "url": "https://github.com/ASLP-lab/MeanVC2",
                    "license": "Apache-2.0",
                }
            ],
        },
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": PACK_FORMAT,
        "id": pack_id,
        "name": args.name,
        "version": args.version,
        "engine": "meanvc2",
        "kind": kind,
        "entry": entry_name,
        "assets_dir": "assets",
        "created_at": utc_now(),
        "files": [],
    }
    if icon_rel:
        manifest["icon"] = icon_rel
    manifest_path = output / "manifest.json"
    manifest["files"] = collect_files(output, {manifest_path})
    write_json(manifest_path, manifest)

    zip_path = output.with_suffix(".zip")
    if not args.no_zip:
        build_zip(output, zip_path)

    print(f"音色包目录：{output}")
    if not args.no_zip:
        print(f"音色包 ZIP：{zip_path}")
    print(f"音色 ID：{pack_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

