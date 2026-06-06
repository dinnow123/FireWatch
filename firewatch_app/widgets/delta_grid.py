"""Delta grid — signed per-cell differences (compare - base).

Negative values (compare safer) render in blue; positive (more dangerous) in
red; near-zero stays neutral so the building structure remains visible.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.sample_data.floorplan_gen import OUTSIDE, WALL, WALL_WEAK


_NEUTRAL = (0x4a, 0x4a, 0x4a)
_RED     = (0xdc, 0x26, 0x26)   # compare more dangerous
_BLUE    = (0x25, 0x63, 0xeb)   # compare safer


def diverging_color(d: float) -> QColor:
    d = -1.0 if d < -1.0 else (1.0 if d > 1.0 else float(d))
    if d >= 0:
        t = min(d / 0.5, 1.0)
        a, b = _NEUTRAL, _RED
    else:
        t = min(-d / 0.5, 1.0)
        a, b = _NEUTRAL, _BLUE
    return QColor(
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


class DeltaGrid(QWidget):
    BG       = QColor("#0d1117")
    ROOM_C   = QColor("#1c2530")
    WALL_C   = QColor("#3a4148")
    WALL_WEAK_C = QColor("#2a3038")
    LINE     = QColor("#1f2731")
    BORDER   = QColor("#30363d")

    SHOW_THRESHOLD = 0.04

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cols = 30
        self.rows = 30
        self._delta: np.ndarray | None = None       # (rows, cols)
        self._cell_map: np.ndarray | None = None
        self.setMinimumHeight(180)

    def set_layout(self, cell_map: np.ndarray | None) -> None:
        self._cell_map = cell_map
        if cell_map is not None:
            self.rows, self.cols = cell_map.shape
        self.update()

    def set_delta(self, delta: np.ndarray | None, cols: int, rows: int) -> None:
        self._delta = delta
        self.cols = cols
        self.rows = rows
        self.update()

    def _layout(self) -> tuple[int, int, int]:
        avail_w = self.width() - 2
        avail_h = self.height() - 2
        cell = max(min(avail_w // self.cols, avail_h // self.rows), 4)
        ox = (self.width() - cell * self.cols) // 2
        oy = (self.height() - cell * self.rows) // 2
        return cell, ox, oy

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.BG)
        cell, ox, oy = self._layout()

        cm = self._cell_map
        if cm is not None:
            for r in range(self.rows):
                for c in range(self.cols):
                    t = int(cm[r, c])
                    if t == OUTSIDE:
                        continue
                    if t == WALL:
                        color = self.WALL_C
                    elif t == WALL_WEAK:
                        color = self.WALL_WEAK_C
                    else:
                        color = self.ROOM_C
                    p.fillRect(ox + c * cell, oy + r * cell, cell, cell, color)

        if self._delta is not None:
            rows, cols = self._delta.shape
            for r in range(min(rows, self.rows)):
                for c in range(min(cols, self.cols)):
                    if cm is not None and int(cm[r, c]) == OUTSIDE:
                        continue
                    d = float(self._delta[r, c])
                    if abs(d) < self.SHOW_THRESHOLD:
                        continue
                    p.fillRect(ox + c * cell, oy + r * cell, cell, cell, diverging_color(d))

        if cell >= 6 and cm is not None:
            p.setPen(QPen(self.LINE, 1))
            for c in range(self.cols + 1):
                x = ox + c * cell
                p.drawLine(x, oy, x, oy + self.rows * cell)
            for r in range(self.rows + 1):
                y = oy + r * cell
                p.drawLine(ox, y, ox + self.cols * cell, y)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self.BORDER, 1))
        p.drawRect(ox, oy, cell * self.cols, cell * self.rows)
