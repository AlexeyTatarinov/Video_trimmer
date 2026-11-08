"""Glass-styled custom widgets: background, panel, pill/round buttons, slider, combo box."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QBrush,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractButton, QCheckBox, QComboBox, QFrame, QLabel, QPushButton, QSizePolicy, QSlider, QVBoxLayout,
    QWidget,
)

from video_trimmer.ui import theme
from video_trimmer.ui.theme import paint_background, paint_glass, paint_icon, with_alpha


class GlassBackground(QWidget):
    """Window background: diagonal gradient with soft light blobs."""

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        paint_background(p, QRectF(self.rect()), theme.current())


class ElidedLabel(QLabel):
    """One-line label that never stretches its container.

    Without measure texts the label is flexible: it takes whatever width the layout gives it and
    shows the text elided with an ellipsis (full text in the tooltip). With ``set_measure_texts``
    its width is fixed to the widest of the given texts (e.g. one per language), so switching
    the text never changes the geometry. ``text()`` always returns the full text.
    """

    PAD = 2

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self._measure: list[str] = []
        self._auto_tip = True
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(False)
        self.setText(text)

    def set_measure_texts(self, texts: list[str]) -> None:
        self._measure = list(texts)
        self.setSizePolicy(QSizePolicy.Fixed if self._measure else QSizePolicy.Ignored,
                           QSizePolicy.Fixed)
        self.updateGeometry()
        self._show_elided()

    def text(self) -> str:  # noqa: A003
        return self._full

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        self._show_elided()

    def _metrics(self) -> QFontMetrics:
        self.ensurePolished()
        return QFontMetrics(self.font())

    def _show_elided(self) -> None:
        avail = max(self.width() - self.PAD, 0)
        fm = self._metrics()
        shown = self._full if fm.horizontalAdvance(self._full) <= avail or self.width() <= 0 \
            else fm.elidedText(self._full, Qt.ElideRight, avail)
        if QLabel.text(self) != shown:
            QLabel.setText(self, shown)
        if self._auto_tip:
            self.setToolTip(self._full if shown != self._full else "")

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self._metrics()
        texts = self._measure or [self._full]
        w = max(fm.horizontalAdvance(t) for t in texts) + self.PAD
        return QSize(w, fm.height() + 2)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        if self._measure:
            return self.sizeHint()
        return QSize(0, self._metrics().height() + 2)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._show_elided()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange, QEvent.Polish):
            self.updateGeometry()
            self._show_elided()


PANEL_RADIUS = 22.0   # corner radius of the glass panels (the video area is clipped to the same)


class GlassPanel(QFrame):
    """Translucent rounded panel with an optional small caption and a ``body`` layout."""

    def __init__(self, title: str = "", parent: QWidget | None = None, shadow: bool = True) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(11, 6, 11, 7)
        self.body.setSpacing(4)
        self.caption = ElidedLabel(title)
        self.caption.setObjectName("caption")
        self.body.addWidget(self.caption)
        self.caption.setVisible(bool(title))
        if shadow:
            theme.add_shadow(self, blur=34, dy=9)

    def setTitle(self, text: str) -> None:  # noqa: N802
        self.caption.setText(text.upper())
        self.caption.setVisible(bool(text))

    def title(self) -> str:
        return self.caption.text()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        paint_glass(p, QRectF(self.rect()).adjusted(1, 1, -1, -1), theme.current(), PANEL_RADIUS)


class GlassButton(QPushButton):
    """Pill button (text) or round icon button, painted with glass gradients.

    States: normal, hover, pressed, disabled, checked (accent glow), keyboard focus.
    ``primary=True`` gives the accent-coloured call-to-action look.
    """

    HEIGHT = 36
    PAD = 26             # horizontal room around the text
    MIN_TEXT_WIDTH = 104  # a text button may be squeezed down to this (text is then elided)

    def __init__(self, text: str = "", icon_kind: str | None = None, primary: bool = False,
                 diameter: int = 44, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._icon_kind = icon_kind
        self._primary = primary
        self._diameter = diameter
        self._hover = False
        self._texts: list[str] = []
        self._shrinkable = False
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFocusPolicy(Qt.StrongFocus)
        if icon_kind:
            self.setFixedSize(diameter, diameter)
        else:
            self.setMinimumHeight(self.HEIGHT)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        theme.add_shadow(self, blur=16, dy=4, strength=0.8)

    # ---- API
    def iconKind(self) -> str | None:  # noqa: N802
        return self._icon_kind

    def setIconKind(self, kind: str | None) -> None:  # noqa: N802
        self._icon_kind = kind
        self.update()

    def isPrimary(self) -> bool:  # noqa: N802
        return self._primary

    def set_texts(self, texts: list[str]) -> None:
        """Texts the button can show (one per language): its width fits the longest of them."""
        self._texts = list(texts)
        self.updateGeometry()

    def set_shrinkable(self, shrinkable: bool) -> None:
        """Allow the layout to squeeze the button below its text width (the text is elided)."""
        self._shrinkable = shrinkable
        self.updateGeometry()

    def _bold_metrics(self) -> QFontMetrics:
        self.ensurePolished()
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        return QFontMetrics(font)

    def sizeHint(self) -> QSize:  # noqa: N802
        if self._icon_kind:
            return QSize(self._diameter, self._diameter)
        fm = self._bold_metrics()
        w = max(fm.horizontalAdvance(t) for t in (self._texts or [self.text()])) + self.PAD
        return QSize(max(w, 80), self.HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        if self._icon_kind:
            return QSize(self._diameter, self._diameter)
        hint = self.sizeHint()
        if not self._shrinkable:
            return hint
        return QSize(min(hint.width(), self.MIN_TEXT_WIDTH), hint.height())

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange, QEvent.Polish):
            self.updateGeometry()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    # ---- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        enabled = self.isEnabled()
        down = self.isDown()
        checked = self.isCheckable() and self.isChecked()
        hover = self._hover and enabled
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -4)
        radius = r.height() / 2
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)

        if self._primary:
            top, bottom = th.primary_top, th.primary_bottom
            if hover:
                top, bottom = top.lighter(112), bottom.lighter(112)
            if down:
                top, bottom = bottom, top
            text_color = th.primary_text
        else:
            top, bottom = th.btn_top, th.btn_bottom
            if hover:
                top, bottom = th.btn_hover_top, th.btn_hover_bottom
            if down:
                top, bottom = th.btn_pressed_top, th.btn_pressed_bottom
            if checked:
                top, bottom = with_alpha(th.accent2, 0.85), with_alpha(th.accent, 0.9)
            text_color = th.primary_text if checked else th.text
        if not enabled:
            top, bottom = with_alpha(top, 0.45), with_alpha(bottom, 0.45)
            text_color = with_alpha(th.text_dim, 0.7)

        # outer glow for hover / checked
        if (hover or checked) and not down:
            glow = QPainterPath()
            glow.addRoundedRect(r.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)
            p.fillPath(glow, with_alpha(th.glow, 0.55 if checked else 0.35))

        fill = QLinearGradient(r.topLeft(), r.bottomLeft())
        fill.setColorAt(0.0, top)
        fill.setColorAt(1.0, bottom)
        p.fillPath(path, fill)

        # gloss on the upper half
        if enabled and not down:
            gloss = QPainterPath()
            gloss.addRoundedRect(r.adjusted(2, 1.5, -2, -r.height() * 0.48), radius * 0.8, radius * 0.8)
            gg = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
            gg.setColorAt(0.0, QColor(255, 255, 255, 110 if th.name == "light" else 70))
            gg.setColorAt(1.0, QColor(255, 255, 255, 5))
            p.fillPath(gloss, gg)
        if down and enabled:  # inset shadow at the top
            inset = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + r.height() * 0.5))
            inset.setColorAt(0.0, QColor(0, 0, 0, 55))
            inset.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillPath(path, inset)

        border = th.btn_border
        if self._primary:
            border = with_alpha(QColor(255, 255, 255), 0.7)
        if checked:
            border = with_alpha(QColor(255, 255, 255), 0.9)
        if not enabled:
            border = with_alpha(border, 0.4)
        p.setPen(QPen(border, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(0.6, 0.6, -0.6, -0.6), radius, radius)

        if self.hasFocus() and self.focusPolicy() != Qt.NoFocus and enabled:
            p.setPen(QPen(with_alpha(th.accent, 0.9), 1.5, Qt.DashLine))
            p.drawRoundedRect(r.adjusted(-1.5, -1.5, 1.5, 1.5), radius + 1.5, radius + 1.5)

        content = r.translated(0, 1 if down else 0)
        if self._icon_kind:
            kind = self._icon_kind
            muted = False
            if kind == "speaker":
                muted = checked
            icon_rect = content.adjusted(content.width() * 0.2, content.height() * 0.2,
                                         -content.width() * 0.2, -content.height() * 0.2)
            paint_icon(p, kind, icon_rect, text_color, muted=muted)
        else:
            font = self.font()
            font.setWeight(font.Weight.DemiBold)
            p.setFont(font)
            p.setPen(text_color)
            text = QFontMetrics(font).elidedText(self.text(), Qt.ElideRight,
                                                 max(int(content.width()) - 8, 10))
            p.drawText(content, Qt.AlignCenter, text)


class GlassSlider(QSlider):
    """Horizontal slider with glass groove, gradient fill and a glowing round handle."""

    MARGIN = 12

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self.setMinimumHeight(30)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._hover = False

    def _x_for(self, value: int) -> float:
        span = self.maximum() - self.minimum()
        frac = (value - self.minimum()) / span if span > 0 else 0.0
        return self.MARGIN + frac * (self.width() - 2 * self.MARGIN)

    def _value_at(self, x: float) -> int:
        width = max(self.width() - 2 * self.MARGIN, 1)
        frac = min(max((x - self.MARGIN) / width, 0.0), 1.0)
        return int(round(self.minimum() + frac * (self.maximum() - self.minimum())))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or not self.isEnabled():
            return
        self.setSliderDown(True)
        self.setSliderPosition(self._value_at(event.position().x()))
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.isSliderDown():
            self.setSliderPosition(self._value_at(event.position().x()))
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.isSliderDown():
            self.setSliderDown(False)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        p = QPainter(self)
        cy = self.height() / 2
        enabled = self.isEnabled()
        x = self._x_for(self.sliderPosition())
        theme.paint_groove(p, self.MARGIN, self.width() - self.MARGIN, cy, th, enabled)
        theme.paint_fill(p, self.MARGIN, x, cy, th, enabled)
        theme.paint_handle(p, QPointF(x, cy), th, 9.0, hot=self.isSliderDown() or self._hover,
                           enabled=enabled)


class GlassComboBox(QComboBox):
    """Combo box (pill look comes from the style sheet) with a painted chevron."""

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        th = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(th.text if self.isEnabled() else th.text_dim, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx, cy = self.width() - 20, self.height() / 2
        p.drawLine(QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2))
        p.drawLine(QPointF(cx, cy + 2), QPointF(cx + 4, cy - 2))


class CloseButton(QAbstractButton):
    """Small round button with a cross (deletes a segment card)."""

    SIZE = 24

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._hover = False

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.SIZE, self.SIZE)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        enabled = self.isEnabled()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if (self._hover or self.isDown()) and enabled:
            p.setPen(Qt.NoPen)
            p.setBrush(with_alpha(th.accent, 0.35 if not self.isDown() else 0.55))
            p.drawEllipse(r)
        color = th.text if enabled else with_alpha(th.text_dim, 0.45)
        p.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap))
        c, d = r.center(), r.width() * 0.22
        p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
        p.drawLine(QPointF(c.x() - d, c.y() + d), QPointF(c.x() + d, c.y() - d))
        if self.hasFocus() and enabled:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(with_alpha(th.accent, 0.9), 1.3, Qt.DashLine))
            p.drawEllipse(r.adjusted(-1, -1, 1, 1))


class StatusProgressBar(QWidget):
    """Wide glass progress bar with the status text inside it (elided, never stretches anything)."""

    HEIGHT = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min, self._max, self._value = 0, 100, 0
        self._text = ""
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    # progress API (same names as QProgressBar)
    def setRange(self, lo: int, hi: int) -> None:  # noqa: N802
        self._min, self._max = lo, max(hi, lo)
        self.update()

    def setValue(self, value: int) -> None:  # noqa: N802
        self._value = min(max(int(value), self._min), self._max)
        self.update()

    def value(self) -> int:
        return self._value

    # status text API (same names as QLabel)
    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text
        self.setToolTip(text)
        self.update()

    def text(self) -> str:
        return self._text

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(300, self.HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(120, self.HEIGHT)

    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 3, -1, -3)
        radius = r.height() / 2
        p.setBrush(th.track)
        p.setPen(QPen(th.track_border, 1.0))
        p.drawRoundedRect(r, radius, radius)
        span = self._max - self._min
        frac = (self._value - self._min) / span if span > 0 else 0.0
        if frac > 0:
            fr = QRectF(r.left(), r.top(), max(r.width() * frac, r.height()), r.height())
            g = QLinearGradient(fr.topLeft(), fr.topRight())
            g.setColorAt(0.0, with_alpha(th.accent2, 0.75))
            g.setColorAt(1.0, with_alpha(th.accent, 0.75))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(fr, radius, radius)
        font = self.font()
        font.setPixelSize(12)
        p.setFont(font)
        p.setPen(th.text)
        text = QFontMetrics(font).elidedText(self._text, Qt.ElideRight, max(int(r.width()) - 24, 10))
        p.drawText(r, Qt.AlignCenter, text)


class GlassCheckBox(QCheckBox):
    """Check box painted in the glass style; its text wraps in a fixed-size box (two lines)."""

    BOX = 20
    GAP = 10
    LINES = 2

    def __init__(self, text: str = "", width: int = 320, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(width, 2 * 6 + self.LINES * QFontMetrics(self.font()).lineSpacing() + 2)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.size()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.size()

    def _text_rect(self) -> QRectF:
        x = self.BOX + self.GAP
        return QRectF(x, 0, self.width() - x, self.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1.5, (self.height() - self.BOX) / 2, self.BOX - 3, self.BOX - 3)
        p.setPen(QPen(th.accent if self.isChecked() or self.hasFocus() else th.input_border, 1.4))
        p.setBrush(th.accent if self.isChecked() else th.input_bg)
        p.drawRoundedRect(box, 6, 6)
        if self.isChecked():
            pen = QPen(QColor(255, 255, 255), 2.2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            c = box.center()
            p.drawPolyline([QPointF(c.x() - 4.2, c.y() + 0.2), QPointF(c.x() - 1.2, c.y() + 3.2),
                            QPointF(c.x() + 4.4, c.y() - 3.2)])
        p.setPen(th.text)
        p.drawText(self._text_rect(), int(Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap), self.text())

    def hitButton(self, pos) -> bool:  # noqa: N802
        return self.rect().contains(pos)


class GlassPopup(QFrame):
    """Small frameless glass popup (closes on a click outside). ``body`` is its layout."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 12, 16, 14)
        self.body.setSpacing(8)

    def popup_below(self, anchor: QWidget, align_right: bool = True, above: bool = False) -> None:
        """Show next to ``anchor`` (below or above it), kept inside the screen."""
        self.ensurePolished()
        self.layout().activate()
        self.adjustSize()
        size = self.sizeHint().expandedTo(self.minimumSizeHint())
        self.resize(size)
        gap = 6
        if above:
            pos = anchor.mapToGlobal(QPoint(0, -size.height() - gap))
        else:
            pos = anchor.mapToGlobal(QPoint(0, anchor.height() + gap))
        if align_right:
            pos.setX(anchor.mapToGlobal(QPoint(anchor.width(), 0)).x() - size.width())
        screen = QGuiApplication.screenAt(anchor.mapToGlobal(anchor.rect().center())) \
            or QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            pos.setX(min(max(pos.x(), geo.left() + 4), geo.right() - size.width() - 4))
            pos.setY(min(max(pos.y(), geo.top() + 4), geo.bottom() - size.height() - 4))
        self.move(pos)
        self.show()

    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 20, 20)
        p.fillPath(path, th.popup_bg)
        paint_glass(p, r, th, 20.0)
