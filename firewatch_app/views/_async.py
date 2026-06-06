"""Off-thread ensemble execution for the app views.

``generate_ensemble`` is pure numpy and can take a few seconds, so running it on
the GUI thread freezes the window. ``EnsembleWorker`` wraps one call so a view can
move it onto a ``QThread`` and receive the cube back through a signal. The worker
lives in the views layer (not the adapter) so ``adapter.py`` stays PyQt-free and
headless-testable.

Usage mirrors the validated UI's ``_RunWorker``::

    thread = QThread(view)
    worker = EnsembleWorker(building, floor, ignition_xy, parameters, seed)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)   # receives the (F,T,rows,cols) cube
    worker.failed.connect(on_failed)       # receives an error message
    thread.start()
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from firewatch_app.bridge.adapter import generate_ensemble


class EnsembleWorker(QObject):
    """Runs one ``generate_ensemble`` call off the UI thread.

    The result is delivered through ``finished``; the view reads it only after
    that signal, so no shared mutable state crosses the thread boundary.
    """

    finished = pyqtSignal(object)  # the (F, T, rows, cols) cube
    failed = pyqtSignal(str)

    def __init__(
        self,
        building,
        floor: str,
        ignition_xy: tuple[int, int],
        parameters: dict | None,
        n_runs: int = 30,
        seed: int = 42,
    ) -> None:
        super().__init__()
        self._building = building
        self._floor = floor
        self._ignition_xy = ignition_xy
        self._parameters = parameters
        self._n_runs = n_runs
        self._seed = seed

    def run(self) -> None:
        try:
            cube: np.ndarray = generate_ensemble(
                self._building,
                self._floor,
                self._ignition_xy,
                parameters=self._parameters,
                n_runs=self._n_runs,
                seed=self._seed,
            )
        except Exception as exc:  # surface to the UI rather than dying silently
            self.failed.emit(str(exc))
            return
        self.finished.emit(cube)
