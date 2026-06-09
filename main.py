"""FireWatch 진입점.

본 앱(firewatch_app)을 바로 실행한다. PyInstaller로 .exe(독립 실행 파일)를
빌드하면 필요한 라이브러리(numpy/PyQt6/matplotlib)가 이미 함께 묶이므로,
별도의 의존성 확인이나 자동 설치 로직은 두지 않는다.

실행:  python main.py  (또는 py main.py)
소스로 실행할 때는 의존성을 먼저 설치해 두면 된다:  pip install -r requirements.txt
"""
from __future__ import annotations

import sys

from firewatch_app.main import main

if __name__ == "__main__":
    sys.exit(main())
