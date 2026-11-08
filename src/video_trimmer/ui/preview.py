"""Video preview. Uses QtMultimedia (PySide6-Addons) when available, else a no-op stand-in."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
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

    SEEK_INTERVAL_MS = 30  # minimum gap between two real seeks while dragging
    DEFAULT_VOLUME = 0.8

    positionChanged = Signal(int)  # milliseconds
    playingChanged = Signal(bool)
    error = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._playing = False
        self._volume = self.DEFAULT_VOLUME
        self._muted = False
        self._audio = None  # QAudioOutput, or None when audio is unavailable/disabled
        self._pending: tuple[int, bool] | None = None
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(self.SEEK_INTERVAL_MS)
        self._seek_timer.timeout.connect(self._on_seek_timer)
        if MULTIMEDIA_AVAILABLE:
            self.video_widget: QWidget = QVideoWidget()
            self._player = QMediaPlayer(self)
            if _audio_allowed():
                self._audio = QAudioOutput(self)
                self._player.setAudioOutput(self._audio)
                self._apply_audio()
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

    # ---- audio state (kept even when no QAudioOutput exists)
    def has_audio_output(self) -> bool:
        return self._audio is not None

    def volume(self) -> float:
        return self._volume

    def is_muted(self) -> bool:
        return self._muted

    def set_volume(self, value: float) -> None:
        self._volume = min(max(float(value), 0.0), 1.0)
        self._apply_audio()

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self._apply_audio()

    def _apply_audio(self) -> None:
        if self._audio is not None:
            self._audio.setVolume(self._volume)
            self._audio.setMuted(self._muted)

    # ---- seeking
    def set_position_ms(self, ms: int) -> None:
        """Seek keeping the play/pause state (used by the main position slider)."""
        self._request_seek(int(ms), force_pause=False, immediate=False)

    def show_frame_at(self, ms: int, immediate: bool = False) -> None:
        """Pause and show the frame at ``ms``. Seeks are throttled to ~30 ms unless ``immediate``."""
        self._request_seek(int(ms), force_pause=True, immediate=immediate)

    def _request_seek(self, ms: int, force_pause: bool, immediate: bool) -> None:
        ms = max(0, ms)
        if immediate:
            self._seek_timer.stop()
            self._pending = None
            self._do_seek(ms, force_pause)
            return
        if self._seek_timer.isActive():
            self._pending = (ms, force_pause)  # only the latest target is kept
            return
        self._do_seek(ms, force_pause)
        self._seek_timer.start()

    def _on_seek_timer(self) -> None:
        if self._pending is not None:
            ms, force_pause = self._pending
            self._pending = None
            self._do_seek(ms, force_pause)
            self._seek_timer.start()

    def _do_seek(self, ms: int, force_pause: bool) -> None:
        if not self._player:
            return
        state = self._player.playbackState()
        # A stopped player does not render a frame after setPosition: keep it paused.
        if state == QMediaPlayer.StoppedState or (force_pause and state == QMediaPlayer.PlayingState):
            self._player.pause()
        self._player.setPosition(ms)

    def set_source(self, path: str) -> None:
        if self._player:
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.pause()  # paused: the first frame is shown and seeks render frames
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
