"""Building section diagram — a floors × columns mini-heatmap.

Each floor is a horizontal strip of ``n_cols`` cells; cell ``(floor, col)`` is
colored by that floor/column's risk. The value is a maximum-intensity projection
over the building depth (rows) — i.e. the hottest cell in that vertical slice —
so "어느 층 어느 열이 타는지" reads off the elevation like a side X-ray.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.sample_data.floorplan_gen import ROOM, WALL_WEAK
from firewatch_app.widgets.heatmap_grid import heat_color


def project_section(frame: np.ndarray, cell_map: np.ndarray | None) -> np.ndarray:
    """Floors × footprint-columns risk: max over rows (depth), non-floor margin dropped.

    ``frame`` is ``(n_floors, rows, cols)`` reach probability at one tick. Columns
    cropped to the building's *burnable footprint* — those containing a ROOM or
    WALL_WEAK cell. This drops both the surrounding-land OUTSIDE gutters and the
    solid concrete perimeter-wall columns (always probability 0), so neither reads
    as gray "safe" floor area; the elevation maps 1:1 to the actual floor width.
    Falls back to the full width when no cell map is available.
    """
    if cell_map is not None and cell_map.size:
        burnable = (cell_map == ROOM) | (cell_map == WALL_WEAK)
        cols = np.where(burnable.any(axis=0))[0]
        if cols.size:
            frame = frame[:, :, int(cols.min()):int(cols.max()) + 1]
    return frame.max(axis=1)


class SectionDiagram(QWidget):
    BG    = QColor("#0d1117")
    FRAME = QColor("#3a4148")
    LABEL = QColor("#e6edf3")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._names: list[str] = []          # top-to-bottom floor names
        self._grid: np.ndarray | None = None  # (n_floors, n_cols), rows already projected
        self.setMinimumHeight(280)

    def set_section(self, names: list[str], grid: np.ndarray | None) -> None:
        """``names`` top-to-bottom; ``grid`` is (n_floors, n_cols) risk in [0,1]."""
        self._names = list(names)
        self._grid = grid
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), self.BG)
        grid = self._grid
        if grid is None or grid.size == 0 or not self._names:
            return

        n = min(len(self._names), grid.shape[0])
        n_cols = grid.shape[1]
        if n == 0 or n_cols == 0:
            return

        margin_t = 18
        margin_b = 14
        margin_l = 56
        margin_r = 76

        avail_h = self.height() - margin_t - margin_b
        floor_h = max(avail_h // n, 22)
        bar_x = margin_l
        bar_w = max(self.width() - margin_l - margin_r, 100)
        # Cell width is the building width split across its columns; never below
        # 1px so a wide building (e.g. 56 cols) still paints without collapsing.
        cell_w = max(bar_w / n_cols, 1.0)

        font_mono = QFont("IBM Plex Mono", 11)

        for i in range(n):
            name = self._names[i]
            row = grid[i]
            y = margin_t + i * floor_h
            h = floor_h - 1

            # Per-column cells (the floor's elevation slice).
            for c in range(n_cols):
                x = int(round(bar_x + c * cell_w))
                x_next = int(round(bar_x + (c + 1) * cell_w))
                w = max(x_next - x, 1)
                p.fillRect(x, y, w, h, heat_color(float(row[c])))

            # Floor outline on top of the cells.
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(self.FRAME, 1))
            p.drawRect(bar_x, y, bar_w, h)

            # Left floor label + right "floor max" readout.
            p.setFont(font_mono)
            p.setPen(QPen(self.LABEL, 1))
            p.drawText(
                0, y, margin_l - 8, h,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                name,
            )
            p.drawText(
                bar_x + bar_w + 8, y, 64, h,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"{float(row.max()) * 100:5.1f}%",
            )
