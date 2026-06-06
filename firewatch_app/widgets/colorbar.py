"""Horizontal colorbar legend for the heatmap (회색 → 주황 → 빨강)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.widgets.heatmap_grid import heat_color


class HeatmapColorbar(QWidget):
    BORDER = QColor("#30363d")
    TICK   = QColor("#8b949e")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setMinimumWidth(160)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        w = self.width()
        h = self.height()
        steps = max(w, 1)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            p.fillRect(i, 0, 1, h, heat_color(t))
        p.setPen(QPen(self.BORDER, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, w - 1, h - 1)
