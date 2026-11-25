"""v0.4.0 (UI part): visible area (crop frame and zoom) per segment.

Run with QT_QPA_PLATFORM=offscreen and VIDEO_TRIMMER_NO_AUDIO=1. The core is the fake of
tests/test_ui.py (probe reports 640x360); the end-to-end test at the bottom uses the real core.
"""
from __future__ import annotations

import inspect
import os
import subprocess
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from video_trimmer import core, i18n
from video_trimmer.ui import preview
from video_trimmer.ui.crop_types import Crop, normalize_crop
from video_trimmer.ui.main_window import MainWindow

from test_ui import app, fake, isolated_settings, win as _win, wait_for  # noqa: F401

pytestmark = pytest.mark.skipif(not preview.MULTIMEDIA_AVAILABLE, reason="QtMultimedia not installed")

LANGS = ["en", "ru", "uk"]
SRC_W, SRC_H = 640, 360          # what the fake probe reports


# ---------------------------------------------------------------- helpers

def pump(ms=60):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.004)


def _mouse(widget, etype, pos, button=Qt.NoButton, buttons=Qt.NoButton, mods=Qt.NoModifier):
    pos = QPointF(pos)
    ev = QMouseEvent(etype, pos, QPointF(widget.mapToGlobal(pos.toPoint())), button, buttons, mods)
    QApplication.sendEvent(widget, ev)
    return ev


def drag(widget, a, b, button=Qt.LeftButton, steps=4):
    a, b = QPointF(a), QPointF(b)
    _mouse(widget, QEvent.MouseButtonPress, a, button, button)
    for i in range(1, steps + 1):
        p = a + (b - a) * (i / steps)
        _mouse(widget, QEvent.MouseMove, p, Qt.NoButton, button)
    _mouse(widget, QEvent.MouseButtonRelease, b, button, Qt.NoButton)


def wheel(widget, pos, steps=1, mods=Qt.NoModifier):
    pos = QPointF(pos)
    ev = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0),
                     QPoint(0, int(120 * steps)), Qt.NoButton, mods, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)
    return ev


def key(widget, k, text="", release=False):
    ev = QKeyEvent(QEvent.KeyRelease if release else QEvent.KeyPress, k, Qt.NoModifier, text)
    QApplication.sendEvent(widget, ev)
    return ev


def rect_tuple(c):
    return (c.x, c.y, c.w, c.h)


def assert_inside(c, w=SRC_W, h=SRC_H):
    assert c.x >= 0 and c.y >= 0 and c.x + c.w <= w and c.y + c.h <= h, c
    assert c.w >= 32 and c.h >= 32, c


@pytest.fixture
def win(_win):
    _win.resize(1200, 860)
    _win.show()
    pump(80)
    return _win


@pytest.fixture
def ov(win):
    return win.crop_overlay


def shrink(ov, crop=Crop(160, 90, 320, 180)):
    ov.set_area(crop, emit=True)
    return crop


# ---------------------------------------------------------------- crop types

def test_crop_type_fields():
    c = Crop(1, 2, 34, 56)
    assert (c.x, c.y, c.w, c.h) == (1, 2, 34, 56)
    assert Crop(1, 2, 34, 56) == c


def test_crop_type_is_the_core_one_when_core_has_it():
    if hasattr(core, "Crop"):
        assert Crop is core.Crop


@pytest.mark.parametrize("raw,expected", [
    (Crop(0, 0, 640, 360), None),                       # full frame = no crop
    (None, None),
    (Crop(10, 10, 101, 51), (10, 10, 100, 50)),         # odd sizes evened
    (Crop(-20, -5, 100, 100), (0, 0, 100, 100)),        # clamped into the picture
    (Crop(600, 300, 100, 100), (540, 260, 100, 100)),   # pushed back inside
    (Crop(5, 5, 10, 8), (5, 5, 32, 32)),                # minimum 32x32
])
def test_normalize_crop(raw, expected):
    got = normalize_crop(raw, 640, 360)
    assert (None if got is None else rect_tuple(got)) == expected


# ---------------------------------------------------------------- overlay placement

def test_overlay_sits_over_the_preview_and_knows_the_source_size(win, ov):
    assert ov.parentWidget() is win.video_widget
    assert ov.geometry() == win.video_widget.rect()
    assert ov.source_size() == QSize(SRC_W, SRC_H)
    assert ov.area() is None and rect_tuple(ov.area_rect()) == (0, 0, SRC_W, SRC_H)
    pic = ov.picture_rect()
    assert abs(pic.width() / pic.height() - 16 / 9) < 0.02
    assert ov.rect().contains(pic.toAlignedRect().adjusted(1, 1, -1, -1))


def test_overlay_is_not_a_native_window(win, ov):
    assert not win.video_widget.testAttribute(Qt.WA_NativeWindow)
    assert not ov.testAttribute(Qt.WA_NativeWindow)
    assert hasattr(win.video_widget, "videoSink")


def test_rounded_corners_still_clip_the_preview(win):
    m = win.video_widget.mask()
    assert not m.isEmpty() and not m.contains(QPoint(0, 0))


def test_frame_is_painted_red_over_the_picture(win, ov):
    shrink(ov)
    pump(40)
    img = win.video_widget.grab().toImage()
    fr = ov.frame_rect()
    p = QPoint(int(fr.left() + fr.width() * 0.3), int(fr.top()) + 1)   # between two handles
    c = img.pixelColor(p)
    assert c.red() > 150 and c.green() < 90 and c.blue() < 90, c.name()


# ---------------------------------------------------------------- drag / resize

def test_drag_inside_moves_the_area_and_keeps_the_size(ov):
    shrink(ov)
    fr = ov.frame_rect()
    scale = ov.picture_rect().width() / SRC_W
    drag(ov, fr.center(), fr.center() + QPointF(50 * scale, 20 * scale))
    c = ov.area()
    assert (c.w, c.h) == (320, 180)
    assert abs(c.x - 210) <= 2 and abs(c.y - 110) <= 2


def test_drag_cannot_leave_the_picture(ov):
    shrink(ov)
    fr = ov.frame_rect()
    drag(ov, fr.center(), fr.center() + QPointF(3000, 3000))
    c = ov.area()
    assert rect_tuple(c) == (SRC_W - 320, SRC_H - 180, 320, 180)
    drag(ov, ov.frame_rect().center(), ov.frame_rect().center() - QPointF(5000, 5000))
    assert rect_tuple(ov.area()) == (0, 0, 320, 180)


@pytest.mark.parametrize("handle", ["tl", "t", "tr", "r", "br", "b", "bl", "l"])
def test_every_handle_resizes_and_stays_even_and_inside(ov, handle):
    shrink(ov)
    before = ov.area()
    hc = ov.handle_rect(handle).center()
    out = QPointF(("r" in handle) * 37 - ("l" in handle) * 37, ("b" in handle) * 23 - ("t" in handle) * 23)
    drag(ov, hc, hc + out)
    c = ov.area()
    assert c != before
    assert c.w % 2 == 0 and c.h % 2 == 0
    assert_inside(c)
    # free proportions: an edge handle changes one dimension only
    if handle in ("l", "r"):
        assert c.h == before.h and c.w > before.w
    if handle in ("t", "b"):
        assert c.w == before.w and c.h > before.h


def test_resize_is_clamped_to_the_picture_and_to_the_minimum(ov):
    shrink(ov)
    hc = ov.handle_rect("br").center()
    drag(ov, hc, hc + QPointF(4000, 4000))
    c = ov.area_rect()
    assert c.x + c.w <= SRC_W and c.y + c.h <= SRC_H
    assert (c.x, c.y) == (160, 90)
    hc = ov.handle_rect("br").center()
    drag(ov, hc, hc - QPointF(4000, 4000))
    c = ov.area()
    assert (c.x, c.y, c.w, c.h) == (160, 90, 32, 32)


def test_handles_are_the_eight_expected_names(ov):
    shrink(ov)
    names = ["tl", "t", "tr", "r", "br", "b", "bl", "l"]
    for n in names:
        assert ov.handle_at(ov.handle_rect(n).center()) == n
    assert ov.handle_at(ov.frame_rect().center()) is None


# ---------------------------------------------------------------- area zoom

def test_wheel_over_the_frame_zooms_the_area_around_the_cursor(ov):
    full = ov.area_rect()
    pic = ov.picture_rect()
    cursor = QPointF(pic.left() + pic.width() * 0.25, pic.top() + pic.height() * 0.25)
    wheel(ov, cursor, steps=2)
    c = ov.area()
    assert c is not None and c.w < full.w and c.h < full.h
    assert_inside(c)
    # the source point under the cursor keeps its relative place inside the area
    assert abs((160 - c.x) / c.w - 0.25) < 0.03 and abs((90 - c.y) / c.h - 0.25) < 0.03
    wheel(ov, ov.frame_rect().center(), steps=-10)
    assert ov.area() is None or ov.area().w >= c.w


def test_wheel_outside_the_frame_does_not_change_the_area(ov):
    shrink(ov, Crop(0, 0, 100, 100))
    pic = ov.picture_rect()
    before = ov.area()
    wheel(ov, QPointF(pic.right() - 5, pic.bottom() - 5), steps=1)
    assert ov.area() == before


def test_zoom_in_out_buttons_and_full_frame(win, ov):
    win.zoom_in_button.click()
    a = ov.area()
    assert a is not None and a.w < SRC_W and a.w % 2 == 0 and a.h % 2 == 0
    # centred
    assert abs((a.x + a.w / 2) - SRC_W / 2) <= 2 and abs((a.y + a.h / 2) - SRC_H / 2) <= 2
    win.zoom_in_button.click()
    b = ov.area()
    assert b.w < a.w
    win.zoom_out_button.click()
    assert ov.area().w > b.w
    win.full_frame_button.click()
    assert ov.area() is None


def test_keyboard_plus_minus_zoom_the_area(win, ov):
    ov.setFocus()
    key(ov, Qt.Key_Plus, "+")
    a = ov.area()
    assert a is not None
    key(ov, Qt.Key_Minus, "-")
    assert ov.area() is None or ov.area().w > a.w
    # also when the focus is elsewhere in the window (not in a text field)
    win.play_button.setFocus()
    key(win.play_button, Qt.Key_Plus, "+")
    assert ov.area() is not None and ov.area().w < SRC_W


def test_area_never_goes_below_the_minimum_by_zooming(ov):
    for _ in range(40):
        ov.zoom_in()
    c = ov.area()
    assert min(c.w, c.h) >= 32 and min(c.w, c.h) <= 34
    assert_inside(c)


# ---------------------------------------------------------------- view zoom (Ctrl+wheel) and pan

def test_ctrl_wheel_zooms_the_view_only(win, ov):
    shrink(ov)
    area = ov.area()
    pic = ov.picture_rect()
    cursor = ov.frame_rect().center()
    wheel(ov, cursor, steps=2, mods=Qt.ControlModifier)
    assert ov.view_zoom() > 1.0
    assert ov.area() == area                                    # the saved result is unchanged
    assert ov.picture_rect().width() > pic.width()
    # the frame stays glued to the picture
    fr = ov.frame_rect()
    assert abs(fr.width() / ov.picture_rect().width() - 320 / SRC_W) < 0.01
    win.fit_view_button.click()
    assert ov.view_zoom() == 1.0 and ov.picture_rect() == pic


def test_ctrl_wheel_also_works_outside_the_frame(ov):
    shrink(ov, Crop(0, 0, 64, 64))
    pic = ov.picture_rect()
    wheel(ov, QPointF(pic.right() - 4, pic.bottom() - 4), steps=1, mods=Qt.ControlModifier)
    assert ov.view_zoom() > 1.0 and rect_tuple(ov.area()) == (0, 0, 64, 64)


def test_middle_drag_pans_and_double_middle_click_fits(ov):
    ov.set_view_zoom(3.0)
    before = ov.picture_rect()
    c = ov.rect().center()
    drag(ov, c, c + QPoint(60, 30), button=Qt.MiddleButton)
    after = ov.picture_rect()
    assert after.topLeft() != before.topLeft()
    assert ov.view_zoom() == 3.0 and ov.area() is None
    # the zoomed picture always covers the fitted rectangle (never pans away)
    drag(ov, c, c + QPoint(5000, 5000), button=Qt.MiddleButton)
    base = ov.base_rect()
    r = ov.picture_rect()
    assert r.left() <= base.left() + 0.5 and r.top() <= base.top() + 0.5
    _mouse(ov, QEvent.MouseButtonDblClick, c, Qt.MiddleButton, Qt.MiddleButton)
    assert ov.view_zoom() == 1.0


def test_space_drag_pans_when_zoomed(ov):
    shrink(ov)
    area = ov.area()
    ov.set_view_zoom(2.0)
    before = ov.picture_rect()
    ov.setFocus()
    key(ov, Qt.Key_Space, " ")
    c = ov.frame_rect().center()
    drag(ov, c, c + QPointF(40, 0))
    key(ov, Qt.Key_Space, " ", release=True)
    assert ov.picture_rect().left() > before.left()
    assert ov.area() == area                                    # pan, not a move of the frame


# ---------------------------------------------------------------- per-card areas

def test_add_segment_stores_the_area_in_the_new_card(win, ov):
    shrink(ov)
    win.range_slider.setValues(1, 5)
    win.add_segment()
    ov.reset_area()
    win.range_slider.setValues(6, 9)
    win.add_segment()
    assert win.segments() == [(1, 5), (6, 9)]
    crops = win.segment_crops()
    assert [None if c is None else rect_tuple(c) for c in crops] == [(160, 90, 320, 180), None]


def test_card_shows_a_crop_mark_with_the_size(win, ov):
    shrink(ov)
    win.range_slider.setValues(1, 5)
    win.add_segment()
    ov.reset_area()
    win.add_segment()
    c0, c1 = win.segment_list.card(0), win.segment_list.card(1)
    assert c0.crop_label.text() == i18n.tr("en", "crop_mark", w=320, h=180)
    assert "320x180" in c0.crop_label.text()
    assert c1.crop_label.text() == ""
    win.set_language("uk")
    assert c0.crop_label.text() == i18n.tr("uk", "crop_mark", w=320, h=180)


def test_clicking_a_card_restores_its_area_and_editing_updates_it(win, ov):
    shrink(ov)
    win.range_slider.setValues(1, 5)
    win.add_segment()
    ov.reset_area()
    win.range_slider.setValues(6, 9)
    win.add_segment()
    win.segment_list.setCurrentRow(0)
    assert rect_tuple(ov.area()) == (160, 90, 320, 180)
    assert win.range_slider.low() == 1
    win.segment_list.setCurrentRow(1)
    assert ov.area() is None
    # editing mode: changing the frame edits the selected card
    ov.set_area(Crop(0, 0, 200, 100), emit=True)
    assert rect_tuple(win.segment_crops()[1]) == (0, 0, 200, 100)
    assert "200x100" in win.segment_list.card(1).crop_label.text()
    assert rect_tuple(win.segment_crops()[0]) == (160, 90, 320, 180)
    # draft mode: the frame no longer edits any card
    win.segment_list.setCurrentRow(-1)
    ov.reset_area()
    assert rect_tuple(win.segment_crops()[1]) == (0, 0, 200, 100)


def test_full_frame_button_edits_the_selected_card(win, ov):
    shrink(ov)
    win.add_segment()
    win.segment_list.setCurrentRow(0)
    win.full_frame_button.click()
    assert win.segment_crops() == [None]
    assert win.segment_list.card(0).crop_label.text() == ""


def test_remove_and_move_keep_the_areas_with_their_cards(win, ov):
    for i, crop in enumerate([Crop(0, 0, 64, 64), None, Crop(10, 10, 100, 100)]):
        if crop is None:
            ov.reset_area()
        else:
            ov.set_area(crop, emit=True)
        win.range_slider.setValues(i, i + 1)
        win.add_segment()
    win.move_segment(2, 0)
    assert win.segments() == [(2, 3), (0, 1), (1, 2)]
    assert [None if c is None else c.w for c in win.segment_crops()] == [100, 64, None]
    win.remove_segment_at(1)
    assert win.segments() == [(2, 3), (1, 2)]
    assert [None if c is None else c.w for c in win.segment_crops()] == [100, None]
    win._confirm_clear = lambda: True
    win.clear_segments()
    assert win.segment_crops() == [] and ov.area() is None


def test_opening_a_new_video_resets_the_frame_and_view(win, ov):
    shrink(ov)
    ov.set_view_zoom(2.0)
    win.add_segment()
    win.open_file(win.src_path)
    assert wait_for(lambda: not win.is_busy())
    assert ov.area() is None and ov.view_zoom() == 1.0 and win.segment_crops() == []


# ---------------------------------------------------------------- saving

class CropAwareTrim:
    def __init__(self):
        self.calls = []

    def __call__(self, src, ranges, out_dir, mode="fast", progress=None, crops=None):
        self.calls.append(dict(ranges=list(ranges), mode=mode, crops=crops))
        return [core.Path(out_dir) / f"part{i + 1}.mp4" for i in range(len(ranges))]


def test_save_passes_crops_to_trim_each(win, ov, monkeypatch):
    trim = CropAwareTrim()
    monkeypatch.setattr(core, "trim_each", trim)
    shrink(ov)
    win.range_slider.setValues(1, 5)
    win.add_segment()
    ov.reset_area()
    win.range_slider.setValues(6, 9)
    win.add_segment()
    win.save()
    assert wait_for(lambda: trim.calls and not win.is_busy())
    call = trim.calls[0]
    assert call["ranges"] == [(1, 5), (6, 9)]
    assert [None if c is None else rect_tuple(c) for c in call["crops"]] == [(160, 90, 320, 180), None]
    assert call["mode"] == "fast"                               # the core forces precise per crop


def test_save_without_crops_keeps_the_old_call(win, fake):
    win.range_slider.setValues(1, 5)
    win.add_segment()
    win.save()                                # the fake of test_ui.py has no ``crops`` parameter
    assert wait_for(lambda: fake.calls and not win.is_busy())
    assert fake.calls[0][1] == [(1, 5)]


# ---------------------------------------------------------------- texts

@pytest.mark.parametrize("lang", LANGS)
def test_mode_hint_mentions_precise_saving_of_areas(win, lang):
    win.set_language(lang)
    note = i18n.tr(lang, "mode_crop_note")
    assert note and note in win.fast_radio.toolTip()
    win.show_mode_info()
    pump()
    assert note in win.info_popup.text()
    win.info_popup.hide()


def test_new_keys_exist_in_every_language_with_identical_key_sets():
    keys = [set(i18n.STRINGS[l]) for l in LANGS]
    assert keys[0] == keys[1] == keys[2]
    for k in ("crop_mark", "mode_crop_note", "zoom_in", "zoom_out", "full_frame", "fit_view", "crop_tip"):
        for lang in LANGS:
            assert i18n.tr(lang, k, w=2, h=4)


@pytest.mark.parametrize("lang", LANGS)
def test_zoom_buttons_are_translated(win, lang):
    win.set_language(lang)
    assert win.zoom_in_button.toolTip() == i18n.tr(lang, "zoom_in")
    assert win.zoom_out_button.toolTip() == i18n.tr(lang, "zoom_out")
    assert win.full_frame_button.toolTip() == i18n.tr(lang, "full_frame")
    assert win.fit_view_button.toolTip() == i18n.tr(lang, "fit_view")
    assert i18n.tr(lang, "crop_tip") in win.crop_overlay.toolTip()


def test_zoom_buttons_are_disabled_without_a_video(app, fake):
    w = MainWindow()
    try:
        for b in (w.zoom_in_button, w.zoom_out_button, w.full_frame_button, w.fit_view_button):
            assert not b.isEnabled()
    finally:
        w.close()


# ---------------------------------------------------------------- double click

def test_double_click_inside_the_frame_toggles_fullscreen(win, ov):
    shrink(ov)
    c = ov.frame_rect().center()
    _mouse(ov, QEvent.MouseButtonPress, c, Qt.LeftButton, Qt.LeftButton)
    _mouse(ov, QEvent.MouseButtonRelease, c, Qt.LeftButton, Qt.NoButton)
    _mouse(ov, QEvent.MouseButtonDblClick, c, Qt.LeftButton, Qt.LeftButton)
    _mouse(ov, QEvent.MouseButtonRelease, c, Qt.LeftButton, Qt.NoButton)
    pump()
    assert win.is_fullscreen()
    win.exit_fullscreen()


def test_double_click_on_a_handle_does_not_toggle_fullscreen(win, ov):
    shrink(ov)
    h = ov.handle_rect("br").center()
    _mouse(ov, QEvent.MouseButtonDblClick, h, Qt.LeftButton, Qt.LeftButton)
    _mouse(ov, QEvent.MouseButtonRelease, h, Qt.LeftButton, Qt.NoButton)
    pump()
    assert not win.is_fullscreen()


# ---------------------------------------------------------------- fullscreen

@pytest.fixture
def fs(win):
    win.enter_fullscreen()
    f = win.fullscreen_window()
    img = QImage(SRC_W, SRC_H, QImage.Format_RGB32)
    img.fill(QColor(0, 160, 0))
    f.show_image(img)
    pump()
    yield f
    win.exit_fullscreen()


def test_fullscreen_has_its_own_overlay_with_the_same_area(win, ov, fs):
    win.exit_fullscreen()
    shrink(ov)
    win.enter_fullscreen()
    pump()
    fov = fs.crop_overlay
    assert fov.parentWidget() is fs and fov.geometry() == fs.rect()
    assert fov.area() == ov.area()
    # the overlay is under the panels
    children = fs.children()
    assert children.index(fov) < children.index(fs.footer) and children.index(fov) < children.index(fs.header)


def test_editing_the_area_in_fullscreen_updates_the_main_window_and_the_card(win, ov):
    win.add_segment()
    win.segment_list.setCurrentRow(0)
    win.enter_fullscreen()
    f = win.fullscreen_window()
    f.show_image(QImage(SRC_W, SRC_H, QImage.Format_RGB32))
    pump()
    fov = f.crop_overlay
    fov.zoom_in()
    assert fov.area() is not None
    assert ov.area() == fov.area()
    assert win.segment_crops()[0] == fov.area()
    hc = fov.handle_rect("tl").center()
    drag(fov, hc, hc + QPointF(-20, -20))
    assert win.segment_crops()[0] == fov.area() == ov.area()
    win.exit_fullscreen()


def test_fullscreen_footer_has_full_frame(win, ov, fs):
    fs.crop_overlay.zoom_in()
    assert ov.area() is not None
    b = fs.footer.full_frame_button
    assert b.text() == i18n.tr("en", "full_frame")
    b.click()
    assert ov.area() is None and fs.crop_overlay.area() is None
    win.set_language("ru")
    assert b.text() == i18n.tr("ru", "full_frame")


def test_fullscreen_keys_and_double_click(win, fs):
    fov = fs.crop_overlay
    key(fs, Qt.Key_Plus, "+")
    assert fov.area() is not None
    key(fs, Qt.Key_Minus, "-")
    # a double click inside the frame (bubbling up from the overlay) leaves full screen
    c = fov.frame_rect().center()
    _mouse(fov, QEvent.MouseButtonDblClick, c, Qt.LeftButton, Qt.LeftButton)
    pump()
    assert not win.is_fullscreen()


def test_fullscreen_double_click_on_a_handle_stays(win, fs):
    fov = fs.crop_overlay
    fov.zoom_in()
    _mouse(fov, QEvent.MouseButtonDblClick, fov.handle_rect("r").center(), Qt.LeftButton, Qt.LeftButton)
    pump()
    assert win.is_fullscreen()


def test_fullscreen_view_zoom_moves_the_painted_picture(win, fs):
    r0 = fs.video_rect()
    fov = fs.crop_overlay
    wheel(fov, QPointF(r0.center()), steps=2, mods=Qt.ControlModifier)
    r1 = fs.video_rect()
    assert r1.width() > r0.width() and fov.view_zoom() > 1
    fov.fit_view()
    assert fs.video_rect() == r0


# ---------------------------------------------------------------- real video, real core

@pytest.fixture(scope="module")
def quadrants(tmp_path_factory):
    """4 s, 320x240: red / green / blue / white quadrants."""
    out = tmp_path_factory.mktemp("quad") / "quad.mp4"
    filt = ("color=red:s=160x120:d=4[a];color=green:s=160x120:d=4[b];color=blue:s=160x120:d=4[c];"
            "color=white:s=160x120:d=4[d];[a][b]hstack[t];[c][d]hstack[bt];[t][bt]vstack,format=yuv420p")
    subprocess.run(["/usr/local/bin/ffmpeg", "-y", "-v", "error", "-filter_complex", filt,
                    "-r", "25", "-c:v", "libx264", "-preset", "ultrafast", "-g", "25", str(out)],
                   check=True)
    return out


def _core_supports_crops():
    return hasattr(core, "Crop") and "crops" in inspect.signature(core.trim_each).parameters


def test_real_video_frame_and_overlay_painted_on_top(app, quadrants, monkeypatch, tmp_path):
    w = MainWindow()
    try:
        w.resize(1100, 800)
        w.show()
        w.open_file(str(quadrants))
        assert wait_for(lambda: w.has_video() and not w.is_busy(), 15)
        assert w.crop_overlay.source_size() == QSize(320, 240)
        assert wait_for(lambda: not w.video_widget.frame_image().isNull(), 10)
        w.crop_overlay.set_area(Crop(160, 0, 160, 120), emit=True)          # the green quadrant
        pump(100)
        img = w.video_widget.grab().toImage()
        fr = w.crop_overlay.frame_rect()
        inside = img.pixelColor(fr.center().toPoint())
        assert inside.green() > 90 and inside.red() < 90, inside.name()      # picture, not dimmed
        edge = img.pixelColor(QPoint(int(fr.left() + fr.width() * 0.3), int(fr.bottom())))
        assert edge.red() > 150 and edge.green() < 90, edge.name()            # the red frame is on top
    finally:
        w.close()


@pytest.mark.skipif(not _core_supports_crops(), reason="core without crops (merged separately)")
def test_real_core_end_to_end_two_cards(app, quadrants, monkeypatch, tmp_path, ffprobe_json):
    monkeypatch.setattr(MainWindow, "_notify", lambda self, kind, text: None)
    w = MainWindow()
    out = tmp_path / "out"
    monkeypatch.setattr(w, "_ask_save_dir", lambda default: str(out))
    try:
        w.show()
        w.open_file(str(quadrants))
        assert wait_for(lambda: w.has_video() and not w.is_busy(), 15)
        w.crop_overlay.set_area(Crop(160, 0, 160, 120), emit=True)
        w.range_slider.setValues(0.0, 2.0)
        w.add_segment()
        w.crop_overlay.reset_area()
        w.range_slider.setValues(1.0, 3.0)
        w.add_segment()
        w.save()
        assert wait_for(lambda: not w.is_busy() and len(list(out.glob("*.mp4"))) == 2, 60)
        files = sorted(out.glob("*.mp4"))
        for f in files:
            v = ffprobe_json(f)["video"][0]
            assert (int(v["width"]), int(v["height"])) == (320, 240)
    finally:
        w.close()
