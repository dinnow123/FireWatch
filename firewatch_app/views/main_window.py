"""FireWatch main window — sidebar + stacked main area."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from firewatch_app.views._async import EnsembleWorker
from firewatch_app.views.comparison import ComparisonView
from firewatch_app.views.heatmap import HeatmapView
from firewatch_app.views.parameters import ParametersView
from firewatch_app.views.report_input import ReportInputView
from firewatch_app.views.section import SectionView
from firewatch_app.views.simulation import SimulationView
from firewatch_app.views.summary import SummaryView


# --- screen registry --------------------------------------------------------

@dataclass(frozen=True)
class ScreenSpec:
    key: str
    label: str
    code: str
    commander_only: bool


SCREENS: tuple[ScreenSpec, ...] = (
    ScreenSpec("report",     "신고 입력",       "UC-01/02", commander_only=True),
    ScreenSpec("parameters", "파라미터",        "UC-03",    commander_only=True),
    ScreenSpec("simulation", "시뮬레이션 실행", "UC-04",    commander_only=True),
    ScreenSpec("heatmap",    "히트맵",          "UC-05/06/07", commander_only=False),
    ScreenSpec("section",    "단면도",          "UC-08",    commander_only=False),
    ScreenSpec("summary",    "결과 요약",       "UC-09",    commander_only=False),
    ScreenSpec("comparison", "시나리오 비교",   "UC-10",    commander_only=True),
    ScreenSpec("reset",      "초기화",          "UC-11",    commander_only=True),
)


# --- placeholder page (used until real screens land in later steps) ---------

def _make_placeholder(spec: ScreenSpec) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    body = QLabel("준비 중")
    body.setObjectName("PagePlaceholder")
    body.setAlignment(Qt.AlignmentFlag.AlignCenter)

    layout.addStretch(1)
    layout.addWidget(body, alignment=Qt.AlignmentFlag.AlignCenter)
    layout.addStretch(1)
    return page


# --- top bar ----------------------------------------------------------------

class TopBar(QWidget):
    def __init__(self, on_mode_changed) -> None:
        super().__init__()
        self.setObjectName("TopBar")
        self.setFixedHeight(38)

        self.commander_radio = QRadioButton("Commander")
        self.commander_radio.setObjectName("ModeRadio")
        self.commander_radio.setChecked(True)
        self.commander_radio.toggled.connect(
            lambda checked: checked and on_mode_changed("commander")
        )

        self.field_radio = QRadioButton("Field Operator")
        self.field_radio.setObjectName("ModeRadio")
        self.field_radio.toggled.connect(
            lambda checked: checked and on_mode_changed("field")
        )

        toggle = QWidget()
        toggle.setObjectName("ModeToggle")
        toggle_layout = QHBoxLayout(toggle)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(0)
        toggle_layout.addWidget(self.commander_radio)
        toggle_layout.addWidget(self.field_radio)

        title = QLabel("FireWatch")
        title.setObjectName("AppTitle")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(toggle)
        layout.addSpacing(12)


# --- sidebar ----------------------------------------------------------------

class Sidebar(QWidget):
    def __init__(self, on_select) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)

        self.mode_banner = QLabel("읽기 전용 모드")
        self.mode_banner.setObjectName("ModeBanner")
        self.mode_banner.setVisible(False)

        self.list = QListWidget()
        self.list.setObjectName("SidebarList")
        self.list.setUniformItemSizes(True)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        for spec in SCREENS:
            item = QListWidgetItem(spec.label)
            item.setData(Qt.ItemDataRole.UserRole, spec.key)
            self.list.addItem(item)

        self.list.currentRowChanged.connect(
            lambda row: row >= 0 and on_select(SCREENS[row].key)
        )
        self.list.setCurrentRow(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.mode_banner)
        layout.addWidget(self.list, 1)

    def apply_mode(self, mode: str) -> None:
        is_field = mode == "field"
        self.mode_banner.setVisible(is_field)

        for row in range(self.list.count()):
            item = self.list.item(row)
            spec = SCREENS[row]
            disabled = is_field and spec.commander_only
            flags = item.flags()
            if disabled:
                item.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)

        if is_field:
            current = self.list.currentRow()
            if current < 0 or SCREENS[current].commander_only:
                for row, spec in enumerate(SCREENS):
                    if not spec.commander_only:
                        self.list.setCurrentRow(row)
                        break


# --- main window ------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FireWatch")
        self.resize(1280, 800)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self.top_bar = TopBar(on_mode_changed=self._on_mode_changed)

        self.stack = QStackedWidget()
        self.stack.setObjectName("MainStack")
        self._page_index = {}

        self._report: dict | None = None
        self._parameters: dict | None = None
        self._ensemble = None
        self._run_thread: QThread | None = None
        self._run_worker: EnsembleWorker | None = None
        self._busy_dialog: QProgressDialog | None = None

        self.report_view = ReportInputView()
        self.report_view.reportSubmitted.connect(self._on_report_submitted)
        self.parameters_view = ParametersView()
        self.parameters_view.parametersSaved.connect(self._on_parameters_saved)
        self.simulation_view = SimulationView()
        self.simulation_view.simulationFinished.connect(self._on_simulation_finished)
        self.heatmap_view = HeatmapView()
        self.section_view = SectionView()
        self.summary_view = SummaryView()
        self.comparison_view = ComparisonView()

        custom = {
            "report":     self.report_view,
            "parameters": self.parameters_view,
            "simulation": self.simulation_view,
            "heatmap":    self.heatmap_view,
            "section":    self.section_view,
            "summary":    self.summary_view,
            "comparison": self.comparison_view,
        }
        for spec in SCREENS:
            page = custom.get(spec.key) or _make_placeholder(spec)
            idx = self.stack.addWidget(page)
            self._page_index[spec.key] = idx

        self.sidebar = Sidebar(on_select=self._on_screen_selected)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.stack, 1)

        central_layout.addWidget(self.top_bar)
        central_layout.addWidget(body, 1)

        self.setCentralWidget(central)

    # --- callbacks ----------------------------------------------------------

    def _on_screen_selected(self, key: str) -> None:
        idx = self._page_index.get(key)
        if idx is None:
            return
        if key == "parameters":
            self.parameters_view.set_context(self._report)
        elif key == "simulation":
            self.simulation_view.set_context(self._report, self._parameters)
        elif key == "heatmap":
            self.heatmap_view.set_context(self._report, self._ensemble, self._parameters)
        elif key == "section":
            self.section_view.set_context(self._report, self._ensemble)
        elif key == "summary":
            self.summary_view.set_context(self._report, self._ensemble)
        elif key == "comparison":
            self.comparison_view.set_context(self._report, self._parameters, self._ensemble)
        elif key == "reset":
            self._handle_reset_request()
            return
        self.stack.setCurrentIndex(idx)

    def _on_mode_changed(self, mode: str) -> None:
        self.sidebar.apply_mode(mode)

    def _on_report_submitted(self, report: dict) -> None:
        self._report = report
        self.parameters_view.set_context(report)
        self._goto("parameters")

    def _on_parameters_saved(self, parameters: dict) -> None:
        self._parameters = parameters
        self.simulation_view.set_context(self._report, self._parameters)
        self._goto("simulation")

    def _on_simulation_finished(self, result: dict) -> None:
        # No report -> nothing to compute; just show whatever is cached.
        if self._report is None:
            self._push_ensemble_to_views()
            self._goto("heatmap")
            return
        if self._run_thread is not None:  # a run is already in flight
            return

        n_runs = int(result.get("runs", 30))
        self._run_thread = QThread(self)
        self._run_worker = EnsembleWorker(
            self._report["building"],
            self._report["floor"],
            self._report["ignition_xy"],
            self._parameters,
            n_runs=n_runs,
        )
        self._run_worker.moveToThread(self._run_thread)
        self._run_thread.started.connect(self._run_worker.run)
        self._run_worker.finished.connect(self._on_ensemble_ready)
        self._run_worker.failed.connect(self._on_ensemble_failed)
        self._show_busy(n_runs)
        self._run_thread.start()

    def _on_ensemble_ready(self, cube) -> None:
        self._hide_busy()
        self._teardown_run_thread()
        self._ensemble = cube
        self._push_ensemble_to_views()
        self._goto("heatmap")

    def _on_ensemble_failed(self, message: str) -> None:
        self._hide_busy()
        self._teardown_run_thread()
        QMessageBox.critical(self, "시뮬레이션 오류", f"앙상블 계산 실패:\n{message}")

    # --- busy indicator -----------------------------------------------------

    def _show_busy(self, n_runs: int) -> None:
        """Modal indeterminate spinner shown while the real ensemble computes.

        ``generate_ensemble`` runs as one blocking call on the worker thread and
        emits no per-run progress, so we show an indeterminate (0, 0) bar — an
        honest "working" spinner rather than a fake percentage — with the run
        count in the label. Dismissed in ``_on_ensemble_ready`` / ``_failed``.
        """
        dlg = QProgressDialog(
            f"잠시만 기다려주세요 — 앙상블 {n_runs}회 집계 중…", "", 0, 0, self
        )
        dlg.setWindowTitle("시뮬레이션 진행 중")
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setCancelButton(None)          # the worker can't be cleanly halted mid-run
        dlg.setMinimumDuration(0)          # show immediately, don't wait the default 4 s
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.show()
        self._busy_dialog = dlg

    def _hide_busy(self) -> None:
        if self._busy_dialog is not None:
            self._busy_dialog.close()
            self._busy_dialog = None

    def _teardown_run_thread(self) -> None:
        if self._run_thread is not None:
            self._run_thread.quit()
            self._run_thread.wait()
            self._run_thread = None
        self._run_worker = None

    def _push_ensemble_to_views(self) -> None:
        self.heatmap_view.set_context(self._report, self._ensemble, self._parameters)
        self.section_view.set_context(self._report, self._ensemble)
        self.summary_view.set_context(self._report, self._ensemble)
        self.comparison_view.set_context(self._report, self._parameters, self._ensemble)

    def _goto(self, key: str) -> None:
        idx = self._page_index.get(key)
        if idx is None:
            return
        for row, spec in enumerate(SCREENS):
            if spec.key == key:
                self.sidebar.list.setCurrentRow(row)
                break
        self.stack.setCurrentIndex(idx)

    def _handle_reset_request(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("초기화")
        msg.setText("현재 시뮬레이션을 종료하시겠습니까?")
        msg.setInformativeText("메모리상의 신고 정보·파라미터·앙상블 결과가 모두 제거됩니다.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Ok:
            self._goto("report")
            return
        self._report = None
        self._parameters = None
        self._ensemble = None
        # Clear the two input forms too — otherwise the previous building pick,
        # ignition coord, and equipment toggles linger after "초기화".
        self.report_view.reset()
        self.parameters_view.reset()
        self.heatmap_view.set_context(None, None)
        self.section_view.set_context(None, None)
        self.summary_view.set_context(None, None)
        self.comparison_view.set_context(None, None, None)
        self.simulation_view.set_context(None, None)
        self._goto("report")
