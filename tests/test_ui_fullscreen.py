"""v0.2.3 part B: full-screen video mode (custom painted sink widget, header / footer panels).

Run with QT_QPA_PLATFORM=offscreen and VIDEO_TRIMMER_NO_AUDIO=1.  The offscreen screen is small
(800x600), so geometry is checked relative to the screen rectangle.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QAbstractSlider, QLineEdit

from video_trimmer import i18n
from video_trimmer.ui import fullscreen, preview
from video_trimmer.ui.fullscreen import FullscreenWindow, fit_rect
from video_trimmer.ui.main_window import MainWindow
from video_trimmer.ui.range_slider import RangeSlider
from video_trimmer.ui.segment_cards import SegmentCardList
from video_trimmer.ui.widgets import GlassButton, StatusProgressBar

# fixtures of the main UI tests (fake core; a window with a "loaded" 60 s video)
from test_ui import app, fake, isolated_settings, preview_calls, win as _win, wait_for  # noqa: F401

pytestmark = pytest.mark.skipif(not preview.MULTIMEDIA_AVAILABLE, reason="QtMultimedia not installed")

LANGS = ["en", "ru", "uk"]
THEMES = ["light", "dark"]


@pytest.fixture(autouse=True)
def quick_timings(monkeypatch):
    monkeypatch.setattr(FullscreenWindow, "HIDE_DELAY_MS", 120)
    monkeypatch.setattr(FullscreenWindow, "CURSOR_HIDE_MS", 120)
    monkeypatch.setattr(FullscreenWindow, "ANIM_MS", 10)
    monkeypatch.setattr(FullscreenWindow, "TOAST_MS", 150)


@pytest.fixture
def win(_win):
    _win.show()
    QApplication.processEvents()
    return _win


@pytest.fixture
def fs(win):
    win.enter_fullscreen()
    f = win.fullscreen_window()
    QApplication.processEvents()
    return f


def pump(ms=60):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.004)


def _send(widget, etype, pos, button=Qt.NoButton, buttons=Qt.NoButton):
    """Deliver a mouse event straight to ``widget`` (the offscreen platform may route
    QTest.mouse* calls to another top-level window that overlaps it)."""
    ev = QMouseEvent(etype, QPointF(pos), QPointF(widget.mapToGlobal(pos)), button, buttons,
                     Qt.NoModifier)
    QApplication.sendEvent(widget, ev)


def move_to(f, x, y):
    _send(f, QEvent.MouseMove, QPoint(x, y))


def press(w, pos):
    _send(w, QEvent.MouseButtonPress, pos, Qt.LeftButton, Qt.LeftButton)


def drag_move(w, pos):
    _send(w, QEvent.MouseMove, pos, Qt.NoButton, Qt.LeftButton)


def release(w, pos):
    _send(w, QEvent.MouseButtonRelease, pos, Qt.LeftButton, Qt.NoButton)


def click(w, pos=None):
    pos = pos if pos is not None else w.rect().center()
    press(w, pos)
    release(w, pos)


def dclick(w, pos=None):
    pos = pos if pos is not None else w.rect().center()
    press(w, pos)
    release(w, pos)
    _send(w, QEvent.MouseButtonDblClick, pos, Qt.LeftButton, Qt.LeftButton)
    release(w, pos)


def bottom_point(f):
    return f.width() // 2, f.height() - 6


def reveal_footer(f):
    move_to(f, *bottom_point(f))
    assert wait_for(lambda: f.footer.isVisible() and f.footer_visible())
    pump(40)


def reveal_header(f):
    move_to(f, f.width() // 2, 5)
    assert wait_for(lambda: f.header.isVisible() and f.header_visible())
    pump(40)


# ---------------------------------------------------------------- pure geometry helpers

def test_fit_rect_keeps_aspect_ratio_and_maximises():
    screen = QRect(0, 0, 800, 600)
    assert fit_rect(QSize(320, 240), screen) == screen                    # same aspect: everything
    wide = fit_rect(QSize(1920, 1080), screen)
    assert (wide.width(), wide.height()) == (800, 450) and wide.top() == 75 and wide.left() == 0
    tall = fit_rect(QSize(1080, 1920), screen)
    assert tall.height() == 600 and abs(tall.width() - 337) <= 1
    assert abs(tall.center().x() - 400) <= 1
    for src in (QSize(320, 240), QSize(1920, 1080), QSize(1080, 1920), QSize(3840, 2160)):
        r = fit_rect(src, screen)
        assert screen.contains(r)
        assert abs(r.width() / r.height() - src.width() / src.height()) < 0.01
        assert r.width() == screen.width() or r.height() == screen.height()    # as large as possible
    small = fit_rect(QSize(40, 30), screen)                                    # small video is enlarged
    assert small.width() == 800
    assert fit_rect(QSize(0, 0), screen).isEmpty()


def test_fit_rect_on_an_offset_screen():
    r = fit_rect(QSize(1920, 1080), QRect(1920, 0, 1920, 1200))
    assert r.left() == 1920 and r.width() == 1920 and r.height() == 1080 and r.top() == 60


# ---------------------------------------------------------------- enter / leave

def test_fullscreen_is_off_at_start_and_needs_a_video(app, fake):
    w = MainWindow()
    w.enter_fullscreen()
    assert not w.is_fullscreen()
    w.toggle_fullscreen()
    assert not w.is_fullscreen()
    w.close()


def test_double_click_on_the_video_enters_and_a_second_one_leaves(win):
    assert not win.is_fullscreen()
    dclick(win.video_widget)
    f = win.fullscreen_window()
    assert win.is_fullscreen() and f.isVisible()
    dclick(f, QPoint(f.width() // 2, f.height() // 2))
    assert not win.is_fullscreen() and not f.isVisible()
    assert win.isVisible()


def test_fullscreen_window_covers_the_screen_of_the_main_window(win, fs):
    screen = win.screen()
    assert fs.isVisible() and fs.isFullScreen()
    assert fs.geometry() == screen.geometry()
    assert fs.windowFlags() & Qt.FramelessWindowHint
    assert fs.screen() == screen


def test_video_gets_the_maximum_rectangle_of_the_screen(win, fs):
    fs.show_image(QImage(1920, 1080, QImage.Format_RGB32))
    r = fs.video_rect()
    assert fs.rect().contains(r)
    assert r.width() == fs.width() or r.height() == fs.height()
    assert abs(r.width() / r.height() - 16 / 9) < 0.02


def test_escape_leaves_fullscreen_and_does_not_close_the_program(win, fs):
    QTest.keyClick(fs, Qt.Key_Escape)
    assert not win.is_fullscreen() and not fs.isVisible()
    assert win.isVisible()


def test_escape_in_fullscreen_keeps_the_card_selection(win):
    win.range_slider.setValues(5, 10)
    win.add_segment()
    win.segment_list.setCurrentRow(0)
    win.enter_fullscreen()
    QTest.keyClick(win.fullscreen_window(), Qt.Key_Escape)
    assert not win.is_fullscreen()
    assert win.segment_list.currentRow() == 0


def test_toggle_via_api_both_ways(win):
    win.toggle_fullscreen()
    assert win.is_fullscreen()
    win.toggle_fullscreen()
    assert not win.is_fullscreen()
    win.exit_fullscreen()                     # leaving twice is harmless
    assert not win.is_fullscreen()


def test_space_toggles_play_and_pause(win, fs, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "toggle_play", lambda: calls.append(1))
    QTest.keyClick(fs, Qt.Key_Space)
    QTest.keyClick(fs, Qt.Key_Space)
    assert calls == [1, 1]


def test_double_click_does_nothing_but_toggle_fullscreen(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "toggle_play", lambda: calls.append("play"))
    win.range_slider.setValues(5, 10)
    win.add_segment()
    before = (win.segments(), win.range_slider.low(), win.range_slider.high(),
              win.player.volume(), win.player.is_muted())
    dclick(win.video_widget)
    f = win.fullscreen_window()
    click(f, QPoint(f.width() // 2, f.height() // 2))
    dclick(f, QPoint(f.width() // 2, f.height() // 2))
    assert calls == []
    assert not win.is_fullscreen()
    assert before == (win.segments(), win.range_slider.low(), win.range_slider.high(),
                      win.player.volume(), win.player.is_muted())


def test_closing_the_main_window_closes_fullscreen_too(win, fs):
    win.close()
    assert not fs.isVisible() and not win.isVisible()


def test_closing_the_fullscreen_window_only_leaves_fullscreen(win, fs):
    fs.close()                                # e.g. Alt+F4 on the borderless window
    assert not win.is_fullscreen() and not fs.isVisible()
    assert win.isVisible()


# ---------------------------------------------------------------- player output

def test_player_output_goes_to_the_sink_and_back(win, fs):
    player = win.player._player
    assert player.videoSink() is fs.sink
    win.exit_fullscreen()
    assert player.videoSink() is win.video_widget.videoSink()
    win.enter_fullscreen()
    assert player.videoSink() is fs.sink
    win.exit_fullscreen()
    assert player.videoSink() is win.video_widget.videoSink()


# ---------------------------------------------------------------- header

def test_panels_are_hidden_when_fullscreen_starts(fs):
    assert not fs.header_visible() and not fs.footer_visible()
    assert not fs.header.isVisible() and not fs.footer.isVisible()
    assert not fs.toast.isVisible()


def test_header_has_a_centred_cross_button_that_only_leaves_fullscreen(win, fs):
    reveal_header(fs)
    buttons = fs.header.findChildren(QAbstractButton)
    assert set(buttons) == {fs.exit_button, fs.export_button}      # v0.2.4: Export next to the cross
    assert fs.exit_button.toolTip() == i18n.tr("en", "exit_fullscreen") == "Exit full screen"
    assert fs.exit_button.iconKind() == "cross"
    assert fs.exit_button.width() == fs.exit_button.height()              # round
    centre = fs.exit_button.mapTo(fs, fs.exit_button.rect().center())
    assert abs(centre.x() - fs.width() / 2) <= 1
    assert fs.header.geometry().top() >= 0 and fs.header.width() == fs.width()
    other = [c for c in fs.header.findChildren(QLineEdit)] + fs.header.findChildren(QAbstractSlider)
    assert other == []
    click(fs.exit_button)
    assert not win.is_fullscreen()
    assert win.isVisible()                    # the cross does NOT quit the program


def test_cross_tooltip_is_localised(win, fs):
    for lang in LANGS:
        win.set_language(lang)
        assert fs.exit_button.toolTip() == i18n.tr(lang, "exit_fullscreen")


def test_header_slides_in_from_above_the_top_edge(win, fs):
    move_to(fs, 100, 5)
    assert wait_for(lambda: fs.header.isVisible() and fs.header.y() == 0)
    assert fs.header.height() <= fs.HEADER_ZONE + 10


# ---------------------------------------------------------------- mouse zones and timers

def test_zone_constants():
    assert FullscreenWindow.HEADER_ZONE == 80
    assert FullscreenWindow.FOOTER_ZONE == 140
    assert FullscreenWindow.HIDE_DELAY_MS == 120 or FullscreenWindow.HIDE_DELAY_MS == 1500


def test_header_appears_on_mouse_at_the_top_and_hides_afterwards(fs):
    move_to(fs, fs.width() // 2, fs.HEADER_ZONE - 5)
    assert wait_for(lambda: fs.header.isVisible() and fs.header_visible())
    assert not fs.footer_visible()
    move_to(fs, fs.width() // 2, fs.height() // 2)
    assert wait_for(lambda: not fs.header.isVisible() and not fs.header_visible())


def test_footer_appears_on_mouse_at_the_bottom_and_hides_afterwards(fs):
    move_to(fs, fs.width() // 2, fs.height() - fs.FOOTER_ZONE + 5)
    assert wait_for(lambda: fs.footer.isVisible() and fs.footer_visible())
    assert not fs.header_visible()
    assert wait_for(lambda: fs.rect().contains(fs.footer.geometry()))      # slid fully into view
    move_to(fs, fs.width() // 2, fs.height() // 2)
    assert wait_for(lambda: not fs.footer.isVisible() and not fs.footer_visible())


def test_middle_of_the_screen_shows_no_panel(fs):
    move_to(fs, fs.width() // 2, fs.height() // 2)
    pump(80)
    assert not fs.header_visible() and not fs.footer_visible()


def test_panels_hide_after_inactivity_even_with_the_mouse_in_the_zone(fs):
    move_to(fs, 10, 5)                         # in the zone, but not on the cross button
    assert wait_for(lambda: fs.header_visible())
    assert wait_for(lambda: not fs.header_visible(), 3)


def test_panel_stays_while_the_mouse_is_over_it(fs):
    reveal_footer(fs)
    inside = fs.footer.mapTo(fs, fs.footer.rect().center())
    move_to(fs, inside.x(), inside.y())
    pump(5 * fs.HIDE_DELAY_MS)
    assert fs.footer_visible() and fs.footer.isVisible()


def test_panel_stays_while_a_range_handle_is_dragged(fs):
    reveal_footer(fs)
    s = fs.footer.range_slider
    y = s.height() // 2
    press(s, QPoint(int(s.value_to_x(0)), y))
    move_to(fs, fs.width() // 2, fs.height() // 2)            # the pointer wanders off while dragging
    pump(5 * fs.HIDE_DELAY_MS)
    assert fs.footer_visible()
    release(s, QPoint(int(s.value_to_x(10)), y))
    assert wait_for(lambda: not fs.footer_visible())


def test_both_panels_can_be_hidden_again_and_shown_again(fs):
    for _ in range(2):
        reveal_header(fs)
        move_to(fs, 400, 300)
        assert wait_for(lambda: not fs.header.isVisible())
        reveal_footer(fs)
        move_to(fs, 400, 300)
        assert wait_for(lambda: not fs.footer.isVisible())


def test_cursor_hides_when_idle_without_panels_and_returns_on_motion(fs):
    assert wait_for(lambda: fs.cursor().shape() == Qt.BlankCursor, 3)
    assert fs.cursor_hidden()
    move_to(fs, 300, 300)
    assert fs.cursor().shape() != Qt.BlankCursor and not fs.cursor_hidden()
    assert wait_for(lambda: fs.cursor_hidden(), 3)


def test_cursor_stays_visible_while_a_panel_is_shown(fs, monkeypatch):
    monkeypatch.setattr(FullscreenWindow, "HIDE_DELAY_MS", 100000)    # the panel does not auto hide
    reveal_footer(fs)
    inside = fs.footer.mapTo(fs, fs.footer.rect().center())
    move_to(fs, inside.x(), inside.y())
    pump(4 * fs.CURSOR_HIDE_MS)
    assert not fs.cursor_hidden()


def test_timers_stop_after_leaving_and_cursor_is_reset(win, fs):
    assert wait_for(lambda: fs.cursor_hidden(), 3)
    win.exit_fullscreen()
    assert not fs.cursor_hidden()


# ---------------------------------------------------------------- footer content

ALLOWED_BUTTONS = ["play_button", "mute_button", "set_start_button", "set_end_button", "add_button"]


def test_footer_has_exactly_the_allowed_controls(fs):
    f = fs.footer
    buttons = f.findChildren(QAbstractButton)
    assert sorted(id(b) for b in buttons) == sorted(id(getattr(f, n)) for n in ALLOWED_BUTTONS)
    sliders = f.findChildren(QAbstractSlider)
    assert sorted(id(s) for s in sliders) == sorted(id(s) for s in (f.position_slider, f.volume_slider))
    assert f.findChildren(RangeSlider) == [f.range_slider]
    assert sorted(id(e) for e in f.findChildren(QLineEdit)) == sorted(id(e) for e in (f.start_edit, f.end_edit))
    assert f.position_label is not None
    # forbidden pieces
    assert f.findChildren(SegmentCardList) == [] and f.findChildren(StatusProgressBar) == []


@pytest.mark.parametrize("lang", LANGS)
def test_footer_has_no_forbidden_texts(win, fs, lang):
    win.set_language(lang)
    forbidden = set()
    for key in ("save", "mode", "mode_fast", "mode_precise", "clear_all", "open", "language", "theme"):
        forbidden.add(i18n.tr(lang, key))
    texts = {b.text() for b in fs.footer.findChildren(GlassButton)}
    assert not (texts & forbidden)
    assert fs.footer.add_button.text() == i18n.tr(lang, "add_segment")
    assert fs.footer.set_start_button.text() == i18n.tr(lang, "set_start")
    assert fs.footer.set_end_button.text() == i18n.tr(lang, "set_end")


def test_footer_does_not_contain_gear_or_open(fs):
    assert all(b.iconKind() in (None, "play", "pause", "speaker") for b in fs.footer.findChildren(GlassButton))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("th", THEMES)
def test_footer_geometry_no_overlaps_and_inside(win, lang, th):
    win.set_theme(th)
    win.set_language(lang)
    win.enter_fullscreen()
    fs = win.fullscreen_window()
    f = fs.footer
    fs.show_panels(animate=False)
    pump(40)
    assert fs.rect().contains(f.geometry())
    assert f.height() <= fs.FOOTER_ZONE + 20
    row1 = [f.play_button, f.position_slider, f.position_label, f.mute_button, f.volume_slider]
    row3 = [f.start_label, f.start_edit, f.set_start_button, f.end_label, f.end_edit,
            f.set_end_button, f.add_button]
    allw = row1 + [f.range_slider] + row3
    rects = {w: QRect(w.mapTo(f, w.rect().topLeft()), w.size()) for w in allw}
    for w, r in rects.items():
        assert w.isVisibleTo(f) and r.width() > 0 and r.height() > 0
        assert f.rect().contains(r), (w, r, f.rect())
    import itertools
    for a, b in itertools.combinations(allw, 2):
        assert not rects[a].intersects(rects[b]), (a, b, rects[a], rects[b])
    assert f.volume_slider.width() >= 80
    for row in (row1, row3):
        ys = [rects[w].center().y() for w in row if not isinstance(w, QAbstractSlider)]
        assert max(ys) - min(ys) <= 8


def test_footer_geometry_is_independent_of_language(win):
    win.enter_fullscreen()
    fs = win.fullscreen_window()
    fs.show_panels(animate=False)
    pump(40)
    snap = {}
    for lang in LANGS:
        win.set_language(lang)
        pump(20)
        snap[lang] = (fs.footer.geometry(),
                      [w.geometry() for w in fs.footer.findChildren(GlassButton)],
                      fs.footer.range_slider.geometry())
    assert snap["en"] == snap["ru"] == snap["uk"]


# ---------------------------------------------------------------- state mirrors

def test_volume_syncs_both_ways(win, fs):
    fs.footer.volume_slider.setValue(35)
    assert win.volume_slider.value() == 35 and win.player.volume() == pytest.approx(0.35)
    win.volume_slider.setValue(70)
    assert fs.footer.volume_slider.value() == 70
    assert (fs.footer.volume_slider.minimum(), fs.footer.volume_slider.maximum()) == (0, 100)


def test_mute_syncs_both_ways(win, fs):
    fs.footer.mute_button.click()
    assert win.mute_button.isChecked() and win.player.is_muted()
    assert fs.footer.mute_button.isChecked()
    win.mute_button.click()
    assert not fs.footer.mute_button.isChecked() and not win.player.is_muted()
    assert fs.footer.mute_button.isCheckable() and fs.footer.mute_button.iconKind() == "speaker"
    assert fs.footer.mute_button.toolTip() == win.mute_button.toolTip()


def test_volume_and_mute_reach_the_audio_output_from_the_footer(win, fs):
    from test_ui import FakeAudioOutput
    out = win.player._audio = FakeAudioOutput()
    fs.footer.volume_slider.setValue(20)
    assert out.volume == pytest.approx(0.2)
    fs.footer.mute_button.click()
    assert out.muted is True


def test_position_display_syncs_to_the_footer(win, fs):
    win.preview_at(12.5)
    assert fs.footer.position_slider.value() == 12500
    assert fs.footer.position_label.text() == "00:12.500"
    win._on_player_position(3000)
    assert fs.footer.position_slider.value() == 3000
    assert fs.footer.position_label.text() == "00:03.000"
    assert fs.footer.position_slider.maximum() == win.position_slider.maximum() == 60000


def test_footer_position_slider_seeks(win, fs, monkeypatch):
    seeks = []
    monkeypatch.setattr(win.player, "set_position_ms", lambda ms: seeks.append(ms))
    fs.footer.position_slider.sliderMoved.emit(7000)
    assert seeks == [7000]


def test_footer_position_slider_is_not_overwritten_while_pressed(win, fs):
    s = fs.footer.position_slider
    s.setSliderDown(True)
    s.setValue(9000)
    win._on_player_position(1000)
    assert s.value() == 9000
    s.setSliderDown(False)


def test_footer_play_button_toggles_play(win, fs, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "toggle_play", lambda: calls.append(1))
    fs.footer.play_button.click()
    assert calls == [1]
    monkeypatch.setattr(win.player, "is_playing", lambda: True)
    win.player.playingChanged.emit(True)
    assert fs.footer.play_button.iconKind() == "pause"
    monkeypatch.setattr(win.player, "is_playing", lambda: False)
    win.player.playingChanged.emit(False)
    assert fs.footer.play_button.iconKind() == "play"


def test_range_syncs_both_ways(win, fs):
    fs.footer.range_slider.setValues(7, 33)
    assert (win.range_slider.low(), win.range_slider.high()) == (7, 33)
    assert win.start_edit.text() == "00:07.000"
    win.range_slider.setValues(2, 9)
    assert (fs.footer.range_slider.low(), fs.footer.range_slider.high()) == (2, 9)
    assert fs.footer.start_edit.text() == "00:02.000" and fs.footer.end_edit.text() == "00:09.000"
    assert fs.footer.range_slider.maximum() == 60


def test_footer_fields_edit_the_range(win, fs):
    fs.footer.end_edit.setText("0:40")
    fs.footer.end_edit.editingFinished.emit()
    assert win.range_slider.high() == 40 and fs.footer.range_slider.high() == 40
    assert fs.footer.end_edit.text() == "00:40.000"
    fs.footer.start_edit.setText("nonsense")
    fs.footer.start_edit.editingFinished.emit()
    assert win.range_slider.low() == 0 and fs.footer.start_edit.text() == "00:00.000"


def test_footer_here_buttons_use_the_current_position(win, fs, monkeypatch):
    monkeypatch.setattr(win, "current_position", lambda: 12.0)
    fs.footer.set_start_button.click()
    monkeypatch.setattr(win, "current_position", lambda: 44.0)
    fs.footer.set_end_button.click()
    assert (win.range_slider.low(), win.range_slider.high()) == (12.0, 44.0)
    assert (fs.footer.range_slider.low(), fs.footer.range_slider.high()) == (12.0, 44.0)


def test_footer_edits_a_selected_card_in_fullscreen(win):
    win.range_slider.setValues(5, 10)
    win.add_segment()
    win.segment_list.setCurrentRow(0)
    win.enter_fullscreen()
    fs = win.fullscreen_window()
    fs.footer.range_slider.setValues(6, 11)
    assert win.segments() == [(6.0, 11.0)]


def test_preview_follows_footer_range_handle_drag(win, fs, preview_calls):
    reveal_footer(fs)
    s = fs.footer.range_slider
    y = s.height() // 2
    preview_calls.clear()
    press(s, QPoint(int(s.value_to_x(0)), y))
    drag_move(s, QPoint(int(s.value_to_x(15)), y))
    drag_move(s, QPoint(int(s.value_to_x(20)), y))
    assert preview_calls and preview_calls[-1][0] == pytest.approx(s.low() * 1000, abs=1)
    release(s, QPoint(int(s.value_to_x(20)), y))
    ms, immediate = preview_calls[-1]
    assert immediate and ms == round(s.low() * 1000) and ms == pytest.approx(20000, abs=700)
    n = len(preview_calls)
    press(s, QPoint(int(s.value_to_x(60)), y))
    drag_move(s, QPoint(int(s.value_to_x(45)), y))
    release(s, QPoint(int(s.value_to_x(45)), y))
    assert len(preview_calls) > n
    ms, immediate = preview_calls[-1]
    assert immediate and ms == round(s.high() * 1000) and ms == pytest.approx(45000, abs=700)
    assert fs.footer.position_label.text() == win.position_label.text()


def test_stale_player_positions_ignored_while_dragging_a_footer_handle(win, fs, preview_calls):
    reveal_footer(fs)
    s = fs.footer.range_slider
    y = s.height() // 2
    press(s, QPoint(int(s.value_to_x(0)), y))
    drag_move(s, QPoint(int(s.value_to_x(30)), y))
    shown = fs.footer.position_slider.value()
    win._on_player_position(1000)
    assert fs.footer.position_slider.value() == shown and win.position_slider.value() == shown
    release(s, QPoint(int(s.value_to_x(30)), y))
    win._on_player_position(1000)
    assert fs.footer.position_slider.value() == 1000


def test_footer_enabled_state_mirrors_the_window(win, fs):
    assert fs.footer.add_button.isEnabled() and fs.footer.range_slider.isEnabled()
    win._busy = True
    win._update_enabled()
    assert not fs.footer.add_button.isEnabled() and not fs.footer.range_slider.isEnabled()
    win._busy = False
    win._update_enabled()
    assert fs.footer.add_button.isEnabled()


# ---------------------------------------------------------------- Add and the toast

def test_add_in_fullscreen_creates_a_card_and_shows_the_toast(win, fs):
    fs.footer.range_slider.setValues(5, 20)
    fs.footer.add_button.click()
    assert win.segments() == [(5.0, 20.0)]
    assert win.segment_list.count() == 1 and win.segment_list.currentRow() == -1
    assert fs.toast.isVisible()
    assert fs.toast.text() == "Segment #1 created" == i18n.tr("en", "segment_created", n=1)
    fs.footer.range_slider.setValues(30, 40)
    fs.footer.add_button.click()
    assert win.segments() == [(5.0, 20.0), (30.0, 40.0)]
    assert fs.toast.text() == "Segment #2 created"


def test_toast_disappears_after_a_moment(fs, win):
    win.add_segment()
    assert fs.toast.isVisible()
    assert wait_for(lambda: not fs.toast.isVisible(), 3)


def test_toast_is_localised(win):
    for lang, n in (("ru", 1), ("uk", 2)):
        win.set_language(lang)
        win.enter_fullscreen()
        fs = win.fullscreen_window()
        win.add_segment()
        assert fs.toast.text() == i18n.tr(lang, "segment_created", n=len(win.segments()))
        win.exit_fullscreen()


def test_toast_is_inside_the_screen_and_does_not_cover_the_header_button(fs, win):
    win.add_segment()
    t = QRect(fs.toast.mapTo(fs, QPoint(0, 0)), fs.toast.size())
    assert fs.rect().contains(t)
    reveal_header(fs)
    cross = QRect(fs.exit_button.mapTo(fs, QPoint(0, 0)), fs.exit_button.size())
    assert not t.intersects(cross)


def test_no_toast_when_not_in_fullscreen(win):
    win.add_segment()
    if win._fs is not None:
        assert not win._fs.toast.isVisible()


# ---------------------------------------------------------------- state across enter / leave

def test_state_is_preserved_across_enter_and_exit(win):
    win.range_slider.setValues(5, 20)
    win.add_segment()
    win.range_slider.setValues(30, 44)
    win.add_segment()
    win.segment_list.setCurrentRow(0)
    win.volume_slider.setValue(33)
    win.mute_button.setChecked(True)
    win.preview_at(12.0)
    before = (win.segments(), win.segment_list.currentRow(), win.range_slider.low(),
              win.range_slider.high(), win.volume_slider.value(), win.player.volume(),
              win.mute_button.isChecked(), win.player.is_muted(), win.position_slider.value(),
              win.position_label.text(), win.edit_note.text())
    for _ in range(2):
        win.enter_fullscreen()
        f = win.fullscreen_window()
        assert f.footer.volume_slider.value() == 33 and f.footer.mute_button.isChecked()
        assert (f.footer.range_slider.low(), f.footer.range_slider.high()) == (5, 20)
        assert f.footer.position_slider.value() == 12000
        win.exit_fullscreen()
        after = (win.segments(), win.segment_list.currentRow(), win.range_slider.low(),
                 win.range_slider.high(), win.volume_slider.value(), win.player.volume(),
                 win.mute_button.isChecked(), win.player.is_muted(), win.position_slider.value(),
                 win.position_label.text(), win.edit_note.text())
        assert after == before


def test_changes_made_in_fullscreen_are_kept_after_leaving(win, fs):
    fs.footer.volume_slider.setValue(10)
    fs.footer.mute_button.click()
    fs.footer.range_slider.setValues(3, 8)
    fs.footer.add_button.click()
    win.exit_fullscreen()
    assert win.volume_slider.value() == 10 and win.mute_button.isChecked()
    assert win.segments() == [(3.0, 8.0)]
    assert (win.range_slider.low(), win.range_slider.high()) == (3, 8)


def test_footer_follows_language_and_theme_changes(win, fs):
    win.set_language("uk")
    assert fs.footer.add_button.text() == i18n.tr("uk", "add_segment")
    assert fs.footer.play_button.toolTip() == win.play_button.toolTip()
    light = fs.footer.grab().toImage()
    win.set_theme("dark")
    assert fs.footer.grab().toImage() != light


# ---------------------------------------------------------------- painting

def test_canvas_paints_the_frame_letterboxed_and_black_around(win, fs):
    img = QImage(1600, 900, QImage.Format_RGB32)
    img.fill(QColor(200, 30, 30))
    fs.show_image(img)
    pump(30)
    shot = fs.grab().toImage()
    r = fs.video_rect()
    c = r.center()
    px = shot.pixelColor(c.x(), c.y())
    assert px.red() > 150 and px.green() < 80
    # 16:9 inside 4:3: black bars above and below
    assert shot.pixelColor(fs.width() // 2, 2).name() == "#000000"
    assert shot.pixelColor(fs.width() // 2, fs.height() - 3).name() == "#000000"


def test_canvas_without_a_frame_is_black(fs):
    shot = fs.grab().toImage()
    assert shot.pixelColor(10, 10).name() == "#000000"
    assert shot.pixelColor(fs.width() // 2, fs.height() // 2).name() == "#000000"


def test_header_and_footer_are_painted_over_the_video(win, fs):
    img = QImage(800, 600, QImage.Format_RGB32)
    img.fill(QColor(250, 250, 250))
    fs.show_image(img)
    plain = fs.grab().toImage()
    fs.show_panels(animate=False)
    pump(40)
    with_panels = fs.grab().toImage()
    assert plain != with_panels
    f = fs.footer.geometry()
    assert with_panels.pixelColor(f.center().x(), f.center().y()) != plain.pixelColor(f.center().x(), f.center().y())
    assert fs.header.isVisible() and fs.footer.isVisible()


def test_frames_of_the_sink_are_stored_and_painted(fs):
    from PySide6.QtMultimedia import QVideoFrame
    img = QImage(64, 48, QImage.Format_ARGB32)
    img.fill(QColor(30, 200, 60))
    frame = QVideoFrame(img)
    frame.setStartTime(2_500_000)
    before = fs.frame_count
    fs.sink.setVideoFrame(frame)
    assert fs.frame_count == before + 1
    assert fs.last_frame_ms == pytest.approx(2500, abs=1)
    assert not fs.frame_image().isNull() and fs.frame_image().size() == QSize(64, 48)
    pump(30)
    c = fs.video_rect().center()
    px = fs.grab().toImage().pixelColor(c.x(), c.y())
    assert px.green() > 150 and px.red() < 90


# ---------------------------------------------------------------- real video

@pytest.fixture
def real(app, video_only):
    """A window with the real core and the generated 10 s clip (keyframe every second)."""
    w = MainWindow()
    w.resize(1000, 700)
    w.show()
    w.open_file(str(video_only))
    assert wait_for(lambda: w.has_video() and not w.is_busy(), 15)
    player = w.player._player
    assert wait_for(lambda: player.videoSink().videoSize().isValid(), 10)
    yield w
    wait_for(lambda: not w.is_busy())
    w.close()


def frame_times(sink):
    got = []
    sink.videoFrameChanged.connect(lambda fr: got.append(fr.startTime() / 1000.0))
    return got


def test_real_video_frames_arrive_in_the_fullscreen_widget(real):
    real.enter_fullscreen()
    fs = real.fullscreen_window()
    assert wait_for(lambda: fs.frame_count > 0, 10)
    assert not fs.frame_image().isNull()
    assert fs.frame_image().size() == QSize(320, 240)
    fs.show_panels(animate=False)
    shot = fs.grab().toImage()
    r = fs.video_rect()
    assert not shot.isNull() and r.width() == fs.width() or r.height() == fs.height()
    # the picture really differs from black in the middle
    c = r.center()
    assert shot.pixelColor(c.x(), c.y()).name() != "#000000" or shot.pixelColor(c.x() + 30, c.y()).name() != "#000000"


def test_real_video_dragging_a_footer_handle_delivers_the_frame_of_that_time(real):
    real.enter_fullscreen()
    fs = real.fullscreen_window()
    assert wait_for(lambda: fs.frame_count > 0, 10)
    reveal_footer(fs)
    s = fs.footer.range_slider
    y = s.height() // 2
    press(s, QPoint(int(s.value_to_x(0)), y))
    for t in (1.0, 2.0, 3.0, 4.0):
        drag_move(s, QPoint(int(s.value_to_x(t)), y))
        pump(30)
    release(s, QPoint(int(s.value_to_x(4.0)), y))
    assert wait_for(lambda: abs(fs.last_frame_ms - 4000) <= 250, 8), fs.last_frame_ms
    # the end handle: its frame is shown
    press(s, QPoint(int(s.value_to_x(10)), y))
    drag_move(s, QPoint(int(s.value_to_x(8.0)), y))
    release(s, QPoint(int(s.value_to_x(8.0)), y))
    assert wait_for(lambda: abs(fs.last_frame_ms - real.range_slider.high() * 1000) <= 250, 8), fs.last_frame_ms
    assert abs(real.range_slider.high() - 8.0) < 0.3
    assert abs(real.range_slider.low() - 4.0) < 0.3


def test_real_video_normal_preview_gets_frames_again_after_leaving(real):
    normal = real.video_widget.videoSink()
    got = frame_times(normal)
    real.enter_fullscreen()
    fs = real.fullscreen_window()
    assert wait_for(lambda: fs.frame_count > 0, 10)
    n_fs, n_normal = fs.frame_count, len(got)
    real.preview_at(6.0, immediate=True)
    assert wait_for(lambda: abs(fs.last_frame_ms - 6000) <= 250, 8)
    assert len(got) == n_normal                      # the hidden preview gets nothing meanwhile
    real.exit_fullscreen()
    n_fs = fs.frame_count
    real.preview_at(2.0, immediate=True)
    assert wait_for(lambda: got and abs(got[-1] - 2000) <= 250, 8), got[-3:]
    assert fs.frame_count == n_fs                    # and the fullscreen sink gets nothing now


def test_real_video_position_and_pause_survive_enter_and_exit(real):
    real.preview_at(5.0, immediate=True)
    assert wait_for(lambda: abs(real.player.position_ms() - 5000) <= 200, 8)
    assert not real.player.is_playing()
    real.enter_fullscreen()
    pump(300)
    assert not real.player.is_playing()
    assert abs(real.player.position_ms() - 5000) <= 300
    real.exit_fullscreen()
    pump(300)
    assert not real.player.is_playing() and abs(real.player.position_ms() - 5000) <= 300


def test_real_video_playing_state_survives_enter_and_exit(real):
    real.player.play()
    assert wait_for(real.player.is_playing, 8)
    real.enter_fullscreen()
    fs = real.fullscreen_window()
    n = fs.frame_count
    assert wait_for(lambda: fs.frame_count > n + 3, 8)       # frames keep flowing into the sink
    assert real.player.is_playing()
    real.exit_fullscreen()
    assert real.player.is_playing()
    got = frame_times(real.video_widget.videoSink())
    assert wait_for(lambda: len(got) > 3, 8)                  # ... and back into the preview
    real.player.pause()


def test_real_video_double_click_flow(real):
    dclick(real.video_widget)
    fs = real.fullscreen_window()
    assert real.is_fullscreen() and wait_for(lambda: fs.frame_count > 0, 10)
    dclick(fs, QPoint(300, 300))
    assert not real.is_fullscreen()
