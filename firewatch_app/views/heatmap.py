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

from firewatch_app.sample_data.floorplan_gen import get_layout
from firewatch_app.widgets.colorbar import HeatmapColorbar
from firewatch_app.widgets.heatmap_grid import HeatmapGrid

# Wall-clock seconds represented by one slider step, for the elapsed-time label.
# One snapshot spans 5 engine ticks (see adapter); holding the 10 s/tick mapping
# keeps the displayed timeline honest while the longer horizon reaches ~49 min.
SECONDS_PER_STEP = 50


class HeatmapView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: dict | None = None
        self._ensemble: np.ndarray | None = None
        self._shutter_active = True
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
    ) -> None:
        self._report = report
        self._ensemble = ensemble
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
        legend.addWidget(_legend_label("안전 0%"))
        self.colorbar = HeatmapColorbar()
        legend.addWidget(self.colorbar, 1)
        legend.addWidget(_legend_label("주의 50%"))
        legend.addSpacing(8)
        legend.addWidget(_legend_label("위험 100%"))
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
