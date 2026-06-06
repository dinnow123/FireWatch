"""Floorplan grid widget — pick an ignition cell on a real floor plan."""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.sample_data.floorplan_gen import OUTSIDE, ROOM, WALL, WALL_WEAK


class FloorplanGrid(QWidget):
    cellClicked = pyqtSignal(int, int)
    cellHovered = pyqtSignal(int, int)   # (-1, -1) when leaving

    BG       = QColor("#0d1117")
    OUTSIDE_C = QColor("#0d1117")
    ROOM_C    = QColor("#1c2530")
    WALL_C    = QColor("#3a4148")        # structural concrete/steel
    WALL_WEAK_C = QColor("#2a3038")      # drywall / partition
    LINE     = QColor("#1f2731")
    HOVER    = QColor("#1f3a3c")
    IGNITION = QColor("#dc2626")
    BORDER   = QColor("#30363d")

    def __init__(self, cols: int = 30, rows: int = 30, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cols = cols
        self.rows = rows
        self._cell_map: np.ndarray | None = None
        self.ignition: tuple[int, int] | None = None
        self._hover: tuple[int, int] | None = None
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)

    # --- public API ---------------------------------------------------------

    def set_layout(self, cell_map: np.ndarray) -> None:
        rows, cols = cell_map.shape
        self.rows = rows
        self.cols = cols
        self._cell_map = cell_map
        self.ignition = None
        self.update()

    def clear(self) -> None:
        self.ignition = None
        self.update()

    def cell_type_at(self, x: int, y: int) -> int:
        if self._cell_map is None:
            return ROOM
        if 0 <= y < self._cell_map.shape[0] and 0 <= x < self._cell_map.shape[1]:
            return int(self._cell_map[y, x])
        return OUTSIDE

    # --- geometry helpers ---------------------------------------------------

    def _layout(self) -> tuple[int, int, int]:
        avail_w = self.width() - 2
        avail_h = self.height() - 2
        cell = max(min(avail_w // self.cols, avail_h // self.rows), 4)
        off_x = (self.width() - cell * self.cols) // 2
        off_y = (self.height() - cell * self.rows) // 2
        return cell, off_x, off_y

    def _xy_from_pos(self, pos) -> tuple[int, int] | None:
        cell, ox, oy = self._layout()
        x = int((pos.x() - ox) // cell)
        y = int((pos.y() - oy) // cell)
        if 0 <= x < self.cols and 0 <= y < self.rows:
            return x, y
        return None

    # --- events -------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        xy = self._xy_from_pos(event.position())
        if xy is None:
            return
        if self.cell_type_at(*xy) != ROOM:
            return  # walls and outside are not valid ignition points
        self.ignition = xy
        self.cellClicked.emit(*xy)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        xy = self._xy_from_pos(event.position())
        if xy != self._hover:
            self._hover = xy
            if xy is None:
                self.cellHovered.emit(-1, -1)
            else:
                self.cellHovered.emit(*xy)
            self.update()

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.cellHovered.emit(-1, -1)
            self.update()

    # --- paint --------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.BG)
        cell, ox, oy = self._layout()
        grid_w = cell * self.cols
        grid_h = cell * self.rows

        if self._cell_map is not None:
            cm = self._cell_map
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

        if self._hover is not None:
            hx, hy = self._hover
            ht = self.cell_type_at(hx, hy)
            if ht == ROOM:
                p.fillRect(ox + hx * cell + 1, oy + hy * cell + 1, cell - 1, cell - 1, self.HOVER)

        if self._cell_map is not None and cell >= 6:
            p.setPen(QPen(self.LINE, 1))
            for c in range(self.cols + 1):
                x = ox + c * cell
                p.drawLine(x, oy, x, oy + grid_h)
            for r in range(self.rows + 1):
                y = oy + r * cell
                p.drawLine(ox, y, ox + grid_w, y)

        if self.ignition is not None:
            ix, iy = self.ignition
            cx = ox + ix * cell + cell // 2
            cy = oy + iy * cell + cell // 2
            radius = max(cell // 3, 3)
            p.setBrush(QBrush(self.IGNITION))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self.BORDER, 1))
        p.drawRect(ox, oy, grid_w, grid_h)
