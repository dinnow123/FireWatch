"""Lightweight chart widgets — line and per-floor bars. Custom QPainter, no deps."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from firewatch_app.widgets.heatmap_grid import heat_color


class LineChart(QWidget):
    BG     = QColor("#0d1117")
    AXIS   = QColor("#30363d")
    GRID   = QColor("#1f2731")
    LINE_C = QColor("#10b981")
    FILL   = QColor(16, 185, 129, 38)
    LABEL  = QColor("#8b949e")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series: list[float] = []
        self._max_y: float = 1.0
        self._x_label: str = ""
        self.setMinimumHeight(140)

    def set_series(self, series, x_label: str = "") -> None:
        self._series = list(series)
        self._max_y = max(max(self._series) if self._series else 1.0, 1.0)
        self._x_label = x_label
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), self.BG)
        if len(self._series) < 2:
            return

        ml, mr, mt, mb = 52, 14, 14, 22
        w = self.width() - ml - mr
        h = self.height() - mt - mb
        y_axis = self.height() - mb

        # Horizontal gridlines
        p.setPen(QPen(self.GRID, 1, Qt.PenStyle.DotLine))
        for k in (1, 2, 3):
            yk = mt + (h * k) // 4
            p.drawLine(ml, yk, ml + w, yk)

        # Axis lines
        p.setPen(QPen(self.AXIS, 1))
        p.drawLine(ml, mt, ml, y_axis)
        p.drawLine(ml, y_axis, ml + w, y_axis)

        # Build the path
        n = len(self._series)
        path = QPainterPath()
        for i, v in enumerate(self._series):
            x = ml + (w * i) / (n - 1)
            y = y_axis - (h * v) / self._max_y
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        fill = QPainterPath(path)
        fill.lineTo(ml + w, y_axis)
        fill.lineTo(ml, y_axis)
        fill.closeSubpath()
        p.fillPath(fill, self.FILL)

        p.setPen(QPen(self.LINE_C, 2))
        p.drawPath(path)

        # Y axis labels: 0 and max
        p.setFont(QFont("IBM Plex Mono", 9))
        p.setPen(QPen(self.LABEL, 1))
        p.drawText(
            0, mt - 6, ml - 6, 14,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            f"{int(self._max_y):,}",
        )
        p.drawText(
            0, y_axis - 7, ml - 6, 14,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            "0",
        )

        if self._x_label:
            p.drawText(
                ml, y_axis + 4, w, 16,
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop,
                self._x_label,
            )


class FloorBars(QWidget):
    BG    = QColor("#0d1117")
    TRACK = QColor("#161b22")
    LABEL = QColor("#e6edf3")
    LABEL_DIM = QColor("#8b949e")
    THRESHOLD = 0.70

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, float]] = []
        self.setMinimumHeight(160)

    def set_data(self, data: list[tuple[str, float]]) -> None:
        self._data = list(data)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), self.BG)
        if not self._data:
            return

        n = len(self._data)
        ml = 50
        mr = 64
        mt = 6
        mb = 6
        avail_h = self.height() - mt - mb
        row_h = max(avail_h // n, 14)
        bar_w = self.width() - ml - mr
        bar_h = max(row_h - 6, 8)

        font_mono = QFont("IBM Plex Mono", 11)

        for i, (name, v) in enumerate(self._data):
            v = max(0.0, min(1.0, float(v)))
            y = mt + i * row_h
            cy = y + (row_h - bar_h) // 2

            p.setFont(font_mono)
            p.setPen(QPen(self.LABEL, 1))
            p.drawText(
                0, y, ml - 8, row_h,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                name,
            )

            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(ml, cy, bar_w, bar_h, self.TRACK)
            p.fillRect(ml, cy, int(bar_w * v), bar_h, heat_color(v))

            label_color = self.LABEL if v >= self.THRESHOLD else self.LABEL_DIM
            p.setPen(QPen(label_color, 1))
            p.drawText(
                ml + bar_w + 6, y, mr - 6, row_h,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"{v * 100:5.1f}%",
            )


class RiskBar(QWidget):
    """Single stacked bar of the high/mid/low risk-cell counts + a legend.

    Segment widths are proportional to the counts; colors are fixed to the risk
    level (red 고위험 / orange 중위험 / gray 저위험), not to the count, so the bar
    reads as a distribution at a glance.
    """
    BG     = QColor("#0d1117")
    TRACK  = QColor("#161b22")
    LABEL  = QColor("#e6edf3")
    HIGH_C = QColor("#dc2626")   # 고위험 >70%
    MID_C  = QColor("#f97316")   # 중위험 30~70%
    LOW_C  = QColor("#6b7280")   # 저위험 <30%

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._high = self._mid = self._low = 0
        self.setMinimumHeight(64)

    def set_counts(self, high: int, mid: int, low: int) -> None:
        self._high, self._mid, self._low = int(high), int(mid), int(low)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), self.BG)

        total = self._high + self._mid + self._low
        ml, mr, mt = 8, 8, 6
        bar_w = self.width() - ml - mr
        bar_h = 18
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(ml, mt, bar_w, bar_h, self.TRACK)
        if total > 0:
            x = ml
            for count, color in (
                (self._high, self.HIGH_C), (self._mid, self.MID_C), (self._low, self.LOW_C)
            ):
                seg = int(round(bar_w * count / total))
                if seg > 0:
                    p.fillRect(x, mt, seg, bar_h, color)
                    x += seg

        # Legend: colored swatch + "label N" for each band.
        p.setFont(QFont("IBM Plex Mono", 10))
        ly = mt + bar_h + 12
        x = ml
        for label, count, color in (
            ("고위험", self._high, self.HIGH_C),
            ("중위험", self._mid, self.MID_C),
            ("저위험", self._low, self.LOW_C),
        ):
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(x, ly, 10, 10, color)
            p.setPen(QPen(self.LABEL, 1))
            text = f" {label} {count:,}"
            p.drawText(x + 12, ly - 1, 150, 14,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            x += 12 + 8 * len(text) + 8
