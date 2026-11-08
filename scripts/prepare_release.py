"""Prepare source, checksums and notes for an already committed version."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commentextract.ocr_addon import OCR_COMPATIBILITY, OCR_ENGINE, LEGACY_VERSIONS, LEGACY_FILES_DIGEST

REUSED_ADDON_COMPATIBILITY = "rapidocr-1.4.4-ort-1.19.2-numpy-2.0.2-opencv-5.0.0.93-shapely-2.0.7-pyclipper-1.3.0.post6-win64-py39-v1"
REUSED_ADDON_URL = "https://github.com/puqu123/CommentExtractor/releases/download/v0.2.11/CommentExtractor-v0.2.11-ocr-addon-win64.zip"


def prepare_release(root):
    root = Path(root).resolve()
    version_text = (root / "commentextract/__init__.py").read_text(encoding="utf-8")
    version = re.search(r'__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', version_text).group(1)
    committed = subprocess.check_output(["git", "show", "HEAD:commentextract/__init__.py"], cwd=root).decode()
    if f'__version__ = "{version}"' not in committed:
        raise ValueError("Commit the version change before preparing a public release.")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root).strip():
        raise ValueError("Commit or remove uncommitted changes before preparing a public release.")
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    binary = dist / f"CommentExtractor-v{version}-win64.zip"
    if (OCR_COMPATIBILITY != REUSED_ADDON_COMPATIBILITY or OCR_ENGINE != "rapidocr-onnxruntime==1.4.4"
            or "0.2.11" not in LEGACY_VERSIONS
            or LEGACY_FILES_DIGEST != "f09453590b048bc29ea6811d2029e432568d8a9c66ff9480a4f1f276a2c431be"):
        raise ValueError("The reused OCR addon is incompatible; update the release addon policy before publishing.")
    if not binary.is_file():
        raise ValueError("Build the Windows application first.")
    if binary.stat().st_size >= 100_000_000:
        raise ValueError("Every Windows download must be below 100 MB.")
    source = dist / f"CommentExtractor-v{version}-source.zip"
    subprocess.run(["git", "archive", "--format=zip", f"--prefix=CommentExtractor-v{version}/",
                    f"--output={source}", "HEAD"], cwd=root, check=True)
    checksums = dist / "SHA256SUMS.txt"
    checksums.write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
                                 for path in [binary, source]), encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(rf"^## v{re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)",
                        changelog, flags=re.MULTILINE | re.DOTALL)
    if not section:
        raise ValueError("Add this version's release notes to CHANGELOG.md first.")
    notes = dist / f"release-v{version}.md"
    notes.write_text(section.group(1).strip() + "\n\n"
                     "下载 Windows x64 ZIP，完整解压后运行 CommentExtractor.exe。"
                     f"需要增强识别时，下载 [v0.2.11 OCR 增强包]({REUSED_ADDON_URL})，与本版本兼容；"
                     "将两个 ZIP 解压到同一个目标文件夹，再重启程序启用增强识别。"
                     "源代码及许可文件随版本提供，SHA256SUMS.txt 用于核对压缩包。\n\n"
                     f"使用说明：[简明使用说明](https://github.com/puqu123/CommentExtractor/blob/v{version}/USAGE.md)"
                     "，免安装包内也附有 USAGE.txt。\n"
                     f"问题反馈：[文字诊断与错误码](https://github.com/puqu123/CommentExtractor/blob/v{version}/SUPPORT.md)；"
                     f"[兼容性测试范围及已知限制](https://github.com/puqu123/CommentExtractor/blob/v{version}/COMPATIBILITY.md)。\n", encoding="utf-8")
    return dict(version=version, binary=str(binary), source=str(source), checksums=str(checksums), notes=str(notes))


if __name__ == "__main__":
    print(json.dumps(prepare_release(Path(__file__).resolve().parents[1])))
