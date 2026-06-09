"""Heatmap grid widget — renders per-cell probability with the spec's reach-
probability gradient: 회색 0% (안전) → 주황 50% (주의) → 빨강 100% (위험)
(Analysis 4.5.1 / UC5). The gradient is defined locally so the live UI matches
the spec exactly without disturbing the engine's verification colormap."""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.sample_data.floorplan_gen import OUTSIDE, WALL, WALL_WEAK

# Spec reach-probability anchors (Analysis 4.5.1, UC5 Etc, Glossary):
#   0% → 회색(안전), 50% → 주황(주의), 100% → 빨강(위험).
_C_SAFE = (107, 114, 128)   # gray   #6b7280  안전
_C_WARN = (249, 115, 22)    # orange #f97316  주의
_C_RISK = (220, 38, 38)     # red    #dc2626  위험


def _clamp8(v: float) -> int:
    return 0 if v < 0 else 255 if v > 255 else round(v)


def heat_color(p: float) -> QColor:
    """Smooth, continuous gray→orange→red gradient at probability ``p``.

    The three spec colors sit at p = 0.0 / 0.5 / 1.0 and are joined with a
    per-channel quadratic (Lagrange basis on nodes 0, ½, 1) that passes through
    all three exactly. Unlike piecewise-linear interpolation — which cornered at
    50% — this has no slope break, so the gradient reads as one continuous sweep
    with no visible banding while keeping the spec's named colors at their stops.
    """
    if p <= 0.0:
        return QColor(*_C_SAFE)
    if p >= 1.0:
        return QColor(*_C_RISK)
    l0 = 2.0 * (p - 0.5) * (p - 1.0)
    l1 = -4.0 * p * (p - 1.0)
    l2 = 2.0 * p * (p - 0.5)
    return QColor(
        _clamp8(_C_SAFE[0] * l0 + _C_WARN[0] * l1 + _C_RISK[0] * l2),
        _clamp8(_C_SAFE[1] * l0 + _C_WARN[1] * l1 + _C_RISK[1] * l2),
        _clamp8(_C_SAFE[2] * l0 + _C_WARN[2] * l1 + _C_RISK[2] * l2),
    )


# Confidence (CI) view anchors — sequential greens (ColorBrewer "Greens"). The
# confidence map replaces the risk colors entirely when the CI toggle is on:
#   s = sharpness in [0,1], 0 = wide Wilson CI (uncertain) → pale green,
#   1 = narrow CI (certain) → deep green. "진할수록 신뢰도 높음."
_C_UNSURE = (199, 233, 192)   # #c7e9c0  pale green   낮은 신뢰도
_C_MIDCI  = (65, 171, 93)     # #41ab5d  medium green
_C_SURE   = (0, 109, 44)      # #006d2c  deep green   높은 신뢰도


def confidence_color(s: float) -> QColor:
    """Sequential-green confidence color at sharpness ``s`` (0..1).

    Pale green = low confidence (wide CI), deep green = high confidence (narrow
    CI). Stops at s = 0/0.5/1 joined with the same per-channel quadratic
    (Lagrange basis) as ``heat_color`` so the sweep is continuous, no banding.
    """
    if s <= 0.0:
        return QColor(*_C_UNSURE)
    if s >= 1.0:
        return QColor(*_C_SURE)
    l0 = 2.0 * (s - 0.5) * (s - 1.0)
    l1 = -4.0 * s * (s - 1.0)
    l2 = 2.0 * s * (s - 0.5)
    return QColor(
        _clamp8(_C_UNSURE[0] * l0 + _C_MIDCI[0] * l1 + _C_SURE[0] * l2),
        _clamp8(_C_UNSURE[1] * l0 + _C_MIDCI[1] * l1 + _C_SURE[1] * l2),
        _clamp8(_C_UNSURE[2] * l0 + _C_MIDCI[2] * l1 + _C_SURE[2] * l2),
    )


# Stairwell marker color — light/neutral so it reads as structure, distinct from
# the red heat, gold shutter and sky-blue sprinkler markers.
_C_STAIRS = (226, 232, 240)   # #e2e8f0


def draw_stairs(p: QPainter, x: int, y: int, cell: int) -> None:
    """Draw a stairwell marker (bordered box + step lines) at pixel ``(x, y)``."""
    inset = max(cell // 6, 1)
    bx, by = x + inset, y + inset
    bw = cell - 2 * inset
    color = QColor(*_C_STAIRS)
    if bw < 4:
        # Too small for steps — a plain marker dot keeps it visible.
        s = max(cell // 3, 1)
        p.fillRect(x + (cell - s) // 2, y + (cell - s) // 2, s, s, color)
        return
    p.setBrush(QBrush(QColor(13, 17, 23, 170)))      # dark backing for contrast
    p.setPen(QPen(color, max(cell // 14, 1)))
    p.drawRect(bx, by, bw, bw)
    p.setPen(QPen(color, max(cell // 18, 1)))
    for k in (1, 2, 3):
        yy = by + bw * k // 4
        p.drawLine(bx + 1, yy, bx + bw - 1, yy)


class HeatmapGrid(QWidget):
    cellHovered = pyqtSignal(int, int, float)   # x, y, probability ; (-1,-1,0.0) on leave

    BG       = QColor("#0d1117")
    ROOM_C   = QColor("#1c2530")
    WALL_C   = QColor("#3a4148")
    WALL_WEAK_C = QColor("#2a3038")
    LINE     = QColor("#1f2731")
    BORDER   = QColor("#30363d")
    IGNITION = QColor("#dc2626")
    HOVER    = QColor("#10b981")
    # Fire-shutter (방화벽) marker: gold so it never reads as the orange #f97316
    # "주의 50%" heat band, and as an outline+hatch so it reads as structure, not
    # as a probability fill. Solid gray WALL_C stays the plain structural wall.
    SHUTTER  = QColor("#f5b301")
    # Sprinkler marker: sky blue (water) — a translucent blue cell so it reads as
    # "sprinklered here" without hiding the heat underneath, and never clashes
    # with the red heat band or the gold shutter hatch.
    SPRINKLER = QColor("#38bdf8")

    HEAT_THRESHOLD = 0.05   # below this we keep the building base color

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cols = 30
        self.rows = 30
        self._data: np.ndarray | None = None        # (rows, cols)
        self._cell_map: np.ndarray | None = None    # (rows, cols)
        self._ignition: tuple[int, int] | None = None
        self._shutters: list[tuple[int, int]] = []   # (x, y) fire-shutter cells
        self._sprinklers: list[tuple[int, int]] = []  # (x, y) active-sprinkler cells
        self._stairs: list[tuple[int, int]] = []      # (x, y) inter-floor stairwell cells
        self._confidence: np.ndarray | None = None   # (rows, cols) sharpness 0..1
        self._hover: tuple[int, int] | None = None
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)

    # ---------------------------------------------------------- public api

    def set_layout(self, cell_map: np.ndarray | None) -> None:
        self._cell_map = cell_map
        if cell_map is not None:
            self.rows, self.cols = cell_map.shape
        self.update()

    def set_frame(
        self,
        data: np.ndarray | None,
        cols: int,
        rows: int,
        ignition: tuple[int, int] | None,
    ) -> None:
        self._data = data
        self.cols = cols
        self.rows = rows
        self._ignition = ignition
        self.update()

    def set_shutters(self, cells: list[tuple[int, int]]) -> None:
        """Fire-shutter install cells for the current floor (gold hatch overlay)."""
        self._shutters = list(cells)
        self.update()

    def set_sprinklers(self, cells: list[tuple[int, int]]) -> None:
        """Active-sprinkler cells for the current floor (translucent blue overlay)."""
        self._sprinklers = list(cells)
        self.update()

    def set_stairs(self, cells: list[tuple[int, int]]) -> None:
        """Inter-floor stairwell cells (shown on every floor; stair-step marker)."""
        self._stairs = list(cells)
        self.update()

    def set_confidence(self, sharpness: np.ndarray | None) -> None:
        """Switch the map to the confidence view (``sharpness`` array) or off (None).

        When set, the reachable cells render in the green confidence gradient
        (1.0 = narrow Wilson CI = deep green, 0.0 = wide CI = pale green) instead
        of the risk colors — one map at a time. ``None`` restores the risk map.
        Shape is ``(rows, cols)``, matching the probability frame.
        """
        self._confidence = sharpness
        self.update()

    # ----------------------------------------------------------- geometry

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

    # ---------------------------------------------------------- mouse

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        xy = self._xy_from_pos(event.position())
        if xy != self._hover:
            self._hover = xy
            if xy is None:
                self.cellHovered.emit(-1, -1, 0.0)
            else:
                p = self._prob_at(*xy)
                self.cellHovered.emit(xy[0], xy[1], p)
            self.update()

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.cellHovered.emit(-1, -1, 0.0)
            self.update()

    def _prob_at(self, x: int, y: int) -> float:
        if self._data is None:
            return 0.0
        rows, cols = self._data.shape
        if 0 <= y < rows and 0 <= x < cols:
            return float(self._data[y, x])
        return 0.0

    # ---------------------------------------------------------- paint

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.BG)
        cell, ox, oy = self._layout()

        cm = self._cell_map
        # Building base layer. Bound the loops by the cell_map's own shape as well
        # as rows/cols: a paintEvent must never raise (Qt turns it into qFatal),
        # so we stay in-bounds even if rows/cols transiently desync from cm.
        if cm is not None:
            cm_rows, cm_cols = cm.shape
            for r in range(min(self.rows, cm_rows)):
                for c in range(min(self.cols, cm_cols)):
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

        # Heat overlay — only on room/wall cells, only when prob is meaningful.
        if self._data is not None:
            rows, cols = self._data.shape
            conf = self._confidence
            for r in range(min(rows, self.rows)):
                for c in range(min(cols, self.cols)):
                    if (
                        cm is not None
                        and r < cm.shape[0]
                        and c < cm.shape[1]
                        and int(cm[r, c]) == OUTSIDE
                    ):
                        continue
                    prob = float(self._data[r, c])
                    if prob <= self.HEAT_THRESHOLD:
                        continue
                    # Same reachable cells in both modes; the toggle only swaps the
                    # color scale. Confidence view paints the green CI gradient
                    # (deep = sure) in place of the risk color — one map at a time.
                    # Bounds-checked so a transient shape desync can't raise here.
                    if conf is not None and r < conf.shape[0] and c < conf.shape[1]:
                        s = float(conf[r, c])
                        s = 0.0 if s < 0.0 else 1.0 if s > 1.0 else s
                        color = confidence_color(s)
                    else:
                        color = heat_color(prob)
                    p.fillRect(ox + c * cell, oy + r * cell, cell, cell, color)

        if cell >= 6 and cm is not None:
            p.setPen(QPen(self.LINE, 1))
            for c in range(self.cols + 1):
                x = ox + c * cell
                p.drawLine(x, oy, x, oy + self.rows * cell)
            for r in range(self.rows + 1):
                y = oy + r * cell
                p.drawLine(ox, y, ox + self.cols * cell, y)

        # Active sprinklers: a translucent sky-blue cell marking where suppression
        # is applied. Drawn under the shutter hatch so a cell carrying both keeps
        # the gold hatch legible on top; the alpha keeps any heat readable beneath.
        if self._sprinklers:
            fill = QColor(self.SPRINKLER)
            fill.setAlpha(95)
            p.setBrush(QBrush(fill))
            p.setPen(QPen(self.SPRINKLER, 1))
            for sx, sy in self._sprinklers:
                if 0 <= sx < self.cols and 0 <= sy < self.rows:
                    p.drawRect(ox + sx * cell, oy + sy * cell, cell, cell)

        # Fire shutters (방화벽): gold diagonal hatch + border, drawn on top of the
        # heat so a tripped shutter cell stays legible as structure even when the
        # surrounding cells are red. Distinct from orange heat and from gray walls.
        if self._shutters:
            p.setBrush(QBrush(self.SHUTTER, Qt.BrushStyle.BDiagPattern))
            p.setPen(QPen(self.SHUTTER, 2))
            for sx, sy in self._shutters:
                if 0 <= sx < self.cols and 0 <= sy < self.rows:
                    p.drawRect(ox + sx * cell, oy + sy * cell, cell, cell)

        # Inter-floor stairwell marker (drawn on every floor at the same cell).
        for sx, sy in self._stairs:
            if 0 <= sx < self.cols and 0 <= sy < self.rows:
                draw_stairs(p, ox + sx * cell, oy + sy * cell, cell)

        if self._hover is not None:
            hx, hy = self._hover
            p.setPen(QPen(self.HOVER, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(ox + hx * cell, oy + hy * cell, cell, cell)

        if self._ignition is not None:
            ix, iy = self._ignition
            cx = ox + ix * cell + cell // 2
            cy = oy + iy * cell + cell // 2
            radius = max(cell // 3, 3)
            p.setBrush(QBrush(QColor("#000000")))
            p.setPen(QPen(self.IGNITION, 1))
            p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self.BORDER, 1))
        p.drawRect(ox, oy, cell * self.cols, cell * self.rows)
