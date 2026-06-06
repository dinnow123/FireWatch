"""FireWatch desktop app entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

from firewatch_app.views.main_window import MainWindow


THEME_PATH = Path(__file__).parent / "theme.qss"


def _pick_default_font() -> QFont:
    available = set(QFontDatabase.families())
    chain = [
        name
        for name in ("IBM Plex Sans KR", "Apple SD Gothic Neo", "Segoe UI", "Noto Sans CJK KR")
        if name in available
    ]
    font = QFont()
    if chain:
        font.setFamilies(chain)
    font.setPointSize(10)
    return font


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FireWatch")
    app.setOrganizationName("FireWatch Project")

    app.setFont(_pick_default_font())

    if THEME_PATH.exists():
        app.setStyleSheet(THEME_PATH.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
