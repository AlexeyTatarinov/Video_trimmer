"""Main window: preview, range selection, segment list, save."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractSlider, QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QMainWindow,
    QMessageBox, QScrollArea, QSizePolicy, QVBoxLayout,
)

from video_trimmer import core, i18n
from video_trimmer.ui import theme
from video_trimmer.ui.preview import PreviewPlayer
from video_trimmer.ui.range_slider import RangeSlider
from video_trimmer.ui.popups import ModeInfoPopup, SettingsPopup
from video_trimmer.ui.segment_cards import SegmentCardList
try:  # needs QtMultimedia (PySide6-Addons)
    from video_trimmer.ui.fullscreen import FullscreenController
except ImportError:  # pragma: no cover - depends on installation
    FullscreenController = None
from video_trimmer.ui.widgets import (
    ElidedLabel, GlassBackground, GlassButton, GlassPanel, GlassSlider, StatusProgressBar,
)
from video_trimmer.ui.timefmt import format_time, parse_time
from video_trimmer.ui.worker import Worker, start_worker


MIN_WINDOW_SIZE = QSize(960, 600)
TIME_FIELD_SIZE = QSize(116, 32)


class MainWindow(QMainWindow):
    # Relay used to run worker callbacks on the GUI thread (queued across threads).
    _gui_call = Signal(object)
    displayTimeChanged = Signal(int)   # ms shown by the position slider / label (also while paused)
    segmentCreated = Signal(int)       # number (1-based) of the card that "Add" has just created

    def __init__(self, language: str | None = None, settings=None) -> None:
        super().__init__()
        self._settings = settings if settings is not None else theme.make_settings()
        self.theme_name = theme.load_theme_name(self._settings)
        theme.set_current(self.theme_name)
        if language is None:
            language = theme.load_language(self._settings, i18n.STRINGS, i18n.DEFAULT_LANGUAGE)
        self.language = language if language in i18n.STRINGS else i18n.DEFAULT_LANGUAGE
        self._src: str | None = None
        self._duration = 0.0
        self._segments: list[tuple[float, float]] = []
        self._syncing = False
        self._busy = False
        self._external_drag = False   # a range handle is being dragged in the full-screen footer
        self._fullscreen = None
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
        if FullscreenController is not None:
            self._fullscreen = FullscreenController(self)
        self.retranslate()
        self._update_enabled()
        theme.apply_theme(self, self.theme_name)
        self.settings_popup.sync(self.language, self.theme_name)

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
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(6)
        T = i18n.all_texts

        # header: title on the left; "Open video" and the gear on the right
        header = QHBoxLayout()
        header.setSpacing(10)
        self.title_label = ElidedLabel()
        self.title_label.setObjectName("title")
        self.title_label.set_measure_texts(T("window_title"))
        self.open_button = GlassButton()
        self.open_button.set_texts(T("open"))
        self.open_button.clicked.connect(self._choose_file)
        self.settings_button = GlassButton(icon_kind="gear", diameter=38)
        self.settings_button.clicked.connect(self.show_settings)
        self.settings_popup = SettingsPopup(self)
        self.settings_popup.languageChosen.connect(self.set_language)
        self.settings_popup.themeChosen.connect(self.set_theme)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.open_button)
        header.addWidget(self.settings_button)
        lay.addLayout(header)

        # video: the only stretching element (the widget ignores the video's native size)
        video_panel = GlassPanel(shadow=False)
        video_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        video_panel.body.setContentsMargins(8, 8, 8, 8)
        self.player = PreviewPlayer(self)
        self.video_widget = self.player.video_widget
        if hasattr(self.video_widget, "doubleClicked"):
            self.video_widget.doubleClicked.connect(self.toggle_fullscreen)
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
        row.setSpacing(10)
        self.play_button = GlassButton(icon_kind="play", diameter=42, primary=True)
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
        self.mute_button = GlassButton(icon_kind="speaker", diameter=38)
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
        self.transport_box = transport
        lay.addWidget(transport)

        # range: the two-handle slider, and ONE row with the fields and the segment buttons
        self.range_box = GlassPanel()
        rl = self.range_box.body
        self.range_slider = RangeSlider()
        self.range_slider.rangeChanged.connect(self._on_range_changed)
        self.range_slider.handleMoved.connect(self._on_handle_moved)
        self.range_slider.dragStarted.connect(self._on_drag_started)
        self.range_slider.dragFinished.connect(self._on_drag_finished)
        rl.addWidget(self.range_slider)
        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.start_label, self.end_label = ElidedLabel(), ElidedLabel()
        self.start_label.set_measure_texts(T("start") + T("end"))
        self.end_label.set_measure_texts(T("start") + T("end"))
        self.start_edit, self.end_edit = QLineEdit(), QLineEdit()
        for edit in (self.start_edit, self.end_edit):
            edit.setFixedSize(TIME_FIELD_SIZE)
            edit.setAlignment(Qt.AlignCenter)
        self.start_edit.editingFinished.connect(lambda: self._edit_finished(True))
        self.end_edit.editingFinished.connect(lambda: self._edit_finished(False))
        self.set_start_button, self.set_end_button = GlassButton(), GlassButton()
        for b in (self.set_start_button, self.set_end_button):
            b.set_texts(T("set_start") + T("set_end"))
        self.set_start_button.clicked.connect(self.set_start_from_position)
        self.set_end_button.clicked.connect(self.set_end_from_position)
        self.add_button, self.clear_button = GlassButton(), GlassButton()
        self.add_button.set_texts(T("add_segment"))
        self.clear_button.set_texts(T("clear_all"))
        self.add_button.clicked.connect(self.add_segment)
        self.clear_button.clicked.connect(self.clear_segments)
        controls.addWidget(self.start_label)
        controls.addWidget(self.start_edit)
        controls.addWidget(self.set_start_button)
        controls.addSpacing(4)
        controls.addWidget(self.end_label)
        controls.addWidget(self.end_edit)
        controls.addWidget(self.set_end_button)
        # "Editing segment #N": it lives in the free space of this row (it takes the place of the
        # stretch and is elided when narrow), so showing it never changes the geometry
        self.edit_note = ElidedLabel()
        self.edit_note.setObjectName("editNote")
        self.edit_note.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        controls.addWidget(self.edit_note, 1)
        controls.addWidget(self.add_button)
        controls.addWidget(self.clear_button)
        rl.addLayout(controls)
        lay.addWidget(self.range_box)

        # segments: their own container with the wrapping, reorderable cards
        self.segments_box = GlassPanel()
        self.segment_list = SegmentCardList()
        self.segment_list.currentRowChanged.connect(self._on_row_changed)
        self.segment_list.removeRequested.connect(self.remove_segment_at)
        self.segment_list.moveRequested.connect(self.move_segment)
        self.segments_box.body.addWidget(self.segment_list)
        lay.addWidget(self.segments_box)

        # bottom row: mode (+ info), progress bar with the status inside, save
        bottom_panel = GlassPanel()
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.mode_label = ElidedLabel()
        self.mode_label.set_measure_texts(T("mode"))
        self.fast_radio, self.precise_radio = GlassButton(), GlassButton()
        self.fast_radio.set_texts(T("mode_fast"))
        self.precise_radio.set_texts(T("mode_precise"))
        for b in (self.fast_radio, self.precise_radio):
            b.setCheckable(True)
        self.fast_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.fast_radio)
        self.mode_group.addButton(self.precise_radio)
        self.info_button = GlassButton(icon_kind="question", diameter=30)
        self.info_button.clicked.connect(self.show_mode_info)
        self.info_popup = ModeInfoPopup(self)
        self.progress_bar = StatusProgressBar()
        self.progress_bar.setRange(0, 100)
        self.status_label = self.progress_bar  # the status text is drawn inside the progress bar
        self.save_button = GlassButton(primary=True)
        self.save_button.set_texts(T("save"))
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        bottom.addWidget(self.mode_label)
        bottom.addWidget(self.fast_radio)
        bottom.addWidget(self.precise_radio)
        bottom.addWidget(self.info_button)
        bottom.addSpacing(6)
        bottom.addWidget(self.progress_bar, 1)
        bottom.addSpacing(6)
        bottom.addWidget(self.save_button)
        bottom_panel.body.addLayout(bottom)
        lay.addWidget(bottom_panel)
        # Alt+Left / Alt+Right must work wherever the focus is (buttons and sliders use arrows)
        for w in (self.scroll_area, *root.findChildren(GlassButton), *root.findChildren(QAbstractSlider)):
            w.installEventFilter(self)

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
        theme.save_language(self._settings, lang)
        self.settings_popup.sync(self.language, self.theme_name)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self.t("window_title"))
        self.title_label.setText(self.t("window_title"))
        self.open_button.setText(self.t("open"))
        self.settings_button.setToolTip(self.t("settings"))
        self.settings_popup.retranslate(self.language)
        self._update_mute_button()
        self.volume_slider.setToolTip(self.t("volume"))
        self._update_play_text()
        self.start_label.setText(self.t("start"))
        self.end_label.setText(self.t("end"))
        self.set_start_button.setText(self.t("set_start"))
        self.set_start_button.setToolTip(self.t("set_start_tip"))
        self.set_end_button.setText(self.t("set_end"))
        self.set_end_button.setToolTip(self.t("set_end_tip"))
        self.add_button.setText(self.t("add_segment"))
        self.add_button.setToolTip(self.t("add_segment_tip"))
        self.video_widget.setToolTip(self.t("fullscreen_tip"))
        self.clear_button.setText(self.t("clear_all"))
        self.clear_button.setToolTip(self.t("clear_all_tip"))
        self.segments_box.setToolTip(self.t("segments"))
        self.mode_label.setText(self.t("mode"))
        self.fast_radio.setText(self.t("mode_fast"))
        self.fast_radio.setToolTip(f"<p>{self.t('mode_fast_tip')}</p>")
        self.precise_radio.setText(self.t("mode_precise"))
        self.precise_radio.setToolTip(f"<p>{self.t('mode_precise_tip')}</p>")
        self.info_button.setToolTip(self.t("mode_info"))
        self.info_popup.set_language(self.language)
        self.save_button.setText(self.t("save"))
        self._refresh_segment_items()
        self._update_edit_note()
        self._update_save_tip()
        self._show_status(self._status_key, **self._status_kwargs)
        if self._fullscreen is not None:
            self._fullscreen.retranslate()

    def show_settings(self) -> None:
        self.settings_popup.sync(self.language, self.theme_name)
        self.settings_popup.popup_below(self.settings_button, align_right=True)

    def show_mode_info(self) -> None:
        self.info_popup.set_language(self.language)
        self.info_popup.popup_below(self.info_button, align_right=False, above=True)

    def _show_status(self, key: str, **kw: object) -> None:
        self._status_key, self._status_kwargs = key, kw
        self.progress_bar.setText(self.t(key, **kw))

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
        for w in (self.add_button, self.clear_button, self.set_start_button,
                  self.set_end_button, self.start_edit, self.end_edit, self.range_slider,
                  self.segment_list, self.play_button, self.position_slider):
            w.setEnabled(loaded)
        self.save_button.setEnabled(loaded and bool(self._segments))   # nothing to save without cards
        self._update_save_tip()
        self.segment_list.set_removable(loaded)
        self.open_button.setEnabled(not self._busy)
        if self._fullscreen is not None:
            self._fullscreen.sync_enabled()

    def _update_save_tip(self) -> None:
        explain = self.has_video() and not self._segments
        self.save_button.setToolTip(self.t("save_disabled_tip") if explain else "")

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
        if self._fullscreen is not None:
            self._fullscreen.apply_theme(name)
        theme.save_theme_name(self._settings, name)
        self.settings_popup.sync(self.language, self.theme_name)

    def toggle_theme(self) -> None:
        self.set_theme("dark" if self.theme_name == "light" else "light")

    # ------------------------------------------------------------------ audio
    def _on_mute_toggled(self, muted: bool) -> None:
        self.player.set_muted(muted)
        self._update_mute_button()

    def _update_mute_button(self) -> None:
        self.mute_button.setToolTip(self.t("unmute" if self.mute_button.isChecked() else "mute"))
        if self._fullscreen is not None and self._fullscreen.window is not None:
            self._fullscreen.window.footer.mute_button.setToolTip(self.mute_button.toolTip())

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
        self.progress_bar.setText(text)
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
        self._segments = []                       # no cards: the sliders hold the draft (whole file)
        self.segment_list.setCurrentRow(-1)
        self._syncing = True
        try:
            self.range_slider.setMaximum(self._duration)
            self.range_slider.setValues(0.0, self._duration)
            self.start_edit.setText(format_time(0.0))
            self.end_edit.setText(format_time(self._duration))
        finally:
            self._syncing = False
        self.position_slider.setRange(0, int(self._duration * 1000))
        self.player.set_source(path)
        self.progress_bar.setValue(0)
        self._show_status("ready")
        self._refresh_segment_items(select=-1)
        self._update_edit_note()
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
        self.displayTimeChanged.emit(int(ms))

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
        if self.range_slider.is_dragging() or self._external_drag:
            return  # the displayed time follows the handle being dragged
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(ms)
        self.position_label.setText(format_time(ms / 1000.0))
        self.displayTimeChanged.emit(int(ms))

    # ------------------------------------------------------------------ segments
    def _refresh_segment_items(self, select: int | None = None) -> None:
        self.segment_list.set_segments(self._segments, self.language, select)

    def editing_row(self) -> int:
        """Row of the card being edited, or -1 in draft mode (no card selected)."""
        row = self.segment_list.currentRow()
        return row if 0 <= row < len(self._segments) else -1

    def _update_edit_note(self) -> None:
        row = self.editing_row()
        self.edit_note.setText(self.t("editing_segment", n=row + 1) if row >= 0 else "")

    def _load_range(self, start: float, end: float, preview: bool = False) -> None:
        """Put a range into the slider and the time fields without editing any card."""
        self._syncing = True
        try:
            self.range_slider.setValues(start, end)
            self.start_edit.setText(format_time(start))
            self.end_edit.setText(format_time(end))
        finally:
            self._syncing = False
        if preview:
            self.preview_at(start, immediate=True)

    def _select_row(self, row: int, preview: bool = False) -> None:
        """Load segment ``row`` into the slider and time fields."""
        if 0 <= row < len(self._segments):
            self._load_range(*self._segments[row], preview=preview)

    def _on_row_changed(self, row: int) -> None:
        """A card was selected (editing mode) or the selection was cleared (draft mode)."""
        self._update_edit_note()
        if row >= 0:
            self._select_row(row, preview=True)

    def _on_range_changed(self, low: float, high: float) -> None:
        if self._syncing:
            return
        self.start_edit.setText(format_time(low))
        self.end_edit.setText(format_time(high))
        row = self.editing_row()
        if row >= 0:                       # editing mode: the slider edits that card ...
            self._segments[row] = (low, high)
            self.segment_list.update_segment(row, self._segments[row])
        # ... draft mode: it only moves the draft (no card changes)

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
        """Create a NEW card from the current slider range (overlaps and repeats are allowed).

        No card is selected afterwards, so moving the slider never changes an existing card.
        """
        if not self.has_video() or self._busy:
            return
        low, high = self.range_slider.low(), self.range_slider.high()
        if high <= low:
            self._show_status("empty_segment")
            return
        self._segments.append((low, high))
        number = len(self._segments)
        self._refresh_segment_items(select=-1)
        self._update_edit_note()
        self.segment_list.ensureWidgetVisible(self.segment_list.card(number - 1), 4, 4)
        self._update_enabled()
        self._show_status("segment_created", n=number)
        self.segmentCreated.emit(number)

    def remove_segment_at(self, row: int) -> None:
        """Remove card ``row`` (its cross). Deleting the edited card ends editing mode."""
        if not 0 <= row < len(self._segments) or self._busy:
            return
        current = self.editing_row()
        del self._segments[row]
        if current < 0 or row == current:
            new_row = -1
        else:
            new_row = current - 1 if row < current else current
        self._refresh_segment_items(select=new_row)
        self._update_edit_note()
        self._update_enabled()

    def move_segment(self, src: int, dst: int) -> None:
        """Move card ``src`` to position ``dst``; the order defines the saving order."""
        n = len(self._segments)
        if self._busy or not (0 <= src < n and 0 <= dst < n) or src == dst:
            return
        focused = self.segment_list.isAncestorOf(QApplication.focusWidget())
        self._segments.insert(dst, self._segments.pop(src))
        self._refresh_segment_items(select=dst)
        self._select_row(dst)
        self._update_edit_note()
        if focused:
            self.segment_list.card(dst).setFocus()
        self.segment_list.ensureWidgetVisible(self.segment_list.card(dst), 4, 4)

    def move_selected(self, delta: int) -> None:
        row = self.editing_row()
        if row >= 0:
            self.move_segment(row, row + delta)

    def _confirm_clear(self) -> bool:
        """Ask before throwing several segments away (tests replace this method)."""
        answer = QMessageBox.question(
            self, self.t("confirm_clear_title"),
            self.t("confirm_clear_text", count=len(self._segments)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def clear_segments(self) -> None:
        """Remove all cards (asks if there are several); the draft goes back to the whole file."""
        if self._busy or not self.has_video():
            return
        if len(self._segments) > 1 and not self._confirm_clear():
            return
        self._segments = []
        self._refresh_segment_items(select=-1)
        self._load_range(0.0, self._duration, preview=True)
        self._update_edit_note()
        self._update_enabled()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Esc leaves editing mode (back to the draft); the card keeps its range.
        if event.key() == Qt.Key_Escape and self.editing_row() >= 0:
            self.segment_list.setCurrentRow(-1)
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ full screen
    @property
    def _fs(self):
        """The full-screen window if it has been created, else None."""
        return self._fullscreen.window if self._fullscreen is not None else None

    def fullscreen_window(self):
        return self._fullscreen.ensure_window() if self._fullscreen is not None else None

    def is_fullscreen(self) -> bool:
        return self._fullscreen is not None and self._fullscreen.active

    def enter_fullscreen(self) -> None:
        if self._fullscreen is not None:
            self._fullscreen.enter()

    def exit_fullscreen(self) -> None:
        if self._fullscreen is not None:
            self._fullscreen.exit()

    def toggle_fullscreen(self) -> None:
        if self.is_fullscreen():
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        # Alt+Left / Alt+Right move the selected card. The scroll area would otherwise swallow
        # the arrow keys (as do buttons and sliders), so the shortcut is caught on them.
        if (event.type() == QEvent.KeyPress and event.modifiers() & Qt.AltModifier
                and event.key() in (Qt.Key_Left, Qt.Key_Right)):
            if self.has_video() and not self._busy:
                self.move_selected(-1 if event.key() == Qt.Key_Left else 1)
            return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ saving
    def _ask_save_dir(self, default: Path) -> str:
        return QFileDialog.getExistingDirectory(self, self.t("save_dialog_title"), str(default))

    def save(self) -> None:
        if self._busy or not self.has_video() or not self._segments:
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
        if self._fullscreen is not None:
            self._fullscreen.shutdown()      # never leave a full-screen window behind
        self.player.stop()
        if self._thread is not None and self._thread.isRunning():
            self._thread.wait()
        super().closeEvent(event)
