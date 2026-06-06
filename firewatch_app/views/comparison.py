"""Screen 7 — Scenario comparison (UC10).

Side-by-side: base scenario (whatever the user already ran) vs. a re-run with a
different parameter set. Below, a per-cell difference (compare − base) so the
operator can read where each toggle helps or hurts.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from firewatch.domain import Scenario
from firewatch_app.bridge.adapter import params_to_simparameters
from firewatch_app.sample_data.floorplan_gen import get_layout
from firewatch_app.views._async import EnsembleWorker
from firewatch_app.widgets.delta_grid import DeltaGrid
from firewatch_app.widgets.heatmap_grid import HeatmapGrid


class ComparisonView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: dict | None = None
        self._base_params: dict | None = None
        self._compare_params: dict | None = None
        self._base_ensemble: np.ndarray | None = None
        self._compare_ensemble: np.ndarray | None = None
        self._floor_idx = 0
        self._t_idx = 0
        self._run_thread: QThread | None = None
        self._run_worker: EnsembleWorker | None = None
        self._build_ui()
        self._refresh()

    # --------------------------------------------------------- public

    def set_context(
        self,
        report: dict | None,
        base_params: dict | None,
        base_ensemble: np.ndarray | None,
    ) -> None:
        self._report = report
        self._base_params = dict(base_params) if base_params else None
        self._base_ensemble = base_ensemble
        self._compare_ensemble = None
        self._compare_params = None

        cell_map = get_layout(report["building"].id) if report else None
        self.base_grid.set_layout(cell_map)
        self.compare_grid.set_layout(cell_map)
        self.delta_grid.set_layout(cell_map)

        self._floor_idx = (
            report["building"].floors.index(report["floor"])
            if report and report["floor"] in report["building"].floors
            else 0
        )
        self._t_idx = (base_ensemble.shape[1] - 1) if base_ensemble is not None else 0

        self._rebuild_floor_tabs()
        self._refresh_slider_range()
        self._reset_param_panel()
        self._refresh()

    # --------------------------------------------------------------- ui

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        host = QFrame()
        host.setObjectName("FloorplanPanel")
        v = QVBoxLayout(host)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)

        # ---- top control bar ----
        ctrl = QHBoxLayout()
        ctrl.setSpacing(14)
        ctrl.addWidget(_field_label("비교 시나리오 설정"))
        self.cb_sprinkler = QCheckBox("스프링클러")
        self.cb_shutter   = QCheckBox("방화셔터")
        for cb in (self.cb_sprinkler, self.cb_shutter):
            ctrl.addWidget(cb)
        ctrl.addStretch(1)
        self.run_btn = QPushButton("비교 실행")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._on_run_compare)
        ctrl.addWidget(self.run_btn)
        v.addLayout(ctrl)

        self.empty_label = QLabel("시뮬레이션 결과 없음 — 시뮬레이션을 먼저 실행하세요.")
        self.empty_label.setObjectName("FieldLabel")
        v.addWidget(self.empty_label)

        # ---- floor tabs ----
        floor_row = QHBoxLayout()
        floor_row.setSpacing(8)
        floor_row.addWidget(_field_label("층"))
        self.floor_tabs_layout = QHBoxLayout()
        self.floor_tabs_layout.setSpacing(6)
        floor_row.addLayout(self.floor_tabs_layout)
        floor_row.addStretch(1)
        v.addLayout(floor_row)

        self.floor_tabs_group = QButtonGroup(self)
        self.floor_tabs_group.setExclusive(True)
        self.floor_tabs_group.idToggled.connect(self._on_floor_changed)

        # ---- two heatmaps side by side ----
        grids = QHBoxLayout()
        grids.setSpacing(14)
        grids.addLayout(self._build_grid_block("기준 시나리오", "base"))
        grids.addLayout(self._build_grid_block("비교 시나리오", "compare"))
        v.addLayout(grids, 4)

        # ---- time slider ----
        time_row = QHBoxLayout()
        time_row.setSpacing(10)
        time_row.addWidget(_field_label("시각"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 0)
        self.time_slider.valueChanged.connect(self._on_time_changed)
        time_row.addWidget(self.time_slider, 1)
        self.time_label = QLabel("─")
        self.time_label.setObjectName("CoordDisplay")
        self.time_label.setMinimumWidth(80)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        time_row.addWidget(self.time_label)
        v.addLayout(time_row)

        # ---- delta grid ----
        delta_head = QHBoxLayout()
        delta_head.addWidget(_field_label("Δ — 비교가 더 위험하면 빨강, 더 안전하면 파랑"))
        delta_head.addStretch(1)
        self.delta_summary = QLabel("")
        self.delta_summary.setObjectName("HoverCoord")
        delta_head.addWidget(self.delta_summary)
        v.addLayout(delta_head)

        self.delta_grid = DeltaGrid()
        v.addWidget(self.delta_grid, 3)

        outer.addWidget(host, 1)

    def _build_grid_block(self, title: str, role: str) -> QVBoxLayout:
        wrap = QVBoxLayout()
        wrap.setSpacing(4)
        wrap.addWidget(_field_label(title))
        grid = HeatmapGrid()
        if role == "base":
            self.base_grid = grid
        else:
            self.compare_grid = grid
        wrap.addWidget(grid, 1)
        return wrap

    # ------------------------------------------------- floor & time

    def _rebuild_floor_tabs(self) -> None:
        while self.floor_tabs_layout.count():
            item = self.floor_tabs_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                self.floor_tabs_group.removeButton(w)
                w.deleteLater()
        if not self._report:
            return
        for idx, name in enumerate(self._report["building"].floors):
            btn = QPushButton(name)
            btn.setObjectName("FloorTab")
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.setMinimumWidth(40)
            self.floor_tabs_group.addButton(btn, idx)
            self.floor_tabs_layout.addWidget(btn)
            if idx == self._floor_idx:
                btn.setChecked(True)

    def _on_floor_changed(self, idx: int, checked: bool) -> None:
        if not checked:
            return
        self._floor_idx = idx
        self._refresh()

    def _refresh_slider_range(self) -> None:
        self.time_slider.blockSignals(True)
        if self._base_ensemble is None:
            self.time_slider.setRange(0, 0)
        else:
            n_t = self._base_ensemble.shape[1]
            self.time_slider.setRange(0, n_t - 1)
            self.time_slider.setValue(self._t_idx)
        self.time_slider.blockSignals(False)

    def _on_time_changed(self, value: int) -> None:
        self._t_idx = value
        self._refresh()

    def _reset_param_panel(self) -> None:
        if not self._base_params:
            for cb in (self.cb_sprinkler, self.cb_shutter):
                cb.setChecked(False)
            return
        # Default the comparison panel to the OPPOSITE of base for the suppressors
        # so a user can immediately see what flipping the switches does.
        self.cb_sprinkler.setChecked(not bool(self._base_params.get("sprinkler")))
        self.cb_shutter.setChecked(not bool(self._base_params.get("shutter")))

    # ----------------------------------------------------- run compare

    def _gather_compare_params(self) -> dict:
        return {
            "sprinkler": self.cb_sprinkler.isChecked(),
            "shutter":   self.cb_shutter.isChecked(),
        }

    def _make_scenario(self, params: dict | None, cube: np.ndarray) -> Scenario:
        """Bundle a finished run (its params + reach-probability cube) as a Scenario."""
        return Scenario(params_to_simparameters(params), cube)

    def _on_run_compare(self) -> None:
        if not self._report or self._base_ensemble is None:
            return
        if self._run_thread is not None:  # a compare run is already in flight
            return
        params = self._gather_compare_params()
        self._compare_params = params
        b = self._report["building"]

        self.run_btn.setEnabled(False)
        self.run_btn.setText("비교 실행 중…")
        self._run_thread = QThread(self)
        self._run_worker = EnsembleWorker(
            b, self._report["floor"], self._report["ignition_xy"],
            params,
            seed=43,   # different draw than the base run
        )
        self._run_worker.moveToThread(self._run_thread)
        self._run_thread.started.connect(self._run_worker.run)
        self._run_worker.finished.connect(self._on_compare_ready)
        self._run_worker.failed.connect(self._on_compare_failed)
        self._run_thread.start()

    def _on_compare_ready(self, cube) -> None:
        self._teardown_run_thread()
        self.run_btn.setText("비교 실행")
        self._compare_ensemble = cube
        self._refresh()

    def _on_compare_failed(self, message: str) -> None:
        self._teardown_run_thread()
        self.run_btn.setText("비교 실행")
        self._refresh()
        QMessageBox.critical(self, "비교 오류", f"비교 시나리오 계산 실패:\n{message}")

    def _teardown_run_thread(self) -> None:
        if self._run_thread is not None:
            self._run_thread.quit()
            self._run_thread.wait()
            self._run_thread = None
        self._run_worker = None

    # ----------------------------------------------------------- refresh

    def _floor_shutters(self, building, floor_name: str, params: dict | None) -> list:
        """Shutter cells for a scenario — empty when that scenario disables shutters."""
        active = True if params is None else bool(params.get("shutter", True))
        if not active:
            return []
        return [
            (e.x, e.y)
            for e in building.equipment
            if e.type == "shutter" and e.floor == floor_name
        ]

    def _refresh(self) -> None:
        has_base = self._base_ensemble is not None and self._report is not None
        self.empty_label.setVisible(not has_base)
        self.run_btn.setEnabled(has_base)
        self.time_slider.setEnabled(has_base)
        for cb in (self.cb_sprinkler, self.cb_shutter):
            cb.setEnabled(has_base)

        if not has_base:
            # Match the grids' dims to the loaded layout so a non-square building
            # outline can render before results arrive. Hardcoding 30×30 here
            # would desync rows/cols from a non-square cell_map (e.g. BLDG002
            # 35×25) and crash the paint with an out-of-bounds index.
            if self._report is not None:
                cols, rows = self._report["building"].grid_size
            else:
                cols, rows = 30, 30
            self.base_grid.set_shutters([])
            self.compare_grid.set_shutters([])
            self.base_grid.set_frame(None, cols, rows, None)
            self.compare_grid.set_frame(None, cols, rows, None)
            self.delta_grid.set_delta(None, cols, rows)
            self.time_label.setText("─")
            self.delta_summary.setText("")
            return

        building = self._report["building"]
        cols, rows = building.grid_size
        floor_name = building.floors[self._floor_idx]
        ig_floor_idx = building.floors.index(self._report["floor"])
        ignition_xy = self._report["ignition_xy"] if self._floor_idx == ig_floor_idx else None

        base_frame = self._base_ensemble[self._floor_idx, self._t_idx]
        self.base_grid.set_shutters(self._floor_shutters(building, floor_name, self._base_params))
        self.base_grid.set_frame(base_frame, cols, rows, ignition_xy)

        if self._compare_ensemble is not None:
            cmp_frame = self._compare_ensemble[self._floor_idx, self._t_idx]
            self.compare_grid.set_shutters(
                self._floor_shutters(building, floor_name, self._compare_params)
            )
            self.compare_grid.set_frame(cmp_frame, cols, rows, ignition_xy)

            # UC10: the view bundles each run as a domain Scenario and asks it for
            # the per-cell Δ, then shows the current floor/time frame of the result.
            # The view no longer subtracts cubes itself.
            base_scn = self._make_scenario(self._base_params, self._base_ensemble)
            cmp_scn = self._make_scenario(self._compare_params, self._compare_ensemble)
            delta = cmp_scn.compute_delta(base_scn)[self._floor_idx, self._t_idx]
            self.delta_grid.set_delta(delta, cols, rows)

            mean_delta = float(delta.mean())
            sign = "+" if mean_delta >= 0 else "−"
            self.delta_summary.setText(
                f"평균 Δ {sign}{abs(mean_delta) * 100:.2f}%   "
                f"위험↑ 셀 {int((delta > 0.05).sum())}   "
                f"안전↑ 셀 {int((delta < -0.05).sum())}"
            )
        else:
            self.compare_grid.set_shutters([])
            self.compare_grid.set_frame(None, cols, rows, None)
            self.delta_grid.set_delta(None, cols, rows)
            self.delta_summary.setText("비교 실행 전")

        self.time_label.setText(f"t = {self._t_idx:02d}")


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label
