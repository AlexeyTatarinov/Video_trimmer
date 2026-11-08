"""Main window: preview, range selection, segment list, save."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QScrollArea, QSizePolicy, QVBoxLayout,
)

from video_trimmer import core, i18n
from video_trimmer.ui import theme
from video_trimmer.ui.preview import PreviewPlayer
from video_trimmer.ui.range_slider import RangeSlider
from video_trimmer.ui.segment_cards import SegmentCardList
from video_trimmer.ui.widgets import (
    ElidedLabel, GlassBackground, GlassButton, GlassComboBox, GlassPanel, GlassSlider,
)
from video_trimmer.ui.timefmt import format_time, parse_time
from video_trimmer.ui.worker import Worker, start_worker


MIN_WINDOW_SIZE = QSize(760, 560)


class MainWindow(QMainWindow):
    # Relay used to run worker callbacks on the GUI thread (queued across threads).
    _gui_call = Signal(object)

    def __init__(self, language: str = i18n.DEFAULT_LANGUAGE, settings=None) -> None:
        super().__init__()
        self._settings = settings if settings is not None else theme.make_settings()
        self.theme_name = theme.load_theme_name(self._settings)
        theme.set_current(self.theme_name)
        self.language = language if language in i18n.STRINGS else i18n.DEFAULT_LANGUAGE
        self._src: str | None = None
        self._duration = 0.0
        self._segments: list[tuple[float, float]] = []
        self._syncing = False
        self._busy = False
        self._thread = None
        self._worker: Worker | None = None
        self._status_key = "ready"
        self._status_kwargs: dict = {}
        self._gui_call.connect(self._invoke)
        self.setAcceptDrops(True)
        self.setMinimumSize(MIN_WINDOW_SIZE)
        self.resize(self._initial_size().expandedTo(MIN_WINDOW_SIZE))
        self._build_ui()
        self._connect_player()
        self.retranslate()
        self._update_enabled()
        theme.apply_theme(self, self.theme_name)
        self._update_theme_button()

    # ------------------------------------------------------------------ build
    def _build_ui(self) -> None:
        # The whole interface lives in a scroll area: when the window (or screen) is smaller than
        # the content, it scrolls instead of clipping or overlapping.
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("mainScroll")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        root = GlassBackground()
        self.scroll_area.setWidget(root)
        self.setCentralWidget(self.scroll_area)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(20, 14, 20, 16)
        lay.setSpacing(12)
        T = i18n.all_texts

        # header: title, open, language, theme
        header = QHBoxLayout()
        header.setSpacing(12)
        self.title_label = ElidedLabel()
        self.title_label.setObjectName("title")
        self.title_label.set_measure_texts(T("window_title"))
        self.open_button = GlassButton()
        self.open_button.set_texts(T("open"))
        self.open_button.clicked.connect(self._choose_file)
        self.language_label = ElidedLabel()
        self.language_label.set_measure_texts(T("language"))
        self.language_combo = GlassComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
        self.language_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.language_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.language_combo.currentIndexChanged.connect(
            lambda _i: self.set_language(self.language_combo.currentData()))
        self.theme_button = GlassButton(icon_kind="moon", diameter=42)
        self.theme_button.clicked.connect(self.toggle_theme)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.open_button)
        header.addSpacing(8)
        header.addWidget(self.language_label)
        header.addWidget(self.language_combo)
        header.addWidget(self.theme_button)
        lay.addLayout(header)

        # video: the only stretching element (the widget ignores the video's native size)
        video_panel = GlassPanel(shadow=False)
        video_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        video_panel.body.setContentsMargins(10, 10, 10, 10)
        self.player = PreviewPlayer(self)
        self.video_widget = self.player.video_widget
        self.video_widget.setAutoFillBackground(True)
        pal = self.video_widget.palette()
        pal.setColor(pal.ColorRole.Window, QColor(8, 8, 14))
        self.video_widget.setPalette(pal)
        video_panel.body.addWidget(self.video_widget, 1)
        self.video_panel = video_panel
        lay.addWidget(video_panel, 1)

        # transport: play, position, time, mute, volume (always fully visible)
        transport = GlassPanel()
        row = QHBoxLayout()
        row.setSpacing(12)
        self.play_button = GlassButton(icon_kind="play", diameter=52, primary=True)
        self.play_button.clicked.connect(self.toggle_play)
        self.position_slider = GlassSlider()
        self.position_slider.setRange(0, 0)
        self.position_slider.setMinimumWidth(100)
        self.position_slider.sliderMoved.connect(self._seek)
        self.position_label = ElidedLabel(format_time(0))
        self.position_label.setObjectName("time")
        self.position_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.position_label.set_measure_texts(
            [f"{d}{d}:{d}{d}:{d}{d}.{d}{d}{d}" for d in "0123456789"])
        self.mute_button = GlassButton(icon_kind="speaker", diameter=42)
        self.mute_button.setCheckable(True)
        self.mute_button.toggled.connect(self._on_mute_toggled)
        self.volume_slider = GlassSlider()
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(round(self.player.volume() * 100)))
        self.volume_slider.setMinimumWidth(90)
        self.volume_slider.setMaximumWidth(160)
        self.volume_slider.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        row.addWidget(self.play_button)
        row.addWidget(self.position_slider, 1)
        row.addWidget(self.position_label)
        row.addSpacing(6)
        row.addWidget(self.mute_button)
        row.addWidget(self.volume_slider)
        transport.body.addLayout(row)
        lay.addWidget(transport)

        # range
        self.range_box = GlassPanel()
        rl = self.range_box.body
        self.range_slider = RangeSlider()
        self.range_slider.rangeChanged.connect(self._on_range_changed)
        self.range_slider.handleMoved.connect(self._on_handle_moved)
        self.range_slider.dragStarted.connect(self._on_drag_started)
        self.range_slider.dragFinished.connect(self._on_drag_finished)
        rl.addWidget(self.range_slider)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.start_label, self.end_label = ElidedLabel(), ElidedLabel()
        self.start_label.set_measure_texts(T("start") + T("end"))
        self.end_label.set_measure_texts(T("start") + T("end"))
        self.start_edit, self.end_edit = QLineEdit(), QLineEdit()
        for edit in (self.start_edit, self.end_edit):
            edit.setFixedSize(136, 38)
            edit.setAlignment(Qt.AlignCenter)
        self.start_edit.editingFinished.connect(lambda: self._edit_finished(True))
        self.end_edit.editingFinished.connect(lambda: self._edit_finished(False))
        self.set_start_button, self.set_end_button = GlassButton(), GlassButton()
        for b in (self.set_start_button, self.set_end_button):
            b.set_texts(T("set_start") + T("set_end"))
        self.set_start_button.clicked.connect(self.set_start_from_position)
        self.set_end_button.clicked.connect(self.set_end_from_position)
        grid.addWidget(self.start_label, 0, 0)
        grid.addWidget(self.start_edit, 0, 1)
        grid.addWidget(self.set_start_button, 0, 2)
        grid.addWidget(self.end_label, 1, 0)
        grid.addWidget(self.end_edit, 1, 1)
        grid.addWidget(self.set_end_button, 1, 2)
        grid.setColumnStretch(3, 1)
        rl.addLayout(grid)
        lay.addWidget(self.range_box)

        # segments: wrapping cards + add / remove
        self.segments_box = GlassPanel()
        sl = QHBoxLayout()
        sl.setSpacing(14)
        self.segment_list = SegmentCardList()
        self.segment_list.currentRowChanged.connect(self._on_row_changed)
        self.segment_list.removeRequested.connect(self.remove_segment_at)
        side = QVBoxLayout()
        side.setSpacing(6)
        self.add_button, self.remove_button = GlassButton(), GlassButton()
        for b in (self.add_button, self.remove_button):
            b.set_texts(T("add_segment") + T("remove_segment"))
        self.add_button.clicked.connect(self.add_segment)
        self.remove_button.clicked.connect(self.remove_segment)
        side.addWidget(self.add_button)
        side.addWidget(self.remove_button)
        side.addStretch(1)
        sl.addWidget(self.segment_list, 1)
        sl.addLayout(side)
        self.segments_box.body.addLayout(sl)
        lay.addWidget(self.segments_box)

        # mode + save
        bottom_panel = GlassPanel()
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.mode_label = ElidedLabel()
        self.mode_label.set_measure_texts(T("mode"))
        self.fast_radio, self.precise_radio = GlassButton(), GlassButton()
        self.fast_radio.set_texts(T("mode_fast"))
        self.precise_radio.set_texts(T("mode_precise"))
        for b in (self.fast_radio, self.precise_radio):
            b.setCheckable(True)
            b.set_shrinkable(True)  # the only buttons that may be squeezed (elided) when narrow
        self.fast_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.fast_radio)
        self.mode_group.addButton(self.precise_radio)
        self.save_button = GlassButton(primary=True)
        self.save_button.set_texts(T("save"))
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        for w in (self.mode_label, self.fast_radio, self.precise_radio):
            bottom.addWidget(w)
        bottom.addStretch(1)
        bottom.addWidget(self.save_button)
        bottom_panel.body.addLayout(bottom)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        bottom_panel.body.addWidget(self.progress_bar)
        self.status_label = ElidedLabel()  # one line, elided: a long text never resizes anything
        self.status_label.setObjectName("status")
        bottom_panel.body.addWidget(self.status_label)
        lay.addWidget(bottom_panel)

    def _initial_size(self) -> QSize:
        """Comfortable default, never more than 90% of the usable screen area."""
        screen = QGuiApplication.primaryScreen()
        want = QSize(1120, 820)
        if screen is None:
            return want
        geo = screen.availableGeometry()
        return QSize(min(want.width(), int(geo.width() * 0.9)),
                     min(want.height(), int(geo.height() * 0.9)))

    def _connect_player(self) -> None:
        self.player.positionChanged.connect(self._on_player_position)
        self.player.playingChanged.connect(lambda _p: self._update_play_text())
        self.player.error.connect(self._on_player_error)

    # ------------------------------------------------------------------ i18n
    def t(self, key: str, **kw: object) -> str:
        return i18n.tr(self.language, key, **kw)

    def set_language(self, lang: str) -> None:
        if lang not in i18n.STRINGS:
            return
        self.language = lang
        idx = self.language_combo.findData(lang)
        if idx != self.language_combo.currentIndex():
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(idx)
            self.language_combo.blockSignals(False)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self.t("window_title"))
        self.title_label.setText(self.t("window_title"))
        self.open_button.setText(self.t("open"))
        self._update_theme_button()
        self._update_mute_button()
        self.volume_slider.setToolTip(self.t("volume"))
        self._update_play_text()
        self.range_box.setTitle(self.t("start") + " / " + self.t("end"))
        self.start_label.setText(self.t("start"))
        self.end_label.setText(self.t("end"))
        self.set_start_button.setText(self.t("set_start"))
        self.set_end_button.setText(self.t("set_end"))
        self.segments_box.setTitle(self.t("segments"))
        self.add_button.setText(self.t("add_segment"))
        self.remove_button.setText(self.t("remove_segment"))
        self.mode_label.setText(self.t("mode"))
        self.fast_radio.setText(self.t("mode_fast"))
        self.fast_radio.setToolTip(self.t("mode_fast_tip"))
        self.precise_radio.setText(self.t("mode_precise"))
        self.precise_radio.setToolTip(self.t("mode_precise_tip"))
        self.language_label.setText(self.t("language"))
        self.save_button.setText(self.t("save"))
        self._refresh_segment_items()
        self._show_status(self._status_key, **self._status_kwargs)

    def _show_status(self, key: str, **kw: object) -> None:
        self._status_key, self._status_kwargs = key, kw
        self.status_label.setText(self.t(key, **kw))

    # ------------------------------------------------------------------ state
    def is_busy(self) -> bool:
        return self._busy

    def has_video(self) -> bool:
        return self._src is not None and self._duration > 0

    def segments(self) -> list[tuple[float, float]]:
        return list(self._segments)

    def mode(self) -> str:
        return "precise" if self.precise_radio.isChecked() else "fast"

    def current_position(self) -> float:
        return self.player.position_ms() / 1000.0

    def _update_enabled(self) -> None:
        loaded = self.has_video() and not self._busy
        for w in (self.save_button, self.add_button, self.set_start_button, self.set_end_button,
                  self.start_edit, self.end_edit, self.range_slider, self.segment_list,
                  self.play_button, self.position_slider):
            w.setEnabled(loaded)
        self.remove_button.setEnabled(loaded and len(self._segments) > 1)
        self.segment_list.set_removable(loaded)
        self.open_button.setEnabled(not self._busy)

    def _update_play_text(self) -> None:
        playing = self.player.is_playing()
        self.play_button.setIconKind("pause" if playing else "play")
        self.play_button.setToolTip(self.t("pause" if playing else "play"))

    # ------------------------------------------------------------------ theme
    def set_theme(self, name: str) -> None:
        if name not in theme.THEMES:
            return
        self.theme_name = name
        theme.apply_theme(self, name)
        theme.save_theme_name(self._settings, name)
        self._update_theme_button()

    def toggle_theme(self) -> None:
        self.set_theme("dark" if self.theme_name == "light" else "light")

    def _update_theme_button(self) -> None:
        # the button shows (and offers) the theme you would switch to
        dark = self.theme_name == "dark"
        self.theme_button.setIconKind("sun" if dark else "moon")
        self.theme_button.setToolTip(self.t("theme_to_light" if dark else "theme_to_dark"))

    # ------------------------------------------------------------------ audio
    def _on_mute_toggled(self, muted: bool) -> None:
        self.player.set_muted(muted)
        self._update_mute_button()

    def _update_mute_button(self) -> None:
        self.mute_button.setToolTip(self.t("unmute" if self.mute_button.isChecked() else "mute"))

    def _on_volume_changed(self, value: int) -> None:
        self.player.set_volume(value / 100.0)

    # ------------------------------------------------------------------ messages
    def _notify(self, kind: str, text: str) -> None:
        """Show a modal message. ``kind`` is 'info' or 'error'."""
        if kind == "error":
            QMessageBox.critical(self, self.t("error_title"), text)
        else:
            QMessageBox.information(self, self.t("info_title"), text)

    def _error(self, text: str) -> None:
        self.status_label.setText(text)
        self._notify("error", text)

    # ------------------------------------------------------------------ file open
    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.t("open_dialog_title"), "", self.t("video_filter"))
        if path:
            self.open_file(path)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.open_file(urls[0].toLocalFile())

    def open_file(self, path: str) -> None:
        if self._busy:
            return
        path = str(path)
        self._show_status("loading")
        self._run(lambda _p: core.probe(path),
                  on_result=lambda info: self._on_probed(path, info),
                  on_error=self._error)

    def _on_probed(self, path: str, info: core.VideoInfo) -> None:
        if info.duration <= 0:
            self._error(self.t("empty_duration"))
            return
        self._src, self._duration = path, float(info.duration)
        self._segments = [(0.0, self._duration)]
        self.range_slider.setMaximum(self._duration)
        self.position_slider.setRange(0, int(self._duration * 1000))
        self.player.set_source(path)
        self.progress_bar.setValue(0)
        self._show_status("ready")
        self._refresh_segment_items(select=-1)
        self.segment_list.setCurrentRow(0)
        self._select_row(0)
        self._update_enabled()

    def _on_player_error(self, *_args) -> None:
        self._show_status("preview_unavailable")

    # ------------------------------------------------------------------ playback
    def toggle_play(self) -> None:
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()

    def _seek(self, ms: int) -> None:
        self.player.set_position_ms(ms)

    def _show_time(self, ms: int) -> None:
        """Make the position slider and label show ``ms`` (without seeking)."""
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(ms)
        self.position_slider.blockSignals(False)
        self.position_label.setText(format_time(ms / 1000.0))

    def preview_at(self, seconds: float, immediate: bool = False) -> None:
        """Show the video frame at ``seconds`` (one preview, jumps to the handle being edited)."""
        ms = int(round(max(seconds, 0.0) * 1000))
        self._show_time(ms)
        self.player.show_frame_at(ms, immediate=immediate)

    def _handle_value(self, which: str) -> float:
        return self.range_slider.low() if which == "start" else self.range_slider.high()

    def _on_handle_moved(self, which: str, value: float) -> None:
        if not self._syncing:
            self.preview_at(value)

    def _on_drag_started(self, which: str) -> None:
        self.preview_at(self._handle_value(which), immediate=True)

    def _on_drag_finished(self, which: str) -> None:
        self.preview_at(self._handle_value(which), immediate=True)

    def _on_player_position(self, ms: int) -> None:
        if self.range_slider.is_dragging():
            return  # the displayed time follows the handle being dragged
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(ms)
        self.position_label.setText(format_time(ms / 1000.0))

    # ------------------------------------------------------------------ segments
    def _refresh_segment_items(self, select: int | None = None) -> None:
        self.segment_list.set_segments(self._segments, self.language, select)

    def _select_row(self, row: int, preview: bool = False) -> None:
        """Load segment ``row`` into the slider and time fields."""
        if not 0 <= row < len(self._segments):
            return
        s, e = self._segments[row]
        self._syncing = True
        try:
            self.range_slider.setValues(s, e)
            self.start_edit.setText(format_time(s))
            self.end_edit.setText(format_time(e))
        finally:
            self._syncing = False
        if preview:
            self.preview_at(s, immediate=True)

    def _on_row_changed(self, row: int) -> None:
        self._select_row(row, preview=True)

    def _on_range_changed(self, low: float, high: float) -> None:
        row = self.segment_list.currentRow()
        if self._syncing or not 0 <= row < len(self._segments):
            return
        self._segments[row] = (low, high)
        self.start_edit.setText(format_time(low))
        self.end_edit.setText(format_time(high))
        self.segment_list.update_segment(row, self._segments[row])

    def _edit_finished(self, is_start: bool) -> None:
        edit = self.start_edit if is_start else self.end_edit
        try:
            value = parse_time(edit.text())
        except ValueError:
            self._show_status("bad_time", text=edit.text())
            value = None
        if value is not None:
            (self.range_slider.setLow if is_start else self.range_slider.setHigh)(value)
        # Re-display the (possibly clamped / unchanged) value.
        edit.setText(format_time(self.range_slider.low() if is_start else self.range_slider.high()))

    def set_start_from_position(self) -> None:
        self.range_slider.setLow(self.current_position())

    def set_end_from_position(self) -> None:
        self.range_slider.setHigh(self.current_position())

    def add_segment(self) -> None:
        """Append a copy of the selected segment (overlaps and duplicates are allowed)."""
        if not self._segments:
            return
        row = self.segment_list.currentRow()
        if not 0 <= row < len(self._segments):
            row = len(self._segments) - 1
        self._segments.append(self._segments[row])
        new_row = len(self._segments) - 1
        self._refresh_segment_items(select=new_row)
        self._select_row(new_row)
        self.segment_list.ensureWidgetVisible(self.segment_list.card(new_row), 4, 4)
        self._update_enabled()

    def remove_segment(self) -> None:
        """Remove the selected segment; the last remaining one cannot be removed."""
        self.remove_segment_at(self.segment_list.currentRow())

    def remove_segment_at(self, row: int) -> None:
        """Remove segment ``row`` (a card's cross); the last remaining one cannot be removed."""
        if len(self._segments) <= 1 or not 0 <= row < len(self._segments) or self._busy:
            return
        current = self.segment_list.currentRow()
        del self._segments[row]
        if row < current:
            new_row = current - 1
        else:
            new_row = min(current if row != current else row, len(self._segments) - 1)
        self._refresh_segment_items(select=new_row)
        self._select_row(new_row, preview=(row == current))
        self._update_enabled()

    # ------------------------------------------------------------------ saving
    def _ask_save_dir(self, default: Path) -> str:
        return QFileDialog.getExistingDirectory(self, self.t("save_dialog_title"), str(default))

    def save(self) -> None:
        if self._busy or not self.has_video():
            return
        src, mode = self._src, self.mode()
        try:
            ranges = core.validate_segments(list(self._segments), self._duration)
        except core.TrimError as exc:
            self._error(str(exc))
            return
        out_dir = self._ask_save_dir(Path(src).parent)
        if not out_dir:
            return
        self.progress_bar.setValue(0)
        self._show_status("saving")
        self._run(
            lambda progress: core.trim_each(src, ranges, out_dir, mode, progress),
            on_result=lambda paths: self._on_saved(paths, out_dir),
            on_error=self._error,
            on_progress=lambda v: self.progress_bar.setValue(int(round(min(max(v, 0.0), 1.0) * 100))),
        )

    def _on_saved(self, paths, out_dir) -> None:
        self.progress_bar.setValue(100)
        self._show_status("saved", count=len(list(paths)), folder=str(out_dir))
        self._notify("info", self.t("saved", count=len(list(paths)), folder=str(out_dir)))

    # ------------------------------------------------------------------ threading
    def _run(self, fn, on_result, on_error, on_progress=None) -> None:
        worker = Worker(fn)
        worker.result.connect(lambda value: self._gui_call.emit(lambda: on_result(value)))
        worker.error.connect(lambda text: self._gui_call.emit(lambda: on_error(text)))
        if on_progress:
            worker.progress.connect(lambda v: self._gui_call.emit(lambda: on_progress(v)))
        self._worker = worker
        self._busy = True
        self._update_enabled()
        self._thread = start_worker(worker)
        self._thread.finished.connect(self._on_thread_finished)

    @Slot(object)
    def _invoke(self, fn) -> None:
        fn()

    def _on_thread_finished(self) -> None:
        self._busy = False
        self._update_enabled()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.player.stop()
        if self._thread is not None and self._thread.isRunning():
            self._thread.wait()
        super().closeEvent(event)
