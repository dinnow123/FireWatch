"""Horizontal colorbar legend for the heatmap.

Two modes, switched with the CI toggle:
    * ``"risk"``       회색 → 주황 → 빨강  (reach probability, default)
    * ``"confidence"`` 연녹 → 진녹          (Wilson-CI confidence)
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.widgets.heatmap_grid import confidence_color, heat_color


class HeatmapColorbar(QWidget):
    BORDER = QColor("#30363d")
    TICK   = QColor("#8b949e")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "risk"
        self.setFixedHeight(14)
        self.setMinimumWidth(160)

    def set_mode(self, mode: str) -> None:
        """Switch the gradient between ``"risk"`` and ``"confidence"``."""
        if mode not in ("risk", "confidence"):
            mode = "risk"
        if mode != self._mode:
            self._mode = mode
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        w = self.width()
        h = self.height()
        color_fn = confidence_color if self._mode == "confidence" else heat_color
        steps = max(w, 1)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            p.fillRect(i, 0, 1, h, color_fn(t))
        p.setPen(QPen(self.BORDER, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, w - 1, h - 1)
