"""Render the editable SVG into portable PNG and multi-resolution Windows ICO."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def build_icon():
    app = QGuiApplication.instance() or QGuiApplication([])
    assets = Path(__file__).resolve().parents[1] / "commentextract/assets"
    renderer = QSvgRenderer(str(assets / "app.svg"))
    if not renderer.isValid():
        raise ValueError("Invalid icon SVG")
    image = QImage(512, 512, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    if not image.save(str(assets / "app.png")):
        raise RuntimeError("Cannot save icon PNG")
    with Image.open(assets / "app.png") as icon:
        icon.save(assets / "app.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    print("Icon assets ready:", assets)


if __name__ == "__main__":
    build_icon()
