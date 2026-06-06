"""Screen 3 — Run Ensemble (UC4). Simulated progress over a few seconds."""
from __future__ import annotations

import random
from datetime import datetime

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# Spec UC4 / EnsembleRunner: the ensemble runs 20–50 times. Default 30 matches
# the UI mockup text in Analysis 4.4.1 ("회차 N/30", "30회 완료").
MIN_RUNS     = 20
MAX_RUNS     = 50
DEFAULT_RUNS = 30
TICK_MS      = 120   # ~120 ms per simulated run


class SimulationView(QWidget):
    simulationFinished = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: dict | None = None
        self._parameters: dict | None = None
        self._current_run = 0
        self._total_runs = DEFAULT_RUNS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._build_ui()
        self._refresh_summary()

    # -------------------------------------------------------- public set_context

    def set_context(self, report: dict | None, parameters: dict | None) -> None:
        self._report = report
        self._parameters = parameters
        self._refresh_summary()

    # -------------------------------------------------------------------- ui

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        host = QFrame()
        host.setObjectName("FloorplanPanel")
        v = QVBoxLayout(host)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        v.addWidget(_field_label("신고 정보"))
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("BuildingInfo")
        self.summary_label.setWordWrap(True)
        v.addWidget(self.summary_label)

        v.addSpacing(4)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)
        self.start_btn = QPushButton("시뮬레이션 시작")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setMinimumHeight(34)
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setEnabled(False)
        ctrl_row.addWidget(self.start_btn)
        ctrl_row.addWidget(self.cancel_btn)
        ctrl_row.addSpacing(12)

        ctrl_row.addWidget(_field_label("회차"))
        self.run_spin = QSpinBox()
        self.run_spin.setRange(MIN_RUNS, MAX_RUNS)
        self.run_spin.setValue(DEFAULT_RUNS)
        self.run_spin.setSingleStep(1)
        self.run_spin.setSuffix(" 회")
        self.run_spin.setFixedWidth(84)
        self.run_spin.valueChanged.connect(self._on_runs_changed)
        ctrl_row.addWidget(self.run_spin)
        ctrl_row.addStretch(1)

        self.run_label = QLabel(f"0 / {self._total_runs}")
        self.run_label.setObjectName("CoordDisplay")
        ctrl_row.addWidget(self.run_label)
        v.addLayout(ctrl_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, self._total_runs)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        v.addWidget(self.progress)

        v.addSpacing(4)
        v.addWidget(_field_label("로그"))

        self.log = QTextEdit()
        self.log.setObjectName("LogConsole")
        self.log.setReadOnly(True)
        v.addWidget(self.log, 1)

        outer.addWidget(host, 1)

        self.start_btn.clicked.connect(self._start)
        self.cancel_btn.clicked.connect(self._cancel)

    # ------------------------------------------------------------- summary

    def _refresh_summary(self) -> None:
        if not self._report:
            self.summary_label.setText("신고 정보 없음 — 신고 입력 화면에서 먼저 등록하세요.")
            # Keep the button clickable so pressing it prompts the user to file a report.
            self.start_btn.setEnabled(not self._timer.isActive())
            return

        b = self._report["building"]
        floor = self._report["floor"]
        x, y = self._report["ignition_xy"]
        time = self._report["ignition_time"]

        if self._parameters:
            mark = lambda flag: "켜짐" if flag else "꺼짐"
            param_text = (
                f"스프링클러 {mark(self._parameters['sprinkler'])}, "
                f"방화셔터 {mark(self._parameters['shutter'])}"
            )
        else:
            param_text = "기본값"

        self.summary_label.setText(
            f"건물 — {b.name} ({b.address})\n"
            f"발화 — {floor} ({x}, {y}) · {time}\n"
            f"파라미터 — {param_text}"
        )
        self.start_btn.setEnabled(not self._timer.isActive())

    # ------------------------------------------------------- run count

    def _on_runs_changed(self, value: int) -> None:
        self._total_runs = value
        self.progress.setRange(0, value)
        self.progress.setValue(0)
        self.run_label.setText(f"0 / {value}")

    # ------------------------------------------------------------- run loop

    def _start(self) -> None:
        if not self._report:
            QMessageBox.warning(self, "신고 필요", "신고를 입력해주십시오.")
            return
        self._current_run = 0
        self.progress.setRange(0, self._total_runs)
        self.progress.setValue(0)
        self.run_label.setText(f"0 / {self._total_runs}")
        self.log.clear()
        self._append(f"시뮬레이션 엔진 초기화 — 앙상블 {self._total_runs}회")
        self._append("앙상블 시뮬레이션 시작")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.run_spin.setEnabled(False)
        self._timer.start(TICK_MS)

    def _cancel(self) -> None:
        if not self._timer.isActive():
            return
        self._timer.stop()
        self.cancel_btn.setEnabled(False)
        self.start_btn.setEnabled(True)
        self.run_spin.setEnabled(True)
        self._append("사용자 취소 — 진행 결과 폐기")

    def _tick(self) -> None:
        self._current_run += 1
        self.progress.setValue(self._current_run)
        self.run_label.setText(f"{self._current_run} / {self._total_runs}")

        if (
            self._current_run == 1
            or self._current_run % 5 == 0
            or self._current_run == self._total_runs
        ):
            cells = 90 + self._current_run * 8 + random.randint(-6, 6)
            self._append(
                f"회차 {self._current_run}/{self._total_runs} 완료 — 도달 셀 {cells}"
            )

        if self._current_run >= self._total_runs:
            self._timer.stop()
            self.cancel_btn.setEnabled(False)
            self.start_btn.setEnabled(True)
            self.run_spin.setEnabled(True)
            self._append("앙상블 결과 종합 완료")
            self.simulationFinished.emit({"runs": self._total_runs})

    def _append(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"{ts}  {msg}")


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label
