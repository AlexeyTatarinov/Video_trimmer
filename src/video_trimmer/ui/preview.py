"""Video preview. Uses QtMultimedia (PySide6-Addons) when available, else a no-op stand-in."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QRectF, QSize, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QRegion
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

try:  # QtMultimedia is shipped in PySide6-Addons, not in PySide6-Essentials
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
    MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on installation
    MULTIMEDIA_AVAILABLE = False


VIDEO_MIN_SIZE = QSize(320, 180)
VIDEO_HINT_SIZE = QSize(640, 360)

if MULTIMEDIA_AVAILABLE:
    class ResponsiveVideoWidget(QWidget):
        """Preview surface: paints the frames of its own QVideoSink, with the crop frame on top.

        v0.4.0: this used to be a QVideoWidget. On Windows that is a native window, and ordinary
        widgets (the red crop frame) cannot reliably be painted above it. Like the full-screen
        window (v0.2.3), the preview now receives the frames through a QVideoSink and paints them
        itself, so the ``CropOverlay`` child is always on top and the view zoom is a simple
        painter transform.

        Its size never depends on the frame size of the loaded video: the hint is constant, the
        minimum is small and the policy is Expanding/Ignored (the layout decides).
        """

        doubleClicked = Signal()
        CORNER_RADIUS = 22.0   # same as the glass panel it sits in (widgets.PANEL_RADIUS)
        BACKGROUND = QColor(8, 8, 14)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            from video_trimmer.ui.crop_overlay import CropOverlay
            self.setMinimumSize(VIDEO_MIN_SIZE)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
            self.setAttribute(Qt.WA_OpaquePaintEvent, True)
            self._image = QImage()
            self.frame_count = 0
            self.adopt_frame_size = False   # take the source size from the frames (no probe size)
            self._sink = QVideoSink(self)
            self._sink.videoFrameChanged.connect(self._on_frame)
            self.crop_overlay = CropOverlay(self)
            self.crop_overlay.viewChanged.connect(self.update)
            self.crop_overlay.setGeometry(self.rect())

        # ---- frames
        def videoSink(self) -> QVideoSink:  # noqa: N802 - same name as QVideoWidget's
            return self._sink

        def _on_frame(self, frame) -> None:
            image = frame.toImage()
            if not image.isNull():
                self.frame_count += 1
                self.show_image(image)

        def show_image(self, image: QImage) -> None:
            """Show ``image`` (frames from the sink; also used by tests and screenshots)."""
            self._image = image
            if not image.isNull():
                if self.adopt_frame_size and not self.crop_overlay.has_source():
                    self.adopt_frame_size = False
                    self.crop_overlay.set_source_size(image.width(), image.height())
                self.crop_overlay.set_frame_size(image.size())
            self.update()

        def frame_image(self) -> QImage:
            return self._image

        def clear_image(self) -> None:
            self._image = QImage()
            self.update()

        def picture_rect(self) -> QRectF:
            return self.crop_overlay.picture_rect()

        def paintEvent(self, event) -> None:  # noqa: N802
            p = QPainter(self)
            p.fillRect(self.rect(), self.BACKGROUND)
            if not self._image.isNull():
                target = self.picture_rect()
                if target.isEmpty():
                    target = QRectF(self.rect())
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p.drawImage(target, self._image)

        def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
            if event.button() == Qt.LeftButton:
                self.doubleClicked.emit()
                event.accept()
            else:
                super().mouseDoubleClickEvent(event)

        def resizeEvent(self, event) -> None:  # noqa: N802
            super().resizeEvent(event)
            self.crop_overlay.setGeometry(self.rect())
            self._update_mask()

        def showEvent(self, event) -> None:  # noqa: N802
            super().showEvent(event)
            self._update_mask()

        def _update_mask(self) -> None:
            """Clip the picture to rounded corners (the full-screen picture is not this widget)."""
            r = self.CORNER_RADIUS
            if self.width() <= 2 * r or self.height() <= 2 * r:
                self.clearMask()
                return
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), r, r)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

        def sizeHint(self) -> QSize:  # noqa: N802
            return QSize(VIDEO_HINT_SIZE)

        def minimumSizeHint(self) -> QSize:  # noqa: N802
            return QSize(VIDEO_MIN_SIZE)


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
            self.video_widget: QWidget = ResponsiveVideoWidget()
            if _audio_allowed():
                self._audio = QAudioOutput(self)
            self._sink_override = None
            self._player = self._make_player()
        else:
            self._player = None
            self.video_widget = QLabel("QtMultimedia (PySide6-Addons) is not installed:\npreview unavailable.")
            self.video_widget.setAlignment(Qt.AlignCenter)
            self.video_widget.setMinimumSize(VIDEO_MIN_SIZE)
            self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)

    def _make_player(self):
        player = QMediaPlayer(self)
        if self._audio is not None:
            player.setAudioOutput(self._audio)
        player.setVideoSink(self._sink_override or self.video_widget.videoSink())
        player.positionChanged.connect(lambda ms: self.positionChanged.emit(int(ms)))
        player.playbackStateChanged.connect(self._on_state)
        player.errorOccurred.connect(lambda *_a: self.error.emit())
        if self._audio is not None:
            self._apply_audio()
        return player

    # ---- video output (v0.2.3: the full-screen widget takes the picture over and gives it back)
    def set_video_sink(self, sink) -> None:
        """Send the frames to ``sink`` (a QVideoSink) instead of the preview widget."""
        self._sink_override = sink
        if self._player is not None:
            self._player.setVideoSink(sink)

    def restore_video_output(self) -> None:
        """Send the frames to the preview widget again."""
        self._sink_override = None
        if self._player is not None:
            self._player.setVideoSink(self.video_widget.videoSink())

    def refresh_frame(self) -> None:
        """Re-render the current frame of a paused player (e.g. in a newly attached output)."""
        if self._player is not None and self._player.playbackState() == QMediaPlayer.PausedState:
            self._player.setPosition(self._player.position())

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

    def release(self) -> None:
        """Let go of the video file (so that it can be moved or deleted)."""
        self._pending = None
        self._seek_timer.stop()
        if self._player:
            # Windows (Media Foundation) keeps the file open until the player object is gone:
            # destroy it now and start a fresh one, so the file can be moved or deleted.
            old = self._player
            old.stop()
            old.setSource(QUrl())
            try:
                old.positionChanged.disconnect()
                old.playbackStateChanged.disconnect()
                old.errorOccurred.disconnect()
            except (RuntimeError, TypeError):
                pass
            old.setVideoSink(None)
            old.setParent(None)
            try:
                import shiboken6
                shiboken6.delete(old)
            except Exception:              # noqa: BLE001
                old.deleteLater()
            self._playing = False
            self._player = self._make_player()
