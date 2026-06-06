"""Screen 6 — Result summary (UC9)."""
from __future__ import annotations

import numpy as np
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from firewatch_app.widgets.charts import FloorBars, LineChart


class SummaryView(QWidget):
    AREA_THRESHOLD = 0.5    # cells with prob > this count as "burning area"
    HOT_THRESHOLD  = 0.7    # cells with prob >= this count as "hot"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: dict | None = None
        self._ensemble: np.ndarray | None = None
        self._build_ui()
        self._refresh()

    def set_context(self, report: dict | None, ensemble: np.ndarray | None) -> None:
        self._report = report
        self._ensemble = ensemble
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

        # ---- Left: stats ----
        stats = QFrame()
        stats.setObjectName("InputPanel")
        stats.setFixedWidth(280)
        sv = QVBoxLayout(stats)
        sv.setContentsMargins(20, 20, 20, 20)
        sv.setSpacing(14)

        self.area_label   = self._stat_block(sv, "화재 확산 면적")
        self.floors_label = self._stat_block(sv, "영향 받은 층 수")
        self.avg_label    = self._stat_block(sv, "평균 도달 확률")
        self.hot_label    = self._stat_block(sv, "위험 셀 수 (≥70%)")
        sv.addStretch(1)

        body.addWidget(stats)

        # ---- Right: charts ----
        right = QVBoxLayout()
        right.setSpacing(10)

        right.addWidget(_field_label("시간별 확산 면적 (m²)"))
        self.line = LineChart()
        right.addWidget(self.line, 2)

        right.addWidget(_field_label("층별 위험도 — 도달 확률 상위 10% 평균"))
        self.bars = FloorBars()
        right.addWidget(self.bars, 3)

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
        val = QLabel("─")
        val.setObjectName("StatValue")

        wrap_layout.addWidget(lbl)
        wrap_layout.addWidget(val)
        parent_layout.addWidget(wrap)
        return val

    # --------------------------------------------------------------- compute

    def _refresh(self) -> None:
        if self._ensemble is None or self._report is None:
            self.empty_label.setVisible(True)
            for lbl in (self.area_label, self.floors_label, self.avg_label, self.hot_label):
                lbl.setText("─")
            self.line.set_series([])
            self.bars.set_data([])
            return

        self.empty_label.setVisible(False)
        e = self._ensemble                # (F, T, R, C)
        last = e[:, -1]                   # (F, R, C)

        burning_mask_last = last > self.AREA_THRESHOLD
        area_cells = int(burning_mask_last.sum())
        self.area_label.setText(f"{area_cells:,} m²")

        affected = int(burning_mask_last.reshape(last.shape[0], -1).any(axis=1).sum())
        total_floors = e.shape[0]
        self.floors_label.setText(f"{affected} / {total_floors}")

        self.avg_label.setText(f"{float(last.mean()) * 100:.1f}%")

        hot = int((last >= self.HOT_THRESHOLD).sum())
        self.hot_label.setText(f"{hot:,}")

        # Time series — burning cells per timestep.
        per_t = (e > self.AREA_THRESHOLD).reshape(e.shape[0], e.shape[1], -1).sum(axis=(0, 2))
        self.line.set_series(per_t.tolist(), x_label="t (step)")

        # Per-floor risk (top-10% mean, top floor first).
        floors = self._report["building"].floors
        risks: list[tuple[str, float]] = []
        for f, name in enumerate(floors):
            flat = last[f].ravel()
            k = max(1, int(flat.size * 0.10))
            top = np.partition(flat, -k)[-k:]
            risks.append((name, float(top.mean())))
        risks.reverse()
        self.bars.set_data(risks)


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label
