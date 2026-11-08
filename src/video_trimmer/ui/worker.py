"""Run a blocking callable in a background QThread."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from video_trimmer import core


class Worker(QObject):
    """Runs ``fn(progress)`` once; reports through signals (queued to the GUI thread)."""

    progress = Signal(float)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, fn: Callable[[Callable[[float], None]], object]) -> None:
        super().__init__()
        self._fn = fn

    @Slot()
    def run(self) -> None:
        try:
            self.result.emit(self._fn(self.progress.emit))
        except core.TrimError as exc:
            self.error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - never let a thread die silently
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


def start_worker(worker: Worker) -> QThread:
    """Move ``worker`` to a new thread and start it. Caller must keep both references."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    thread.start()
    return thread
