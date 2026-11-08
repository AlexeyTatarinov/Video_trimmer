"""Glass popups: settings (language + theme, opened by the gear) and the mode explanation."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel

from video_trimmer import i18n
from video_trimmer.ui.widgets import ElidedLabel, GlassButton, GlassCheckBox, GlassPopup

THEME_ORDER = ("light", "dark")


class SettingsPopup(GlassPopup):
    """Language selector and theme toggle. Its size does not depend on the language."""

    languageChosen = Signal(str)
    themeChosen = Signal(str)
    autoCloseChanged = Signal(bool)
    deleteSourceChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPopup")
        self.language_label = ElidedLabel()
        self.language_label.setObjectName("caption")
        self.language_label.set_measure_texts([t.upper() for t in i18n.all_texts("language")])
        self.theme_label = ElidedLabel()
        self.theme_label.setObjectName("caption")
        self.theme_label.set_measure_texts([t.upper() for t in i18n.all_texts("theme")])

        self.language_buttons: dict[str, GlassButton] = {}
        self.theme_buttons: dict[str, GlassButton] = {}
        lang_row, theme_row = QHBoxLayout(), QHBoxLayout()
        lang_row.setSpacing(6)
        theme_row.setSpacing(6)
        self._lang_group, self._theme_group = QButtonGroup(self), QButtonGroup(self)
        for code, name in i18n.LANGUAGES.items():
            b = GlassButton(name)
            b.set_texts([name])
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, code=code: self.languageChosen.emit(code))
            self._lang_group.addButton(b)
            lang_row.addWidget(b)
            self.language_buttons[code] = b
        for name in THEME_ORDER:
            b = GlassButton()
            b.set_texts(i18n.all_texts(f"theme_{name}"))
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, name=name: self.themeChosen.emit(name))
            self._theme_group.addButton(b)
            theme_row.addWidget(b)
            self.theme_buttons[name] = b
        theme_row.addStretch(1)
        self.body.addWidget(self.language_label)
        self.body.addLayout(lang_row)
        self.body.addSpacing(4)
        self.body.addWidget(self.theme_label)
        self.body.addLayout(theme_row)
        self.body.addSpacing(4)
        self.auto_close_check = GlassCheckBox()
        self.auto_close_check.toggled.connect(self.autoCloseChanged)
        self.body.addWidget(self.auto_close_check)
        self.delete_source_check = GlassCheckBox()
        self.delete_source_check.toggled.connect(self.deleteSourceChanged)
        self.body.addWidget(self.delete_source_check)

    def retranslate(self, lang: str) -> None:
        self.language_label.setText(i18n.tr(lang, "language").upper())
        self.theme_label.setText(i18n.tr(lang, "theme").upper())
        for name, b in self.theme_buttons.items():
            b.setText(i18n.tr(lang, f"theme_{name}"))
        self.auto_close_check.setText(i18n.tr(lang, "auto_close_after_export"))
        self.auto_close_check.update()
        self.delete_source_check.setText(i18n.tr(lang, "delete_source_after_export"))
        self.delete_source_check.update()

    def sync(self, language: str, theme_name: str, auto_close: bool | None = None,
             delete_source: bool | None = None) -> None:
        """Show the current choices (no signals)."""
        if auto_close is not None:
            self.auto_close_check.blockSignals(True)
            self.auto_close_check.setChecked(bool(auto_close))
            self.auto_close_check.blockSignals(False)
        if delete_source is not None:
            self.delete_source_check.blockSignals(True)
            self.delete_source_check.setChecked(bool(delete_source))
            self.delete_source_check.blockSignals(False)
        for code, b in self.language_buttons.items():
            b.setChecked(code == language)
        for name, b in self.theme_buttons.items():
            b.setChecked(name == theme_name)


class ModeInfoPopup(GlassPopup):
    """Explains the two save modes in simple words."""

    WIDTH = 420

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("modeInfoPopup")
        self.setFixedWidth(self.WIDTH)
        self._labels: list[QLabel] = []
        for _ in range(2):
            lab = QLabel()
            lab.setObjectName("popupText")
            lab.setWordWrap(True)
            lab.setTextFormat(Qt.PlainText)
            self.body.addWidget(lab)
            self._labels.append(lab)

    def set_language(self, lang: str) -> None:
        for lab, mode in zip(self._labels, ("fast", "precise")):
            lab.setText(f"{i18n.tr(lang, 'mode_' + mode)}: {i18n.tr(lang, 'mode_' + mode + '_tip')}")
        self.fit()

    def fit(self) -> None:
        """Make the popup exactly as tall as its wrapped texts (call after the style is applied)."""
        self.ensurePolished()
        m = self.body.contentsMargins()
        inner = self.WIDTH - m.left() - m.right()
        for lab in self._labels:
            lab.ensurePolished()
        heights = [lab.heightForWidth(inner) for lab in self._labels]
        self.setFixedHeight(m.top() + m.bottom() + sum(heights) + self.body.spacing() * (len(heights) - 1))

    def text(self) -> str:
        return "\n\n".join(lab.text() for lab in self._labels)
