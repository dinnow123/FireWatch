"""Screen 5 — Building section view (UC8).

Time-linked like the heatmap: the slider scrubs the ensemble's tick axis and the
stacked section redraws each floor's top-10% reach probability at that tick, so
the chimney effect (upper floors heating up as time advances) reads off the
vertical stack over time.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from firewatch_app.sample_data.floorplan_gen import get_layout
from firewatch_app.widgets.section_diagram import SectionDiagram, project_section


class SectionView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: dict | None = None
        self._ensemble: np.ndarray | None = None
        self._t_idx = 0
        self._build_ui()
        self._refresh()

    def set_context(self, report: dict | None, ensemble: np.ndarray | None) -> None:
        self._report = report
        self._ensemble = ensemble
        self._t_idx = 0
        self._refresh_slider_range()
        self._refresh()

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        host = QFrame()
        host.setObjectName("FloorplanPanel")
        v = QVBoxLayout(host)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(_field_label("건물 단면도 — 도달 확률 (열별 최대)"))
        head.addStretch(1)
        self.empty_label = QLabel("시뮬레이션 결과 없음 — 시뮬레이션을 먼저 실행하세요.")
        self.empty_label.setObjectName("FieldLabel")
        head.addWidget(self.empty_label)
        v.addLayout(head)

        self.diagram = SectionDiagram()
        v.addWidget(self.diagram, 1)

        # --- time slider row (mirrors the heatmap scrubber) ---
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
        self.time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        time_row.addWidget(self.time_label)
        v.addLayout(time_row)

        outer.addWidget(host, 1)

    # ------------------------------------------------------ time slider

    def _refresh_slider_range(self) -> None:
        self.time_slider.blockSignals(True)
        if self._ensemble is None:
            self.time_slider.setRange(0, 0)
        else:
            self.time_slider.setRange(0, self._ensemble.shape[1] - 1)
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
            self.diagram.set_section([], None)
            self.time_label.setText("─")
            return

        floors = list(self._report["building"].floors)
        frame = self._ensemble[:, self._t_idx]   # (n_floors, rows, cols)
        # Max-intensity projection over the depth (rows), cropped to the building's
        # columns: each (floor, col) keeps the hottest cell in that vertical slice,
        # so the elevation shows *where* along the building width fire reaches —
        # without the surrounding-land OUTSIDE gutters. Top floor drawn first.
        cell_map = get_layout(self._report["building"].id)
        section = project_section(frame, cell_map)   # (n_floors, n_building_cols)
        self.diagram.set_section(list(reversed(floors)), section[::-1])

        n_t = self._ensemble.shape[1]
        self.time_label.setText(f"t = {self._t_idx:02d} / {n_t - 1:02d}")


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label
