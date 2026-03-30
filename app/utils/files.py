from __future__ import annotations

import csv
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

import chardet

try:
    import py7zr
except Exception:  # pragma: no cover
    py7zr = None

SUPPORTED_LOG_SUFFIXES = {".log", ".txt", ".csv", ".metrics", ".trace"}
ProgressCallback = Callable[[str, int], None]


class ArchiveHandlingError(RuntimeError):
    pass


def detect_encoding(path: Path) -> str:
    with path.open("rb") as f:
        raw = f.read(4096)
    result = chardet.detect(raw)
    return result.get("encoding") or "utf-8"


def read_text_stream(path: Path):
    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, errors="replace", newline="") as f:
        for line in f:
            yield line.rstrip("\n")


def sniff_csv(path: Path) -> bool:
    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, errors="replace", newline="") as f:
        sample = f.read(2048)
    try:
        csv.Sniffer().sniff(sample)
        return "," in sample
    except Exception:
        return False


def _call_progress(cb: ProgressCallback | None, stage: str, percent: int) -> None:
    if cb:
        cb(stage, percent)


def unpack_archive(src: Path, dst_dir: Path, progress_callback: ProgressCallback | None = None) -> list[Path]:
    dst_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()
    extracted: list[Path] = []
    _call_progress(progress_callback, f"识别输入文件: {src.name}", 5)
    if suffix == ".zip":
        with zipfile.ZipFile(src) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            total = max(len(names), 1)
            for idx, name in enumerate(names, start=1):
                zf.extract(name, dst_dir)
                _call_progress(progress_callback, f"解压 ZIP: {name}", 5 + int(idx / total * 20))
    elif suffix in {".tar", ".gz", ".tgz", ".bz2"}:
        with tarfile.open(src) as tf:
            members = [m for m in tf.getmembers() if m.isfile()]
            total = max(len(members), 1)
            for idx, member in enumerate(members, start=1):
                tf.extract(member, dst_dir)
                _call_progress(progress_callback, f"解压 TAR: {member.name}", 5 + int(idx / total * 20))
    elif suffix == ".7z":
        if py7zr is None:
            raise ArchiveHandlingError(
                "当前环境缺少 py7zr，无法解析 .7z 压缩包。Windows 本地请先执行: pip install py7zr"
            )
        try:
            with py7zr.SevenZipFile(src, mode="r") as archive:
                names = [n for n in archive.getnames() if not n.endswith("/")]
                archive.extractall(path=dst_dir)
                total = max(len(names), 1)
                for idx, name in enumerate(names, start=1):
                    _call_progress(progress_callback, f"解压 7z: {name}", 5 + int(idx / total * 20))
        except Exception as exc:
            raise ArchiveHandlingError(
                f"7z 解压失败: {exc}。请确认压缩包未损坏，且本地已安装 py7zr；若为加密 7z，请先手工解压后再上传目录内日志。"
            ) from exc
    else:
        copied = dst_dir / src.name
        shutil.copy2(src, copied)
        _call_progress(progress_callback, f"复制单文件: {src.name}", 20)
        return [copied]
    for p in dst_dir.rglob("*"):
        if p.is_file():
            extracted.append(p)
    _call_progress(progress_callback, f"解压完成，共 {len(extracted)} 个文件", 25)
    return extracted


def iter_supported_files(paths: list[Path]) -> list[Path]:
    result = []
    for p in paths:
        if p.is_file() and (p.suffix.lower() in SUPPORTED_LOG_SUFFIXES or p.suffix == ""):
            result.append(p)
    return sorted(result)
