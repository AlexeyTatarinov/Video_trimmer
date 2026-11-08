"""Geometry tests for v0.2.1/v0.2.2 (responsive layout, no overlaps, compact panels, segment cards).

Run with QT_QPA_PLATFORM=offscreen and VIDEO_TRIMMER_NO_AUDIO=1.
"""
from __future__ import annotations

import itertools
import os
import subprocess
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QComboBox, QLineEdit, QScrollArea, QSlider, QWidget,
)

from video_trimmer import core, i18n
from video_trimmer.ui import theme
from video_trimmer.ui.main_window import MainWindow
from video_trimmer.ui.range_slider import RangeSlider
from video_trimmer.ui.widgets import GlassPanel

from conftest import FFMPEG

SIZES = [(960, 600), (1024, 700), (1366, 768), (1920, 1040), (2560, 1400), "max"]
THEMES = ["light", "dark"]
LANGS = ["en", "ru", "uk"]
MIN_W, MIN_H = 960, 600


def size_id(s):
    return "maximised" if s == "max" else f"{s[0]}x{s[1]}"


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(theme, "make_settings", lambda: QSettings(path, QSettings.IniFormat))
    theme.set_current("light")
    yield
    theme.set_current("light")


def pump(ms=60):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.004)
    QApplication.processEvents()


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


class FakeCore:
    def __init__(self, duration):
        self.duration = duration

    def install(self, monkeypatch):
        monkeypatch.setattr(core, "probe", lambda p: core.VideoInfo(self.duration, 640, 360, True, True))
        monkeypatch.setattr(core, "validate_segments", lambda r, d: list(r))


@pytest.fixture
def make_window(app, monkeypatch, tmp_path):
    FakeCore(36000.0).install(monkeypatch)  # ten hours: the hours time format is used
    windows = []

    def factory(lang="en", th="light", size=(1024, 700), segments=1, load=True):
        w = MainWindow(language=lang)
        windows.append(w)
        w.set_theme(th)
        w.set_language(lang)
        small_screen = app.primaryScreen().availableGeometry().width() < MIN_W
        if size == "max" and not small_screen:
            w.showMaximized()
        elif size == "max":
            # the offscreen screen (800x600) is smaller than the minimum window: use a big window
            w.resize(1600, 900)
            w.show()
        else:
            w.resize(*size)
            w.show()
        pump()
        if load:
            src = tmp_path / "in.mp4"
            src.write_bytes(b"x")
            w.open_file(str(src))
            assert wait_for(lambda: w.has_video() and not w.is_busy())
            for i in range(segments - 1):
                w.range_slider.setValues(3600.0 * 9 + i, 3600.0 * 9 + 3599.0 - i)
                w.add_segment()
        pump()
        return w

    yield factory
    for w in windows:
        wait_for(lambda: not w.is_busy())
        w.close()


# ------------------------------------------------------------------ helpers

def scroll_area(w) -> QScrollArea:
    return w.scroll_area


def content(w) -> QWidget:
    return w.scroll_area.widget()


def rect_in(widget: QWidget, ref: QWidget) -> QRect:
    return QRect(widget.mapTo(ref, widget.rect().topLeft()), widget.size())


def intersects(a: QRect, b: QRect) -> bool:
    return a.intersects(b) and not a.intersected(b).isEmpty()


def interactive_widgets(w: MainWindow) -> list[QWidget]:
    kinds = (QAbstractButton, QSlider, RangeSlider, QLineEdit, QComboBox)
    out = []
    for x in w.findChildren(QWidget):
        if isinstance(x, kinds) and x.window() is w and "qt_" not in x.objectName():
            if x.parent() is not None and x.parent().objectName().startswith("qt_scrollarea_hcontainer"):
                continue
            if isinstance(x, QSlider) and x.parent() is not None and isinstance(x.parent(), QScrollArea):
                continue
            if x.objectName().startswith("qt_"):
                continue
            out.append(x)
    return out


def named_geometry(w: MainWindow) -> dict:
    names = ["open_button", "settings_button", "play_button", "mute_button", "set_start_button",
             "set_end_button", "add_button", "clear_button", "fast_radio", "precise_radio",
             "info_button", "save_button", "video_widget", "position_slider", "volume_slider",
             "range_slider", "start_edit", "end_edit", "position_label", "progress_bar",
             "segment_list", "title_label", "start_label", "end_label", "mode_label"]
    c = content(w)
    geo = {n: rect_in(getattr(w, n), c).getRect() for n in names}
    for i, p in enumerate(w.findChildren(GlassPanel)):
        geo[f"panel{i}"] = rect_in(p, c).getRect()
    geo["content"] = c.size().toTuple()
    return geo


# ------------------------------------------------------------------ (a) panels do not overlap

@pytest.mark.parametrize("size", SIZES, ids=size_id)
@pytest.mark.parametrize("th", THEMES)
@pytest.mark.parametrize("lang", LANGS)
def test_panels_and_controls_do_not_overlap(make_window, size, th, lang):
    w = make_window(lang, th, size)
    c = content(w)
    panels = w.findChildren(GlassPanel)
    assert len(panels) >= 5
    rects = [rect_in(p, c) for p in panels]
    for (i, a), (j, b) in itertools.combinations(enumerate(rects), 2):
        assert not intersects(a, b), f"panels {i} {a} and {j} {b} overlap"
    # the video widget lies inside the video panel and never over a neighbour
    vrect = rect_in(w.video_widget, c)
    owners = [r for r in rects if r.contains(vrect)]
    assert len(owners) == 1, f"video {vrect} not inside exactly one panel: {rects}"
    # interactive widgets do not intersect one another
    items = interactive_widgets(w)
    assert len(items) >= 15
    boxes = [(x, rect_in(x, c)) for x in items if x.isVisibleTo(w)]
    for (xa, a), (xb, b) in itertools.combinations(boxes, 2):
        assert not intersects(a, b), f"{xa} {a} overlaps {xb} {b}"
    # nothing sticks out of the scrollable content, no horizontal scrolling is needed
    for p, r in zip(panels, rects):
        assert c.rect().contains(r), f"panel {r} outside content {c.rect()}"
    assert not scroll_area(w).horizontalScrollBar().isVisible()


# ------------------------------------------------------------------ (b) controls visible and reachable

@pytest.mark.parametrize("size", SIZES, ids=size_id)
@pytest.mark.parametrize("th", THEMES)
@pytest.mark.parametrize("lang", LANGS)
def test_every_control_is_visible_and_reachable(make_window, size, th, lang):
    w = make_window(lang, th, size, segments=3)
    c = content(w)
    sa = scroll_area(w)
    for x in interactive_widgets(w):
        assert x.isVisibleTo(w), f"{x} hidden"
        assert x.width() > 0 and x.height() > 0, f"{x} has zero size"
        assert c.rect().contains(rect_in(x, c)), f"{x} outside the content"
    # sound controls, always
    assert w.mute_button.isVisibleTo(w) and w.volume_slider.isVisibleTo(w)
    assert w.volume_slider.width() >= 90
    # the controls row is in the viewport without scrolling, at every size >= the minimum
    assert w.width() >= MIN_W and w.height() >= MIN_H
    view = QRect(sa.viewport().mapTo(w, sa.viewport().rect().topLeft()), sa.viewport().size())
    for x in (w.play_button, w.position_slider, w.position_label, w.mute_button, w.volume_slider):
        r = QRect(x.mapTo(w, x.rect().topLeft()), x.size())
        assert view.contains(r), f"{x} {r} not in the viewport {view} without scrolling"
    # the time label fits the longest time text
    fm = QFontMetrics(w.position_label.font())
    assert w.position_label.width() >= fm.horizontalAdvance("00:00:00.000")
    # nothing wider than the window
    assert not sa.horizontalScrollBar().isVisible()


def test_minimum_size_and_initial_size(make_window, app):
    w = make_window("en", "light", (1024, 700), load=False)
    assert w.minimumWidth() <= MIN_W + 40 and w.minimumHeight() <= MIN_H + 40
    assert w.minimumWidth() >= 900
    fresh = MainWindow()
    geo = app.primaryScreen().availableGeometry()
    assert fresh.width() <= max(int(geo.width() * 0.9), fresh.minimumWidth())
    assert fresh.height() <= max(int(geo.height() * 0.9), fresh.minimumHeight())
    fresh.close()


def test_small_window_scrolls_instead_of_clipping(make_window):
    w = make_window("ru", "light", (MIN_W, MIN_H), segments=25)
    sa = scroll_area(w)
    assert not sa.horizontalScrollBar().isVisible()
    # a screen/window shorter than the content: it scrolls, nothing is clipped
    w.setMinimumSize(0, 0)
    w.resize(MIN_W, 300)
    pump()
    assert sa.verticalScrollBar().maximum() > 0
    assert not sa.horizontalScrollBar().isVisible()
    sa.verticalScrollBar().setValue(sa.verticalScrollBar().maximum())
    pump()
    c = content(w)
    r = rect_in(w.save_button, w)                    # the last control becomes reachable
    view = QRect(sa.viewport().mapTo(w, sa.viewport().rect().topLeft()), sa.viewport().size())
    assert view.contains(r)
    assert c.height() > sa.viewport().height()


# ------------------------------------------------------------------ (c) language does not change geometry

@pytest.mark.parametrize("size", [(960, 600), (1366, 768), (1920, 1040), "max"], ids=size_id)
@pytest.mark.parametrize("th", THEMES)
def test_geometry_is_identical_across_languages(make_window, size, th):
    w = make_window("en", th, size, segments=3)
    base = named_geometry(w)
    for lang in ("ru", "uk", "en"):
        w.set_language(lang)
        pump()
        got = named_geometry(w)
        for key, value in base.items():
            assert got[key] == value, f"{key} changed with language {lang}: {value} -> {got[key]}"


def test_texts_are_elided_not_stretched(make_window):
    w = make_window("en", "light", (MIN_W, MIN_H))
    before = named_geometry(w)
    w.progress_bar.setText("x" * 400)
    pump()
    assert named_geometry(w) == before


# ------------------------------------------------------------------ (d) segment cards

@pytest.mark.parametrize("n", [1, 7, 25])
@pytest.mark.parametrize("size", [(MIN_W, MIN_H), (1366, 768), (1920, 1040)], ids=size_id)
@pytest.mark.parametrize("th", THEMES)
def test_cards_do_not_overlap_wrap_and_are_not_clipped(make_window, n, size, th):
    w = make_window("uk", th, size, segments=n)
    lst = w.segment_list
    cards = lst.cards()
    assert len(cards) == n == len(w.segments())
    inner = lst.widget()
    rects = [rect_in(c, inner) for c in cards]
    for (i, a), (j, b) in itertools.combinations(enumerate(rects), 2):
        assert not intersects(a, b), f"cards {i} and {j} overlap"
    # one standard size
    assert len({(c.width(), c.height()) for c in cards}) == 1
    cw, ch = cards[0].width(), cards[0].height()
    avail = lst.viewport().width()
    for r in rects:
        assert r.right() < inner.width() + 1 and r.left() >= 0
    rows = sorted({r.top() for r in rects})
    per_row = max(1, (avail + 8) // (cw + 8))
    if n * (cw + 8) - 8 > avail:
        assert len(rows) >= 2, f"{n} cards of {cw}px must wrap in {avail}px"
    else:
        assert len(rows) == 1
    assert len(rows) >= -(-n // (per_row + 1))
    # no clipped text
    for c in cards:
        for label in c.text_labels():
            fm = QFontMetrics(label.font())
            assert label.width() >= fm.horizontalAdvance(label.text()), (
                f"clipped: {label.text()!r} in {label.width()}px")
            assert c.rect().contains(rect_in(label, c))
        assert c.delete_button.isVisibleTo(w) and c.delete_button.width() > 0
    # height grows to about two rows, then scrolls (compact layout)
    sa_h = lst.height()
    assert sa_h <= 2 * ch + 2 * 12 + 40
    if len(rows) > 2:
        assert lst.verticalScrollBar().maximum() > 0
    if len(rows) <= 2:
        assert lst.verticalScrollBar().maximum() == 0
    # the card of the longest content fits: hours format
    assert any(":" in lbl.text() and "9:" in lbl.text() for c in cards for lbl in c.text_labels()) or n == 1


def test_card_width_covers_the_longest_text(make_window):
    w = make_window("en", "light", (1366, 768), segments=2)
    card = w.segment_list.cards()[0]
    fm = QFontMetrics(card.range_label.font())
    longest = "88:88:88.888 - 88:88:88.888"
    assert card.range_label.width() >= fm.horizontalAdvance(longest)


def test_card_click_selects_and_highlights(make_window):
    w = make_window("en", "light", (1366, 768), segments=4)
    cards = w.segment_list.cards()
    assert w.segment_list.currentRow() == 3
    from PySide6.QtTest import QTest
    QTest.mouseClick(cards[1], Qt.LeftButton)
    assert w.segment_list.currentRow() == 1
    assert cards[1].is_selected() and not cards[3].is_selected()
    for th in THEMES:
        w.set_theme(th)
        pump()
        a = cards[1].grab().toImage()
        b = cards[2].grab().toImage()
        assert a != b, f"selected card looks the same as the others in the {th} theme"


def test_card_delete_button_removes_that_segment(make_window):
    w = make_window("en", "light", (1366, 768), segments=3)
    before = w.segments()
    from PySide6.QtTest import QTest
    QTest.mouseClick(w.segment_list.cards()[0].delete_button, Qt.LeftButton)
    pump()
    assert w.segments() == before[1:]
    for _ in range(5):
        if len(w.segments()) > 1:
            QTest.mouseClick(w.segment_list.cards()[0].delete_button, Qt.LeftButton)
            pump()
    assert len(w.segments()) == 1
    last = w.segment_list.cards()[0]
    assert not last.delete_button.isEnabled()          # the cross is disabled on the only segment
    w.remove_segment_at(0)
    assert len(w.segments()) == 1


# ------------------------------------------------------------------ (e) real video: 4K and portrait

def _make_clip(path, size, secs=2):
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i",
           f"testsrc2=size={size}:rate=5:duration={secs}", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return path


@pytest.fixture(scope="module")
def clip_4k(tmp_path_factory):
    return _make_clip(tmp_path_factory.mktemp("big") / "uhd.mp4", "3840x2160")


@pytest.fixture(scope="module")
def clip_portrait(tmp_path_factory):
    return _make_clip(tmp_path_factory.mktemp("port") / "portrait.mp4", "1080x1920")


@pytest.mark.parametrize("which", ["clip_4k", "clip_portrait"])
@pytest.mark.parametrize("size", [(MIN_W, MIN_H), (1366, 768), (1920, 1040)], ids=size_id)
def test_video_widget_is_independent_of_the_video(app, monkeypatch, request, which, size):
    path = request.getfixturevalue(which)
    w = MainWindow()
    try:
        w.resize(*size)
        w.show()
        pump()
        c = content(w)
        before = rect_in(w.video_widget, c)
        hint_before = w.video_widget.sizeHint()
        panels_before = [rect_in(p, c).getRect() for p in w.findChildren(GlassPanel)]
        w.open_file(str(path))
        assert wait_for(lambda: w.has_video() and not w.is_busy(), 15)
        player = getattr(w.player, "_player", None)
        if player is not None:
            wait_for(lambda: player.videoSink().videoSize().isValid(), 10)
        pump(400)
        after = rect_in(w.video_widget, c)
        assert after.size() == before.size(), f"video widget grew: {before} -> {after}"
        assert w.video_widget.sizeHint() == hint_before
        assert after.width() < 1800 or size[0] >= 1920
        panels_after = [rect_in(p, c).getRect() for p in w.findChildren(GlassPanel)]
        assert panels_after == panels_before
        video_panel = next(p for p in w.findChildren(GlassPanel) if p.isAncestorOf(w.video_widget))
        assert rect_in(video_panel, c).contains(after)
        assert not scroll_area(w).horizontalScrollBar().isVisible()
        rects = [rect_in(p, c) for p in w.findChildren(GlassPanel)]
        for a, b in itertools.combinations(rects, 2):
            assert not intersects(a, b)
    finally:
        w.close()
