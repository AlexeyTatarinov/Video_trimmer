"""v0.2.4: rounded video frame (A), export from the full-screen header (B), auto-close (C)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtWidgets import QAbstractButton, QApplication, QCheckBox

from video_trimmer import core, i18n
from video_trimmer.ui import fullscreen, preview, theme, widgets
from video_trimmer.ui.fullscreen import FullscreenWindow
from video_trimmer.ui.main_window import MainWindow

from test_ui import app, fake, isolated_settings, win as _win, wait_for  # noqa: F401
from test_ui_fullscreen import click, pump, reveal_header, quick_timings  # noqa: F401

LANGS = ["en", "ru", "uk"]
needs_mm = pytest.mark.skipif(not preview.MULTIMEDIA_AVAILABLE, reason="QtMultimedia not installed")


@pytest.fixture
def win(_win, monkeypatch):
    monkeypatch.setattr(MainWindow, "AUTO_CLOSE_MS", 60)
    _win.show()
    QApplication.processEvents()
    return _win


@pytest.fixture
def fs(win):
    win.enter_fullscreen()
    f = win.fullscreen_window()
    QApplication.processEvents()
    return f


# ------------------------------------------------------------------ A. rounded video
def _corner_inset(mask, y):
    """x of the first masked-in pixel in row ``y``."""
    for x in range(mask.boundingRect().width()):
        if mask.contains(QPoint(x, y)):
            return x
    return None


@needs_mm
def test_video_radius_equals_panel_radius():
    assert widgets.PANEL_RADIUS == 22.0
    assert preview.ResponsiveVideoWidget.CORNER_RADIUS == widgets.PANEL_RADIUS


@needs_mm
@pytest.mark.parametrize("size", [(1120, 820), (1366, 768), (1000, 640)])
@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_video_area_is_clipped_to_rounded_corners(win, size, theme_name):
    win.resize(*size)
    win.set_theme(theme_name)
    pump(40)
    v = win.video_widget
    m = v.mask()
    assert not m.isEmpty()
    assert m.boundingRect() == QRect(0, 0, v.width(), v.height())     # follows the current size
    w, h = v.width(), v.height()
    r = int(widgets.PANEL_RADIUS)
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        assert not m.contains(QPoint(*corner))                        # no square corner left
    for inner in ((r, r), (w - 1 - r, r), (r, h - 1 - r), (w - 1 - r, h - 1 - r),
                  (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)):
        assert m.contains(QPoint(*inner))
    # the curve really is a circle of the panel radius: row 0 starts about r - sqrt(r^2-(r-.5)^2)
    x0 = _corner_inset(m, 0)
    assert r - 8 <= x0 <= r - 3, x0
    assert _corner_inset(m, r // 2) < x0                               # widening towards the middle


@needs_mm
def test_mask_survives_resize_and_theme_change(win):
    before = win.video_widget.size()
    win.resize(1000, 640)
    pump(40)
    assert win.video_widget.size() != before
    win.set_theme("dark")
    win.set_theme("light")
    assert win.video_widget.mask().boundingRect().size() == win.video_widget.size()
    assert not win.video_widget.mask().contains(QPoint(0, 0))


@needs_mm
def test_fullscreen_stays_unrounded(win, fs):
    assert fs.mask().isEmpty()                      # edge-to-edge, no clipping of the window


# ------------------------------------------------------------------ B. export in the header
def _add_card(win):
    win.range_slider.setValues(5, 10)
    win.add_segment()


@needs_mm
def test_header_has_export_next_to_a_still_centred_cross(win, fs):
    _add_card(win)
    reveal_header(fs)
    assert isinstance(fs.export_button, QAbstractButton) and fs.export_button.parent() is fs.header
    assert set(fs.header.findChildren(QAbstractButton)) == {fs.exit_button, fs.export_button}
    centre = fs.exit_button.mapTo(fs, fs.exit_button.rect().center())
    assert abs(centre.x() - fs.width() / 2) <= 1                       # cross stays centred
    ex = QRect(fs.export_button.mapTo(fs, QPoint(0, 0)), fs.export_button.size())
    cross = QRect(fs.exit_button.mapTo(fs, QPoint(0, 0)), fs.exit_button.size())
    assert ex.left() > cross.right() and not ex.intersects(cross)      # next to the cross
    assert fs.rect().contains(ex)
    assert fs.export_button.text() == i18n.tr("en", "export")
    click(fs.exit_button)                                              # the cross only leaves
    assert not win.is_fullscreen() and win.isVisible()
    assert not win.is_busy()


@needs_mm
def test_export_in_fullscreen_uses_the_same_path_as_save(win, fs, fake):
    win.range_slider.setValues(20, 30)
    win.add_segment()
    win.range_slider.setValues(5, 10)
    win.add_segment()
    win.precise_radio.setChecked(True)
    reveal_header(fs)
    assert fs.export_button.isEnabled()
    click(fs.export_button)
    assert wait_for(lambda: not win.is_busy() and fake.calls)
    src, ranges, out_dir, mode = fake.calls[0]
    assert ranges == [(20.0, 30.0), (5.0, 10.0)] and mode == "precise"
    assert out_dir == win.out_dir and src == win.src_path
    assert win.asked and win.asked[0] == str(core.Path(win.src_path).parent)
    assert win.is_fullscreen() and win.isVisible()                    # still full screen, alive
    assert not any(k == "info" for k, _ in win.notes)                 # no modal over full screen


@needs_mm
def test_export_disabled_without_cards_and_while_busy(win, fs, fake):
    reveal_header(fs)
    assert not fs.export_button.isEnabled()
    assert fs.export_button.toolTip() == i18n.tr("en", "save_disabled_tip")
    _add_card(win)
    assert fs.export_button.isEnabled() and fs.export_button.toolTip() == ""
    win._busy = True
    win._update_enabled()
    assert not fs.export_button.isEnabled()
    win._busy = False
    win._update_enabled()
    assert fs.export_button.isEnabled()
    n = len(fake.calls)
    win.remove_segment_at(0)
    assert not fs.export_button.isEnabled()
    fs.export_button.click()
    pump(60)
    assert len(fake.calls) == n


@needs_mm
@pytest.mark.parametrize("lang", LANGS)
def test_export_texts_are_translated(win, fs, lang):
    win.set_language(lang)
    assert fs.export_button.text() == i18n.tr(lang, "export")
    assert i18n.tr(lang, "export") != "" and i18n.tr(lang, "exporting", percent=5) != ""


@needs_mm
def test_progress_and_result_toast_in_fullscreen(win, fs, fake, monkeypatch):
    monkeypatch.setattr(FullscreenWindow, "TOAST_MS", 2000)
    fake.progress_values = [0.25]
    _add_card(win)
    seen = []
    orig = FullscreenWindow.show_toast
    monkeypatch.setattr(FullscreenWindow, "show_toast",
                        lambda self, text, **k: (seen.append(text), orig(self, text, **k))[1])
    win.save()
    assert wait_for(lambda: not win.is_busy() and fake.calls)
    pump(40)
    assert i18n.tr("en", "exporting", percent=25) in seen
    assert seen[-1] == i18n.tr("en", "saved", count=1, folder=win.out_dir)
    assert fs.toast.isVisible()


@needs_mm
def test_error_in_fullscreen_is_shown_not_swallowed(win, fs, fake):
    fake.error = "disk full"
    _add_card(win)
    win.save()
    assert wait_for(lambda: not win.is_busy() and fs.toast.isVisible() and "disk full" in fs.toast.text())
    assert "disk full" in win.progress_bar.text()
    assert win.isVisible()


@needs_mm
def test_panels_stay_while_exporting(win, fs, fake, monkeypatch):
    _add_card(win)
    reveal_header(fs)
    win._busy = True                         # an export is running
    win._update_enabled()
    fs.set_export_active(True)
    pump(400)                                # many hide delays (120 ms in tests)
    assert fs.header_visible() and fs.header.isVisible()
    fs.set_export_active(False)
    win._busy = False
    win._update_enabled()
    assert wait_for(lambda: not fs.header_visible(), 3)


@needs_mm
def test_pointer_over_export_button_keeps_header_open(win, fs):
    _add_card(win)
    reveal_header(fs)
    p = fs.export_button.mapTo(fs, fs.export_button.rect().center())
    fs.handle_mouse_moved(p)
    pump(400)
    assert fs.header_visible()


# ------------------------------------------------------------------ C. auto-close setting
def test_checkbox_default_off_and_in_popup(win):
    cb = win.settings_popup.auto_close_check
    assert isinstance(cb, QCheckBox) and not cb.isChecked()
    assert win.auto_close_enabled() is False


def test_checkbox_persists(win, isolated_settings):
    win.settings_popup.auto_close_check.click()
    assert win.auto_close_enabled() is True
    assert QSettings(isolated_settings, QSettings.IniFormat).value("auto_close_after_export") in (True, "true")
    w2 = MainWindow()
    assert w2.auto_close_enabled() is True and w2.settings_popup.auto_close_check.isChecked()
    w2.settings_popup.auto_close_check.click()
    w3 = MainWindow()
    assert w3.auto_close_enabled() is False and not w3.settings_popup.auto_close_check.isChecked()


@pytest.mark.parametrize("lang", LANGS)
def test_checkbox_text_translated(win, lang):
    win.set_language(lang)
    assert win.settings_popup.auto_close_check.text() == i18n.tr(lang, "auto_close_after_export")


def test_i18n_keys_identical():
    keys = [set(i18n.STRINGS[l]) for l in LANGS]
    assert keys[0] == keys[1] == keys[2]
    assert i18n.tr("en", "auto_close_after_export") == "Close the program automatically after export"


def test_popup_size_independent_of_language(win):
    sizes = set()
    for lang in LANGS:
        win.set_language(lang)
        win.settings_popup.ensurePolished()
        win.settings_popup.layout().activate()
        s = win.settings_popup.sizeHint()
        sizes.add((s.width(), s.height()))
    assert len(sizes) == 1


class CloseSpy:
    def __init__(self, win):
        self.n = 0
        orig = win.close

        def close():
            self.n += 1
            return orig()
        win.close = close


def test_auto_close_off_never_closes(win, fake):
    spy = CloseSpy(win)
    _add_card(win)
    win.save()
    assert wait_for(lambda: not win.is_busy() and fake.calls)
    pump(300)
    assert spy.n == 0 and win.isVisible()
    assert win.notes and win.notes[-1][0] == "info"                   # modal result as before


def test_auto_close_on_closes_after_full_success(win, fake):
    win.settings_popup.auto_close_check.click()
    spy = CloseSpy(win)
    _add_card(win)
    win.range_slider.setValues(12, 14)
    win.add_segment()
    win.save()
    assert wait_for(lambda: not win.is_busy() and fake.calls)
    assert win.isVisible()                                            # message first, not instantly
    assert i18n.tr("en", "saved", count=2, folder=win.out_dir) in win.progress_bar.text()
    assert wait_for(lambda: not win.isVisible(), 3)
    assert spy.n == 1
    assert not win.notes                                              # no blocking dialog
    assert win._thread is None or not win._thread.isRunning()


def test_auto_close_on_never_closes_on_error(win, fake):
    win.settings_popup.auto_close_check.click()
    spy = CloseSpy(win)
    fake.error = "boom"
    _add_card(win)
    win.save()
    assert wait_for(lambda: not win.is_busy() and win.notes)
    pump(300)
    assert spy.n == 0 and win.isVisible() and win.notes[-1][0] == "error"


def test_auto_close_cancelled_when_untoggled_or_new_work_starts(win, fake, monkeypatch):
    monkeypatch.setattr(MainWindow, "AUTO_CLOSE_MS", 200)
    win.settings_popup.auto_close_check.click()
    spy = CloseSpy(win)
    _add_card(win)
    win.save()
    assert wait_for(lambda: not win.is_busy() and fake.calls)
    win.settings_popup.auto_close_check.click()                       # switched off in time
    pump(400)
    assert spy.n == 0 and win.isVisible()


def test_cancelled_folder_dialog_does_not_close(win, fake, monkeypatch):
    win.settings_popup.auto_close_check.click()
    spy = CloseSpy(win)
    monkeypatch.setattr(win, "_ask_save_dir", lambda d: "")
    _add_card(win)
    win.save()
    pump(300)
    assert spy.n == 0 and win.isVisible()


@needs_mm
def test_auto_close_from_fullscreen(win, fs, fake):
    win.settings_popup.auto_close_check.click()
    _add_card(win)
    reveal_header(fs)
    click(fs.export_button)
    assert wait_for(lambda: fake.calls)
    assert wait_for(lambda: not win.isVisible(), 3)
    assert not win.is_fullscreen()
    assert not fs.isVisible()
