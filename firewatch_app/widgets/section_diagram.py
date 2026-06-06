"""Building section diagram — stacked floor rectangles colored by risk."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.widgets.heatmap_grid import heat_color


class SectionDiagram(QWidget):
    BG    = QColor("#0d1117")
    FRAME = QColor("#3a4148")
    LABEL = QColor("#e6edf3")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, float]] = []
        self.setMinimumHeight(280)

    def set_data(self, data: list[tuple[str, float]]) -> None:
        """`data` is top-to-bottom: [(floor_name, risk 0..1), ...]"""
        self._data = list(data)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), self.BG)
        if not self._data:
            return

        n = len(self._data)
        margin_t = 18
        margin_b = 14
        margin_l = 56
        margin_r = 76

        avail_h = self.height() - margin_t - margin_b
        floor_h = max(avail_h // n, 22)
        bar_x = margin_l
        bar_w = max(self.width() - margin_l - margin_r, 100)

        font_mono = QFont("IBM Plex Mono", 11)

        for i, (name, risk) in enumerate(self._data):
            y = margin_t + i * floor_h
            p.fillRect(bar_x, y, bar_w, floor_h - 1, heat_color(risk))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(self.FRAME, 1))
            p.drawRect(bar_x, y, bar_w, floor_h - 1)

            p.setFont(font_mono)
            p.setPen(QPen(self.LABEL, 1))
            p.drawText(
                0, y, margin_l - 8, floor_h - 1,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                name,
            )
            p.drawText(
                bar_x + bar_w + 8, y, 64, floor_h - 1,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"{risk * 100:5.1f}%",
            )
