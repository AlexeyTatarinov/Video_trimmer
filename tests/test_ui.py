"""UI tests. Run with QT_QPA_PLATFORM=offscreen. The core is replaced by a fake."""
from __future__ import annotations

import os
import re
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from video_trimmer import core, i18n
from video_trimmer.ui.timefmt import format_time, parse_time
from video_trimmer.ui.range_slider import RangeSlider
from video_trimmer.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


# ---------------------------------------------------------------- time helpers

def test_format_time_basic():
    assert format_time(0) == "00:00.000"
    assert format_time(12.5) == "00:12.500"
    assert format_time(75.25) == "01:15.250"
    assert format_time(3725.5) == "1:02:05.500"


def test_format_time_clamps_negative_and_rounds():
    assert format_time(-3) == "00:00.000"
    assert format_time(59.9996) == "01:00.000"


@pytest.mark.parametrize("text,expected", [
    ("12.5", 12.5),
    ("12", 12.0),
    ("1:30", 90.0),
    ("01:15.250", 75.25),
    ("1:02:05.5", 3725.5),
    ("  00:05  ", 5.0),
    ("0,5", 0.5),
])
def test_parse_time_ok(text, expected):
    assert parse_time(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "1:2:3:4", "-5", "1:-5", "1::5", "1:75", ":"])
def test_parse_time_invalid(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_time_roundtrip():
    for v in (0.0, 0.001, 1.5, 59.999, 61.0, 3600.0, 7322.123):
        assert parse_time(format_time(v)) == pytest.approx(v, abs=0.0006)


# ---------------------------------------------------------------- range slider

def test_range_slider_clamping(app):
    s = RangeSlider()
    s.setMaximum(100.0)
    assert (s.low(), s.high()) == (0.0, 100.0)
    s.setHigh(40)
    s.setLow(60)  # cannot pass the high handle
    assert s.low() == 40
    s.setHigh(10)  # cannot go below the low handle
    assert s.high() == 40
    s.setLow(-5)
    assert s.low() == 0
    s.setHigh(1000)
    assert s.high() == 100


def test_range_slider_set_values_and_signal(app):
    s = RangeSlider()
    s.setMaximum(50.0)
    got = []
    s.rangeChanged.connect(lambda lo, hi: got.append((lo, hi)))
    s.setValues(10, 20)
    assert got == [(10, 20)]
    s.setValues(10, 20)  # no change, no signal
    assert got == [(10, 20)]
    s.setValues(-3, 999)
    assert (s.low(), s.high()) == (0, 50)
    s.setValues(30, 20)  # inverted input is clamped, never inverted
    assert s.low() <= s.high()


def test_range_slider_shrinking_maximum_clamps(app):
    s = RangeSlider()
    s.setMaximum(100)
    s.setValues(50, 90)
    s.setMaximum(60)
    assert (s.low(), s.high()) == (50, 60)


def test_range_slider_pixel_mapping_roundtrip(app):
    s = RangeSlider()
    s.resize(400, 30)
    s.setMaximum(80.0)
    for v in (0.0, 20.0, 80.0):
        assert s.x_to_value(s.value_to_x(v)) == pytest.approx(v, abs=0.3)
    assert s.x_to_value(-100) == 0.0
    assert s.x_to_value(10000) == 80.0


def test_range_slider_mouse_drag_moves_nearest_handle(app):
    s = RangeSlider()
    s.resize(400, 30)
    s.setMaximum(100.0)
    s.show()
    y = s.height() // 2
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(0)), y))
    QTest.mouseMove(s, QPoint(int(s.value_to_x(25)), y))
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(25)), y))
    assert s.low() == pytest.approx(25, abs=0.5)
    assert s.high() == 100
    # drag the high handle past the low one: clamped
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(100)), y))
    QTest.mouseMove(s, QPoint(int(s.value_to_x(5)), y))
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(5)), y))
    assert s.high() == pytest.approx(s.low())


# ---------------------------------------------------------------- i18n

def test_i18n_identical_keys():
    assert set(i18n.STRINGS) == {"en", "ru", "uk"}
    en = set(i18n.STRINGS["en"])
    for lang in ("ru", "uk"):
        assert set(i18n.STRINGS[lang]) == en, lang


def test_i18n_values_nonempty_and_placeholders_match():
    for key, en_val in i18n.STRINGS["en"].items():
        en_ph = set(re.findall(r"\{(\w+)\}", en_val))
        for lang in ("ru", "uk"):
            val = i18n.STRINGS[lang][key]
            assert val.strip(), (lang, key)
            assert set(re.findall(r"\{(\w+)\}", val)) == en_ph, (lang, key)


def test_i18n_tr_and_fallback():
    assert i18n.DEFAULT_LANGUAGE == "en"
    assert i18n.tr("en", "save") != i18n.tr("ru", "save")
    assert i18n.tr("xx", "save") == i18n.tr("en", "save")
    assert "x.mp4" in i18n.tr("en", "saved", path="x.mp4")


# ---------------------------------------------------------------- main window

class FakeCore:
    def __init__(self, duration=60.0):
        self.duration = duration
        self.trim_calls = []
        self.trim_error = None
        self.progress_values = [0.0, 0.5, 1.0]

    def install(self, monkeypatch):
        monkeypatch.setattr(core, "probe", self.probe)
        monkeypatch.setattr(core, "trim", self.trim)
        monkeypatch.setattr(core, "default_output_path", lambda src: core.Path(str(src)).with_name("clip_trimmed.mp4"))
        monkeypatch.setattr(core, "validate_ranges", self.validate)

    def probe(self, path):
        return core.VideoInfo(self.duration, 640, 360, True, True)

    def validate(self, ranges, duration):
        if not ranges:
            raise core.TrimError("no ranges")
        out = sorted(ranges)
        prev_end = 0.0
        for s, e in out:
            if not (0 <= s < e <= duration + 0.001) or s < prev_end:
                raise core.TrimError("bad range")
            prev_end = e
        return out

    def trim(self, src, ranges, dst, mode="fast", progress=None):
        if self.trim_error:
            raise core.TrimError(self.trim_error)
        self.trim_calls.append((str(src), list(ranges), str(dst), mode))
        for v in self.progress_values:
            if progress:
                progress(v)
        return core.Path(dst)


@pytest.fixture
def fake(monkeypatch):
    f = FakeCore()
    f.install(monkeypatch)
    return f


@pytest.fixture
def win(app, fake, monkeypatch, tmp_path):
    notes = []
    monkeypatch.setattr(MainWindow, "_notify", lambda self, kind, text: notes.append((kind, text)))
    w = MainWindow()
    w.notes = notes
    w.dst = str(tmp_path / "out.mp4")
    monkeypatch.setattr(w, "_ask_save_path", lambda default: w.dst)
    src = tmp_path / "in.mp4"
    src.write_bytes(b"not a real video")
    w.open_file(str(src))
    assert wait_for(lambda: w.has_video() and not w.is_busy())
    yield w
    wait_for(lambda: not w.is_busy())
    w.close()


def test_window_default_language_is_english(win):
    assert win.language == "en"
    assert win.save_button.text() == i18n.tr("en", "save")


def test_default_single_segment_covers_whole_file(win):
    assert win.segments() == [(0.0, 60.0)]
    assert win.range_slider.high() == 60.0
    assert win.start_edit.text() == "00:00.000"
    assert win.end_edit.text() == "01:00.000"


def test_controls_disabled_without_video(app, fake):
    w = MainWindow()
    assert not w.save_button.isEnabled()
    assert not w.add_button.isEnabled()
    w.close()


def test_segment_add_and_remove(win):
    win.range_slider.setValues(0, 20)
    assert win.segments() == [(0.0, 20.0)]
    win.add_segment()  # takes the largest free gap
    assert win.segments() == [(0.0, 20.0), (20.0, 60.0)]
    assert win.segment_list.currentRow() == 1
    win.range_slider.setValues(30, 40)
    assert win.segments()[1] == (30.0, 40.0)
    win.remove_segment()
    assert win.segments() == [(0.0, 20.0)]
    win.remove_segment()  # last one cannot be removed
    assert len(win.segments()) == 1


def test_add_segment_without_free_space_reports(win):
    win.add_segment()
    assert len(win.segments()) == 1
    assert win.notes and win.notes[-1][0] == "error"


def test_time_fields_update_segment(win):
    win.end_edit.setText("0:30")
    win.end_edit.editingFinished.emit()
    assert win.segments() == [(0.0, 30.0)]
    win.start_edit.setText("garbage")
    win.start_edit.editingFinished.emit()
    assert win.segments() == [(0.0, 30.0)]
    assert win.start_edit.text() == "00:00.000"
    win.start_edit.setText("45")  # beyond end: clamped to end
    win.start_edit.editingFinished.emit()
    assert win.segments() == [(30.0, 30.0)]


def test_take_current_position(win, monkeypatch):
    monkeypatch.setattr(win, "current_position", lambda: 12.0)
    win.set_start_from_position()
    monkeypatch.setattr(win, "current_position", lambda: 40.0)
    win.set_end_from_position()
    assert win.segments() == [(12.0, 40.0)]


def test_save_passes_ranges_and_mode_and_reports_success(win, fake):
    win.range_slider.setValues(5, 10)
    win.add_segment()
    win.range_slider.setValues(20, 30)
    win.precise_radio.setChecked(True)
    progress = []
    win.progress_bar.valueChanged.connect(progress.append)
    win.save()
    assert wait_for(lambda: not win.is_busy() and fake.trim_calls)
    src, ranges, dst, mode = fake.trim_calls[0]
    assert ranges == [(5.0, 10.0), (20.0, 30.0)]
    assert mode == "precise"
    assert dst == win.dst
    assert win.progress_bar.value() == 100
    assert win.notes[-1][0] == "info"
    assert win.dst in win.notes[-1][1]


def test_save_default_mode_is_fast_and_uses_default_output_path(win, fake, monkeypatch):
    seen = []
    monkeypatch.setattr(win, "_ask_save_path", lambda default: seen.append(str(default)) or win.dst)
    win.save()
    assert wait_for(lambda: fake.trim_calls)
    assert fake.trim_calls[0][3] == "fast"
    assert seen and seen[0].endswith("clip_trimmed.mp4")


def test_save_cancelled_dialog_does_nothing(win, fake, monkeypatch):
    monkeypatch.setattr(win, "_ask_save_path", lambda default: "")
    win.save()
    assert not win.is_busy()
    assert fake.trim_calls == []


def test_trim_error_text_is_shown(win, fake):
    fake.trim_error = "ffmpeg exploded politely"
    win.save()
    assert wait_for(lambda: win.notes and not win.is_busy())
    kind, text = win.notes[-1]
    assert kind == "error"
    assert "ffmpeg exploded politely" in text


def test_invalid_ranges_error_shown_without_starting_trim(win, fake):
    win.range_slider.setValues(10, 10)  # empty segment is rejected by validate_ranges
    win.save()
    assert win.notes[-1][0] == "error"
    assert not win.is_busy()
    assert fake.trim_calls == []


def test_language_switch_changes_strings(win):
    en_save = win.save_button.text()
    win.set_language("ru")
    assert win.language == "ru"
    assert win.save_button.text() == i18n.tr("ru", "save") != en_save
    win.set_language("uk")
    assert win.save_button.text() == i18n.tr("uk", "save")
    assert win.windowTitle() == i18n.tr("uk", "window_title")
    win.set_language("en")
    assert win.save_button.text() == en_save


def test_language_combo_switches_language(win):
    idx = win.language_combo.findData("uk")
    win.language_combo.setCurrentIndex(idx)
    assert win.language == "uk"


def test_probe_error_is_reported(app, fake, monkeypatch, tmp_path):
    notes = []
    monkeypatch.setattr(MainWindow, "_notify", lambda self, kind, text: notes.append((kind, text)))

    def bad_probe(path):
        raise core.TrimError("cannot read this file")

    monkeypatch.setattr(core, "probe", bad_probe)
    w = MainWindow()
    w.open_file(str(tmp_path / "x.mp4"))
    assert wait_for(lambda: notes and not w.is_busy())
    assert notes[-1][0] == "error" and "cannot read this file" in notes[-1][1]
    assert not w.has_video()
    w.close()
