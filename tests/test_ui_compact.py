"""v0.2.2 tests: compact layout, video share, one-row controls, gear popup, card reordering,
Clear all, mode explanations.  Run with QT_QPA_PLATFORM=offscreen and VIDEO_TRIMMER_NO_AUDIO=1."""
from __future__ import annotations

import itertools
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from video_trimmer import core, i18n
from video_trimmer.ui import theme
from video_trimmer.ui.main_window import MainWindow
from video_trimmer.ui.widgets import GlassPanel

from test_ui import FakeCore, wait_for

LANGS = ["en", "ru", "uk"]
THEMES = ["light", "dark"]
MIN_W = 960


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(theme, "make_settings", lambda: QSettings(path, QSettings.IniFormat))
    theme.set_current("light")
    yield path
    theme.set_current("light")


def pump(ms=60):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.004)
    QApplication.processEvents()


@pytest.fixture
def fake(monkeypatch):
    f = FakeCore(duration=600.0)
    f.install(monkeypatch)
    return f


@pytest.fixture
def make(app, fake, monkeypatch, tmp_path):
    windows = []
    monkeypatch.setattr(MainWindow, "_notify", lambda self, kind, text: None)

    def factory(size=(1366, 768), segments=1, lang="en", th="light"):
        w = MainWindow(language=lang)
        windows.append(w)
        w.set_theme(th)
        w.resize(*size)
        w.show()
        pump()
        monkeypatch.setattr(w, "_ask_save_dir", lambda default: str(tmp_path / "out"))
        src = tmp_path / "in.mp4"
        src.write_bytes(b"x")
        w.open_file(str(src))
        assert wait_for(lambda: w.has_video() and not w.is_busy())
        for i in range(segments - 1):
            w.range_slider.setValues(10.0 * (i + 1), 10.0 * (i + 1) + 5)
            w.add_segment()
        pump()
        return w

    yield factory
    for w in windows:
        wait_for(lambda: not w.is_busy())
        w.close()


def rect_in(widget: QWidget, ref: QWidget) -> QRect:
    return QRect(widget.mapTo(ref, widget.rect().topLeft()), widget.size())


def share(w) -> float:
    return rect_in(w.video_panel, w.scroll_area.widget()).height() / w.height()


# ------------------------------------------------------------------ video share

def test_video_share_1920x1040(make):
    w = make((1920, 1040))
    assert share(w) >= 0.65, f"video share {share(w):.3f}"
    assert not w.scroll_area.verticalScrollBar().isVisible()


def test_video_share_1366x768_without_scroll(make):
    w = make((1366, 768))
    assert share(w) >= 0.50, f"video share {share(w):.3f}"
    assert not w.scroll_area.verticalScrollBar().isVisible()


def test_video_is_the_stretching_panel(make):
    w = make((1920, 1040))
    c = w.scroll_area.widget()
    others = [rect_in(p, c).height() for p in w.findChildren(GlassPanel) if p is not w.video_panel]
    assert rect_in(w.video_panel, c).height() > 1.5 * sum(others)


def test_many_segments_still_keep_video_the_biggest(make):
    w = make((1920, 1040), segments=12)
    assert share(w) >= 0.55


# ------------------------------------------------------------------ top row + gear popup

def test_header_row_title_left_buttons_right(make):
    w = make((1366, 768))
    c = w.scroll_area.widget()
    t, o, g = (rect_in(x, c) for x in (w.title_label, w.open_button, w.settings_button))
    assert t.right() < o.left() < o.right() < g.left()
    assert abs(t.center().y() - o.center().y()) <= 4 and abs(o.center().y() - g.center().y()) <= 4
    assert g.width() == g.height()                       # round gear button
    assert g.right() > c.width() - 40                     # on the right edge


def test_language_and_theme_are_not_in_the_main_layout(make):
    w = make((1366, 768))
    popup = w.settings_popup
    c = w.scroll_area.widget()
    for b in (*popup.language_buttons.values(), *popup.theme_buttons.values()):
        assert not c.isAncestorOf(b)
        assert not b.isVisible()                          # the popup is closed
    assert not hasattr(w, "language_combo") and not hasattr(w, "theme_button")


@pytest.mark.parametrize("lang", LANGS)
def test_gear_popup_opens_and_stays_inside_the_screen(make, lang):
    w = make((1366, 768), lang=lang)
    w.settings_button.click()
    pump()
    popup = w.settings_popup
    assert popup.isVisible()
    assert popup.width() > 0 and popup.height() > 0
    geo = QApplication.primaryScreen().availableGeometry()
    assert geo.contains(popup.frameGeometry()) or popup.frameGeometry().intersected(geo) == popup.frameGeometry()
    assert not popup.grab().isNull()
    popup.hide()


def test_gear_popup_language_selection_works_and_persists(make, fake, isolated_settings):
    w = make((1366, 768))
    w.settings_button.click()
    w.settings_popup.language_buttons["ru"].click()
    assert w.language == "ru"
    assert w.save_button.text() == i18n.tr("ru", "save")
    assert w.settings_popup.language_buttons["ru"].isChecked()
    assert not w.settings_popup.language_buttons["en"].isChecked()
    w2 = MainWindow()                                   # a new run restores the language
    assert w2.language == "ru"
    w2.close()
    w.settings_popup.language_buttons["uk"].click()
    assert MainWindow().language == "uk"


def test_gear_popup_theme_selection_works_and_persists(make, fake, isolated_settings):
    w = make((1366, 768))
    w.settings_button.click()
    w.settings_popup.theme_buttons["dark"].click()
    assert w.theme_name == "dark" and theme.current().name == "dark"
    assert w.settings_popup.theme_buttons["dark"].isChecked()
    w2 = MainWindow()
    assert w2.theme_name == "dark"
    w2.close()
    w.settings_popup.theme_buttons["light"].click()
    assert w.theme_name == "light"
    assert theme.load_theme_name(QSettings(isolated_settings, QSettings.IniFormat)) == "light"


def test_explicit_language_argument_wins_over_saved_one(make, fake):
    w = make((1366, 768))
    w.set_language("uk")
    w2 = MainWindow(language="en")
    assert w2.language == "en"
    w2.close()


# ------------------------------------------------------------------ one-row controls

@pytest.mark.parametrize("width", [MIN_W, 1100, 1366, 1920])
@pytest.mark.parametrize("lang", LANGS)
def test_range_controls_share_one_row(make, width, lang):
    w = make((width, 700), lang=lang, segments=3)
    c = w.scroll_area.widget()
    order = [w.start_label, w.start_edit, w.set_start_button, w.end_label, w.end_edit,
             w.set_end_button, w.add_button, w.clear_button]
    rects = [rect_in(x, c) for x in order]
    centers = [r.center().y() for r in rects]
    assert max(centers) - min(centers) <= 2, f"not one row: {rects}"
    for a, b in zip(rects, rects[1:]):
        assert a.right() < b.left(), f"{a} overlaps / is right of {b}"
    box = rect_in(w.range_box, c)
    assert all(box.contains(r) for r in rects)
    # the two-handle slider is above the row, inside the same panel
    s = rect_in(w.range_slider, c)
    assert s.bottom() < min(r.top() for r in rects) and box.contains(s)
    # the labels and the time fields are fully readable
    for edit in (w.start_edit, w.end_edit):
        assert edit.fontMetrics().horizontalAdvance("00:00:00.000") + 16 <= edit.width()


def test_one_panel_has_sliders_sound_and_add_button(make):
    w = make((1920, 1040))
    c = w.scroll_area.widget()
    # the two sliders (position, range), sound controls and "Add segment" are all visible at once
    for x in (w.position_slider, w.range_slider, w.mute_button, w.volume_slider, w.add_button):
        assert x.isVisibleTo(w)
        assert c.rect().contains(rect_in(x, c))
    assert not w.scroll_area.verticalScrollBar().isVisible()


def test_button_captions_are_short_with_tooltips(make):
    w = make((1366, 768))
    for b in (w.set_start_button, w.set_end_button, w.add_button, w.clear_button):
        assert b.toolTip()
    for lang in LANGS:
        for key in ("set_start", "set_end", "add_segment", "clear_all"):
            assert len(i18n.tr(lang, key)) <= 18


# ------------------------------------------------------------------ bottom row

def test_bottom_row_mode_progress_save_in_one_row(make):
    w = make((1366, 768))
    c = w.scroll_area.widget()
    order = [w.mode_label, w.fast_radio, w.precise_radio, w.info_button, w.progress_bar, w.save_button]
    rects = [rect_in(x, c) for x in order]
    assert max(r.center().y() for r in rects) - min(r.center().y() for r in rects) <= 2
    for a, b in zip(rects, rects[1:]):
        assert a.right() < b.left()
    assert rects[4].width() > 250                          # wide progress bar
    assert w.info_button.width() == w.info_button.height() <= 32
    assert not hasattr(w, "status_label") or w.status_label is w.progress_bar


def test_status_text_lives_in_the_progress_bar(make):
    w = make((1366, 768))
    w._show_status("ready")
    assert w.progress_bar.text() == i18n.tr("en", "ready")
    w.set_language("ru")
    assert w.progress_bar.text() == i18n.tr("ru", "ready")


def test_mode_radio_buttons_are_exclusive(make):
    w = make((1366, 768))
    assert w.mode() == "fast"
    w.precise_radio.click()
    assert w.mode() == "precise" and not w.fast_radio.isChecked()
    w.fast_radio.click()
    assert w.mode() == "fast"


@pytest.mark.parametrize("lang", LANGS)
def test_mode_explanations_exist_in_every_language(lang):
    fast, precise = i18n.tr(lang, "mode_fast_tip"), i18n.tr(lang, "mode_precise_tip")
    assert len(fast) > 60 and len(precise) > 40 and fast != precise
    key_fast = {"en": "keyframe", "ru": "ключев", "uk": "ключов"}[lang]
    key_precise = {"en": "re-encoded", "ru": "перекодируется", "uk": "перекодовується"}[lang]
    assert key_fast in fast and key_precise in fast and key_precise in precise
    assert i18n.tr(lang, "mode_fast") != i18n.tr(lang, "mode_precise")


@pytest.mark.parametrize("lang", LANGS)
def test_mode_tooltips_and_info_popup(make, lang):
    w = make((1366, 768), lang=lang)
    assert i18n.tr(lang, "mode_fast_tip") in w.fast_radio.toolTip()
    assert i18n.tr(lang, "mode_precise_tip") in w.precise_radio.toolTip()
    assert w.info_button.toolTip()
    w.info_button.click()
    pump()
    assert w.info_popup.isVisible()
    text = w.info_popup.text()
    assert i18n.tr(lang, "mode_fast_tip") in text and i18n.tr(lang, "mode_precise_tip") in text
    w.info_popup.hide()


# ------------------------------------------------------------------ cards: delete / clear

def test_cross_deletes_and_is_disabled_on_the_last_card(make):
    w = make((1366, 768), segments=3)
    assert all(c.delete_button.isEnabled() for c in w.segment_list.cards())
    QTest.mouseClick(w.segment_list.card(1).delete_button, Qt.LeftButton)
    assert len(w.segments()) == 2
    w.segment_list.card(0).delete_button.click()
    assert len(w.segments()) == 1
    assert not w.segment_list.card(0).delete_button.isEnabled()


def test_remove_button_is_gone(make):
    w = make((1366, 768))
    assert not hasattr(w, "remove_button")
    for lang in LANGS:
        assert i18n.tr(lang, "clear_all")


def test_clear_all_with_one_segment_needs_no_confirmation(make, monkeypatch):
    w = make((1366, 768))
    asked = []
    monkeypatch.setattr(w, "_confirm_clear", lambda: asked.append(1) or True)
    w.range_slider.setValues(5, 20)
    w.clear_button.click()
    assert asked == []
    assert w.segments() == [(0.0, 600.0)]


def test_clear_all_asks_and_resets_to_one_full_segment(make, monkeypatch):
    w = make((1366, 768), segments=4)
    asked = []
    monkeypatch.setattr(w, "_confirm_clear", lambda: asked.append(1) or True)
    w.clear_button.click()
    assert asked == [1]
    assert w.segments() == [(0.0, 600.0)]
    assert w.segment_list.count() == 1 and w.segment_list.currentRow() == 0
    assert w.range_slider.low() == 0 and w.range_slider.high() == 600
    assert not w.segment_list.card(0).delete_button.isEnabled()


def test_clear_all_declined_keeps_everything(make, monkeypatch):
    w = make((1366, 768), segments=4)
    before = w.segments()
    monkeypatch.setattr(w, "_confirm_clear", lambda: False)
    w.clear_button.click()
    assert w.segments() == before and w.segment_list.count() == 4


def test_clear_all_confirmation_is_a_yes_no_question(make, monkeypatch):
    w = make((1366, 768), segments=3)
    seen = {}

    def fake_question(parent, title, text, buttons=None, default=None):
        seen.update(title=title, text=text, buttons=buttons)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    w.clear_segments()
    assert seen["buttons"] == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    assert "3" in seen["text"]
    assert len(w.segments()) == 1


# ------------------------------------------------------------------ cards: reordering

RANGES = [(10.0, 15.0), (20.0, 25.0), (30.0, 35.0), (40.0, 45.0)]


def four(make):
    w = make((1366, 768), segments=1)
    for i, r in enumerate(RANGES):
        w.range_slider.setValues(*r)         # edits the selected segment
        if i < len(RANGES) - 1:
            w.add_segment()                  # a copy that becomes the selected one
    pump()
    assert w.segments() == RANGES
    return w


def drag_to(w, src: int, slot: int, release=True):
    """Press on card ``src``, drag to the insertion slot ``slot`` (0..n) with real mouse events."""
    lst = w.segment_list
    cards = lst.cards()
    sc = cards[src]
    start = QPoint(sc.width() // 2, sc.height() // 2)
    if slot < len(cards):
        target = cards[slot].mapToGlobal(QPoint(4, cards[slot].height() // 2))
    else:
        last = cards[-1]
        target = last.mapToGlobal(QPoint(last.width() - 3, last.height() // 2))
    QTest.mousePress(sc, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(sc, start + QPoint(14, 0))
    QTest.mouseMove(sc, sc.mapFromGlobal(target))
    if release:
        QTest.mouseRelease(sc, Qt.LeftButton, Qt.NoModifier, sc.mapFromGlobal(target))
    return sc, sc.mapFromGlobal(target)


def test_drag_card_to_the_end(make, fake):
    w = four(make)
    drag_to(w, 0, 4)
    assert w.segments() == [RANGES[1], RANGES[2], RANGES[3], RANGES[0]]
    assert w.segment_list.currentRow() == 3                # selection follows the moved card
    assert [c.index_label.text() for c in w.segment_list.cards()] == ["#1", "#2", "#3", "#4"]
    assert "00:10.000" in w.segment_list.card(3).range_label.text()
    w.save()
    assert wait_for(lambda: fake.calls and not w.is_busy())
    assert fake.calls[0][1] == [RANGES[1], RANGES[2], RANGES[3], RANGES[0]]


def test_drag_card_to_the_front(make, fake):
    w = four(make)
    drag_to(w, 3, 0)
    assert w.segments() == [RANGES[3], RANGES[0], RANGES[1], RANGES[2]]
    assert w.segment_list.currentRow() == 0


def test_drag_card_into_the_middle(make):
    w = four(make)
    drag_to(w, 0, 2)                    # before card 2 -> lands at index 1
    assert w.segments() == [RANGES[1], RANGES[0], RANGES[2], RANGES[3]]
    assert w.segment_list.currentRow() == 1
    drag_to(w, 3, 1)
    assert w.segments() == [RANGES[1], RANGES[3], RANGES[0], RANGES[2]]


def test_drop_in_place_changes_nothing(make):
    w = four(make)
    drag_to(w, 1, 1)
    drag_to(w, 1, 2)
    assert w.segments() == RANGES


def test_insertion_indicator_is_visible_while_dragging_only(make):
    w = four(make)
    lst = w.segment_list
    assert not lst.drop_indicator.isVisible()
    sc, pos = drag_to(w, 0, 3, release=False)
    assert lst.drop_indicator.isVisible()
    inner = lst.widget()
    ind = QRect(lst.drop_indicator.mapTo(inner, QPoint(0, 0)), lst.drop_indicator.size())
    c2, c3 = (QRect(lst.card(i).mapTo(inner, QPoint(0, 0)), lst.card(i).size()) for i in (2, 3))
    assert c2.right() <= ind.center().x() <= c3.left()      # between card 3 and card 4
    assert ind.height() >= c3.height() - 6
    QTest.mouseRelease(sc, Qt.LeftButton, Qt.NoModifier, pos)
    assert not lst.drop_indicator.isVisible()


def test_short_click_does_not_reorder_but_selects(make):
    w = four(make)
    QTest.mouseClick(w.segment_list.card(2), Qt.LeftButton)
    assert w.segments() == RANGES and w.segment_list.currentRow() == 2


def test_alt_arrows_move_the_selected_card(make, fake):
    w = four(make)
    w.segment_list.setCurrentRow(1)
    card = w.segment_list.card(1)
    card.setFocus()
    QTest.keyClick(card, Qt.Key_Right, Qt.AltModifier)
    assert w.segments() == [RANGES[0], RANGES[2], RANGES[1], RANGES[3]]
    assert w.segment_list.currentRow() == 2                # the selection follows the card
    QTest.keyClick(w.segment_list.card(2), Qt.Key_Left, Qt.AltModifier)
    QTest.keyClick(w.segment_list.card(1), Qt.Key_Left, Qt.AltModifier)
    assert w.segments() == [RANGES[1], RANGES[0], RANGES[2], RANGES[3]]
    assert w.segment_list.currentRow() == 0
    QTest.keyClick(w.segment_list.card(0), Qt.Key_Left, Qt.AltModifier)   # at the edge: nothing
    assert w.segments() == [RANGES[1], RANGES[0], RANGES[2], RANGES[3]]
    w.segment_list.setCurrentRow(3)
    QTest.keyClick(w.segment_list.card(3), Qt.Key_Right, Qt.AltModifier)
    assert w.segments()[-1] == RANGES[3]
    assert [c.index_label.text() for c in w.segment_list.cards()] == ["#1", "#2", "#3", "#4"]
    w.save()
    assert wait_for(lambda: fake.calls and not w.is_busy())
    assert fake.calls[0][1] == [RANGES[1], RANGES[0], RANGES[2], RANGES[3]]


def test_alt_arrows_work_when_focus_is_elsewhere(make):
    w = four(make)
    w.segment_list.setCurrentRow(0)
    w.add_button.setFocus()
    QTest.keyClick(w.add_button, Qt.Key_Right, Qt.AltModifier)
    assert w.segments()[1] == RANGES[0]


def test_plain_arrows_still_change_selection_only(make):
    w = four(make)
    w.segment_list.setCurrentRow(1)
    QTest.keyClick(w.segment_list.card(1), Qt.Key_Right)
    assert w.segment_list.currentRow() == 2 and w.segments() == RANGES


def test_reorder_updates_range_slider_to_selected_card(make):
    w = four(make)
    drag_to(w, 0, 4)
    assert (w.range_slider.low(), w.range_slider.high()) == RANGES[0]
    assert w.start_edit.text() == "00:10.000"


# ------------------------------------------------------------------ geometry stays stable

@pytest.mark.parametrize("th", THEMES)
def test_reordering_does_not_change_geometry(make, th):
    w = four(make)
    w.set_theme(th)
    c = w.scroll_area.widget()
    before = [rect_in(p, c).getRect() for p in w.findChildren(GlassPanel)]
    drag_to(w, 0, 4)
    after = [rect_in(p, c).getRect() for p in w.findChildren(GlassPanel)]
    assert before == after


@pytest.mark.parametrize("size", [(MIN_W, 600), (1366, 768), (1920, 1040), (2560, 1400)],
                         ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("th", THEMES)
def test_no_overlap_everything_visible(make, size, lang, th):
    w = make(size, segments=7, lang=lang, th=th)
    c = w.scroll_area.widget()
    panels = w.findChildren(GlassPanel)
    rects = [rect_in(p, c) for p in panels]
    for a, b in itertools.combinations(rects, 2):
        assert not a.intersected(b).isValid() or a.intersected(b).isEmpty()
    assert all(c.rect().contains(r) for r in rects)
    assert not w.scroll_area.horizontalScrollBar().isVisible()
    for x in (w.open_button, w.settings_button, w.play_button, w.mute_button, w.volume_slider,
              w.add_button, w.clear_button, w.fast_radio, w.precise_radio, w.info_button,
              w.progress_bar, w.save_button):
        assert x.isVisibleTo(w) and c.rect().contains(rect_in(x, c))
