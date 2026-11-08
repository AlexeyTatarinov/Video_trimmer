"""Liquid-glass themes: palettes, stylesheet generator and painting helpers.

Qt cannot blur what is behind a widget, so "glass" is emulated: gradient window
background with soft light blobs, translucent gradient panels with a light border and a
top sheen, glowing round slider handles, soft drop shadows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

ORGANIZATION = "VideoTrimmer"
APPLICATION = "VideoTrimmer"
DEFAULT_THEME = "light"
THEME_NAMES = ("light", "dark")


def C(r: int, g: int, b: int, a: int = 255) -> QColor:
    return QColor(r, g, b, a)


def css(color: QColor) -> str:
    """QColor -> ``rgba(r,g,b,a)`` usable in a Qt style sheet (alpha 0..255)."""
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


def with_alpha(color: QColor, alpha: float) -> QColor:
    """Copy of ``color`` whose alpha is multiplied by ``alpha`` (0..1)."""
    out = QColor(color)
    out.setAlpha(max(0, min(255, int(round(color.alpha() * alpha)))))
    return out


@dataclass(frozen=True)
class Theme:
    name: str
    bg_stops: tuple[QColor, QColor, QColor]
    blob_a: QColor
    blob_b: QColor
    panel_top: QColor
    panel_bottom: QColor
    panel_border: QColor
    sheen: QColor
    text: QColor
    text_dim: QColor
    accent: QColor
    accent2: QColor
    glow: QColor
    btn_top: QColor
    btn_bottom: QColor
    btn_border: QColor
    btn_hover_top: QColor
    btn_hover_bottom: QColor
    btn_pressed_top: QColor
    btn_pressed_bottom: QColor
    primary_top: QColor
    primary_bottom: QColor
    primary_text: QColor
    track: QColor
    track_border: QColor
    handle_top: QColor
    handle_bottom: QColor
    input_bg: QColor
    input_border: QColor
    selection: QColor
    shadow: QColor
    popup_bg: QColor
    video_bg: QColor


LIGHT = Theme(
    name="light",
    bg_stops=(C(0xDD, 0xE7, 0xEC), C(0xAB, 0xBE, 0xC8), C(0x7C, 0x95, 0xA3)),
    blob_a=C(255, 255, 255, 170),
    blob_b=C(96, 150, 190, 120),
    panel_top=C(255, 255, 255, 120),
    panel_bottom=C(255, 255, 255, 52),
    panel_border=C(255, 255, 255, 215),
    sheen=C(255, 255, 255, 120),
    text=C(0x16, 0x26, 0x32),
    text_dim=C(0x3B, 0x52, 0x62),
    accent=C(0x2F, 0x7F, 0xD0),
    accent2=C(0x7C, 0xC2, 0xF4),
    glow=C(70, 150, 230, 150),
    btn_top=C(255, 255, 255, 190),
    btn_bottom=C(255, 255, 255, 80),
    btn_border=C(255, 255, 255, 235),
    btn_hover_top=C(255, 255, 255, 235),
    btn_hover_bottom=C(255, 255, 255, 135),
    btn_pressed_top=C(190, 210, 222, 150),
    btn_pressed_bottom=C(255, 255, 255, 150),
    primary_top=C(0x8C, 0xCB, 0xF7),
    primary_bottom=C(0x2F, 0x7F, 0xD0),
    primary_text=C(255, 255, 255),
    track=C(20, 55, 80, 70),
    track_border=C(255, 255, 255, 150),
    handle_top=C(255, 255, 255),
    handle_bottom=C(0xD3, 0xE2, 0xEC),
    input_bg=C(255, 255, 255, 110),
    input_border=C(255, 255, 255, 220),
    selection=C(47, 127, 208, 85),
    shadow=C(20, 50, 75, 105),
    popup_bg=C(0xE6, 0xEE, 0xF2),
    video_bg=C(0x0E, 0x16, 0x20),
)

DARK = Theme(
    name="dark",
    bg_stops=(C(0x45, 0x1E, 0x72), C(0x2A, 0x12, 0x4D), C(0x14, 0x07, 0x2C)),
    blob_a=C(200, 90, 255, 110),
    blob_b=C(90, 70, 230, 110),
    panel_top=C(205, 130, 255, 70),
    panel_bottom=C(140, 60, 215, 34),
    panel_border=C(225, 175, 255, 140),
    sheen=C(255, 220, 255, 60),
    text=C(0xF6, 0xEC, 0xFF),
    text_dim=C(0xC9, 0xB3, 0xEA),
    accent=C(0xC1, 0x5B, 0xFF),
    accent2=C(0x8F, 0x6B, 0xFF),
    glow=C(205, 100, 255, 170),
    btn_top=C(225, 160, 255, 105),
    btn_bottom=C(130, 60, 215, 70),
    btn_border=C(235, 195, 255, 170),
    btn_hover_top=C(235, 185, 255, 150),
    btn_hover_bottom=C(160, 80, 235, 105),
    btn_pressed_top=C(70, 20, 120, 150),
    btn_pressed_bottom=C(150, 70, 230, 90),
    primary_top=C(0xE0, 0x7C, 0xFF),
    primary_bottom=C(0x7E, 0x4C, 0xF0),
    primary_text=C(255, 255, 255),
    track=C(15, 0, 40, 130),
    track_border=C(225, 175, 255, 80),
    handle_top=C(255, 235, 255),
    handle_bottom=C(0xD9, 0xB0, 0xF5),
    input_bg=C(30, 5, 70, 120),
    input_border=C(225, 175, 255, 120),
    selection=C(200, 100, 255, 100),
    shadow=C(4, 0, 18, 190),
    popup_bg=C(0x2D, 0x14, 0x52),
    video_bg=C(0x0B, 0x04, 0x16),
)

THEMES: dict[str, Theme] = {"light": LIGHT, "dark": DARK}

_current = LIGHT


def current() -> Theme:
    return _current


def set_current(name: str) -> Theme:
    global _current
    _current = THEMES.get(name, LIGHT)
    return _current


# --------------------------------------------------------------------------- settings
def make_settings():
    """The persistent settings store (tests monkeypatch this to a temporary file)."""
    from PySide6.QtCore import QSettings
    return QSettings(ORGANIZATION, APPLICATION)


def load_theme_name(settings) -> str:
    name = str(settings.value("theme", DEFAULT_THEME))
    return name if name in THEMES else DEFAULT_THEME


def save_theme_name(settings, name: str) -> None:
    settings.setValue("theme", name)
    settings.sync()


def load_language(settings, available, default: str) -> str:
    code = str(settings.value("language", default))
    return code if code in available else default


def save_language(settings, code: str) -> None:
    settings.setValue("language", code)
    settings.sync()


# --------------------------------------------------------------------------- stylesheet
def stylesheet(th: Theme) -> str:
    """Style sheet for the standard widgets (custom widgets paint themselves)."""
    return f"""
* {{ font-family: "Segoe UI", "SF Pro Text", "Noto Sans", "DejaVu Sans", sans-serif; font-size: 13px; }}
QLabel {{ color: {css(th.text)}; background: transparent; }}
QLabel#title {{ font-size: 21px; font-weight: 600; }}
QLabel#caption {{ color: {css(th.text_dim)}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#time {{ color: {css(th.text)}; font-size: 13px; font-weight: 600; }}
QLabel#status {{ color: {css(th.text_dim)}; }}
QLabel#popupText {{ color: {css(th.text)}; font-size: 13px; }}
QLineEdit {{
    color: {css(th.text)}; background: {css(th.input_bg)};
    border: 1px solid {css(th.input_border)}; border-radius: 15px;
    padding: 3px 8px; min-height: 22px; selection-background-color: {css(th.accent)};
    selection-color: white;
}}
QLineEdit:focus {{ border: 1px solid {css(th.accent)}; }}
QLineEdit:disabled {{ color: {css(th.text_dim)}; }}
QComboBox {{
    color: {css(th.text)}; background: {css(th.input_bg)};
    border: 1px solid {css(th.input_border)}; border-radius: 17px;
    padding: 6px 34px 6px 16px; min-height: 22px;
}}
QComboBox:hover {{ border: 1px solid {css(th.accent)}; }}
QComboBox::drop-down {{ border: none; width: 30px; }}
QComboBox QAbstractItemView {{
    color: {css(th.text)}; background: {css(th.popup_bg)};
    border: 1px solid {css(th.input_border)}; border-radius: 10px; padding: 4px;
    selection-background-color: {css(th.selection)}; selection-color: {css(th.text)}; outline: none;
}}
QScrollArea#segmentList, QScrollArea#segmentList > QWidget, QWidget#segmentInner {{ background: transparent; }}
QLabel#cardIndex {{ color: {css(th.accent)}; font-weight: 700; font-size: 14px; }}
QLabel#cardIndex[selected="true"] {{ color: {css(th.text)}; }}
QLabel#cardRange {{ font-weight: 600; }}
QLabel#cardDim {{ color: {css(th.text_dim)}; font-size: 12px; }}
QProgressBar {{
    background: {css(th.track)}; border: 1px solid {css(th.track_border)};
    border-radius: 7px; min-height: 14px; max-height: 14px; text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {css(th.accent2)}, stop:1 {css(th.accent)});
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {css(th.track_border)}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {css(th.track_border)}; border-radius: 4px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
QToolTip {{
    color: {css(th.text)}; background: {css(th.popup_bg)};
    border: 1px solid {css(th.input_border)}; border-radius: 6px; padding: 4px 8px;
}}
QMessageBox, QDialog {{ background: {css(th.popup_bg)}; }}
QMessageBox QPushButton {{
    color: {css(th.text)}; min-width: 84px; min-height: 22px; padding: 6px 16px;
    border-radius: 17px; border: 1px solid {css(th.btn_border)};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {css(th.btn_hover_top)}, stop:1 {css(th.btn_bottom)});
}}
QMessageBox QPushButton:hover {{ border: 1px solid {css(th.accent)}; }}
"""


# --------------------------------------------------------------------------- shadows
def add_shadow(widget: QWidget, blur: float = 36, dy: float = 10, strength: float = 1.0) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    effect.setColor(with_alpha(current().shadow, strength))
    effect.setProperty("vt_strength", strength)
    widget.setGraphicsEffect(effect)


def apply_theme(root: QWidget, name: str) -> Theme:
    """Make ``name`` current, restyle ``root`` and repaint / recolour every child."""
    th = set_current(name)
    root.setStyleSheet(stylesheet(th))
    for w in [root, *root.findChildren(QWidget)]:
        effect = w.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            strength = effect.property("vt_strength")
            effect.setColor(with_alpha(th.shadow, float(strength) if strength else 1.0))
        w.update()
    return th


# --------------------------------------------------------------------------- painting
def paint_background(p: QPainter, rect: QRectF, th: Theme) -> None:
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, th.bg_stops[0])
    g.setColorAt(0.5, th.bg_stops[1])
    g.setColorAt(1.0, th.bg_stops[2])
    p.fillRect(rect, g)
    for center, radius, color in (
        (QPointF(rect.width() * 0.12, rect.height() * 0.05), rect.width() * 0.55, th.blob_a),
        (QPointF(rect.width() * 0.95, rect.height() * 0.85), rect.width() * 0.6, th.blob_b),
    ):
        rg = QRadialGradient(center, radius)
        rg.setColorAt(0.0, color)
        rg.setColorAt(1.0, with_alpha(color, 0.0))
        p.fillRect(rect, rg)


def paint_glass(p: QPainter, rect: QRectF, th: Theme, radius: float = 22.0) -> None:
    """Frosted translucent panel: gradient fill, sheen, light border, top highlight."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    fill.setColorAt(0.0, th.panel_top)
    fill.setColorAt(1.0, th.panel_bottom)
    p.fillPath(path, fill)
    sheen = QRadialGradient(QPointF(rect.left() + rect.width() * 0.2, rect.top()), rect.width() * 0.75)
    sheen.setColorAt(0.0, th.sheen)
    sheen.setColorAt(1.0, with_alpha(th.sheen, 0.0))
    p.fillPath(path, sheen)
    # border: bright on the top-left, dimmer on the bottom-right
    border = QLinearGradient(rect.topLeft(), rect.bottomRight())
    border.setColorAt(0.0, th.panel_border)
    border.setColorAt(0.5, with_alpha(th.panel_border, 0.45))
    border.setColorAt(1.0, with_alpha(th.panel_border, 0.8))
    p.setPen(QPen(QBrush(border), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), radius, radius)
    # soft inner highlight just below the top edge
    inner = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + radius * 1.6))
    inner.setColorAt(0.0, with_alpha(th.panel_border, 0.55))
    inner.setColorAt(1.0, with_alpha(th.panel_border, 0.0))
    p.setPen(QPen(QBrush(inner), 1.0))
    p.drawRoundedRect(rect.adjusted(2.2, 2.2, -2.2, -2.2), radius - 2, radius - 2)
    p.restore()


def paint_groove(p: QPainter, x0: float, x1: float, cy: float, th: Theme, enabled: bool = True,
                 height: float = 6.0) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(x0, cy - height / 2, max(x1 - x0, 1.0), height)
    k = 1.0 if enabled else 0.5
    p.setBrush(with_alpha(th.track, k))
    p.setPen(QPen(with_alpha(th.track_border, k), 1.0))
    p.drawRoundedRect(rect, height / 2, height / 2)
    p.restore()


def paint_fill(p: QPainter, x0: float, x1: float, cy: float, th: Theme, enabled: bool = True,
               height: float = 6.0) -> None:
    if x1 <= x0:
        return
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    k = 1.0 if enabled else 0.4
    rect = QRectF(x0, cy - height / 2, x1 - x0, height)
    g = QLinearGradient(rect.topLeft(), rect.topRight())
    g.setColorAt(0.0, with_alpha(th.accent2, k))
    g.setColorAt(1.0, with_alpha(th.accent, k))
    # glow under the filled part
    p.setPen(Qt.NoPen)
    p.setBrush(with_alpha(th.glow, 0.35 * k))
    p.drawRoundedRect(rect.adjusted(-1, -3, 1, 3), height, height)
    p.setBrush(g)
    p.drawRoundedRect(rect, height / 2, height / 2)
    p.restore()


def paint_handle(p: QPainter, center: QPointF, th: Theme, radius: float = 9.0, hot: bool = False,
                 enabled: bool = True) -> None:
    """Round glowing slider handle."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    k = 1.0 if enabled else 0.45
    glow_r = radius * (2.3 if hot else 1.8)
    rg = QRadialGradient(center, glow_r)
    rg.setColorAt(0.0, with_alpha(th.glow, (0.9 if hot else 0.55) * k))
    rg.setColorAt(1.0, with_alpha(th.glow, 0.0))
    p.setPen(Qt.NoPen)
    p.setBrush(rg)
    p.drawEllipse(center, glow_r, glow_r)
    body = QLinearGradient(QPointF(center.x(), center.y() - radius), QPointF(center.x(), center.y() + radius))
    body.setColorAt(0.0, with_alpha(th.handle_top, k))
    body.setColorAt(1.0, with_alpha(th.handle_bottom, k))
    p.setBrush(body)
    p.setPen(QPen(with_alpha(th.accent, 0.9 * k), 1.4))
    p.drawEllipse(center, radius, radius)
    # small specular highlight
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, int(200 * k)))
    p.drawEllipse(QPointF(center.x() - radius * 0.25, center.y() - radius * 0.4), radius * 0.35, radius * 0.22)
    p.restore()


def paint_icon(p: QPainter, kind: str, rect: QRectF, color: QColor, muted: bool = False) -> None:
    """Simple vector icons: play, pause, speaker (muted via flag), sun, moon, folder."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    c = rect.center()
    s = min(rect.width(), rect.height())
    pen = QPen(color, max(1.6, s * 0.09), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind == "play":
        path = QPainterPath()
        path.moveTo(c.x() - s * 0.2, c.y() - s * 0.3)
        path.lineTo(c.x() - s * 0.2, c.y() + s * 0.3)
        path.lineTo(c.x() + s * 0.32, c.y())
        path.closeSubpath()
        p.setBrush(color)
        p.drawPath(path)
    elif kind == "pause":
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        w, h = s * 0.14, s * 0.56
        p.drawRoundedRect(QRectF(c.x() - s * 0.2, c.y() - h / 2, w, h), w / 2, w / 2)
        p.drawRoundedRect(QRectF(c.x() + s * 0.06, c.y() - h / 2, w, h), w / 2, w / 2)
    elif kind == "speaker":
        body = QPainterPath()
        x = c.x() - s * 0.3
        body.moveTo(x, c.y() - s * 0.12)
        body.lineTo(x + s * 0.14, c.y() - s * 0.12)
        body.lineTo(x + s * 0.34, c.y() - s * 0.3)
        body.lineTo(x + s * 0.34, c.y() + s * 0.3)
        body.lineTo(x + s * 0.14, c.y() + s * 0.12)
        body.lineTo(x, c.y() + s * 0.12)
        body.closeSubpath()
        p.setBrush(color)
        p.drawPath(body)
        p.setBrush(Qt.NoBrush)
        if muted:
            ox = c.x() + s * 0.12
            p.drawLine(QPointF(ox, c.y() - s * 0.14), QPointF(ox + s * 0.28, c.y() + s * 0.14))
            p.drawLine(QPointF(ox, c.y() + s * 0.14), QPointF(ox + s * 0.28, c.y() - s * 0.14))
        else:
            for i, r in enumerate((0.17, 0.3)):
                arc = QRectF(c.x() + s * 0.04 - s * r, c.y() - s * r, s * r * 2, s * r * 2)
                p.drawArc(arc, -40 * 16, 80 * 16)
    elif kind == "sun":
        p.drawEllipse(c, s * 0.16, s * 0.16)
        for k in range(8):
            import math
            a = math.radians(k * 45)
            p.drawLine(QPointF(c.x() + math.cos(a) * s * 0.28, c.y() + math.sin(a) * s * 0.28),
                       QPointF(c.x() + math.cos(a) * s * 0.4, c.y() + math.sin(a) * s * 0.4))
    elif kind == "moon":
        outer = QPainterPath()
        outer.addEllipse(c, s * 0.3, s * 0.3)
        cut = QPainterPath()
        cut.addEllipse(QPointF(c.x() + s * 0.17, c.y() - s * 0.1), s * 0.27, s * 0.27)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(outer.subtracted(cut))
    elif kind == "gear":
        import math
        teeth, r_out, r_in = 8, s * 0.40, s * 0.30
        path = QPainterPath()
        steps = teeth * 4
        for k in range(steps):
            a = 2 * math.pi * k / steps
            r = r_out if (k % 4) in (0, 1) else r_in
            pt = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            path.moveTo(pt) if k == 0 else path.lineTo(pt)
        path.closeSubpath()
        hole = QPainterPath()
        hole.addEllipse(c, s * 0.13, s * 0.13)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path.subtracted(hole))
    elif kind == "question":
        from PySide6.QtGui import QFont
        font = QFont(p.font())
        font.setBold(True)
        font.setPixelSize(max(int(s * 1.05), 8))
        p.setFont(font)
        p.setPen(color)
        p.drawText(rect, Qt.AlignCenter, "?")
    elif kind == "folder":
        path = QPainterPath()
        l, t, r, b = c.x() - s * 0.34, c.y() - s * 0.24, c.x() + s * 0.34, c.y() + s * 0.26
        path.moveTo(l, t + s * 0.1)
        path.lineTo(l, b)
        path.lineTo(r, b)
        path.lineTo(r, t + s * 0.1)
        path.lineTo(l + s * 0.3, t + s * 0.1)
        path.lineTo(l + s * 0.22, t)
        path.lineTo(l, t)
        path.closeSubpath()
        p.drawPath(path)
    p.restore()
