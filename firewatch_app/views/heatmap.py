"""Screen 4 — Heatmap (UC5/6/7)."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from firewatch.engine.result import wilson_interval
from firewatch_app.bridge.adapter import stairwell_cell
from firewatch_app.sample_data.floorplan_gen import get_layout
from firewatch_app.widgets.colorbar import HeatmapColorbar
from firewatch_app.widgets.heatmap_grid import HeatmapGrid

# Wall-clock seconds represented by one slider step, for the elapsed-time label.
# One snapshot spans 5 engine ticks (see adapter); holding the 10 s/tick mapping
# keeps the displayed timeline honest while the longer horizon reaches ~49 min.
SECONDS_PER_STEP = 50

# Confidence view: a cell whose 95% Wilson CI spans at least this much
# probability is treated as fully uncertain (most faded). Fixed in absolute
# probability units so the shading means the same thing across run counts — more
# runs shrink every CI, so the whole map reads sharper. (~0.30 = a 30-point
# spread, a genuinely wide interval.)
CI_WIDTH_REF = 0.30


def _confidence_frame(prob_frame: np.ndarray, n_runs: int) -> np.ndarray | None:
    """Per-cell confidence sharpness in [0,1] derived from the Wilson CI width.

    The cube frame value ``p`` is the fraction of ensemble runs that had ignited
    a cell, so ``count = round(p · n)`` recovers each cell's binomial success
    count; the *validated* engine ``wilson_interval`` then gives ``(lower, upper)``
    and the CI width is ``upper - lower``. Sharpness = ``1 - clamp(width / REF)``,
    so a narrow CI → 1.0 (vivid) and a wide CI → 0.0 (faint). Only ``n+1`` distinct
    counts are possible, so we build a width lookup with ``n+1`` engine calls and
    map the whole frame through it — vectorized, no per-cell Python loop.
    """
    if n_runs <= 0:
        return None
    counts = np.clip(np.rint(prob_frame * n_runs).astype(int), 0, n_runs)
    width_lut = np.empty(n_runs + 1, dtype=np.float32)
    for c in range(n_runs + 1):
        low, high = wilson_interval(c, n_runs)
        width_lut[c] = high - low
    width = width_lut[counts]
    return (1.0 - np.clip(width / CI_WIDTH_REF, 0.0, 1.0)).astype(np.float32)


class HeatmapView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: dict | None = None
        self._ensemble: np.ndarray | None = None
        self._shutter_active = True
        self._stairs: tuple[int, int] | None = None   # inter-floor stairwell cell
        self._ci_view = False          # confidence-interval shading toggle
        self._n_runs = 30              # ensemble N, needed for the Wilson width
        self._floor_idx = 0
        self._t_idx = 0
        self._t_zero: datetime | None = None
        self._build_ui()
        self._refresh()

    # ----------------------------------------------------------- public api

    def set_context(
        self,
        report: dict | None,
        ensemble: np.ndarray | None,
        parameters: dict | None = None,
        n_runs: int = 30,
    ) -> None:
        self._report = report
        self._ensemble = ensemble
        self._stairs = stairwell_cell(report["building"]) if report else None
        # Ensemble N drives the Wilson CI width; the toggle state itself is kept
        # on the view so floor/time changes (and a fresh run) preserve it.
        self._n_runs = int(n_runs) if n_runs else 30
        # Firewalls only form when shutters were active for this run, so the gold
        # hatch is shown only then (default-on when params are unspecified).
        self._shutter_active = True if parameters is None else bool(parameters.get("shutter", True))
        if report and report.get("ignition_time"):
            try:
                self._t_zero = datetime.strptime(
                    report["ignition_time"], "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                self._t_zero = None
        else:
            self._t_zero = None
        self._floor_idx = (
            report["building"].floors.index(report["floor"])
            if report and report["floor"] in report["building"].floors
            else 0
        )
        self._t_idx = 0

        cell_map = get_layout(report["building"].id) if report else None
        self.grid.set_layout(cell_map)

        self._rebuild_floor_tabs()
        self._refresh_slider_range()
        self._refresh()

    # ----------------------------------------------------------------- ui

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        host = QFrame()
        host.setObjectName("FloorplanPanel")
        v = QVBoxLayout(host)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        # --- floor tabs row ---
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(6)
        self.floor_tabs_layout = tabs_row
        self.floor_tabs_group = QButtonGroup(self)
        self.floor_tabs_group.setExclusive(True)
        self.floor_tabs_group.idToggled.connect(self._on_floor_changed)
        tabs_wrap = QHBoxLayout()
        tabs_wrap.setSpacing(8)
        tabs_wrap.addWidget(_label("층"))
        tabs_wrap.addLayout(tabs_row)
        tabs_wrap.addStretch(1)
        self.empty_label = QLabel("시뮬레이션 결과 없음 — 시뮬레이션을 먼저 실행하세요.")
        self.empty_label.setObjectName("FieldLabel")
        tabs_wrap.addWidget(self.empty_label)
        # Confidence-interval shading toggle (UC6). Color keeps encoding
        # probability; opacity encodes how tight each cell's Wilson CI is.
        self.ci_toggle = QPushButton("신뢰구간 보기")
        self.ci_toggle.setObjectName("FloorTab")
        self.ci_toggle.setCheckable(True)
        self.ci_toggle.setChecked(self._ci_view)
        self.ci_toggle.setFixedHeight(26)
        self.ci_toggle.toggled.connect(self._on_ci_toggled)
        tabs_wrap.addWidget(self.ci_toggle)
        v.addLayout(tabs_wrap)

        # --- grid + hover info ---
        self.hover_label = QLabel("")
        self.hover_label.setObjectName("HoverCoord")
        v.addWidget(self.hover_label, 0, Qt.AlignmentFlag.AlignRight)

        self.grid = HeatmapGrid()
        self.grid.cellHovered.connect(self._on_cell_hovered)
        v.addWidget(self.grid, 1)

        # --- time slider row ---
        time_row = QHBoxLayout()
        time_row.setSpacing(10)
        time_row.addWidget(_label("시각"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 0)
        self.time_slider.valueChanged.connect(self._on_time_changed)
        time_row.addWidget(self.time_slider, 1)
        self.time_label = QLabel("─")
        self.time_label.setObjectName("CoordDisplay")
        self.time_label.setMinimumWidth(180)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        time_row.addWidget(self.time_label)
        v.addLayout(time_row)

        # --- colorbar ---
        legend = QHBoxLayout()
        legend.setSpacing(8)
        self._legend_low = _legend_label("안전 0%")
        legend.addWidget(self._legend_low)
        self.colorbar = HeatmapColorbar()
        legend.addWidget(self.colorbar, 1)
        self._legend_mid = _legend_label("주의 50%")
        legend.addWidget(self._legend_mid)
        legend.addSpacing(8)
        self._legend_high = _legend_label("위험 100%")
        legend.addWidget(self._legend_high)
        v.addLayout(legend)

        outer.addWidget(host, 1)

    # -------------------------------------------------------- floor tabs

    def _rebuild_floor_tabs(self) -> None:
        # Clear existing
        while self.floor_tabs_layout.count():
            item = self.floor_tabs_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                self.floor_tabs_group.removeButton(w)
                w.deleteLater()
        if not self._report:
            return
        floors = list(self._report["building"].floors)
        for idx, name in enumerate(floors):
            btn = QPushButton(name)
            btn.setObjectName("FloorTab")
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.setMinimumWidth(40)
            self.floor_tabs_group.addButton(btn, idx)
            self.floor_tabs_layout.addWidget(btn)
            if idx == self._floor_idx:
                btn.setChecked(True)

    def _on_floor_changed(self, floor_idx: int, checked: bool) -> None:
        if not checked:
            return
        self._floor_idx = floor_idx
        self._refresh()

    def _on_ci_toggled(self, checked: bool) -> None:
        self._ci_view = checked
        self._apply_legend_mode()
        self._refresh()

    def _apply_legend_mode(self) -> None:
        """Swap the colorbar gradient + legend labels to match the active map."""
        if self._ci_view:
            self.colorbar.set_mode("confidence")
            self._legend_low.setText("불확실")
            self._legend_mid.setText("보통")
            self._legend_high.setText("확실")
        else:
            self.colorbar.set_mode("risk")
            self._legend_low.setText("안전 0%")
            self._legend_mid.setText("주의 50%")
            self._legend_high.setText("위험 100%")

    # ------------------------------------------------------ time slider

    def _refresh_slider_range(self) -> None:
        self.time_slider.blockSignals(True)
        if self._ensemble is None:
            self.time_slider.setRange(0, 0)
            self.time_slider.setValue(0)
        else:
            n_t = self._ensemble.shape[1]
            self.time_slider.setRange(0, n_t - 1)
            self.time_slider.setValue(0)
        self.time_slider.blockSignals(False)

    def _on_time_changed(self, value: int) -> None:
        self._t_idx = value
        self._refresh()

    # ---------------------------------------------------------- refresh

    def _refresh(self) -> None:
        has_data = self._ensemble is not None and self._report is not None
        self.empty_label.setVisible(not has_data)
        self.time_slider.setEnabled(has_data)
        self.ci_toggle.setEnabled(has_data)

        if not has_data:
            # Keep the grid's dims in sync with whatever layout is loaded so the
            # building outline can render before results arrive. Falling back to a
            # hardcoded 30x30 here would desync rows/cols from a non-square
            # cell_map and crash the paint with an out-of-bounds index.
            if self._report is not None:
                cols, rows = self._report["building"].grid_size
            else:
                cols, rows = 30, 30
            self.grid.set_shutters([])
            self.grid.set_stairs([])
            self.grid.set_confidence(None)
            self.grid.set_frame(None, cols, rows, None)
            self.time_label.setText("─")
            return

        building = self._report["building"]
        cols, rows = building.grid_size
        frame = self._ensemble[self._floor_idx, self._t_idx]
        ig_floor_idx = building.floors.index(self._report["floor"])
        ignition_xy = self._report["ignition_xy"] if self._floor_idx == ig_floor_idx else None
        floor_name = building.floors[self._floor_idx]
        shutters = (
            [
                (e.x, e.y)
                for e in building.equipment
                if e.type == "shutter" and e.floor == floor_name
            ]
            if self._shutter_active
            else []
        )
        self.grid.set_shutters(shutters)
        self.grid.set_stairs([self._stairs] if self._stairs else [])
        self.grid.set_confidence(
            _confidence_frame(frame, self._n_runs) if self._ci_view else None
        )
        self.grid.set_frame(frame, cols, rows, ignition_xy)

        # Update time label
        elapsed = self._t_idx * SECONDS_PER_STEP
        if self._t_zero is not None:
            wall = self._t_zero + timedelta(seconds=elapsed)
            wall_text = wall.strftime("%H:%M:%S")
        else:
            wall_text = "─"
        mm, ss = divmod(elapsed, 60)
        self.time_label.setText(f"+{mm:02d}:{ss:02d}   {wall_text}")

    # --------------------------------------------------------- hover

    def _on_cell_hovered(self, x: int, y: int, prob: float) -> None:
        if x < 0:
            self.hover_label.setText("")
        else:
            self.hover_label.setText(f"({x:>2}, {y:>2})  {prob * 100:5.1f}%")


# --- helpers ---------------------------------------------------------------

def _label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


def _legend_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("LegendLabel")
    return label
