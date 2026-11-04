"""Keep desktop exceptions visible even in the windowed Windows executable."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys


def install_exception_handler(parent):
    directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CommentExtractor" / "logs"
    logfile = directory / "app.log"
    logger = logging.getLogger("commentextract")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(logfile, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    except OSError:
        logfile = None

    def on_exception(kind, value, trace):
        logger.error("Desktop exception", exc_info=(kind, value, trace))
        from .support import exception_details
        detail = exception_details(value)
        parent.diagnostic_events.append({"phase": "ui", "error": detail})
        parent.report_button.setEnabled(True)
        from PySide6.QtWidgets import QMessageBox
        suffix = f"\n错误记录：{logfile}" if logfile else ""
        QMessageBox.critical(parent, "操作未完成", f"[{detail['code']}] {kind.__name__}：{value}{suffix}\n可在“处理记录 → 脱敏诊断”复制不含文档内容的技术报告。")

    sys.excepthook = on_exception
