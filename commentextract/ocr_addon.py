"""Check the optional portable OCR files without importing their native libraries."""
import importlib.util
import json
import hashlib
from pathlib import Path
import sys

ADDON_SCHEMA = 1
OCR_ENGINE = "rapidocr-onnxruntime==1.4.4"
OCR_COMPATIBILITY = "rapidocr-1.4.4-ort-1.19.2-numpy-2.0.2-opencv-5.0.0.93-shapely-2.0.7-pyclipper-1.3.0.post6-win64-py39-v1"
# Legacy packages have no compatibility ID. Their file lists and sizes match;
# the v0.2.11 and v0.2.12 model/runtime contents have also been compared.
LEGACY_VERSIONS = {"0.2.8", "0.2.9", "0.2.10", "0.2.11", "0.2.12"}
LEGACY_FILES_DIGEST = "f09453590b048bc29ea6811d2029e432568d8a9c66ff9480a4f1f276a2c431be"
INSTALL_HINT = "请将增强 OCR 扩展包与主程序包解压到同一个目录，保留合并后的 _internal 文件夹，再重启程序。"


def rapidocr_status():
    if not getattr(sys, "frozen", False):
        if importlib.util.find_spec("rapidocr_onnxruntime"):
            return True, "增强 OCR 已安装，离线运行。"
        return False, "源码环境未安装增强 OCR；请安装项目的 ocr 可选依赖。"
    root = Path(sys._MEIPASS)
    try:
        data = json.loads((root / "ocr-addon.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("invalid addon manifest")
        files = data.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("empty addon manifest")
        canonical = json.dumps(files, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        legacy = (data.get("compatibility") is None and data.get("app_version") in LEGACY_VERSIONS
                  and hashlib.sha256(canonical).hexdigest() == LEGACY_FILES_DIGEST)
        if (data.get("schema") != ADDON_SCHEMA or data.get("engine") != OCR_ENGINE
                or (data.get("compatibility") != OCR_COMPATIBILITY and not legacy)):
            return False, "增强 OCR 扩展包不兼容，需要更新扩展包。" + INSTALL_HINT
        for name, size in files.items():
            path = root / name
            if Path(name).is_absolute() or Path(name).drive or ".." in Path(name).parts or type(size) is not int or size < 1:
                raise ValueError("invalid addon manifest")
            if not path.is_file() or path.stat().st_size != size:
                return False, "增强 OCR 扩展包不完整。" + INSTALL_HINT
    except (OSError, ValueError, TypeError):
        return False, "未安装可用的增强 OCR 扩展包。" + INSTALL_HINT
    return True, "增强 OCR 扩展包已就绪，离线运行。"
