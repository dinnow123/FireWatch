"""Read-only equipment map for the parameters screen (UC3).

Draws one building floor with its installed sprinklers and fire shutters laid on
top of the floorplan. Each marker's opacity follows the on/off toggle: active
equipment is solid, disabled equipment is faded — so turning a facility off in
the form visibly dims it on the map.

Honesty note on "influence range": the engine cools only the single installed
sprinkler cell (``np.subtract(heat, cooling, where=mask)`` — no radius), so a
sprinkler's influence is exactly one cell. The marker therefore tints exactly
that one cell rather than drawing a fictional spray radius.

Coordinate convention matches the floorplan/heatmap widgets: equipment ``(x, y)``
is ``(col, row)`` and the cell map is indexed ``cell_map[row, col]``.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.sample_data.floorplan_gen import OUTSIDE, WALL, WALL_WEAK


class EquipmentMap(QWidget):
    BG          = QColor("#0d1117")
    ROOM_C      = QColor("#1c2530")
    WALL_C      = QColor("#3a4148")
    WALL_WEAK_C = QColor("#2a3038")
    LINE        = QColor("#1f2731")
    BORDER      = QColor("#30363d")

    SPRINKLER = QColor("#38bdf8")   # sky blue
    SHUTTER   = QColor("#f5b301")   # amber/gold

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cols = 30
        self.rows = 30
        self._cell_map: np.ndarray | None = None
        self._sprinklers: list[tuple[int, int]] = []
        self._shutters: list[tuple[int, int]] = []
        self._sprinkler_on = True
        self._shutter_on = True
        self.setMinimumSize(360, 360)

    # --- public API ---------------------------------------------------------

    def set_layout(self, cell_map: np.ndarray | None) -> None:
        if cell_map is None:
            self._cell_map = None
        else:
            self.rows, self.cols = cell_map.shape
            self._cell_map = cell_map
        self.update()

    def set_equipment(
        self,
        sprinklers: list[tuple[int, int]],
        shutters: list[tuple[int, int]],
    ) -> None:
        self._sprinklers = list(sprinklers)
        self._shutters = list(shutters)
        self.update()

    def set_states(self, sprinkler_on: bool, shutter_on: bool) -> None:
        self._sprinkler_on = sprinkler_on
        self._shutter_on = shutter_on
        self.update()

    # --- geometry -----------------------------------------------------------

    def _geometry(self) -> tuple[int, int, int]:
        avail_w = self.width() - 2
        avail_h = self.height() - 2
        cell = max(min(avail_w // self.cols, avail_h // self.rows), 4)
        off_x = (self.width() - cell * self.cols) // 2
        off_y = (self.height() - cell * self.rows) // 2
        return cell, off_x, off_y

    # --- paint --------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.BG)
        if self._cell_map is None:
            return
        cell, ox, oy = self._geometry()
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

        if cell >= 6:
            p.setPen(QPen(self.LINE, 1))
            grid_w, grid_h = cell * self.cols, cell * self.rows
            for c in range(self.cols + 1):
                x = ox + c * cell
                p.drawLine(x, oy, x, oy + grid_h)
            for r in range(self.rows + 1):
                y = oy + r * cell
                p.drawLine(ox, y, ox + grid_w, y)

        self._draw_markers(
            p, cell, ox, oy, self._sprinklers, self.SPRINKLER, self._sprinkler_on, "circle"
        )
        self._draw_markers(
            p, cell, ox, oy, self._shutters, self.SHUTTER, self._shutter_on, "square"
        )

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self.BORDER, 1))
        p.drawRect(ox, oy, cell * self.cols, cell * self.rows)

    def _draw_markers(
        self,
        p: QPainter,
        cell: int,
        ox: int,
        oy: int,
        cells: list[tuple[int, int]],
        color: QColor,
        on: bool,
        shape: str,
    ) -> None:
        fill = QColor(color)
        fill.setAlpha(235 if on else 55)
        edge = QColor(color)
        edge.setAlpha(255 if on else 110)
        tint = QColor(color)
        tint.setAlpha(70 if on else 20)   # the single influenced cell
        margin = max(cell // 4, 2)
        for x, y in cells:
            if not (0 <= x < self.cols and 0 <= y < self.rows):
                continue
            cx = ox + x * cell
            cy = oy + y * cell
            p.fillRect(cx, cy, cell, cell, tint)
            p.setBrush(QBrush(fill))
            p.setPen(QPen(edge, 1))
            if shape == "circle":
                p.drawEllipse(cx + margin, cy + margin, cell - 2 * margin, cell - 2 * margin)
            else:
                p.drawRect(cx + margin, cy + margin, cell - 2 * margin, cell - 2 * margin)
