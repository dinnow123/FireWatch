"""Screen 6 — Result summary (UC9).

Surfaces the *ensemble* value: not just how far fire spread, but the risk
distribution, the confidence (Wilson CI) of the estimate, which floor is worst,
and the spread dynamics — the design's "uncertainty quantification" intent.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from firewatch.engine.result import wilson_interval
from firewatch_app.sample_data.floorplan_gen import ROOM, WALL_WEAK, get_layout
from firewatch_app.widgets.charts import LineChart, RiskBar
from firewatch_app.widgets.section_diagram import SectionDiagram, project_section


class SummaryView(QWidget):
    AREA_THRESHOLD = 0.5    # cells with prob > this count as "burning area"
    HIGH = 0.70             # 고위험 분류 경계
    MID  = 0.30             # 중위험 하한

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: dict | None = None
        self._ensemble: np.ndarray | None = None
        self._n_runs = 30
        self._build_ui()
        self._refresh()

    def set_context(
        self,
        report: dict | None,
        ensemble: np.ndarray | None,
        n_runs: int = 30,
    ) -> None:
        self._report = report
        self._ensemble = ensemble
        self._n_runs = int(n_runs) if n_runs else 30
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

        self.empty_label = QLabel("시뮬레이션 결과 없음 — 시뮬레이션을 먼저 실행하세요.")
        self.empty_label.setObjectName("FieldLabel")
        v.addWidget(self.empty_label)

        body = QHBoxLayout()
        body.setSpacing(20)

        # ---- Left: scalar stats ----
        stats = QFrame()
        stats.setObjectName("InputPanel")
        stats.setFixedWidth(280)
        sv = QVBoxLayout(stats)
        sv.setContentsMargins(20, 20, 20, 20)
        sv.setSpacing(12)

        self.runs_label   = self._stat_block(sv, "앙상블 회차")
        self.area_label   = self._stat_block(sv, "화재 확산 면적 (1셀≈1㎡)")
        self.floors_label = self._stat_block(sv, "영향 받은 층 수")
        self.avg_label    = self._stat_block(sv, "평균 도달 확률")
        self.ci_label     = self._stat_block(sv, "평균 신뢰구간 (Wilson)")
        self.top_label    = self._stat_block(sv, "최위험 층 (확산 면적)")
        self.peak_label   = self._stat_block(sv, "최대 확산 시점")
        sv.addStretch(1)

        body.addWidget(stats)

        # ---- Right: charts ----
        right = QVBoxLayout()
        right.setSpacing(10)

        right.addWidget(_field_label("위험 등급별 셀 분포 — 고(>70%)/중(30~70%)/저(<30%)"))
        self.risk_bar = RiskBar()
        right.addWidget(self.risk_bar, 0)

        right.addWidget(_field_label("시간별 확산 면적 (㎡)"))
        self.line = LineChart()
        right.addWidget(self.line, 2)

        right.addWidget(_field_label("층별·열별 위험도 — 도달 확률 (열별 최대)"))
        self.section = SectionDiagram()
        right.addWidget(self.section, 3)

        body.addLayout(right, 1)
        v.addLayout(body, 1)

        outer.addWidget(host, 1)

    def _stat_block(self, parent_layout, label_text: str) -> QLabel:
        wrap = QFrame()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(2)

        lbl = QLabel(label_text)
        lbl.setObjectName("FieldLabel")
        lbl.setWordWrap(True)
        val = QLabel("─")
        val.setObjectName("StatValue")

        wrap_layout.addWidget(lbl)
        wrap_layout.addWidget(val)
        parent_layout.addWidget(wrap)
        return val

    # --------------------------------------------------------------- compute

    def _mean_ci_halfwidth(self, last: np.ndarray) -> float | None:
        """Mean Wilson CI half-width over reached cells (prob > 0). None if N/A.

        Reuses the engine's validated ``wilson_interval``: counts = round(p·N),
        so only N+1 distinct widths exist — build them once and index the frame.
        """
        n = self._n_runs
        reached = last > 0.0
        if n <= 0 or not reached.any():
            return None
        half_lut = np.empty(n + 1, dtype=np.float64)
        for c in range(n + 1):
            low, high = wilson_interval(c, n)
            half_lut[c] = (high - low) / 2.0
        counts = np.clip(np.rint(last * n).astype(int), 0, n)
        return float(half_lut[counts][reached].mean())

    def _refresh(self) -> None:
        if self._ensemble is None or self._report is None:
            self.empty_label.setVisible(True)
            for lbl in (self.runs_label, self.area_label, self.floors_label,
                        self.avg_label, self.ci_label, self.top_label, self.peak_label):
                lbl.setText("─")
            self.risk_bar.set_counts(0, 0, 0)
            self.line.set_series([])
            self.section.set_section([], None)
            return

        self.empty_label.setVisible(False)
        e = self._ensemble                # (F, T, R, C)
        last = e[:, -1]                   # (F, R, C)
        floors = list(self._report["building"].floors)
        cell_map = get_layout(self._report["building"].id)   # (R, C)
        burnable = (cell_map == ROOM) | (cell_map == WALL_WEAK)

        self.runs_label.setText(f"{self._n_runs}회 기반")

        burning_mask_last = last > self.AREA_THRESHOLD
        self.area_label.setText(f"{int(burning_mask_last.sum()):,} ㎡")

        affected = int(burning_mask_last.reshape(last.shape[0], -1).any(axis=1).sum())
        self.floors_label.setText(f"{affected} / {e.shape[0]}")

        self.avg_label.setText(f"{float(last.mean()) * 100:.1f}%")

        half = self._mean_ci_halfwidth(last)
        self.ci_label.setText("─" if half is None else f"±{half * 100:.1f}%")

        # Risk distribution over the building's burnable cells (all floors).
        bmask = burnable[None]
        high = int(((last > self.HIGH) & bmask).sum())
        mid  = int(((last > self.MID) & (last <= self.HIGH) & bmask).sum())
        low  = int(((last <= self.MID) & bmask).sum())
        self.risk_bar.set_counts(high, mid, low)

        # Most dangerous floor by spread area (reached cells, 1 cell ≈ 1 ㎡).
        spread = (last > 0.0).reshape(e.shape[0], -1).sum(axis=1)
        if int(spread.max()) > 0:
            f = int(spread.argmax())
            self.top_label.setText(f"{floors[f]}  ({int(spread[f]):,} ㎡)")
        else:
            self.top_label.setText("─")

        # Spread dynamics — burning cells per tick + peak growth tick.
        per_t = (e > self.AREA_THRESHOLD).reshape(e.shape[0], e.shape[1], -1).sum(axis=(0, 2))
        self.line.set_series(per_t.tolist(), x_label="t (step)")
        if per_t.size >= 2:
            growth = np.diff(per_t)
            t_peak = int(growth.argmax()) + 1
            self.peak_label.setText(f"t={t_peak}  (+{int(growth.max()):,} ㎡)")
        else:
            self.peak_label.setText("─")

        # Floor × column elevation (cropped to the burnable footprint).
        section = project_section(last, cell_map)
        self.section.set_section(list(reversed(floors)), section[::-1])


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label
