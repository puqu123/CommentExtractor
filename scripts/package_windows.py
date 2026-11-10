"""Create the main ZIP and optionally a separate OCR add-on ZIP.

Both archives share the CommentExtractor/ root. Extracting them into the same
destination restores the original PyInstaller paths; no installer is needed.
"""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commentextract import __version__
from commentextract.ocr_addon import ADDON_SCHEMA, OCR_COMPATIBILITY, OCR_ENGINE

MAX_DOWNLOAD_BYTES = 100_000_000
OCR_COMPONENTS = {"cv2", "rapidocr_onnxruntime", "onnxruntime", "numpy", "numpy.libs",
                  "shapely", "shapely.libs", "pyclipper"}
README = """增强 OCR 扩展包（可选）

1. 将主程序 ZIP 和本扩展 ZIP 分别传入公司电脑，每份都小于 100 MB。
2. 关闭 CommentExtractor，将两个 ZIP 解压到同一个目标文件夹。
   两个包都有 CommentExtractor 这一层目录，允许同名文件夹合并。
3. 最终应在 CommentExtractor 文件夹内看到 CommentExtractor.exe 和 _internal。
   不要把扩展包单独留在另一个目录，也不要解压成多层 CommentExtractor。
4. 重新打开程序，在“评审 Word ＋ 原手册…”中选择“离线增强 OCR”。

主程序单独即可读取标准批注、执行 Windows OCR、保存截图并导出 Excel。
本包提供 RapidOCR 模型及本地运行库，无需安装 Python，无需联网下载。
兼容的扩展包可以随主程序更新继续使用。识别效果仍需对照原图核对。
"""


def is_ocr_file(relative):
    parts = Path(relative).parts
    return len(parts) >= 2 and parts[0] == "_internal" and parts[1].lower() in OCR_COMPONENTS


def package_windows(bundle, dist=None, max_bytes=MAX_DOWNLOAD_BYTES, include_addon=True):
    bundle = Path(bundle).resolve()
    if not (bundle / "CommentExtractor.exe").is_file():
        raise ValueError("Build the Windows application first.")
    dist = Path(dist).resolve() if dist else bundle.parents[1]
    dist.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in bundle.rglob("*") if p.is_file() and p.name != "ocr-addon.json")
    addon_files = [p for p in files if is_ocr_file(p.relative_to(bundle))]
    if include_addon:
        if not any(p.suffix == ".onnx" for p in addon_files):
            raise ValueError("The build is missing local OCR weights.")
        required = {"rapidocr-onnxruntime": "1.4.4", "onnxruntime": "1.19.2", "numpy": "2.0.2",
                    "opencv-python": "5.0.0.93", "shapely": "2.0.7", "pyclipper": "1.3.0.post6"}
        installed = {name: metadata.version(name) for name in required}
        if installed != required or sys.version_info[:2] != (3, 9) or sys.maxsize < 2**32:
            raise ValueError("OCR 运行库或 Python 环境已变化，请先更新兼容标识并验证扩展包。")
        manifest = {"schema": ADDON_SCHEMA, "app_version": __version__, "engine": OCR_ENGINE,
                    "compatibility": OCR_COMPATIBILITY,
                    "files": {p.relative_to(bundle / "_internal").as_posix(): p.stat().st_size for p in addon_files}}
        marker = bundle / "_internal" / "ocr-addon.json"
        marker.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        addon_readme = bundle / "OCR_ADDON_README.txt"
        addon_readme.write_text(README, encoding="utf-8-sig")
        if addon_readme not in files:
            files.append(addon_readme)
    archives = [dist / f"CommentExtractor-v{__version__}-win64.zip"]
    if include_addon:
        archives.append(dist / f"CommentExtractor-v{__version__}-ocr-addon-win64.zip")
    temporary = []
    try:
        for archive_index, target in enumerate(archives):
            addon = include_addon and archive_index == 1
            with tempfile.NamedTemporaryFile(dir=dist, suffix=".zip", delete=False) as stream:
                path = Path(stream.name)
            temporary.append(path)
            with ZipFile(path, "w", ZIP_DEFLATED, compresslevel=9) as archive:
                for source in files:
                    if include_addon and not addon and source == addon_readme:
                        continue
                    is_addon_component = is_ocr_file(source.relative_to(bundle))
                    if (include_addon and is_addon_component != bool(addon)) or (not include_addon and is_addon_component):
                        continue
                    archive.write(source, source.relative_to(bundle.parent).as_posix())
                if addon:
                    archive.write(marker, "CommentExtractor/_internal/ocr-addon.json")
                    archive.write(addon_readme, "CommentExtractor/OCR_ADDON_README.txt")
                    # The optional download carries its native-library notices too.
                    for source in sorted((bundle / "licenses").rglob("*")):
                        if source.is_file():
                            archive.write(source, "CommentExtractor/ocr-licenses/" + source.relative_to(bundle / "licenses").as_posix())
            if path.stat().st_size >= max_bytes:
                raise ValueError(f"{target.name} reaches the {max_bytes:,}-byte download limit; no new archives installed.")
        for path, target in zip(temporary, archives):
            path.replace(target)
        checksums = []
        for target in archives:
            line = hashlib.sha256(target.read_bytes()).hexdigest() + "  " + target.name + "\n"
            target.with_suffix(".sha256").write_text(line, encoding="utf-8")
            checksums.append(line)
            print(f"Ready: {target.name} ({target.stat().st_size:,} bytes; {target.stat().st_size / 1_000_000:.1f} MB)")
        (dist / f"CommentExtractor-v{__version__}-SHA256SUMS.txt").write_text("".join(checksums), encoding="utf-8")
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return archives


if __name__ == "__main__":
    main_only = "--main-only" in sys.argv[1:]
    arguments = [value for value in sys.argv[1:] if value != "--main-only"]
    bundle = arguments[0] if arguments else f"dist/v{__version__}/CommentExtractor"
    package_windows(bundle, include_addon=not main_only)
