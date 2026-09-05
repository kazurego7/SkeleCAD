"""Render generated SVG previews with FreeCAD's bundled Qt, without a browser."""
import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    args = parser.parse_args()
    if not args.input.is_file() or min(args.width, args.height) <= 0:
        raise ValueError("Existing SVG and positive image dimensions are required")
    app = QGuiApplication([])
    renderer = QSvgRenderer(str(args.input.resolve()))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {args.input}")
    image = QImage(args.width, args.height, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, args.width, args.height))
    finally:
        painter.end()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(args.output.resolve()), "PNG"):
        raise RuntimeError(f"Could not save preview: {args.output}")
    print(f"Rendered {args.output}: {image.width()} x {image.height()}")
    app.quit()


if __name__ == "__main__":
    main()
