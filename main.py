"""FireWatch 진입점 — 의존성 부트스트랩.

표준 라이브러리만으로 동작한다. 무거운 third-party 의존성(numpy, PyQt6,
matplotlib)이 import 가능한지 먼저 확인하고, 빠진 게 있으면 tkinter 팝업으로
``pip install -r requirements.txt`` 설치를 제안한 뒤 본 앱(PyQt6)을 실행한다.

이 모듈은 절대 top-level에서 numpy/PyQt6/matplotlib/firewatch_app 를 import 하지
않는다 — 의존성이 하나도 없는 맨 인터프리터에서도 실행돼야 하기 때문. 본 앱은
의존성이 보장된 뒤에 ``launch_app()`` 안에서 지연 import 한다. 부트스트랩과 앱
로직(firewatch_app)은 이렇게 완전히 분리돼 있다.

실행:  python3 main.py
"""
from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"

# import 이름 -> pip 패키지(표시) 이름. 세 패키지 모두 동일하게 매핑된다.
REQUIRED: dict[str, str] = {
    "numpy": "numpy",
    "PyQt6": "PyQt6",
    "matplotlib": "matplotlib",
}


# --------------------------------------------------------------- dependency check

def missing_dependencies() -> list[str]:
    """import 불가능한 REQUIRED 패키지의 pip 이름 목록을 반환한다.

    실제로 import 하지 않고 ``importlib.util.find_spec`` 으로만 확인하므로,
    설치돼 있지 않아도 ImportError 로 죽지 않고 무거운 모듈을 로드하지도 않는다.
    """
    missing: list[str] = []
    for import_name, pip_name in REQUIRED.items():
        try:
            available = importlib.util.find_spec(import_name) is not None
        except (ImportError, ValueError):
            available = False
        if not available:
            missing.append(pip_name)
    return missing


def _pip_install_command() -> list[str]:
    """현재 인터프리터로 requirements.txt 를 설치하는 pip 명령."""
    return [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]


# ----------------------------------------------------------------- install worker

def _install_worker(cmd: list[str], log_q) -> None:
    """pip 를 별도 스레드에서 실행하고 출력 라인을 큐로 흘려보낸다.

    GUI 스레드를 막지 않도록 worker 스레드에서 돌리고, 결과는 큐를 통해
    메인(tk) 스레드가 폴링한다. 마지막에 ("done", returncode) 를 넣는다.
    """
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        log_q.put(("line", f"pip 실행 실패: {exc}"))
        log_q.put(("done", 1))
        return

    if proc.stdout is not None:
        for line in proc.stdout:
            log_q.put(("line", line.rstrip("\n")))
        proc.stdout.close()
    code = proc.wait()
    log_q.put(("done", code))


# --------------------------------------------------------------------- tkinter GUI

def run_installer_gui(missing: list[str]) -> str:
    """설치 안내 팝업을 띄운다. 반환: 'cancelled' | 'installed' | 'failed'.

    디스플레이가 없는 환경(headless)에서 Tk 초기화가 실패하면 콘솔 프롬프트로
    폴백한다.
    """
    import queue
    import threading
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    try:
        root = tk.Tk()
    except tk.TclError:
        return _console_fallback(missing)

    state = {"result": "cancelled", "proceeded": False}
    log_q: "queue.Queue[tuple[str, object]]" = queue.Queue()

    root.title("FireWatch — 의존성 설치")
    root.resizable(False, False)

    container = tk.Frame(root, padx=20, pady=18)
    container.pack(fill="both", expand=True)

    # --- 확인 화면 -------------------------------------------------------
    confirm = tk.Frame(container)
    tk.Label(
        confirm,
        text="FireWatch 실행에 필요한 다음 라이브러리를 설치합니다:",
        justify="left", anchor="w",
    ).pack(fill="x")
    tk.Label(
        confirm,
        text="\n".join(f"   •  {name}" for name in missing),
        justify="left", anchor="w", font="TkFixedFont",
    ).pack(fill="x", pady=(8, 8))
    tk.Label(
        confirm,
        text="설치 명령:  pip install -r requirements.txt",
        justify="left", anchor="w", fg="#666666",
    ).pack(fill="x")
    confirm_btns = tk.Frame(confirm)
    confirm_btns.pack(fill="x", pady=(16, 0))

    # --- 설치 화면 -------------------------------------------------------
    install = tk.Frame(container)
    install_label = tk.Label(
        install, text="라이브러리를 설치하는 중입니다…",
        justify="left", anchor="w",
    )
    install_label.pack(fill="x")
    progress = ttk.Progressbar(install, mode="indeterminate", length=420)
    progress.pack(fill="x", pady=(10, 8))
    log_view = ScrolledText(install, width=64, height=14, state="disabled", font="TkFixedFont")
    log_view.pack(fill="both", expand=True)
    install_btns = tk.Frame(install)
    install_btns.pack(fill="x", pady=(12, 0))

    def append_log(text: str) -> None:
        log_view.configure(state="normal")
        log_view.insert("end", text + "\n")
        log_view.see("end")
        log_view.configure(state="disabled")

    def on_cancel() -> None:
        state["result"] = "cancelled"
        root.destroy()

    def proceed() -> None:
        if state["proceeded"]:
            return
        state["proceeded"] = True
        state["result"] = "installed"
        try:
            root.destroy()
        except tk.TclError:
            pass

    def poll_queue() -> None:
        try:
            while True:
                kind, payload = log_q.get_nowait()
                if kind == "line":
                    if payload:
                        append_log(str(payload))
                elif kind == "done":
                    progress.stop()
                    if payload == 0:
                        install_label.configure(text="설치 완료 — 앱을 실행합니다.")
                        append_log("\n[완료] 모든 라이브러리를 설치했습니다.")
                        ttk.Button(install_btns, text="앱 실행", command=proceed).pack(side="right")
                        root.after(1200, proceed)
                    else:
                        state["result"] = "failed"
                        install_label.configure(text="설치 실패")
                        append_log("\n[실패] 자동 설치에 실패했습니다.")
                        append_log("수동 설치:  pip install -r requirements.txt")
                        ttk.Button(install_btns, text="닫기", command=root.destroy).pack(side="right")
                    return  # 폴링 종료
        except queue.Empty:
            pass
        root.after(100, poll_queue)

    def start_install() -> None:
        confirm.pack_forget()
        install.pack(fill="both", expand=True)
        # 설치 중에는 창 닫기를 무시해 중간 종료를 막는다.
        root.protocol("WM_DELETE_WINDOW", lambda: None)
        progress.start(12)
        cmd = _pip_install_command()
        append_log("$ " + " ".join(cmd))
        threading.Thread(target=_install_worker, args=(cmd, log_q), daemon=True).start()
        root.after(100, poll_queue)

    ttk.Button(confirm_btns, text="취소", command=on_cancel).pack(side="right")
    ttk.Button(confirm_btns, text="확인", command=start_install).pack(side="right", padx=(0, 8))

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    confirm.pack(fill="both", expand=True)
    root.update_idletasks()
    root.mainloop()
    return state["result"]


def _console_fallback(missing: list[str]) -> str:
    """디스플레이가 없을 때의 콘솔 폴백 — 같은 흐름을 텍스트로 제공."""
    print("다음 라이브러리를 설치합니다:")
    for name in missing:
        print(f"  - {name}")
    try:
        answer = input("설치하시겠습니까? [Y/n] ").strip().lower()
    except EOFError:
        answer = "n"
    if answer in ("", "y", "yes"):
        code = subprocess.call(_pip_install_command())
        return "installed" if code == 0 else "failed"
    return "cancelled"


def _print_manual_hint(missing: list[str]) -> None:
    print("자동 설치에 실패했습니다. 아래 명령으로 수동 설치 후 다시 실행하세요:")
    print("    pip install -r requirements.txt")
    print("부족한 라이브러리:", ", ".join(missing))


# ----------------------------------------------------------------------- launch

def launch_app() -> int:
    """본 PyQt6 앱을 실행한다 (이 시점엔 의존성이 보장돼 있다)."""
    from firewatch_app.main import main as app_main

    return app_main()


def main() -> int:
    missing = missing_dependencies()
    if not missing:
        return launch_app()

    result = run_installer_gui(missing)

    if result == "installed":
        # 방금 설치한 패키지를 같은 프로세스에서 찾을 수 있도록 캐시 무효화 후 재확인.
        importlib.invalidate_caches()
        still_missing = missing_dependencies()
        if still_missing:
            _print_manual_hint(still_missing)
            return 1
        return launch_app()

    if result == "failed":
        _print_manual_hint(missing)
        return 1

    print("설치를 취소했습니다. 프로그램을 종료합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
