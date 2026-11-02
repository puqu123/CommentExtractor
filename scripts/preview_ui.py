"""Developer-only offscreen UI preview using fictional demo files."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtCore import QItemSelectionModel
from commentextract.app import MainWindow
from commentextract.extract import extract_file
from tests.samples import create_samples

if __name__ == "__main__":
    base = Path("local_data/demo")
    create_samples(base)
    application = QApplication([])
    # Qt's offscreen plugin has no Windows font discovery. Use an installed font
    # for this developer screenshot; never copy system fonts into the distribution.
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    application.setFont(QFont("Microsoft YaHei UI", 10))
    window = MainWindow()
    window.resize(1600, 980)
    for path in sorted(base.iterdir()):
        window.add_result(extract_file(path))
    window.file_list.setCurrentRow(3, QItemSelectionModel.ClearAndSelect)
    window.show()
    application.processEvents()
    window.grab().save("local_data/ui-preview.png")
    window.dirty = False
    window.close()
