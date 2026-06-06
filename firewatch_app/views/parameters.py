"""Screen 2 — Parameter setup (UC3)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from firewatch_app.sample_data.floorplan_gen import get_layout
from firewatch_app.widgets.equipment_map import EquipmentMap


DEFAULTS: dict = {
    "sprinkler": True,
    "shutter":   True,
}


class ParametersView(QWidget):
    parametersSaved = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: dict | None = None
        self._building = None
        self._floor_idx = 0
        self._build_ui()
        self._apply(DEFAULTS)

    # ------------------------------------------------------------------ ui

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        host = QFrame()
        host.setObjectName("FloorplanPanel")
        host_layout = QHBoxLayout(host)
        host_layout.setContentsMargins(24, 24, 24, 24)
        host_layout.setSpacing(20)

        # Build the map first so the form's toggles can wire into it.
        map_panel = self._build_map_panel()
        form = self._build_form()
        host_layout.addWidget(form, 0, Qt.AlignmentFlag.AlignTop)
        host_layout.addWidget(map_panel, 1)

        outer.addWidget(host, 1)

    def _build_form(self) -> QFrame:
        form = QFrame()
        form.setObjectName("InputPanel")
        form.setFixedWidth(380)

        v = QVBoxLayout(form)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        v.addWidget(_section("소방 설비"))
        self.cb_sprinkler  = QCheckBox("스프링클러")
        self.lbl_sprinkler = _status_label()
        self.cb_shutter    = QCheckBox("방화셔터")
        self.lbl_shutter   = _status_label()
        v.addLayout(_equipment_row(self.cb_sprinkler, self.lbl_sprinkler))
        v.addLayout(_equipment_row(self.cb_shutter, self.lbl_shutter))
        self.cb_sprinkler.toggled.connect(lambda on: _set_status(self.lbl_sprinkler, on))
        self.cb_shutter.toggled.connect(lambda on: _set_status(self.lbl_shutter, on))
        # Live-link the toggles to the map opacity (off = faded, on = solid).
        self.cb_sprinkler.toggled.connect(self._sync_map_states)
        self.cb_shutter.toggled.connect(self._sync_map_states)

        v.addWidget(_hint(
            "지도에서 설비 위치를 확인하세요. 스프링클러 영향 범위는 설치 셀 1칸입니다."
        ))

        v.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.default_btn = QPushButton("기본값으로 진행")
        self.save_btn    = QPushButton("저장")
        self.save_btn.setObjectName("Primary")
        btn_row.addStretch(1)
        btn_row.addWidget(self.default_btn)
        btn_row.addWidget(self.save_btn)
        v.addLayout(btn_row)

        self.default_btn.clicked.connect(self._on_default)
        self.save_btn.clicked.connect(self._on_save)

        return form

    def _build_map_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("FloorplanPanel")
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        tabs_wrap = QHBoxLayout()
        tabs_wrap.setSpacing(8)
        tabs_wrap.addWidget(_field_label("층"))
        self.floor_tabs_layout = QHBoxLayout()
        self.floor_tabs_layout.setSpacing(6)
        self.floor_tabs_group = QButtonGroup(self)
        self.floor_tabs_group.setExclusive(True)
        self.floor_tabs_group.idToggled.connect(self._on_floor_changed)
        tabs_wrap.addLayout(self.floor_tabs_layout)
        tabs_wrap.addStretch(1)
        self.map_empty = QLabel("건물 미선택 — 신고 입력 화면에서 먼저 등록하세요.")
        self.map_empty.setObjectName("FieldLabel")
        tabs_wrap.addWidget(self.map_empty)
        v.addLayout(tabs_wrap)

        self.map = EquipmentMap()
        v.addWidget(self.map, 1)

        legend = QHBoxLayout()
        legend.setSpacing(14)
        legend.addWidget(_legend_dot("스프링클러 · 영향 1칸", "#38bdf8"))
        legend.addWidget(_legend_dot("방화셔터", "#f5b301"))
        legend.addStretch(1)
        hint = QLabel("끔 = 흐리게 · 켬 = 진하게")
        hint.setObjectName("FieldLabel")
        legend.addWidget(hint)
        v.addLayout(legend)

        return panel

    # -------------------------------------------------------- public context

    def set_context(self, report: dict | None) -> None:
        """Load a building so the map can show its sprinkler/shutter positions."""
        self._report = report
        self._building = report["building"] if report else None
        self._floor_idx = 0
        if self._building is not None:
            floors = list(self._building.floors)
            ig_floor = report.get("floor")
            self._floor_idx = floors.index(ig_floor) if ig_floor in floors else 0

        self._rebuild_floor_tabs()
        self.map.set_layout(get_layout(self._building.id) if self._building else None)
        self.map_empty.setVisible(self._building is None)
        self._refresh_map()

    # ----------------------------------------------------------- floor tabs

    def _rebuild_floor_tabs(self) -> None:
        while self.floor_tabs_layout.count():
            item = self.floor_tabs_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                self.floor_tabs_group.removeButton(w)
                w.deleteLater()
        if self._building is None:
            return
        for idx, name in enumerate(self._building.floors):
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
        self._refresh_map()

    # ----------------------------------------------------------------- map

    def _refresh_map(self) -> None:
        if self._building is None:
            self.map.set_equipment([], [])
            return
        floor_name = self._building.floors[self._floor_idx]
        sprinklers = [
            (e.x, e.y)
            for e in self._building.equipment
            if e.type == "sprinkler" and e.floor == floor_name
        ]
        shutters = [
            (e.x, e.y)
            for e in self._building.equipment
            if e.type == "shutter" and e.floor == floor_name
        ]
        self.map.set_equipment(sprinklers, shutters)
        self._sync_map_states()

    def _sync_map_states(self) -> None:
        self.map.set_states(self.cb_sprinkler.isChecked(), self.cb_shutter.isChecked())

    # -------------------------------------------------------- state helpers

    def _apply(self, params: dict) -> None:
        self.cb_sprinkler.setChecked(params["sprinkler"])
        self.cb_shutter.setChecked(params["shutter"])
        _set_status(self.lbl_sprinkler, params["sprinkler"])
        _set_status(self.lbl_shutter, params["shutter"])

    def _gather(self) -> dict:
        return {
            "sprinkler": self.cb_sprinkler.isChecked(),
            "shutter":   self.cb_shutter.isChecked(),
        }

    # ----------------------------------------------------------------- reset

    def reset(self) -> None:
        """Restore defaults (all active) and drop the loaded building map."""
        self._apply(DEFAULTS)
        self.set_context(None)

    # ------------------------------------------------------------ callbacks

    def _on_default(self) -> None:
        self._apply(DEFAULTS)
        self.parametersSaved.emit(dict(DEFAULTS))

    def _on_save(self) -> None:
        self.parametersSaved.emit(self._gather())


# --- helpers ---------------------------------------------------------------

def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionLabel")
    return label


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    label.setWordWrap(True)
    return label


def _status_label() -> QLabel:
    label = QLabel()
    label.setObjectName("EquipStatus")
    return label


def _legend_dot(text: str, color: str) -> QWidget:
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    dot = QLabel()
    dot.setFixedSize(12, 12)
    dot.setStyleSheet(f"background:{color}; border-radius:6px;")
    label = QLabel(text)
    label.setObjectName("LegendLabel")
    row.addWidget(dot)
    row.addWidget(label)
    return wrap


def _equipment_row(checkbox: QCheckBox, status: QLabel) -> QHBoxLayout:
    """A facility checkbox with its on/off status text pinned to the right."""
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(checkbox)
    row.addStretch(1)
    row.addWidget(status)
    return row


def _set_status(label: QLabel, on: bool) -> None:
    """Make the toggle state explicit: '작동 중' (green) vs '작동 끔' (amber)."""
    label.setText("작동 중" if on else "작동 끔")
    label.setProperty("state", "on" if on else "off")
    label.style().unpolish(label)
    label.style().polish(label)
