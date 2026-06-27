"""Generate smartring.ico using PyQt5."""
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QIcon
from PyQt5.QtCore import Qt, QPoint, QSize


def make_icon_pixmap(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    margin = size * 0.12
    r = (size - margin * 2) / 2
    cx, cy = size / 2, size / 2
    outer_r = int(r)
    inner_r = int(r * 0.38)

    # Outer ring background
    p.setBrush(QBrush(QColor(45, 45, 52)))
    p.setPen(QPen(QColor("#0078D4"), max(2, int(size * 0.06))))
    p.drawEllipse(QPoint(int(cx), int(cy)), outer_r, outer_r)

    # Inner dot
    p.setBrush(QBrush(QColor("#0078D4")))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPoint(int(cx), int(cy)), inner_r, inner_r)

    p.end()
    return pix


def main():
    app = QApplication(sys.argv)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    icon = QIcon()
    for s in sizes:
        icon.addPixmap(make_icon_pixmap(s))

    pixmap = icon.pixmap(QSize(256, 256))
    pixmap.save("smartring.ico", "ICO")
    print("smartring.ico generated with sizes:", sizes)


if __name__ == "__main__":
    main()
