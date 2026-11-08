"""Full-screen video mode (v0.2.3).

A native QVideoWidget cannot reliably be covered by ordinary widgets on Windows (the panels may
end up *under* the video). So for full screen the player's output is redirected to a
``QVideoSink`` owned by a dedicated frameless top-level widget. That widget paints the received
frames itself (QPainter, aspect ratio kept, letterboxed, as large as the screen allows) and holds
ordinary child widgets on top: a header with one centred cross button and a footer with the
transport / range / sound controls.

The main window is the single source of truth (position, volume, mute, range, cards). The
``FullscreenController`` keeps the widgets of the footer in sync with the main window both ways.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter
from PySide6.QtMultimedia import QVideoSink
from PySide6.QtWidgets import (
    QApplication, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget,
)

from video_trimmer import i18n
from video_trimmer.ui import theme
from video_trimmer.ui.range_slider import RangeSlider
from video_trimmer.ui.theme import paint_glass, with_alpha
from video_trimmer.ui.timefmt import format_time
from video_trimmer.ui.widgets import ElidedLabel, GlassButton, GlassPanel, GlassSlider

TIME_FIELD_SIZE = QSize(116, 32)


def fit_rect(src: QSize, dst: QRect) -> QRect:
    """The largest rectangle of the aspect ratio of ``src`` that fits ``dst``, centred in it."""
    if src.width() <= 0 or src.height() <= 0 or dst.width() <= 0 or dst.height() <= 0:
        return QRect()
    scale = min(dst.width() / src.width(), dst.height() / src.height())
    w = max(1, min(dst.width(), round(src.width() * scale)))
    h = max(1, min(dst.height(), round(src.height() * scale)))
    return QRect(dst.left() + (dst.width() - w) // 2, dst.top() + (dst.height() - h) // 2, w, h)


class _Opaque(QWidget):
    """Base of the panels: swallows mouse clicks so they never reach the video underneath."""

    def mousePressEvent(self, event) -> None:  # noqa: N802
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        event.accept()


class FullscreenHeader(_Opaque):
    """Slides in from the top edge: the round cross button stays in the exact centre; the
    "Export" button sits to the right of it (v0.2.4)."""

    HEIGHT = 84
    BUTTON = 56

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.exit_button = GlassButton(icon_kind="cross", diameter=self.BUTTON)
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.export_button = GlassButton(primary=True)
        self.export_button.setFocusPolicy(Qt.NoFocus)
        self.export_button.set_texts(i18n.all_texts("export"))
        # three columns; the two outer ones stretch equally, so the cross is always centred
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 12, 0, 16)
        lay.setHorizontalSpacing(0)
        lay.setColumnStretch(0, 1)
        lay.setColumnStretch(2, 1)
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addSpacing(20)
        right.addWidget(self.export_button)
        right.addStretch(1)
        lay.addWidget(self.exit_button, 0, 1, Qt.AlignCenter)
        lay.addLayout(right, 0, 2)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(0, 0, 0, 120))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), g)


class FullscreenFooter(GlassPanel):
    """Slides in from the bottom edge: the static panels of the main window without the mode,
    Save, the cards, Clear all, language / theme and Open video."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent=parent)
        T = i18n.all_texts
        self.setObjectName("fullscreenFooter")
        self.body.setContentsMargins(14, 6, 14, 8)
        self.body.setSpacing(3)

        # row 1: play, position, time, mute, volume
        row = QHBoxLayout()
        row.setSpacing(10)
        self.play_button = GlassButton(icon_kind="play", diameter=42, primary=True)
        self.position_slider = GlassSlider()
        self.position_slider.setRange(0, 0)
        self.position_slider.setMinimumWidth(100)
        self.position_label = ElidedLabel(format_time(0))
        self.position_label.setObjectName("time")
        self.position_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.position_label.set_measure_texts(
            [f"{d}{d}:{d}{d}:{d}{d}.{d}{d}{d}" for d in "0123456789"])
        self.mute_button = GlassButton(icon_kind="speaker", diameter=38)
        self.mute_button.setCheckable(True)
        self.volume_slider = GlassSlider()
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setMinimumWidth(90)
        self.volume_slider.setMaximumWidth(160)
        self.volume_slider.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        row.addWidget(self.play_button)
        row.addWidget(self.position_slider, 1)
        row.addWidget(self.position_label)
        row.addSpacing(6)
        row.addWidget(self.mute_button)
        row.addWidget(self.volume_slider)
        self.body.addLayout(row)

        # row 2: the two-handle range slider
        self.range_slider = RangeSlider()
        self.body.addWidget(self.range_slider)

        # row 3: Start / End fields with the "here" buttons, and Add
        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.start_label, self.end_label = ElidedLabel(), ElidedLabel()
        for lab in (self.start_label, self.end_label):
            lab.set_measure_texts(T("start") + T("end"))
        self.start_edit, self.end_edit = QLineEdit(), QLineEdit()
        for edit in (self.start_edit, self.end_edit):
            edit.setFixedSize(TIME_FIELD_SIZE)
            edit.setAlignment(Qt.AlignCenter)
        self.set_start_button, self.set_end_button = GlassButton(), GlassButton()
        for b in (self.set_start_button, self.set_end_button):
            b.set_texts(T("set_start") + T("set_end"))
        self.add_button = GlassButton(primary=True)
        self.add_button.set_texts(T("add_segment"))
        controls.addWidget(self.start_label)
        controls.addWidget(self.start_edit)
        controls.addWidget(self.set_start_button)
        controls.addSpacing(10)
        controls.addWidget(self.end_label)
        controls.addWidget(self.end_edit)
        controls.addWidget(self.set_end_button)
        controls.addStretch(1)
        controls.addWidget(self.add_button)
        self.body.addLayout(controls)

        # the window itself keeps the keyboard focus (Space / Esc), except in the time fields
        from PySide6.QtWidgets import QAbstractButton, QAbstractSlider
        for w in (*self.findChildren(QAbstractButton), *self.findChildren(QAbstractSlider),
                  self.range_slider):
            w.setFocusPolicy(Qt.NoFocus)
        for edit in (self.start_edit, self.end_edit):
            edit.setFocusPolicy(Qt.ClickFocus)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        # over a moving picture the plain glass is too see-through: put the popup tint under it
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.current().popup_bg)
        p.drawRoundedRect(r, 22, 22)
        paint_glass(p, r, theme.current(), 22.0)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        event.accept()

    def is_interacting(self) -> bool:
        """True while a handle / slider is being dragged or a time field is being edited."""
        return (self.range_slider.is_dragging() or self.position_slider.isSliderDown()
                or self.volume_slider.isSliderDown() or self.start_edit.hasFocus()
                or self.end_edit.hasFocus())


class Toast(QLabel):
    """Short glass notice ("Segment #N created")."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.setContentsMargins(28, 12, 28, 12)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)
        self.hide()

    def fit_text(self, text: str, max_width: int) -> None:
        """Set the text; a text wider than ``max_width`` wraps instead of leaving the screen."""
        self.setText(text)
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        self.adjustSize()
        if self.width() > max_width:
            self.setWordWrap(True)
            self.setFixedWidth(max_width)
            self.setFixedHeight(self.heightForWidth(max_width))
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme.current()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.fillRect(self.rect(), Qt.transparent)
        p.setBrush(th.popup_bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        paint_glass(p, r, th, r.height() / 2)
        p.end()
        super().paintEvent(event)


class FullscreenWindow(QWidget):
    """Frameless full-screen top-level widget: paints sink frames, hosts header / footer / toast."""

    # timings and zones; tests shorten the times
    HEADER_ZONE = 80          # px from the top edge that reveal the header
    FOOTER_ZONE = 140         # px from the bottom edge that reveal the footer
    HIDE_DELAY_MS = 1500      # panels hide this long after the mouse leaves / stops
    CURSOR_HIDE_MS = 1500     # the cursor hides after this much inactivity when no panel is shown
    ANIM_MS = 220             # slide duration
    TOAST_MS = 2000           # how long the "segment created" notice stays
    SIDE_MARGIN = 24
    BOTTOM_MARGIN = 14
    FOOTER_MAX_WIDTH = 1280

    exitRequested = Signal()
    toggleRequested = Signal()      # a double click on the picture
    playToggleRequested = Signal()  # Space
    exportRequested = Signal()      # the "Export" button of the header (v0.2.4)

    def __init__(self, owner: QWidget) -> None:
        super().__init__(owner, Qt.Window | Qt.FramelessWindowHint)
        self.setObjectName("fullscreenWindow")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle(i18n.tr(i18n.DEFAULT_LANGUAGE, "window_title"))
        self._image = QImage()
        self._active = False
        self._cursor_hidden = False
        self._last_pos = QPoint(-1, -1)
        self._shown = {"header": False, "footer": False}
        self.frame_count = 0
        self.last_frame_ms = -1.0

        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._on_frame)
        self.header = FullscreenHeader(self)
        self.exit_button = self.header.exit_button
        self.exit_button.clicked.connect(self.exitRequested)
        self.export_button = self.header.export_button
        self.export_button.clicked.connect(self.exportRequested)
        self._export_active = False
        self.footer = FullscreenFooter(self)
        self.toast = Toast(self)

        self._anims = {"header": QPropertyAnimation(self.header, b"pos", self),
                       "footer": QPropertyAnimation(self.footer, b"pos", self)}
        for key, anim in self._anims.items():
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(lambda key=key: self._anim_finished(key))
        self._toast_anim = QPropertyAnimation(self.toast._effect, b"opacity", self)
        self._toast_anim.finished.connect(self._toast_anim_finished)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timeout)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.timeout.connect(self._on_cursor_timeout)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._fade_toast)
        self._layout_panels()

    # ------------------------------------------------------------------ frames and painting
    def _on_frame(self, frame) -> None:
        self.frame_count += 1
        start = frame.startTime()
        self.last_frame_ms = start / 1000.0 if start >= 0 else -1.0
        image = frame.toImage()
        if not image.isNull():
            self._image = image
            self.update()

    def frame_image(self) -> QImage:
        return self._image

    def show_image(self, image: QImage) -> None:
        """Show ``image`` (used for tests and screenshots; normally frames come from the sink)."""
        self._image = image
        self.update()

    def video_rect(self) -> QRect:
        """Where the picture is painted: as large as the window allows, aspect ratio kept."""
        if self._image.isNull():
            return QRect()
        return fit_rect(self._image.size(), self.rect())

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if not self._image.isNull():
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.drawImage(self.video_rect(), self._image)

    # ------------------------------------------------------------------ panels
    def header_visible(self) -> bool:
        return self._shown["header"]

    def footer_visible(self) -> bool:
        return self._shown["footer"]

    def _panel(self, key: str) -> QWidget:
        return self.header if key == "header" else self.footer

    def _panel_rect(self, key: str, shown: bool) -> QRect:
        """Geometry of a panel at its shown / hidden (just outside the screen) position."""
        W, H = self.width(), self.height()
        if key == "header":
            h = FullscreenHeader.HEIGHT
            return QRect(0, 0 if shown else -h, W, h)
        self.footer.ensurePolished()
        hint = self.footer.sizeHint()
        w = min(W - 2 * self.SIDE_MARGIN, self.FOOTER_MAX_WIDTH)
        w = max(w, min(hint.width(), W), 1)      # never narrower than its controls need
        h = hint.height()
        y = H - h - self.BOTTOM_MARGIN if shown else H
        return QRect((W - w) // 2, y, w, h)

    def _layout_panels(self) -> None:
        for key in self._shown:
            if self._anims[key].state() == QPropertyAnimation.Running:
                continue
            self._panel(key).setGeometry(self._panel_rect(key, self._shown[key]))
        self._place_toast()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_panels()

    def _set_panel(self, key: str, shown: bool, animate: bool = True) -> None:
        panel, anim = self._panel(key), self._anims[key]
        changed = self._shown[key] != shown
        self._shown[key] = shown
        target = self._panel_rect(key, shown)
        if not changed and not (anim.state() == QPropertyAnimation.Running):
            if shown and not panel.isVisible():
                panel.setGeometry(target)
                panel.show()
            return
        anim.stop()
        if shown:
            if not panel.isVisible():
                panel.setGeometry(self._panel_rect(key, False))
                panel.show()
            panel.setGeometry(QRect(panel.pos(), target.size()))
            panel.raise_()
            self.toast.raise_()
        if not animate or not panel.isVisible():
            panel.setGeometry(target)
            if not shown:
                panel.hide()
            return
        anim.setDuration(max(int(self.ANIM_MS), 1))
        anim.setStartValue(panel.pos())
        anim.setEndValue(target.topLeft())
        anim.start()

    def _anim_finished(self, key: str) -> None:
        if not self._shown[key]:
            self._panel(key).hide()

    def show_panels(self, header: bool = True, footer: bool = True, animate: bool = True) -> None:
        if header:
            self._set_panel("header", True, animate)
        if footer:
            self._set_panel("footer", True, animate)
        self._restart_hide_timer()

    def hide_panels(self, animate: bool = True) -> None:
        for key in self._shown:
            self._set_panel(key, False, animate)

    def _any_panel(self) -> bool:
        return any(self._shown.values())

    def _panel_has_mouse(self, key: str) -> bool:
        """True while the pointer rests on the usable part of a shown panel (it then stays open)."""
        if not self._shown[key]:
            return False
        if key == "header":     # the strip is only a scrim: just the two buttons count
            r = QRect(self.exit_button.mapTo(self, QPoint(0, 0)), self.exit_button.size())
            r = r.united(QRect(self.export_button.mapTo(self, QPoint(0, 0)), self.export_button.size()))
        else:
            r = self.footer.geometry()
        return r.contains(self._last_pos)

    # ------------------------------------------------------------------ mouse zones and timers
    def handle_mouse_moved(self, pos: QPoint) -> None:
        """Reveal the header / footer when the pointer is in their zones; restart the timers."""
        self._last_pos = QPoint(pos)
        self._wake_cursor()
        in_header = pos.y() <= self.HEADER_ZONE or (self._shown["header"] and pos.y() <= self.header.geometry().bottom())
        in_footer = pos.y() >= self.height() - self.FOOTER_ZONE or self._panel_has_mouse("footer")
        if in_header:
            self._set_panel("header", True)
        if in_footer:
            self._set_panel("footer", True)
        if self._any_panel():
            self._restart_hide_timer()

    def _restart_hide_timer(self) -> None:
        if self._any_panel():
            self._hide_timer.start(max(int(self.HIDE_DELAY_MS), 1))

    def _on_hide_timeout(self) -> None:
        keep = False
        for key in ("header", "footer"):
            if not self._shown[key]:
                continue
            busy = key == "footer" and self.footer.is_interacting()
            if self._panel_has_mouse(key) or busy or self._export_active:
                keep = True
            else:
                self._set_panel(key, False)
        if keep:
            self._restart_hide_timer()

    def _wake_cursor(self) -> None:
        if self._cursor_hidden:
            self._cursor_hidden = False
            self.unsetCursor()
        if self._active:
            self._cursor_timer.start(max(int(self.CURSOR_HIDE_MS), 1))

    def _on_cursor_timeout(self) -> None:
        if self._any_panel():
            self._cursor_timer.start(max(int(self.CURSOR_HIDE_MS), 1))
            return
        self._cursor_hidden = True
        self.setCursor(Qt.BlankCursor)

    def cursor_hidden(self) -> bool:
        return self._cursor_hidden

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        # While active every mouse move of this window (also over the panels, which would swallow
        # it) is seen here.
        if event.type() == QEvent.MouseMove and isinstance(obj, QWidget) and obj.window() is self:
            self.handle_mouse_moved(self.mapFromGlobal(event.globalPosition().toPoint()))
        return False

    # ------------------------------------------------------------------ toast
    def show_toast(self, text: str, sticky: bool = False, duration_ms: int | None = None) -> None:
        """Show a notice. ``sticky`` keeps it until the next toast (export progress)."""
        self._toast_anim.stop()
        self._toast_timer.stop()
        self.toast._effect.setOpacity(1.0)
        self.toast.fit_text(text, max(self.width() - 2 * self.SIDE_MARGIN, 200))
        self._place_toast()
        self.toast.show()
        self.toast.raise_()
        if not sticky:
            ms = self.TOAST_MS if duration_ms is None else duration_ms
            self._toast_timer.start(max(int(ms), 1))

    def set_export_active(self, active: bool) -> None:
        """While an export runs the panels stay open and the header is shown."""
        self._export_active = bool(active)
        if active and self._active:
            self.show_panels(header=True, footer=False)
        elif not active:
            self._restart_hide_timer()

    def _place_toast(self) -> None:
        t = self.toast
        if not t.wordWrap():
            t.adjustSize()
        t.move((self.width() - t.width()) // 2, self.HEADER_ZONE + 24)

    def _fade_toast(self) -> None:
        self._toast_anim.stop()
        self._toast_anim.setDuration(max(int(self.ANIM_MS), 1))
        self._toast_anim.setStartValue(1.0)
        self._toast_anim.setEndValue(0.0)
        self._toast_anim.start()

    def _toast_anim_finished(self) -> None:
        if self.toast._effect.opacity() <= 0.01:
            self.toast.hide()

    # ------------------------------------------------------------------ keys, clicks, closing
    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.toggleRequested.emit()
            event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.exitRequested.emit()
        elif event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.playToggleRequested.emit()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()              # Alt+F4 on the borderless window only leaves full screen
        self.exitRequested.emit()

    # ------------------------------------------------------------------ begin / end
    def begin(self, screen) -> None:
        """Cover ``screen`` and start reacting to the mouse."""
        if screen is not None:
            self.setScreen(screen)
            self.setGeometry(screen.geometry())
        self._active = True
        self._shown = {"header": False, "footer": False}
        self.header.hide()
        self.footer.hide()
        self.toast.hide()
        self.showFullScreen()
        self._layout_panels()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)
        QApplication.instance().installEventFilter(self)
        self._wake_cursor()

    def end(self) -> None:
        self._active = False
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        for t in (self._hide_timer, self._cursor_timer, self._toast_timer):
            t.stop()
        for a in (*self._anims.values(), self._toast_anim):
            a.stop()
        self._cursor_hidden = False
        self.unsetCursor()
        self._shown = {"header": False, "footer": False}
        self.header.hide()
        self.footer.hide()
        self.toast.hide()
        self.hide()


class FullscreenController(QObject):
    """Owns the full-screen window and mirrors the main window's state into its footer."""

    def __init__(self, main) -> None:
        super().__init__(main)
        self.main = main
        self.window: FullscreenWindow | None = None
        self.active = False
        self._mirroring = False

    # ------------------------------------------------------------------ lifecycle
    def ensure_window(self) -> FullscreenWindow:
        if self.window is None:
            self._create()
        return self.window

    def _create(self) -> None:
        mw = self.main
        w = self.window = FullscreenWindow(mw)
        theme.apply_theme(w, mw.theme_name)
        f = w.footer
        w.exitRequested.connect(mw.exit_fullscreen)
        w.toggleRequested.connect(mw.toggle_fullscreen)
        w.exportRequested.connect(mw.save)
        w.playToggleRequested.connect(lambda: mw.toggle_play())
        # transport
        f.play_button.clicked.connect(lambda: mw.toggle_play())
        f.position_slider.sliderMoved.connect(lambda ms: mw._seek(ms))
        mw.displayTimeChanged.connect(self._mirror_time)
        mw.player.playingChanged.connect(lambda _p: self._mirror_play())
        # sound
        f.volume_slider.valueChanged.connect(self._footer_volume)
        mw.volume_slider.valueChanged.connect(self._main_volume)
        f.mute_button.toggled.connect(self._footer_mute)
        mw.mute_button.toggled.connect(self._main_mute)
        # range
        f.range_slider.rangeChanged.connect(self._footer_range)
        mw.range_slider.rangeChanged.connect(self._main_range)
        f.range_slider.dragStarted.connect(self._footer_drag_started)
        f.range_slider.dragFinished.connect(self._footer_drag_finished)
        f.start_edit.editingFinished.connect(lambda: self._footer_edit(True))
        f.end_edit.editingFinished.connect(lambda: self._footer_edit(False))
        f.set_start_button.clicked.connect(lambda: mw.set_start_from_position())
        f.set_end_button.clicked.connect(lambda: mw.set_end_from_position())
        f.add_button.clicked.connect(lambda: mw.add_segment())
        mw.segmentCreated.connect(self._segment_created)

    def enter(self) -> None:
        mw = self.main
        if self.active or not mw.has_video():
            return
        w = self.ensure_window()
        self.sync_all()
        self.active = True
        w.begin(mw.screen())
        if mw.is_exporting():
            w.set_export_active(True)
        mw.player.set_video_sink(w.sink)
        mw.player.refresh_frame()

    def exit(self) -> None:
        if not self.active:
            return
        mw = self.main
        self.active = False
        mw.player.restore_video_output()
        self.window.end()
        mw.player.refresh_frame()
        mw.activateWindow()

    def shutdown(self) -> None:
        """The main window is closing: never leave a full-screen window behind."""
        if self.active:
            self.exit()
        if self.window is not None:
            self.window.end()

    # ------------------------------------------------------------------ sync main -> footer
    def sync_all(self) -> None:
        mw, f = self.main, self.window.footer
        self._mirroring = True
        try:
            f.range_slider.setMaximum(mw.range_slider.maximum())
            f.range_slider.setValues(mw.range_slider.low(), mw.range_slider.high())
            f.volume_slider.setValue(mw.volume_slider.value())
            f.mute_button.setChecked(mw.mute_button.isChecked())
            f.position_slider.setRange(mw.position_slider.minimum(), mw.position_slider.maximum())
            f.position_slider.setValue(mw.position_slider.value())
        finally:
            self._mirroring = False
        f.position_label.setText(mw.position_label.text())
        self._mirror_texts()
        self._mirror_play()
        self.sync_enabled()
        self.retranslate()

    def _mirror_texts(self) -> None:
        f, mw = self.window.footer, self.main
        f.start_edit.setText(format_time(mw.range_slider.low()))
        f.end_edit.setText(format_time(mw.range_slider.high()))

    def sync_enabled(self) -> None:
        if self.window is None:
            return
        mw, f = self.main, self.window.footer
        for mine, theirs in ((f.play_button, mw.play_button), (f.position_slider, mw.position_slider),
                             (f.range_slider, mw.range_slider), (f.start_edit, mw.start_edit),
                             (f.end_edit, mw.end_edit), (f.set_start_button, mw.set_start_button),
                             (f.set_end_button, mw.set_end_button), (f.add_button, mw.add_button)):
            mine.setEnabled(theirs.isEnabled())
        self.window.export_button.setEnabled(mw.save_button.isEnabled())
        tip = ""
        if mw.is_busy():
            tip = mw.t("saving")
        elif not mw.segments():
            tip = mw.t("save_disabled_tip")
        self.window.export_button.setToolTip(tip)

    def retranslate(self) -> None:
        if self.window is None:
            return
        mw, f = self.main, self.window.footer
        f.start_label.setText(mw.t("start"))
        f.end_label.setText(mw.t("end"))
        f.set_start_button.setText(mw.t("set_start"))
        f.set_start_button.setToolTip(mw.t("set_start_tip"))
        f.set_end_button.setText(mw.t("set_end"))
        f.set_end_button.setToolTip(mw.t("set_end_tip"))
        f.add_button.setText(mw.t("add_segment"))
        f.add_button.setToolTip(mw.t("add_segment_tip"))
        f.mute_button.setToolTip(mw.mute_button.toolTip())
        f.volume_slider.setToolTip(mw.t("volume"))
        self.window.exit_button.setToolTip(mw.t("exit_fullscreen"))
        self.window.export_button.setText(mw.t("export"))
        self.window.setWindowTitle(mw.t("window_title"))
        self._mirror_play()

    def apply_theme(self, name: str) -> None:
        if self.window is not None:
            theme.apply_theme(self.window, name)

    def _mirror_play(self) -> None:
        if self.window is None:
            return
        f, mw = self.window.footer, self.main
        f.play_button.setIconKind(mw.play_button.iconKind())
        f.play_button.setToolTip(mw.play_button.toolTip())

    def _mirror_time(self, ms: int) -> None:
        if self.window is None:
            return
        f = self.window.footer
        if not f.position_slider.isSliderDown():
            f.position_slider.blockSignals(True)
            f.position_slider.setRange(0, self.main.position_slider.maximum())
            f.position_slider.setValue(ms)
            f.position_slider.blockSignals(False)
            f.position_slider.update()
        f.position_label.setText(format_time(ms / 1000.0))

    def _main_volume(self, value: int) -> None:
        if self.window is None:
            return
        f = self.window.footer
        if f.volume_slider.value() != value:
            f.volume_slider.blockSignals(True)
            f.volume_slider.setValue(value)
            f.volume_slider.blockSignals(False)

    def _footer_volume(self, value: int) -> None:
        if self.main.volume_slider.value() != value:
            self.main.volume_slider.setValue(value)

    def _main_mute(self, muted: bool) -> None:
        if self.window is None:
            return
        f = self.window.footer
        f.mute_button.blockSignals(True)
        f.mute_button.setChecked(muted)
        f.mute_button.blockSignals(False)
        f.mute_button.setToolTip(self.main.mute_button.toolTip())

    def _footer_mute(self, muted: bool) -> None:
        if self.main.mute_button.isChecked() != muted:
            self.main.mute_button.setChecked(muted)
        self.window.footer.mute_button.setToolTip(self.main.mute_button.toolTip())

    def _main_range(self, low: float, high: float) -> None:
        if self._mirroring or self.window is None:
            return
        f = self.window.footer
        self._mirroring = True
        try:
            f.range_slider.setMaximum(self.main.range_slider.maximum())
            f.range_slider.setValues(low, high)
        finally:
            self._mirroring = False
        self._mirror_texts()

    def _footer_range(self, low: float, high: float) -> None:
        if self._mirroring:
            return
        self._mirroring = True
        try:
            self.main.range_slider.setValues(low, high)
        finally:
            self._mirroring = False
        self._mirror_texts()

    def _footer_drag_started(self, which: str) -> None:
        self.main._external_drag = True
        self.main._on_drag_started(which)

    def _footer_drag_finished(self, which: str) -> None:
        self.main._external_drag = False
        self.main._on_drag_finished(which)

    def _footer_edit(self, is_start: bool) -> None:
        mw, f = self.main, self.window.footer
        src, dst = (f.start_edit, mw.start_edit) if is_start else (f.end_edit, mw.end_edit)
        dst.setText(src.text())
        mw._edit_finished(is_start)
        self._mirror_texts()
        src.clearFocus()
        self.window.setFocus()

    def _segment_created(self, n: int) -> None:
        if self.active:
            self.window.show_toast(self.main.t("segment_created", n=n))
