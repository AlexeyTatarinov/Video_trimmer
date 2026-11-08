"""Regenerate src/video_trimmer/assets/icon.png and icon.ico (original design, drawn with Qt)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

OUT = Path(__file__).resolve().parent.parent / "src" / "video_trimmer" / "assets"


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    s = size / 256.0
    p.scale(s, s)
    tile = QRectF(10, 10, 236, 236)
    # glass tile: deep blue gradient
    g = QLinearGradient(0, 10, 0, 246)
    g.setColorAt(0, QColor("#7CC2F4"))
    g.setColorAt(1, QColor("#1F5FB0"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawRoundedRect(tile, 58, 58)
    # soft highlight on the upper half
    hl = QPainterPath()
    hl.addRoundedRect(QRectF(18, 16, 220, 118), 50, 50)
    hg = QLinearGradient(0, 16, 0, 134)
    hg.setColorAt(0, QColor(255, 255, 255, 120))
    hg.setColorAt(1, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(hg))
    p.drawPath(hl)
    # rim
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 150), 3))
    p.drawRoundedRect(tile.adjusted(1.5, 1.5, -1.5, -1.5), 56, 56)
    # range-slider motif: track, bright selected part, two handles, tiny cut marks
    y = 140.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 90))
    p.drawRoundedRect(QRectF(44, y - 9, 168, 18), 9, 9)
    p.setBrush(QColor("#FFFFFF"))
    p.drawRoundedRect(QRectF(88, y - 9, 80, 18), 9, 9)
    for cx in (88, 168):
        rg = QRadialGradient(QPointF(cx - 4, y - 6), 26)
        rg.setColorAt(0, QColor("#FFFFFF"))
        rg.setColorAt(1, QColor("#CFE6FA"))
        p.setPen(QPen(QColor("#1F5FB0"), 5))
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(cx, y), 20, 20)
    # play triangle above the selection
    tri = QPainterPath()
    tri.moveTo(112, 66)
    tri.lineTo(112, 108)
    tri.lineTo(150, 87)
    tri.closeSubpath()
    p.setPen(QPen(QColor("#FFFFFF"), 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor("#FFFFFF"))
    p.drawPath(tri)
    p.end()
    return img


def main() -> int:
    QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    draw(512).save(str(OUT / "icon.png"))
    # ICO: Qt's writer stores a single size per file; build multi-size ICO by hand (PNG entries).
    import io
    import struct
    from PySide6.QtCore import QBuffer, QByteArray
    sizes = [16, 24, 32, 48, 64, 128, 256]
    blobs = []
    for sz in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.WriteOnly)
        draw(sz).save(buf, "PNG")
        blobs.append(bytes(ba))
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for sz, b in zip(sizes, blobs):
        entries += struct.pack("<BBBBHHII", sz % 256, sz % 256, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    (OUT / "icon.ico").write_bytes(head + entries + b"".join(blobs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
