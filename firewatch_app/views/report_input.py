"""Screen 1 — Report input (UC1) and building load (UC2)."""
from __future__ import annotations

from PyQt6.QtCore import QDateTime, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from firewatch_app.sample_data.buildings import BUILDINGS, Building, find_building
from firewatch_app.sample_data.floorplan_gen import get_layout
from firewatch_app.widgets.floorplan import FloorplanGrid


class ReportInputView(QWidget):
    reportSubmitted = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._building: Building | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_input_panel())
        root.addWidget(self._build_floorplan_panel(), 1)

    # ------------------------------------------------------------------ left

    def _build_input_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("InputPanel")
        panel.setFixedWidth(320)

        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        # Building picker (primary path) — every demo building is shown up-front
        # as a selectable card so a first-time user can just click one.
        v.addWidget(_field_label("건물 선택 — 목록에서 클릭"))
        self.building_list = QListWidget()
        self.building_list.setObjectName("BuildingList")
        self.building_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.building_list.setWordWrap(True)
        self.building_list.setMaximumHeight(212)
        for b in BUILDINGS:
            item = QListWidgetItem(
                f"{b.name}\n{len(b.floors)}개 층 · {b.grid_size[0]}×{b.grid_size[1]} 셀 · {b.address}"
            )
            item.setData(Qt.ItemDataRole.UserRole, b)
            self.building_list.addItem(item)
        self.building_list.currentItemChanged.connect(self._on_building_selected)
        v.addWidget(self.building_list)

        # Address search (secondary path) — free-text lookup.
        v.addWidget(_field_label("또는 주소로 검색"))
        addr_row = QHBoxLayout()
        addr_row.setSpacing(6)
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("주소 입력")
        self.search_btn = QPushButton("검색")
        addr_row.addWidget(self.address_input, 1)
        addr_row.addWidget(self.search_btn)
        v.addLayout(addr_row)

        self.building_info = QLabel("건물 정보 없음")
        self.building_info.setObjectName("BuildingInfo")
        self.building_info.setWordWrap(True)
        v.addWidget(self.building_info)

        v.addSpacing(4)

        v.addWidget(_field_label("발화 층"))
        self.floor_combo = QComboBox()
        self.floor_combo.setEnabled(False)
        v.addWidget(self.floor_combo)

        v.addWidget(_field_label("발화 시각"))
        self.time_input = QDateTimeEdit()
        self.time_input.setDateTime(QDateTime.currentDateTime())
        self.time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.time_input.setCalendarPopup(False)
        v.addWidget(self.time_input)

        v.addWidget(_field_label("발화 좌표"))
        self.coord_display = QLabel("─")
        self.coord_display.setObjectName("CoordDisplay")
        v.addWidget(self.coord_display)

        v.addStretch(1)

        self.submit_btn = QPushButton("신고 등록")
        self.submit_btn.setObjectName("Primary")
        self.submit_btn.setEnabled(False)
        v.addWidget(self.submit_btn)

        # Wire
        self.search_btn.clicked.connect(self._on_search)
        self.address_input.returnPressed.connect(self._on_search)
        self.submit_btn.clicked.connect(self._on_submit)

        return panel

    # ----------------------------------------------------------------- right

    def _build_floorplan_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("FloorplanPanel")

        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 16, 16, 12)
        v.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(_field_label("평면도"))
        header.addStretch(1)
        self.hover_display = QLabel("")
        self.hover_display.setObjectName("HoverCoord")
        header.addWidget(self.hover_display)
        v.addLayout(header)

        self.grid = FloorplanGrid(30, 30)
        self.grid.cellClicked.connect(self._on_cell_clicked)
        self.grid.cellHovered.connect(self._on_cell_hovered)
        v.addWidget(self.grid, 1)

        return panel

    # --------------------------------------------------------------- actions

    def _on_building_selected(self, current: QListWidgetItem | None, _prev=None) -> None:
        building = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if building is None:
            return
        self.address_input.setText(building.address)
        self._load_building(building)

    def _on_search(self) -> None:
        query = self.address_input.text().strip()
        if not query:
            return
        building = find_building(query)
        if building is None:
            self._building = None
            self._sync_list(None)
            self.building_info.setText("미등록 건물 — 다른 주소를 입력하세요.")
            self.floor_combo.clear()
            self.floor_combo.setEnabled(False)
            self.grid.clear()
            self.coord_display.setText("─")
            self._refresh_submit()
            return
        self._sync_list(building)
        self._load_building(building)

    def _load_building(self, building: Building) -> None:
        self._building = building
        self.building_info.setText(
            f"{building.name}\n{building.address}\n"
            f"{len(building.floors)}개 층 · {building.grid_size[0]}×{building.grid_size[1]} 셀"
        )
        self.floor_combo.clear()
        self.floor_combo.addItems(list(building.floors))
        if "1F" in building.floors:
            self.floor_combo.setCurrentText("1F")
        self.floor_combo.setEnabled(True)
        self.grid.set_layout(get_layout(building.id))
        self.coord_display.setText("─")
        self._refresh_submit()

    def _sync_list(self, building: Building | None) -> None:
        """Reflect the loaded building in the list without re-triggering a load."""
        self.building_list.blockSignals(True)
        self.building_list.setCurrentRow(
            -1 if building is None else BUILDINGS.index(building)
        )
        self.building_list.blockSignals(False)

    def _on_cell_clicked(self, x: int, y: int) -> None:
        self.coord_display.setText(f"({x:>2}, {y:>2})")
        self._refresh_submit()

    def _on_cell_hovered(self, x: int, y: int) -> None:
        if x < 0:
            self.hover_display.setText("")
        else:
            self.hover_display.setText(f"({x:>2}, {y:>2})")

    def _refresh_submit(self) -> None:
        self.submit_btn.setEnabled(
            self._building is not None and self.grid.ignition is not None
        )

    # ----------------------------------------------------------------- reset

    def reset(self) -> None:
        """Clear all session input back to IDLE; repository buildings are kept.

        Wipes the active report-in-progress (building pick, address text, floor,
        ignition coord/marker) so a fresh report starts from a blank form. The
        ``BUILDINGS`` catalog itself is never touched — only this view's
        selection state.
        """
        self._building = None
        self.building_list.blockSignals(True)
        self.building_list.setCurrentRow(-1)
        self.building_list.clearSelection()
        self.building_list.blockSignals(False)
        self.address_input.clear()
        self.building_info.setText("건물 정보 없음")
        self.floor_combo.clear()
        self.floor_combo.setEnabled(False)
        self.coord_display.setText("─")
        self.grid.clear()
        self._refresh_submit()

    def _on_submit(self) -> None:
        if self._building is None or self.grid.ignition is None:
            return
        report = {
            "building": self._building,
            "floor": self.floor_combo.currentText(),
            "ignition_xy": self.grid.ignition,
            "ignition_time": self.time_input.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
        }
        self.reportSubmitted.emit(report)


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label
