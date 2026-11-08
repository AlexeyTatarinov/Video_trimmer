"""Video preview. Uses QtMultimedia (PySide6-Addons) when available, else a no-op stand-in."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtWidgets import QLabel, QWidget

try:  # QtMultimedia is shipped in PySide6-Addons, not in PySide6-Essentials
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on installation
    MULTIMEDIA_AVAILABLE = False


def _audio_allowed() -> bool:
    """Audio device enumeration crashes on machines without an audio server (CI, containers)."""
    if os.environ.get("VIDEO_TRIMMER_NO_AUDIO"):
        return False
    return os.environ.get("QT_QPA_PLATFORM", "") != "offscreen"


class PreviewPlayer(QObject):
    """Thin wrapper over QMediaPlayer with a stable, tiny API."""

    positionChanged = Signal(int)  # milliseconds
    playingChanged = Signal(bool)
    error = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._playing = False
        if MULTIMEDIA_AVAILABLE:
            self.video_widget: QWidget = QVideoWidget()
            self._player = QMediaPlayer(self)
            if _audio_allowed():
                self._audio = QAudioOutput(self)
                self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self.video_widget)
            self._player.positionChanged.connect(lambda ms: self.positionChanged.emit(int(ms)))
            self._player.playbackStateChanged.connect(self._on_state)
            self._player.errorOccurred.connect(lambda *_a: self.error.emit())
        else:
            self._player = None
            self.video_widget = QLabel("QtMultimedia (PySide6-Addons) is not installed:\npreview unavailable.")
            self.video_widget.setAlignment(Qt.AlignCenter)

    def _on_state(self, state) -> None:
        self._playing = state == QMediaPlayer.PlayingState
        self.playingChanged.emit(self._playing)

    def is_playing(self) -> bool:
        return self._playing

    def position_ms(self) -> int:
        return self._player.position() if self._player else 0

    def set_position_ms(self, ms: int) -> None:
        if self._player:
            self._player.setPosition(ms)

    def set_source(self, path: str) -> None:
        if self._player:
            self._player.setSource(QUrl.fromLocalFile(path))
        else:
            self.error.emit()

    def play(self) -> None:
        if self._player:
            self._player.play()

    def pause(self) -> None:
        if self._player:
            self._player.pause()

    def stop(self) -> None:
        if self._player:
            self._player.stop()
