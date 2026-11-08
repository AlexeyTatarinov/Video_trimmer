"""Main window: preview, range selection, segment list, save."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QSlider, QVBoxLayout, QWidget,
)

from video_trimmer import core, i18n
from video_trimmer.ui.preview import PreviewPlayer
from video_trimmer.ui.range_slider import RangeSlider
from video_trimmer.ui.timefmt import format_time, parse_time
from video_trimmer.ui.worker import Worker, start_worker


class MainWindow(QMainWindow):
    # Relay used to run worker callbacks on the GUI thread (queued across threads).
    _gui_call = Signal(object)

    def __init__(self, language: str = i18n.DEFAULT_LANGUAGE) -> None:
        super().__init__()
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
        self.resize(900, 760)
        self._build_ui()
        self._connect_player()
        self.retranslate()
        self._update_enabled()

    # ------------------------------------------------------------------ build
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)

        self.player = PreviewPlayer(self)
        self.video_widget = self.player.video_widget
        self.video_widget.setMinimumHeight(280)
        lay.addWidget(self.video_widget, 1)

        row = QHBoxLayout()
        self.open_button = QPushButton()
        self.open_button.clicked.connect(self._choose_file)
        self.play_button = QPushButton()
        self.play_button.clicked.connect(self.toggle_play)
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self._seek)
        self.position_label = QLabel(format_time(0))
        row.addWidget(self.open_button)
        row.addWidget(self.play_button)
        row.addWidget(self.position_slider, 1)
        row.addWidget(self.position_label)
        lay.addLayout(row)

        self.range_box = QGroupBox()
        rl = QVBoxLayout(self.range_box)
        self.range_slider = RangeSlider()
        self.range_slider.rangeChanged.connect(self._on_range_changed)
        rl.addWidget(self.range_slider)
        grid = QGridLayout()
        self.start_label, self.end_label = QLabel(), QLabel()
        self.start_edit, self.end_edit = QLineEdit(), QLineEdit()
        for edit in (self.start_edit, self.end_edit):
            edit.setMaximumWidth(120)
            edit.setAlignment(Qt.AlignCenter)
        self.start_edit.editingFinished.connect(lambda: self._edit_finished(True))
        self.end_edit.editingFinished.connect(lambda: self._edit_finished(False))
        self.set_start_button, self.set_end_button = QPushButton(), QPushButton()
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

        self.segments_box = QGroupBox()
        sl = QHBoxLayout(self.segments_box)
        self.segment_list = QListWidget()
        self.segment_list.setMaximumHeight(110)
        self.segment_list.currentRowChanged.connect(self._on_row_changed)
        side = QVBoxLayout()
        self.add_button, self.remove_button = QPushButton(), QPushButton()
        self.add_button.clicked.connect(self.add_segment)
        self.remove_button.clicked.connect(self.remove_segment)
        side.addWidget(self.add_button)
        side.addWidget(self.remove_button)
        side.addStretch(1)
        sl.addWidget(self.segment_list, 1)
        sl.addLayout(side)
        lay.addWidget(self.segments_box)

        bottom = QHBoxLayout()
        self.mode_label = QLabel()
        self.fast_radio, self.precise_radio = QRadioButton(), QRadioButton()
        self.fast_radio.setChecked(True)
        self.language_label = QLabel()
        self.language_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
        self.language_combo.currentIndexChanged.connect(
            lambda _i: self.set_language(self.language_combo.currentData()))
        self.save_button = QPushButton()
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        for w in (self.mode_label, self.fast_radio, self.precise_radio):
            bottom.addWidget(w)
        bottom.addStretch(1)
        bottom.addWidget(self.language_label)
        bottom.addWidget(self.language_combo)
        bottom.addWidget(self.save_button)
        lay.addLayout(bottom)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        lay.addWidget(self.progress_bar)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        lay.addWidget(self.status_label)

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
        self.open_button.setText(self.t("open"))
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
        self.open_button.setEnabled(not self._busy)

    def _update_play_text(self) -> None:
        self.play_button.setText(self.t("pause" if self.player.is_playing() else "play"))

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
        self._refresh_segment_items()
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

    def _on_player_position(self, ms: int) -> None:
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(ms)
        self.position_label.setText(format_time(ms / 1000.0))

    # ------------------------------------------------------------------ segments
    def _segment_text(self, i: int) -> str:
        s, e = self._segments[i]
        return f"{self.t('segment')} {i + 1}: {format_time(s)} - {format_time(e)}"

    def _refresh_segment_items(self) -> None:
        row = self.segment_list.currentRow()
        self.segment_list.blockSignals(True)
        self.segment_list.clear()
        for i in range(len(self._segments)):
            self.segment_list.addItem(self._segment_text(i))
        if 0 <= row < len(self._segments):
            self.segment_list.setCurrentRow(row)
        self.segment_list.blockSignals(False)

    def _select_row(self, row: int) -> None:
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

    def _on_row_changed(self, row: int) -> None:
        self._select_row(row)

    def _on_range_changed(self, low: float, high: float) -> None:
        row = self.segment_list.currentRow()
        if self._syncing or not 0 <= row < len(self._segments):
            return
        self._segments[row] = (low, high)
        self.start_edit.setText(format_time(low))
        self.end_edit.setText(format_time(high))
        item = self.segment_list.item(row)
        if item:
            item.setText(self._segment_text(row))

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
        """Add a segment that fills the largest free gap between existing ones."""
        gaps, cursor = [], 0.0
        for s, e in sorted(self._segments):
            gaps.append((s - cursor, cursor, s))
            cursor = max(cursor, e)
        gaps.append((self._duration - cursor, cursor, self._duration))
        size, start, end = max(gaps)
        if size < 0.1:
            self._error(self.t("no_free_space"))
            return
        self._segments.append((start, end))
        self._refresh_segment_items()
        self.segment_list.setCurrentRow(len(self._segments) - 1)
        self._select_row(len(self._segments) - 1)
        self._update_enabled()

    def remove_segment(self) -> None:
        row = self.segment_list.currentRow()
        if len(self._segments) <= 1 or not 0 <= row < len(self._segments):
            return
        del self._segments[row]
        self._refresh_segment_items()
        new_row = min(row, len(self._segments) - 1)
        self.segment_list.setCurrentRow(new_row)
        self._select_row(new_row)
        self._update_enabled()

    # ------------------------------------------------------------------ saving
    def _ask_save_path(self, default: Path) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self, self.t("save_dialog_title"), str(default), "", options=QFileDialog.Option.DontConfirmOverwrite)
        return path

    def save(self) -> None:
        if self._busy or not self.has_video():
            return
        src, mode = self._src, self.mode()
        try:
            ranges = core.validate_ranges(list(self._segments), self._duration)
            default = core.default_output_path(src)
        except core.TrimError as exc:
            self._error(str(exc))
            return
        dst = self._ask_save_path(default)
        if not dst:
            return
        self.progress_bar.setValue(0)
        self._show_status("saving")
        self._run(
            lambda progress: core.trim(src, ranges, dst, mode, progress),
            on_result=lambda out: self._on_saved(out),
            on_error=self._error,
            on_progress=lambda v: self.progress_bar.setValue(int(round(min(max(v, 0.0), 1.0) * 100))),
        )

    def _on_saved(self, out) -> None:
        self.progress_bar.setValue(100)
        self._show_status("saved", path=str(out))
        self._notify("info", self.t("saved", path=str(out)))

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
