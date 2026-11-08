"""v0.3.0 (APP): delete the source video (to the Recycle Bin) after a fully successful export,
and opening a video passed on the command line."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QCheckBox

from video_trimmer import core, i18n, trash
from video_trimmer.ui import preview, theme
from video_trimmer.ui.main_window import MainWindow

from test_ui import app, fake, win as _win, wait_for  # noqa: F401
from test_ui_fullscreen import click, pump, reveal_header, quick_timings  # noqa: F401

LANGS = ["en", "ru", "uk"]
needs_mm = pytest.mark.skipif(not preview.MULTIMEDIA_AVAILABLE, reason="QtMultimedia not installed")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Like test_ui's, but WITHOUT seeding the delete setting: the real default (ON) is tested."""
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(theme, "make_settings", lambda: QSettings(path, QSettings.IniFormat))
    theme.set_current("light")
    yield path
    theme.set_current("light")


@pytest.fixture
def trashed(monkeypatch):
    """Replace the one trash function: records calls, never touches the real Recycle Bin."""
    calls = []

    def fake_trash(path):
        calls.append(str(path))
    monkeypatch.setattr(trash, "move_to_trash", fake_trash)
    fake_trash.calls = calls
    return calls


@pytest.fixture
def win(_win, monkeypatch, trashed):
    monkeypatch.setattr(MainWindow, "AUTO_CLOSE_MS", 60)
    # these tests are about the DEFAULT (ON): the shared fixture's window was built with the
    # test ini, which has no stored value
    _win.show()
    QApplication.processEvents()
    return _win


def _add_card(win):
    win.range_slider.setValues(5, 10)
    win.add_segment()


def _save_and_wait(win, fake):
    win.save()
    assert win.is_busy()
    assert wait_for(lambda: not win.is_busy())
    QApplication.processEvents()


# ------------------------------------------------------------------ setting
def test_default_on_and_in_popup(win):
    cb = win.settings_popup.delete_source_check
    assert isinstance(cb, QCheckBox) and cb.isChecked()
    assert win.delete_source_enabled() is True


def test_persists_both_ways(win, isolated_settings):
    win.settings_popup.delete_source_check.click()
    assert win.delete_source_enabled() is False
    assert QSettings(isolated_settings, QSettings.IniFormat).value("delete_source_after_export") in (False, "false")
    w2 = MainWindow()
    assert w2.delete_source_enabled() is False and not w2.settings_popup.delete_source_check.isChecked()
    w2.settings_popup.delete_source_check.click()
    w3 = MainWindow()
    assert w3.delete_source_enabled() is True and w3.settings_popup.delete_source_check.isChecked()


@pytest.mark.parametrize("lang", LANGS)
def test_text_translated(win, lang):
    win.set_language(lang)
    assert win.settings_popup.delete_source_check.text() == i18n.tr(lang, "delete_source_after_export")
    assert "Recycle" in i18n.tr("en", "delete_source_after_export")


def test_i18n_keys_identical_and_placeholders_match():
    keys = [set(i18n.STRINGS[l]) for l in LANGS]
    assert keys[0] == keys[1] == keys[2]
    for k in ("saved_trashed", "trash_failed", "file_not_found", "delete_source_after_export"):
        assert k in keys[0]
    for lang in LANGS:
        assert "{count}" in i18n.STRINGS[lang]["saved_trashed"] and "{folder}" in i18n.STRINGS[lang]["saved_trashed"]
        assert "{error}" in i18n.STRINGS[lang]["trash_failed"]
        assert "{path}" in i18n.STRINGS[lang]["file_not_found"]


def test_popup_size_independent_of_language_with_both_checkboxes(win):
    sizes = set()
    for lang in LANGS:
        win.set_language(lang)
        win.settings_popup.ensurePolished()
        win.settings_popup.layout().activate()
        s = win.settings_popup.sizeHint()
        sizes.add((s.width(), s.height()))
    assert len(sizes) == 1


def test_rows_fit_checkbox_text_in_two_lines(win):
    from PySide6.QtGui import QFontMetrics
    cb = win.settings_popup.delete_source_check
    fm = QFontMetrics(cb.font())
    avail = cb.width() - cb.BOX - cb.GAP
    for lang in LANGS:
        r = fm.boundingRect(0, 0, avail, 10000, 0x1000 | 0x0001, i18n.tr(lang, "delete_source_after_export"))
        assert r.height() <= cb.LINES * fm.lineSpacing() + 2, lang


# ------------------------------------------------------------------ deletion
def test_success_moves_source_to_trash_and_returns_to_no_video(win, fake, trashed):
    _add_card(win)
    src = win.src_path
    _save_and_wait(win, fake)
    assert trashed == [src]
    assert not win.has_video() and win._src is None
    assert win.segments() == []
    assert not win.save_button.isEnabled()
    assert i18n.tr("en", "saved_trashed", count=1, folder=win.out_dir) in win.progress_bar.text()
    assert win.notes and win.notes[-1][0] == "info"
    assert "Recycle Bin" in win.notes[-1][1]


def test_status_is_retranslated_after_deletion(win, fake, trashed):
    _add_card(win)
    _save_and_wait(win, fake)
    win.set_language("ru")
    assert i18n.tr("ru", "saved_trashed", count=1, folder=win.out_dir) == win.progress_bar.text()


def test_off_never_deletes(win, fake, trashed):
    win.settings_popup.delete_source_check.click()
    _add_card(win)
    _save_and_wait(win, fake)
    assert trashed == []
    assert win.has_video()
    assert i18n.tr("en", "saved", count=1, folder=win.out_dir) in win.progress_bar.text()


def test_error_never_deletes(win, fake, trashed):
    fake.error = "boom"
    _add_card(win)
    win.save()
    assert wait_for(lambda: not win.is_busy() and win.notes)
    assert trashed == [] and win.has_video()


def test_partial_export_never_deletes(win, fake, trashed, monkeypatch):
    _add_card(win)
    win.range_slider.setValues(12, 14)
    win.add_segment()
    orig = fake.trim_each
    monkeypatch.setattr(core, "trim_each", lambda *a, **k: orig(*a, **k)[:1])    # 1 of 2 files
    _save_and_wait(win, fake)
    assert trashed == [] and win.has_video()


def test_cancelled_folder_dialog_never_deletes(win, fake, trashed, monkeypatch):
    monkeypatch.setattr(win, "_ask_save_dir", lambda d: "")
    _add_card(win)
    win.save()
    pump(200)
    assert trashed == [] and win.has_video()


def test_never_deletes_a_file_that_is_an_output(win, fake, trashed, monkeypatch):
    _add_card(win)
    src = win.src_path
    monkeypatch.setattr(core, "trim_each", lambda s, r, d, m="fast", p=None: [core.Path(src)])
    _save_and_wait(win, fake)
    assert trashed == []
    assert win.has_video()


def test_output_check_uses_resolved_paths(win, fake, trashed, monkeypatch, tmp_path):
    _add_card(win)
    src = core.Path(win.src_path)
    alias = tmp_path / "sub" / ".." / src.name
    (tmp_path / "sub").mkdir()
    monkeypatch.setattr(core, "trim_each", lambda s, r, d, m="fast", p=None: [alias])
    _save_and_wait(win, fake)
    assert trashed == []


def test_player_released_before_moving(win, fake, monkeypatch):
    events = []
    monkeypatch.setattr(trash, "move_to_trash", lambda p: events.append("trash"))
    orig = win.player.release
    monkeypatch.setattr(win.player, "release", lambda: (events.append("release"), orig())[1])
    _add_card(win)
    _save_and_wait(win, fake)
    assert events == ["release", "trash"]


def test_release_clears_the_player_source(win):
    win.player.release()
    if win.player._player is not None:
        assert win.player._player.source().isEmpty()


def test_failure_gives_warning_keeps_video_and_export_counts(win, fake, monkeypatch):
    def boom(path):
        raise OSError("locked by another program")
    monkeypatch.setattr(trash, "move_to_trash", boom)
    reloaded = []
    monkeypatch.setattr(win.player, "set_source", lambda p: reloaded.append(p))   # the test file is no real video
    _add_card(win)
    _save_and_wait(win, fake)
    assert win.has_video()                                   # still loaded: nothing was lost
    assert reloaded == [win.src_path]                        # preview given back
    kinds = [k for k, _ in win.notes]
    assert "warning" in kinds
    warn = [t for k, t in win.notes if k == "warning"][0]
    assert "locked by another program" in warn
    assert warn == i18n.tr("en", "trash_failed", error="locked by another program")
    assert i18n.tr("en", "saved", count=1, folder=win.out_dir) in win.progress_bar.text()
    assert "error" not in kinds


def test_notify_warning_uses_warning_box(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: seen.append(a[2])))
    MainWindow()._notify("warning", "careful")
    assert seen == ["careful"]


# ------------------------------------------------------------------ auto-close ordering
def test_auto_close_deletes_then_closes(win, fake, monkeypatch):
    events = []
    monkeypatch.setattr(trash, "move_to_trash", lambda p: events.append("trash"))
    orig_close = win.close
    monkeypatch.setattr(win, "close", lambda: (events.append("close"), orig_close())[1])
    win.settings_popup.auto_close_check.click()
    _add_card(win)
    win.save()
    assert wait_for(lambda: not win.isVisible(), 3)
    assert events == ["trash", "close"]
    assert not win.notes


def test_auto_close_stays_open_when_delete_fails(win, fake, monkeypatch):
    monkeypatch.setattr(trash, "move_to_trash", lambda p: (_ for _ in ()).throw(OSError("nope")))
    win.settings_popup.auto_close_check.click()
    _add_card(win)
    win.save()
    assert wait_for(lambda: not win.is_busy() and fake.calls)
    pump(300)
    assert win.isVisible()                                   # the warning must not vanish
    assert any(k == "warning" for k, _ in win.notes)


def test_auto_close_without_delete_still_closes(win, fake, trashed):
    win.settings_popup.delete_source_check.click()
    win.settings_popup.auto_close_check.click()
    _add_card(win)
    win.save()
    assert wait_for(lambda: not win.isVisible(), 3)
    assert trashed == []


@needs_mm
def test_fullscreen_export_deletes_and_leaves_fullscreen(win, fake, trashed):
    win.enter_fullscreen()
    fs = win.fullscreen_window()
    _add_card(win)
    reveal_header(fs)
    click(fs.export_button)
    assert wait_for(lambda: fake.calls)
    assert wait_for(lambda: not win.is_busy())
    assert trashed == [win.src_path] or len(trashed) == 1
    assert not win.is_fullscreen() and not win.has_video()


# ------------------------------------------------------------------ command-line open
def test_startup_path_opens_video(win, fake, tmp_path):
    other = tmp_path / "other.mp4"
    other.write_bytes(b"x")
    win.open_startup_path(str(other))
    assert wait_for(lambda: win.has_video() and not win.is_busy())
    assert win._src == str(other)


def test_startup_path_missing_shows_clear_error_and_window_works(win, tmp_path):
    missing = tmp_path / "nope.mp4"
    win.open_startup_path(str(missing))
    assert win.notes[-1][0] == "error"
    assert win.notes[-1][1] == i18n.tr("en", "file_not_found", path=str(missing))
    assert str(missing) in win.notes[-1][1]
    assert win.isVisible()


def test_startup_path_directory_is_an_error(win, tmp_path):
    win.open_startup_path(str(tmp_path))
    assert win.notes[-1][0] == "error"


def test_startup_path_non_video_reports_probe_error(win, monkeypatch, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")

    def probe(path):
        raise core.TrimError("not a video: cannot read")
    monkeypatch.setattr(core, "probe", probe)
    win.open_startup_path(str(bad))
    assert wait_for(lambda: win.notes and win.notes[-1][0] == "error")
    assert "not a video" in win.notes[-1][1]
    assert win.isVisible()


def test_startup_path_with_spaces_and_unicode(win, tmp_path):
    odd = tmp_path / "мій відеоролик (1).mp4"
    odd.write_bytes(b"x")
    win.open_startup_path(str(odd))
    assert wait_for(lambda: win.has_video() and not win.is_busy())
    assert win._src == str(odd)
