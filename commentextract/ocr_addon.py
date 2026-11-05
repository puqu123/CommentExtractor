"""Check the optional portable OCR files without importing their native libraries."""
import importlib.util
import json
from pathlib import Path
import sys

from . import __version__

ADDON_SCHEMA = 1
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
        if data.get("schema") != ADDON_SCHEMA or data.get("app_version") != __version__:
            return False, "增强 OCR 扩展包版本不匹配。" + INSTALL_HINT
        files = data.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("empty addon manifest")
        for name, size in files.items():
            path = root / name
            if Path(name).is_absolute() or Path(name).drive or ".." in Path(name).parts or type(size) is not int or size < 1:
                raise ValueError("invalid addon manifest")
            if not path.is_file() or path.stat().st_size != size:
                return False, "增强 OCR 扩展包不完整。" + INSTALL_HINT
    except (OSError, ValueError, TypeError):
        return False, "未安装可用的增强 OCR 扩展包。" + INSTALL_HINT
    return True, "增强 OCR 扩展包已就绪，离线运行。"
