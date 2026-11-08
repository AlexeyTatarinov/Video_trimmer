"""UI tests. Run with QT_QPA_PLATFORM=offscreen. The core is replaced by a fake."""
from __future__ import annotations

import os
import re
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from video_trimmer import core, i18n
from video_trimmer.ui import preview, theme
from video_trimmer.ui.preview import PreviewPlayer
from video_trimmer.ui.widgets import GlassButton, GlassSlider
from video_trimmer.ui.timefmt import format_time, parse_time
from video_trimmer.ui.range_slider import RangeSlider
from video_trimmer.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never touch the user's real QSettings: every window gets a temporary ini file."""
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(theme, "make_settings", lambda: QSettings(path, QSettings.IniFormat))
    theme.set_current("light")
    yield path
    theme.set_current("light")


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
    assert "x_dir" in i18n.tr("en", "saved", count=2, folder="x_dir")


def test_range_slider_handle_moved_reports_which_handle(app):
    s = RangeSlider()
    s.setMaximum(100.0)
    moved = []
    s.handleMoved.connect(lambda which, v: moved.append((which, v)))
    s.setLow(10)
    s.setHigh(70)
    s.setLow(10)  # unchanged: silent
    assert moved == [("start", 10), ("end", 70)]


def test_range_slider_drag_signals_and_handle_names(app):
    s = RangeSlider()
    s.resize(400, 30)
    s.setMaximum(100.0)
    s.show()
    events = []
    s.dragStarted.connect(lambda w: events.append(("started", w)))
    s.dragFinished.connect(lambda w: events.append(("finished", w)))
    s.handleMoved.connect(lambda w, v: events.append(("moved", w)))
    y = s.height() // 2
    x0, x25 = int(s.value_to_x(0)), int(s.value_to_x(25))
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, QPoint(x0, y))
    assert s.is_dragging()
    QTest.mouseMove(s, QPoint(x25, y))
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, QPoint(x25, y))
    assert not s.is_dragging()
    assert events[0] == ("started", "start")
    assert ("moved", "start") in events
    assert events[-1] == ("finished", "start")
    events.clear()
    x100, x60 = int(s.value_to_x(100)), int(s.value_to_x(60))
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, QPoint(x100, y))
    QTest.mouseMove(s, QPoint(x60, y))
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, QPoint(x60, y))
    assert events[0] == ("started", "end")
    assert events[-1] == ("finished", "end")
    assert s.high() == pytest.approx(60, abs=0.5)


# ---------------------------------------------------------------- themes

def test_two_complete_themes(app):
    assert set(theme.THEMES) == {"light", "dark"}
    assert theme.DEFAULT_THEME == "light"
    fields = theme.Theme.__dataclass_fields__
    for th in theme.THEMES.values():
        for name in fields:
            assert getattr(th, name) is not None
        assert "QPushButton" in theme.stylesheet(th) or "QMessageBox" in theme.stylesheet(th)
    assert theme.stylesheet(theme.LIGHT) != theme.stylesheet(theme.DARK)
    # dark is a dark palette, light is a light one
    assert theme.DARK.bg_stops[1].lightness() < 100 < theme.LIGHT.bg_stops[1].lightness()
    # text must contrast with the background in both themes
    for th in theme.THEMES.values():
        assert abs(th.text.lightness() - th.bg_stops[1].lightness()) > 90


def test_theme_css_color_format(app):
    assert theme.css(theme.C(1, 2, 3, 4)) == "rgba(1,2,3,4)"
    assert theme.with_alpha(theme.C(1, 2, 3, 200), 0.5).alpha() == 100


def test_theme_settings_roundtrip(tmp_path):
    st = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    assert theme.load_theme_name(st) == "light"
    theme.save_theme_name(st, "dark")
    assert theme.load_theme_name(QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)) == "dark"
    st.setValue("theme", "bogus")
    assert theme.load_theme_name(st) == "light"


def test_glass_widgets_paint_in_all_states_and_themes(app):
    for name in ("light", "dark"):
        theme.set_current(name)
        pill = GlassButton("Pill")
        pill.resize(140, 40)
        round_ = GlassButton(icon_kind="speaker", diameter=44)
        round_.setCheckable(True)
        slider = GlassSlider()
        slider.resize(200, 30)
        slider.setRange(0, 100)
        slider.setValue(40)
        rs = RangeSlider()
        rs.resize(300, 40)
        rs.setMaximum(10)
        rs.setValues(2, 6)
        images = []
        for btn in (pill, round_):
            for state in ("normal", "disabled", "checked", "down"):
                btn.setEnabled(state != "disabled")
                if btn.isCheckable():
                    btn.setChecked(state == "checked")
                btn.setDown(state == "down")
                images.append(btn.grab().toImage())
        for w in (slider, rs):
            images.append(w.grab().toImage())
            w.setEnabled(False)
            images.append(w.grab().toImage())
        assert all(not im.isNull() for im in images)
    # the states of a button really look different
    theme.set_current("light")
    b = GlassButton("State")
    b.resize(140, 40)
    normal = b.grab().toImage()
    b.setEnabled(False)
    disabled = b.grab().toImage()
    b.setEnabled(True)
    b.setDown(True)
    pressed = b.grab().toImage()
    assert normal != disabled and normal != pressed and disabled != pressed


def test_slider_handle_follows_theme_colors(app):
    s = RangeSlider()
    s.resize(300, 40)
    s.setMaximum(10)
    s.setValues(2, 6)
    theme.set_current("light")
    light = s.grab().toImage()
    theme.set_current("dark")
    dark = s.grab().toImage()
    assert light != dark


# ---------------------------------------------------------------- preview player (throttling, audio state)

class FakeQPlayer:
    def __init__(self, state=None):
        from PySide6.QtMultimedia import QMediaPlayer
        self.Q = QMediaPlayer
        self.state = state if state is not None else QMediaPlayer.PausedState
        self.positions = []
        self.pauses = 0

    def playbackState(self):
        return self.state

    def pause(self):
        self.pauses += 1
        self.state = self.Q.PausedState

    def setPosition(self, ms):
        self.positions.append(ms)

    def position(self):
        return self.positions[-1] if self.positions else 0


class FakeAudioOutput:
    def __init__(self):
        self.volume = None
        self.muted = None

    def setVolume(self, v):
        self.volume = v

    def setMuted(self, m):
        self.muted = m


needs_mm = pytest.mark.skipif(not preview.MULTIMEDIA_AVAILABLE, reason="QtMultimedia not installed")


@needs_mm
def test_show_frame_is_throttled_and_keeps_last_target(app):
    pp = PreviewPlayer()
    fake = pp._player = FakeQPlayer()
    t0 = time.time()
    n = 0
    while time.time() - t0 < 0.3:
        pp.show_frame_at(n * 100)
        n += 1
        QApplication.processEvents()
        time.sleep(0.005)
    assert wait_for(lambda: not pp._seek_timer.isActive(), 1.0)
    assert fake.positions[0] == 0                      # first request goes through at once
    assert fake.positions[-1] == (n - 1) * 100         # the last target is never lost
    assert len(fake.positions) < n / 2                 # many requests were coalesced
    assert len(fake.positions) <= 0.3 / 0.030 + 3      # at most ~one real seek per 30 ms


@needs_mm
def test_show_frame_immediate_bypasses_throttle(app):
    pp = PreviewPlayer()
    fake = pp._player = FakeQPlayer()
    pp.show_frame_at(1000)
    pp.show_frame_at(2000)           # pending
    pp.show_frame_at(3000, immediate=True)
    assert fake.positions == [1000, 3000]
    assert wait_for(lambda: not pp._seek_timer.isActive(), 1.0)
    assert fake.positions == [1000, 3000]  # the pending 2000 was dropped


@needs_mm
def test_seek_pauses_playing_and_stopped_player(app):
    from PySide6.QtMultimedia import QMediaPlayer
    pp = PreviewPlayer()
    fake = pp._player = FakeQPlayer(QMediaPlayer.PlayingState)
    pp.show_frame_at(500, immediate=True)
    assert fake.pauses == 1 and fake.state == QMediaPlayer.PausedState
    fake.state = QMediaPlayer.StoppedState
    pp.show_frame_at(700, immediate=True)  # a stopped player shows no frame: it is paused first
    assert fake.pauses == 2 and fake.positions == [500, 700]


@needs_mm
def test_plain_position_seek_keeps_playing(app):
    from PySide6.QtMultimedia import QMediaPlayer
    pp = PreviewPlayer()
    fake = pp._player = FakeQPlayer(QMediaPlayer.PlayingState)
    pp.set_position_ms(1234)
    assert fake.positions == [1234] and fake.pauses == 0 and fake.state == QMediaPlayer.PlayingState


def test_audio_disabled_in_offscreen_but_state_is_kept(app):
    pp = PreviewPlayer()
    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    assert not pp.has_audio_output()
    pp.set_volume(0.25)
    pp.set_muted(True)
    assert pp.volume() == 0.25 and pp.is_muted()
    pp.set_volume(7)
    assert pp.volume() == 1.0
    pp.set_volume(-1)
    assert pp.volume() == 0.0
    pp.set_muted(False)
    assert not pp.is_muted()


def test_volume_and_mute_are_passed_to_audio_output(app):
    pp = PreviewPlayer()
    out = pp._audio = FakeAudioOutput()
    assert pp.has_audio_output()
    pp.set_volume(0.4)
    assert out.volume == 0.4
    pp.set_muted(True)
    assert out.muted is True
    pp.set_muted(False)
    assert out.muted is False


def test_audio_allowed_rules(monkeypatch):
    monkeypatch.delenv("VIDEO_TRIMMER_NO_AUDIO", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    assert not preview._audio_allowed()
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    assert preview._audio_allowed()
    monkeypatch.setenv("VIDEO_TRIMMER_NO_AUDIO", "1")
    assert not preview._audio_allowed()


# ---------------------------------------------------------------- main window

class FakeCore:
    """Fake of the v0.2 core contract (validate_segments / trim_each)."""

    def __init__(self, duration=60.0):
        self.duration = duration
        self.calls = []
        self.error = None
        self.progress_values = [0.0, 0.5, 1.0]

    def install(self, monkeypatch):
        monkeypatch.setattr(core, "probe", self.probe)
        monkeypatch.setattr(core, "validate_segments", self.validate)
        monkeypatch.setattr(core, "trim_each", self.trim_each)

        def forbidden(*_a, **_k):
            raise AssertionError("the UI must not use validate_ranges / trim any more")

        monkeypatch.setattr(core, "validate_ranges", forbidden)
        monkeypatch.setattr(core, "trim", forbidden)

    def probe(self, path):
        return core.VideoInfo(self.duration, 640, 360, True, True)

    def validate(self, ranges, duration):
        if not ranges:
            raise core.TrimError("no ranges")
        for s, e in ranges:
            if not (0 <= s < e <= duration + 0.001):
                raise core.TrimError("bad range")
        return list(ranges)  # order preserved, overlaps allowed

    def trim_each(self, src, ranges, out_dir, mode="fast", progress=None):
        if self.error:
            raise core.TrimError(self.error)
        self.calls.append((str(src), list(ranges), str(out_dir), mode))
        for v in self.progress_values:
            if progress:
                progress(v)
        return [core.Path(out_dir) / f"clip_part{i + 1}.mp4" for i in range(len(ranges))]


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
    w.out_dir = str(tmp_path / "out")
    w.asked = []
    monkeypatch.setattr(w, "_ask_save_dir", lambda default: w.asked.append(str(default)) or w.out_dir)
    src = tmp_path / "in.mp4"
    src.write_bytes(b"not a real video")
    w.src_path = str(src)
    w.open_file(str(src))
    assert wait_for(lambda: w.has_video() and not w.is_busy())
    yield w
    wait_for(lambda: not w.is_busy())
    w.close()


@pytest.fixture
def preview_calls(win, monkeypatch):
    """Record every request the window makes to the preview (the real seek is covered above)."""
    calls = []
    monkeypatch.setattr(win.player, "show_frame_at",
                        lambda ms, immediate=False: calls.append((ms, immediate)))
    return calls


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


def test_add_segment_copies_selected_and_is_always_possible(win):
    win.range_slider.setValues(5, 20)
    win.add_segment()
    assert win.segments() == [(5.0, 20.0), (5.0, 20.0)]   # duplicate is fine
    assert win.segment_list.currentRow() == 1
    win.range_slider.setValues(10, 30)                   # overlaps the first one: allowed
    assert win.segments() == [(5.0, 20.0), (10.0, 30.0)]
    win.segment_list.setCurrentRow(0)
    win.add_segment()                                    # copies the selected (first) one
    assert win.segments()[-1] == (5.0, 20.0)
    assert len(win.segments()) == 3
    assert not any(kind == "error" for kind, _ in win.notes)
    # adding works even when the segment covers the whole file (no free space needed)
    win.range_slider.setValues(0, 60)
    win.add_segment()
    assert len(win.segments()) == 4
    assert win.add_button.isEnabled()


def test_remove_any_segment_except_last(win):
    win.range_slider.setValues(0, 10)
    win.add_segment()
    win.range_slider.setValues(10, 20)
    win.add_segment()
    win.range_slider.setValues(20, 30)
    assert win.segments() == [(0, 10), (10, 20), (20, 30)]
    win.segment_list.setCurrentRow(0)
    assert win.remove_button.isEnabled()
    win.remove_segment()                                  # the first can be removed too
    assert win.segments() == [(10, 20), (20, 30)]
    win.segment_list.setCurrentRow(1)
    win.remove_segment()
    assert win.segments() == [(10, 20)]
    assert not win.remove_button.isEnabled()
    win.remove_segment()                                  # the last remaining one stays
    assert win.segments() == [(10, 20)]


def test_segment_list_shows_each_segment(win):
    win.range_slider.setValues(1, 2)
    win.add_segment()
    assert win.segment_list.count() == 2
    card = win.segment_list.card(1)
    assert "00:01.000" in card.range_label.text() and "00:02.000" in card.range_label.text()
    assert card.index_label.text() == "#2"
    assert "00:01.000" in card.duration_label.text()     # duration of the card
    win.range_slider.setValues(1, 5)                      # editing updates the card text
    assert "00:05.000" in win.segment_list.card(1).range_label.text()
    assert i18n.tr("en", "segments") == "Segments (each is saved as a separate file)"


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


# ---- preview follows the handle being edited

def test_preview_follows_start_and_end_handle_drag(win, preview_calls):
    s = win.range_slider
    s.resize(600, 40)
    y = s.height() // 2
    # drag the START handle: the preview shows the start time
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(0)), y))
    QTest.mouseMove(s, QPoint(int(s.value_to_x(15)), y))
    QTest.mouseMove(s, QPoint(int(s.value_to_x(20)), y))
    assert preview_calls and preview_calls[-1][0] == pytest.approx(s.low() * 1000, abs=1)
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(20)), y))
    ms, immediate = preview_calls[-1]
    assert ms == pytest.approx(20000, abs=600) and immediate       # final frame, not throttled
    assert ms == round(s.low() * 1000)
    start_calls = len(preview_calls)
    # drag the END handle: the same preview jumps to the end time
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(60)), y))
    QTest.mouseMove(s, QPoint(int(s.value_to_x(45)), y))
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(45)), y))
    assert len(preview_calls) > start_calls
    ms, immediate = preview_calls[-1]
    assert ms == round(s.high() * 1000) and ms == pytest.approx(45000, abs=600) and immediate
    assert all(c[0] >= 0 for c in preview_calls)


def test_main_position_slider_and_label_follow_displayed_time(win, preview_calls):
    win.range_slider.setLow(12.5)
    assert win.position_slider.value() == 12500
    assert win.position_label.text() == "00:12.500"
    win.range_slider.setHigh(40)
    assert win.position_slider.value() == 40000
    assert win.position_label.text() == "00:40.000"


def test_stale_player_positions_are_ignored_while_dragging(win, preview_calls):
    s = win.range_slider
    s.resize(600, 40)
    y = s.height() // 2
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(0)), y))
    QTest.mouseMove(s, QPoint(int(s.value_to_x(30)), y))
    shown = win.position_slider.value()
    win._on_player_position(1000)         # a late position report from the player
    assert win.position_slider.value() == shown
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, QPoint(int(s.value_to_x(30)), y))


def test_preview_when_editing_time_fields(win, preview_calls):
    win.end_edit.setText("0:30")
    win.end_edit.editingFinished.emit()
    assert preview_calls[-1][0] == 30000
    win.start_edit.setText("0:05.5")
    win.start_edit.editingFinished.emit()
    assert preview_calls[-1][0] == 5500


def test_preview_when_taking_current_position(win, preview_calls, monkeypatch):
    monkeypatch.setattr(win, "current_position", lambda: 12.0)
    win.set_start_from_position()
    assert preview_calls[-1][0] == 12000
    monkeypatch.setattr(win, "current_position", lambda: 40.0)
    win.set_end_from_position()
    assert preview_calls[-1][0] == 40000


def test_selecting_a_segment_previews_its_start(win, preview_calls):
    win.range_slider.setValues(7, 9)
    win.add_segment()
    win.range_slider.setValues(20, 25)
    preview_calls.clear()
    win.segment_list.setCurrentRow(0)
    assert preview_calls[-1][0] == 7000


def test_loading_a_file_does_not_crash_preview_and_player_starts_paused(win):
    assert not win.player.is_playing()


# ---- audio controls

def test_mute_button_toggles_and_keeps_state(win):
    assert win.mute_button.isCheckable() and not win.mute_button.isChecked()
    assert win.mute_button.iconKind() == "speaker"
    tip_normal = win.mute_button.toolTip()
    win.mute_button.click()
    assert win.mute_button.isChecked() and win.player.is_muted()
    assert win.mute_button.toolTip() != tip_normal
    win.mute_button.click()
    assert not win.mute_button.isChecked() and not win.player.is_muted()


def test_mute_and_volume_reach_audio_output(win):
    out = win.player._audio = FakeAudioOutput()
    win.volume_slider.setValue(30)
    assert out.volume == pytest.approx(0.3) and win.player.volume() == pytest.approx(0.3)
    win.mute_button.setChecked(True)
    assert out.muted is True
    win.mute_button.setChecked(False)
    assert out.muted is False


def test_volume_slider_default_and_range(win):
    assert (win.volume_slider.minimum(), win.volume_slider.maximum()) == (0, 100)
    assert win.volume_slider.value() == round(PreviewPlayer.DEFAULT_VOLUME * 100)
    assert win.volume_slider.isEnabled() and win.mute_button.isEnabled()


# ---- themes in the window

def test_default_theme_is_light_and_toggle_switches(win):
    assert win.theme_name == "light" and theme.current().name == "light"
    light_sheet = win.styleSheet()
    win.toggle_theme()
    assert win.theme_name == "dark" and theme.current().name == "dark"
    assert win.styleSheet() != light_sheet
    assert win.theme_button.iconKind() == "sun"
    win.toggle_theme()
    assert win.theme_name == "light" and win.theme_button.iconKind() == "moon"


def test_theme_choice_persists_between_runs(app, fake, isolated_settings):
    w = MainWindow()
    assert w.theme_name == "light"
    w.toggle_theme()
    w.close()
    w2 = MainWindow()
    assert w2.theme_name == "dark"
    assert theme.current().name == "dark"
    w2.close()
    # the temporary scope was used, not the real one
    assert theme.load_theme_name(QSettings(isolated_settings, QSettings.IniFormat)) == "dark"


def test_explicit_settings_object_is_used(app, fake, tmp_path):
    st = QSettings(str(tmp_path / "own.ini"), QSettings.IniFormat)
    theme.save_theme_name(st, "dark")
    w = MainWindow(settings=st)
    assert w.theme_name == "dark"
    w.set_theme("light")
    assert theme.load_theme_name(st) == "light"
    w.close()


def test_window_renders_in_both_themes(win, tmp_path):
    images = {}
    for name in ("light", "dark"):
        win.set_theme(name)
        img = win.grab().toImage()
        assert not img.isNull() and img.width() > 400
        images[name] = img
    assert images["light"] != images["dark"]
    # the glass background is a gradient, not a flat colour
    img = images["light"]
    assert img.pixelColor(5, 5) != img.pixelColor(img.width() - 5, img.height() - 5)


# ---- saving (v0.2: folder + trim_each)

def test_save_passes_ranges_in_order_and_mode_and_reports_success(win, fake):
    win.range_slider.setValues(20, 30)
    win.add_segment()
    win.range_slider.setValues(5, 10)
    win.add_segment()
    win.range_slider.setValues(8, 12)        # overlaps the previous one
    win.precise_radio.setChecked(True)
    win.save()
    assert wait_for(lambda: not win.is_busy() and fake.calls)
    src, ranges, out_dir, mode = fake.calls[0]
    assert ranges == [(20.0, 30.0), (5.0, 10.0), (8.0, 12.0)]   # order preserved, overlaps kept
    assert mode == "precise"
    assert out_dir == win.out_dir and src == win.src_path
    assert win.progress_bar.value() == 100
    kind, text = win.notes[-1]
    assert kind == "info" and "3" in text and win.out_dir in text


def test_save_asks_for_folder_of_source_by_default(win, fake):
    win.save()
    assert wait_for(lambda: fake.calls)
    assert win.asked and win.asked[0] == str(core.Path(win.src_path).parent)
    assert fake.calls[0][3] == "fast"


def test_save_uses_folder_dialog_not_file_dialog(win, fake, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    seen = {}

    def fake_dir(parent, title, start, *a, **k):
        seen["args"] = (title, start)
        return win.out_dir

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(fake_dir))
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("file dialog"))))
    assert MainWindow._ask_save_dir(win, core.Path(win.src_path).parent) == win.out_dir  # real method
    assert seen["args"][1] == str(core.Path(win.src_path).parent)
    assert seen["args"][0] == i18n.tr("en", "save_dialog_title")


def test_save_cancelled_dialog_does_nothing(win, fake, monkeypatch):
    monkeypatch.setattr(win, "_ask_save_dir", lambda default: "")
    win.save()
    assert not win.is_busy()
    assert fake.calls == []


def test_trim_error_text_is_shown(win, fake):
    fake.error = "ffmpeg exploded politely"
    win.save()
    assert wait_for(lambda: win.notes and not win.is_busy())
    kind, text = win.notes[-1]
    assert kind == "error"
    assert "ffmpeg exploded politely" in text


def test_invalid_segment_error_shown_without_starting_trim(win, fake):
    win.range_slider.setValues(10, 10)  # empty segment is rejected by validate_segments
    win.save()
    assert win.notes[-1][0] == "error"
    assert not win.is_busy()
    assert fake.calls == [] and win.asked == []


def test_ui_uses_only_v02_core_functions(win, fake):
    # FakeCore makes validate_ranges / trim raise: a full save must still succeed
    win.save()
    assert wait_for(lambda: fake.calls and not win.is_busy())
    assert win.notes[-1][0] == "info"


def test_language_switch_changes_strings(win):
    en_save = win.save_button.text()
    win.set_language("ru")
    assert win.language == "ru"
    assert win.save_button.text() == i18n.tr("ru", "save") != en_save
    assert win.mute_button.toolTip() == i18n.tr("ru", "mute")
    win.set_language("uk")
    assert win.save_button.text() == i18n.tr("uk", "save")
    assert win.windowTitle() == i18n.tr("uk", "window_title")
    assert win.theme_button.toolTip() == i18n.tr("uk", "theme_to_dark")
    win.set_language("en")
    assert win.save_button.text() == en_save


def test_language_combo_switches_language(win):
    idx = win.language_combo.findData("uk")
    win.language_combo.setCurrentIndex(idx)
    assert win.language == "uk"


def test_saved_message_has_count_and_folder_in_all_languages():
    for lang in ("en", "ru", "uk"):
        text = i18n.tr(lang, "saved", count=4, folder="/x/y")
        assert "4" in text and "/x/y" in text


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
