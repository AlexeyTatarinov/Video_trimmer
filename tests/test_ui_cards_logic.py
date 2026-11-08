"""v0.2.3 part A: segment cards without duplication (draft / editing modes).

Run with QT_QPA_PLATFORM=offscreen and VIDEO_TRIMMER_NO_AUDIO=1.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from video_trimmer import i18n

# fixtures shared with the main UI tests (fake core, window with a "loaded" 60 s video)
from test_ui import app, fake, isolated_settings, preview_calls, win, wait_for  # noqa: F401


def add(w, lo, hi):
    w.range_slider.setValues(lo, hi)
    w.add_segment()


def three(w):
    add(w, 5, 10)
    add(w, 20, 25)
    add(w, 40, 55)
    assert w.segments() == [(5, 10), (20, 25), (40, 55)]


# ---------------------------------------------------------------- empty start, draft mode

def test_list_is_empty_after_opening_a_video(win):
    assert win.segments() == []
    assert win.segment_list.count() == 0
    assert win.segment_list.currentRow() == -1


def test_draft_is_the_whole_file_after_opening(win):
    assert (win.range_slider.low(), win.range_slider.high()) == (0.0, 60.0)
    assert win.start_edit.text() == "00:00.000" and win.end_edit.text() == "01:00.000"


def test_sliders_and_fields_in_draft_mode_do_not_create_cards(win):
    win.range_slider.setValues(5, 20)
    win.end_edit.setText("0:30")
    win.end_edit.editingFinished.emit()
    assert win.range_slider.high() == 30
    assert win.segments() == [] and win.segment_list.count() == 0
    assert win.end_edit.text() == "00:30.000"


def test_reopening_a_video_empties_the_list_again(win, tmp_path):
    add(win, 1, 2)
    src = tmp_path / "other.mp4"
    src.write_bytes(b"x")
    win.open_file(str(src))
    assert wait_for(lambda: not win.is_busy())
    assert win.segments() == [] and win.segment_list.count() == 0
    assert (win.range_slider.low(), win.range_slider.high()) == (0.0, 60.0)


# ---------------------------------------------------------------- Add

def test_first_add_creates_exactly_one_card_from_the_slider(win):
    win.range_slider.setValues(5, 20)
    win.add_button.click()
    assert win.segments() == [(5.0, 20.0)]
    assert win.segment_list.count() == 1                 # no duplicate of anything
    assert "00:05.000" in win.segment_list.card(0).range_label.text()
    assert "00:20.000" in win.segment_list.card(0).range_label.text()


def test_add_leaves_no_card_selected_and_the_slider_where_it_was(win):
    win.range_slider.setValues(5, 20)
    win.add_segment()
    assert win.segment_list.currentRow() == -1
    assert not any(c.is_selected() for c in win.segment_list.cards())
    assert (win.range_slider.low(), win.range_slider.high()) == (5, 20)


def test_slider_after_add_does_not_touch_existing_cards(win):
    win.range_slider.setValues(5, 20)
    win.add_segment()
    win.range_slider.setValues(30, 50)
    win.range_slider.setLow(35)
    win.start_edit.setText("0:36")
    win.start_edit.editingFinished.emit()
    assert win.segments() == [(5.0, 20.0)]
    assert "00:05.000" in win.segment_list.card(0).range_label.text()


def test_second_add_creates_a_second_card_and_keeps_the_first(win):
    add(win, 5, 20)
    add(win, 30, 50)
    assert win.segments() == [(5.0, 20.0), (30.0, 50.0)]
    assert win.segment_list.count() == 2
    assert [c.index_label.text() for c in win.segment_list.cards()] == ["#1", "#2"]


def test_add_twice_with_the_same_range_is_allowed_but_is_the_users_choice(win):
    add(win, 5, 20)
    win.add_segment()                                   # explicit second press
    assert win.segments() == [(5.0, 20.0), (5.0, 20.0)]


def test_add_announces_segment_number(win):
    created = []
    win.segmentCreated.connect(created.append)
    add(win, 5, 20)
    assert win.progress_bar.text() == i18n.tr("en", "segment_created", n=1)
    assert win.progress_bar.text() == "Segment #1 created"
    add(win, 30, 40)
    assert created == [1, 2]
    assert win.progress_bar.text() == "Segment #2 created"


def test_add_of_an_empty_range_is_refused(win):
    created = []
    win.segmentCreated.connect(created.append)
    win.range_slider.setValues(10, 10)
    win.add_segment()
    assert win.segments() == [] and created == []
    assert win.progress_bar.text() == i18n.tr("en", "empty_segment")


def test_add_button_enabled_only_with_a_loaded_video(app, fake):
    from video_trimmer.ui.main_window import MainWindow
    w = MainWindow()
    assert not w.add_button.isEnabled()
    w.close()


# ---------------------------------------------------------------- editing mode

def test_click_on_a_card_selects_it_and_loads_its_range(win):
    three(win)
    win.range_slider.setValues(1, 2)                    # some other draft
    QTest.mouseClick(win.segment_list.card(1), Qt.LeftButton)
    assert win.segment_list.currentRow() == 1
    assert win.segment_list.card(1).is_selected() and not win.segment_list.card(0).is_selected()
    assert (win.range_slider.low(), win.range_slider.high()) == (20, 25)
    assert win.start_edit.text() == "00:20.000" and win.end_edit.text() == "00:25.000"


def test_editing_note_is_visible_only_in_edit_mode(win):
    three(win)
    assert win.edit_note.text() == ""
    win.segment_list.setCurrentRow(1)
    assert win.edit_note.text() == "Editing segment #2"
    assert win.edit_note.text() == i18n.tr("en", "editing_segment", n=2)
    win.segment_list.setCurrentRow(2)
    assert win.edit_note.text() == "Editing segment #3"
    win.segment_list.setCurrentRow(-1)
    assert win.edit_note.text() == ""


def test_editing_note_is_localised(win):
    three(win)
    win.segment_list.setCurrentRow(0)
    win.set_language("ru")
    assert win.edit_note.text() == i18n.tr("ru", "editing_segment", n=1)
    win.set_language("uk")
    assert win.edit_note.text() == i18n.tr("uk", "editing_segment", n=1)
    assert i18n.tr("ru", "editing_segment", n=1) != i18n.tr("uk", "editing_segment", n=1)


def test_slider_edits_only_the_selected_card(win):
    three(win)
    win.segment_list.setCurrentRow(1)
    win.range_slider.setValues(21, 26)
    assert win.segments() == [(5, 10), (21, 26), (40, 55)]
    assert "00:21.000" in win.segment_list.card(1).range_label.text()
    win.start_edit.setText("0:22")
    win.start_edit.editingFinished.emit()
    assert win.segments() == [(5, 10), (22, 26), (40, 55)]
    assert win.start_edit.text() == "00:22.000"


def test_second_click_on_the_selected_card_returns_to_draft_mode(win):
    three(win)
    QTest.mouseClick(win.segment_list.card(1), Qt.LeftButton)
    assert win.segment_list.currentRow() == 1
    QTest.mouseClick(win.segment_list.card(1), Qt.LeftButton)
    assert win.segment_list.currentRow() == -1
    assert not win.segment_list.card(1).is_selected()
    assert (win.range_slider.low(), win.range_slider.high()) == (20, 25)   # stays where it was
    assert win.edit_note.text() == ""
    win.range_slider.setValues(30, 31)                  # now a draft again
    assert win.segments() == [(5, 10), (20, 25), (40, 55)]


def test_esc_returns_to_draft_mode(win):
    three(win)
    win.segment_list.setCurrentRow(2)
    QTest.keyClick(win, Qt.Key_Escape)
    assert win.segment_list.currentRow() == -1
    assert (win.range_slider.low(), win.range_slider.high()) == (40, 55)
    win.range_slider.setValues(1, 2)
    assert win.segments() == [(5, 10), (20, 25), (40, 55)]


def test_esc_works_with_the_focus_on_a_card_and_on_a_button(win):
    three(win)
    win.show()
    win.segment_list.setCurrentRow(0)
    QTest.keyClick(win.segment_list.card(0), Qt.Key_Escape)
    assert win.segment_list.currentRow() == -1
    win.segment_list.setCurrentRow(0)
    QTest.keyClick(win.add_button, Qt.Key_Escape)
    assert win.segment_list.currentRow() == -1


def test_esc_in_draft_mode_does_nothing(win):
    three(win)
    QTest.keyClick(win, Qt.Key_Escape)
    assert win.segments() == [(5, 10), (20, 25), (40, 55)] and win.segment_list.currentRow() == -1


def test_add_in_edit_mode_creates_a_new_card_and_leaves_edit_mode(win):
    three(win)
    win.segment_list.setCurrentRow(0)
    win.add_segment()
    assert win.segments() == [(5, 10), (20, 25), (40, 55), (5, 10)]
    assert win.segment_list.currentRow() == -1
    win.range_slider.setValues(7, 8)
    assert win.segments()[0] == (5, 10)


def test_dragging_a_selected_card_keeps_it_selected(win):
    three(win)
    win.show()
    win.segment_list.setCurrentRow(0)
    card = win.segment_list.card(0)
    start = QPoint(card.width() // 2, card.height() // 2)
    QTest.mousePress(card, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(card, start + QPoint(30, 0))
    QTest.mouseRelease(card, Qt.LeftButton, Qt.NoModifier, start + QPoint(30, 0))
    assert win.segment_list.currentRow() in (0, 1)        # a (possibly no-op) move, still selected


def test_selecting_a_card_previews_its_start(win, preview_calls):
    three(win)
    preview_calls.clear()
    win.segment_list.setCurrentRow(1)
    assert preview_calls[-1][0] == 20000


def test_edit_note_does_not_change_the_geometry(win):
    win.resize(1366, 768)
    win.show()
    three(win)
    QTest.qWait(50)
    widgets = [win.range_box, win.segments_box, win.video_panel, win.transport_box,
               win.range_slider, win.start_edit, win.end_edit, win.set_start_button,
               win.set_end_button, win.add_button, win.clear_button, win.save_button,
               win.segment_list]

    def snapshot():
        return [(w.mapTo(win, w.rect().topLeft()), w.size()) for w in widgets]

    before = snapshot()
    win.segment_list.setCurrentRow(1)
    QTest.qWait(50)
    assert win.edit_note.text()
    assert snapshot() == before
    for lang in ("ru", "uk"):
        win.set_language(lang)
        QTest.qWait(20)
        win.segment_list.setCurrentRow(-1)
        base = snapshot()
        win.segment_list.setCurrentRow(2)
        assert snapshot() == base


# ---------------------------------------------------------------- cross

@pytest.mark.parametrize("row", [0, 1, 2])
def test_cross_deletes_any_card(win, row):
    three(win)
    before = win.segments()
    assert all(c.delete_button.isEnabled() for c in win.segment_list.cards())
    QTest.mouseClick(win.segment_list.card(row).delete_button, Qt.LeftButton)
    assert win.segments() == before[:row] + before[row + 1:]
    assert win.segment_list.count() == 2
    assert [c.index_label.text() for c in win.segment_list.cards()] == ["#1", "#2"]


def test_cross_works_on_the_only_card_and_leaves_an_empty_list(win):
    add(win, 5, 10)
    assert win.segment_list.card(0).delete_button.isEnabled()
    win.segment_list.card(0).delete_button.click()
    assert win.segments() == [] and win.segment_list.count() == 0
    assert not win.save_button.isEnabled()


def test_deleting_the_selected_card_leaves_edit_mode_and_keeps_the_slider(win):
    three(win)
    win.segment_list.setCurrentRow(1)
    win.segment_list.card(1).delete_button.click()
    assert win.segment_list.currentRow() == -1 and win.edit_note.text() == ""
    assert (win.range_slider.low(), win.range_slider.high()) == (20, 25)
    win.range_slider.setValues(1, 2)
    assert win.segments() == [(5, 10), (40, 55)]


def test_deleting_another_card_keeps_the_selection_on_the_same_card(win):
    three(win)
    win.segment_list.setCurrentRow(2)
    win.segment_list.card(0).delete_button.click()
    assert win.segment_list.currentRow() == 1
    assert win.edit_note.text() == i18n.tr("en", "editing_segment", n=2)
    win.range_slider.setValues(41, 56)
    assert win.segments() == [(20, 25), (41, 56)]
    win.segment_list.card(1).delete_button.click()     # the selected one is the last: row stays valid
    assert win.segment_list.currentRow() == -1


# ---------------------------------------------------------------- Clear all

def test_clear_all_with_several_cards_asks_and_empties(win, monkeypatch):
    three(win)
    asked = []
    monkeypatch.setattr(win, "_confirm_clear", lambda: asked.append(1) or True)
    win.segment_list.setCurrentRow(1)
    win.clear_button.click()
    assert asked == [1]
    assert win.segments() == [] and win.segment_list.count() == 0
    assert win.segment_list.currentRow() == -1
    assert (win.range_slider.low(), win.range_slider.high()) == (0.0, 60.0)   # draft: whole file
    assert win.edit_note.text() == ""
    assert not win.save_button.isEnabled()


def test_clear_all_declined_keeps_everything(win, monkeypatch):
    three(win)
    monkeypatch.setattr(win, "_confirm_clear", lambda: False)
    win.range_slider.setValues(1, 2)
    win.clear_button.click()
    assert win.segment_list.count() == 3
    assert (win.range_slider.low(), win.range_slider.high()) == (1, 2)


def test_clear_all_with_one_card_needs_no_confirmation(win, monkeypatch):
    add(win, 5, 10)
    monkeypatch.setattr(win, "_confirm_clear",
                        lambda: (_ for _ in ()).throw(AssertionError("must not ask")))
    win.clear_button.click()
    assert win.segments() == []


def test_clear_all_with_no_cards_resets_the_draft(win, monkeypatch):
    monkeypatch.setattr(win, "_confirm_clear",
                        lambda: (_ for _ in ()).throw(AssertionError("must not ask")))
    win.range_slider.setValues(5, 6)
    win.clear_button.click()
    assert (win.range_slider.low(), win.range_slider.high()) == (0.0, 60.0)


# ---------------------------------------------------------------- Save

def test_save_is_disabled_without_cards_and_explains_why(win):
    assert not win.save_button.isEnabled()
    assert win.save_button.toolTip() == i18n.tr("en", "save_disabled_tip")
    for lang in ("ru", "uk"):
        win.set_language(lang)
        assert win.save_button.toolTip() == i18n.tr(lang, "save_disabled_tip")
    win.set_language("en")
    add(win, 5, 10)
    assert win.save_button.isEnabled()
    assert win.save_button.toolTip() == ""
    win.segment_list.card(0).delete_button.click()
    assert not win.save_button.isEnabled()


def test_save_without_cards_does_nothing(win, fake):
    win.save()
    assert fake.calls == [] and win.asked == [] and not win.is_busy()


def test_save_passes_the_card_ranges_in_order(win, fake):
    three(win)
    win.save()
    assert wait_for(lambda: fake.calls and not win.is_busy())
    assert fake.calls[0][1] == [(5.0, 10.0), (20.0, 25.0), (40.0, 55.0)]


def test_save_uses_edited_values_and_not_the_draft(win, fake):
    three(win)
    win.segment_list.setCurrentRow(1)
    win.range_slider.setValues(22, 27)
    win.segment_list.setCurrentRow(-1)
    win.range_slider.setValues(1, 59)                    # draft only
    win.save()
    assert wait_for(lambda: fake.calls and not win.is_busy())
    assert fake.calls[0][1] == [(5.0, 10.0), (22.0, 27.0), (40.0, 55.0)]


def test_save_after_reordering_uses_card_order(win, fake):
    three(win)
    win.segment_list.setCurrentRow(2)
    win.move_selected(-2)
    win.save()
    assert wait_for(lambda: fake.calls and not win.is_busy())
    assert fake.calls[0][1] == [(40.0, 55.0), (5.0, 10.0), (20.0, 25.0)]


# ---------------------------------------------------------------- i18n

def test_new_texts_exist_in_all_languages():
    keys = ["segment_created", "editing_segment", "save_disabled_tip", "exit_fullscreen",
            "empty_segment", "segments_empty", "fullscreen_tip"]
    for k in keys:
        texts = [i18n.tr(lang, k, n=7) for lang in ("en", "ru", "uk")]
        assert all(texts), k
    for lang in ("en", "ru", "uk"):
        assert "7" in i18n.tr(lang, "segment_created", n=7)
        assert "7" in i18n.tr(lang, "editing_segment", n=7)
    assert i18n.tr("ru", "segment_created", n=3) == "Фрагмент №3 создан"
    assert i18n.tr("ru", "editing_segment", n=3) == "Правка фрагмента №3"
    assert i18n.tr("en", "exit_fullscreen") == "Exit full screen"
