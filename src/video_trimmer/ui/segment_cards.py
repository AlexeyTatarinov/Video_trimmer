"""Segment cards: fixed-size cards in a wrapping flow layout inside a small scroll area.

Cards can be reordered by dragging (an insertion indicator shows the drop place) and with
Alt+Left / Alt+Right (handled by the main window for the selected card).
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QGridLayout, QScrollArea, QSizePolicy, QWidget,
)

from video_trimmer import i18n
from video_trimmer.ui import theme
from video_trimmer.ui.flow_layout import FlowLayout
from video_trimmer.ui.timefmt import format_time
from video_trimmer.ui.theme import with_alpha
from video_trimmer.ui.widgets import CloseButton, ElidedLabel

DIGITS = "0123456789"
SPACING = 8
MARGIN = 4          # room around the cards (selection border, focus)
VISIBLE_ROWS = 2    # the area grows up to this many rows, then it scrolls
MIN_AREA_HEIGHT = 56
INDICATOR_WIDTH = 4


def _by_digit(template: str) -> list[str]:
    """``template`` with every ``@`` replaced by each digit in turn (widest digit wins)."""
    return [template.replace("@", d) for d in DIGITS]


class SegmentCard(QFrame):
    """One segment: index, ``start - end``, duration and a delete cross. Standard fixed size."""

    clicked = Signal(int)
    deleteRequested = Signal(int)
    dragStarted = Signal(int)
    dragMoved = Signal(QPoint)               # global position
    dragFinished = Signal(QPoint, bool)      # global position, cancelled

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._selected = False
        self._hover = False
        self._press_global: QPoint | None = None
        self._dragging = False
        self._toggle_pending = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.index_label = ElidedLabel()
        self.index_label.setObjectName("cardIndex")
        self.index_label.set_measure_texts(_by_digit("#@@@"))
        self.range_label = ElidedLabel()
        self.range_label.setObjectName("cardRange")
        self.range_label.set_measure_texts(_by_digit("@@:@@:@@.@@@ - @@:@@:@@.@@@"))
        self.duration_label = ElidedLabel()
        self.duration_label.setObjectName("cardDim")
        words = i18n.all_texts("duration")
        self.duration_label.set_measure_texts(
            [f"{w}: {t}" for w in words for t in _by_digit("@@:@@:@@.@@@")])
        self.delete_button = CloseButton()
        self.delete_button.clicked.connect(lambda: self.deleteRequested.emit(self._index))
        for lbl in (self.index_label, self.range_label, self.duration_label):
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay = QGridLayout(self)
        lay.setContentsMargins(12, 4, 6, 5)
        lay.setHorizontalSpacing(8)
        lay.setVerticalSpacing(0)
        lay.addWidget(self.index_label, 0, 0, 2, 1, Qt.AlignVCenter)
        lay.addWidget(self.range_label, 0, 1)
        lay.addWidget(self.delete_button, 0, 2, Qt.AlignTop | Qt.AlignRight)
        lay.addWidget(self.duration_label, 1, 1, 1, 2)

    # ---- content
    def text_labels(self) -> list[ElidedLabel]:
        return [self.index_label, self.range_label, self.duration_label]

    def index(self) -> int:
        return self._index

    def set_segment(self, index: int, start: float, end: float, language: str) -> None:
        self._index = index
        self.index_label.setText(f"#{index + 1}")
        self.range_label.setText(f"{format_time(start)} - {format_time(end)}")
        self.duration_label.setText(f"{i18n.tr(language, 'duration')}: {format_time(end - start)}")
        self.setToolTip(f"{i18n.tr(language, 'segment')} {index + 1}")
        self.delete_button.setToolTip(i18n.tr(language, "delete_segment"))
        self.update()

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self.index_label.setProperty("selected", selected)
            st = self.index_label.style()
            st.unpolish(self.index_label)
            st.polish(self.index_label)
            self.update()

    # ---- interaction
    def is_dragging(self) -> bool:
        return self._dragging

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self._press_global = event.globalPosition().toPoint()
            # An unselected card is selected at once (so it can be dragged right away). A click on the
            # selected card is a toggle: it counts only on release, when no drag has started.
            self._toggle_pending = self._selected
            if not self._selected:
                self.clicked.emit(self._index)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press_global is None:
            super().mouseMoveEvent(event)
            return
        pos = event.globalPosition().toPoint()
        if not self._dragging:
            if (pos - self._press_global).manhattanLength() < QApplication.startDragDistance():
                return
            self._dragging = True
            self.dragStarted.emit(self._index)
        self.dragMoved.emit(pos)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        was_dragging = self._dragging
        toggle = self._toggle_pending and event.button() == Qt.LeftButton
        self._press_global, self._dragging, self._toggle_pending = None, False, False
        if was_dragging and event.button() == Qt.LeftButton:
            self.dragFinished.emit(event.globalPosition().toPoint(), False)
            event.accept()
        elif toggle and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self._index)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape and self._dragging:
            self._press_global, self._dragging, self._toggle_pending = None, False, False
            self.dragFinished.emit(QPoint(), True)
        elif event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.clicked.emit(self._index)
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.delete_button.isEnabled():
            self.deleteRequested.emit(self._index)
        else:
            super().keyPressEvent(event)

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
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self._selected:
            fill, pen_color, pen_w = th.selection, th.accent, 2.0
        else:
            fill = th.input_bg
            if self._hover:
                fill = with_alpha(th.selection, 0.45)
            pen_color, pen_w = th.input_border, 1.2
        p.setBrush(fill)
        p.setPen(QPen(pen_color, pen_w))
        p.drawRoundedRect(r, 13, 13)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(with_alpha(th.accent, 0.9), 1.3, Qt.DashLine))
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 15, 15)


class DropIndicator(QWidget):
    """Thin accent bar showing where a dragged card will be inserted."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(with_alpha(th.glow, 0.6))
        p.drawRoundedRect(QRectF(self.rect()), 2, 2)
        p.setBrush(th.accent)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0, -0.5, 0), 2, 2)


class SegmentCardList(QScrollArea):
    """Cards flowing left to right and wrapping; height grows up to two rows, then scrolls."""

    currentRowChanged = Signal(int)
    removeRequested = Signal(int)
    moveRequested = Signal(int, int)    # (from row, to row) after a drag

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: list[SegmentCard] = []
        self._current = -1
        self._language = i18n.DEFAULT_LANGUAGE
        self._removable = True
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setObjectName("segmentList")
        self.viewport().setAutoFillBackground(False)
        inner = QWidget()
        inner.setObjectName("segmentInner")
        inner.setAutoFillBackground(False)
        self._flow = FlowLayout(inner, SPACING)
        self._flow.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        self.setWidget(inner)
        self.drop_indicator = DropIndicator(inner)
        self._drag_src = -1
        self._drag_slot = -1
        self.setFixedHeight(MIN_AREA_HEIGHT)

    # ---- model-ish API (mirrors the old QListWidget calls)
    def count(self) -> int:
        return len(self._cards)

    def cards(self) -> list[SegmentCard]:
        return list(self._cards)

    def card(self, row: int) -> SegmentCard:
        return self._cards[row]

    def currentRow(self) -> int:  # noqa: N802
        return self._current

    def setCurrentRow(self, row: int) -> None:  # noqa: N802
        if not -1 <= row < len(self._cards):
            return
        if row == self._current:
            return
        self._current = row
        for i, c in enumerate(self._cards):
            c.set_selected(i == row)
        if 0 <= row < len(self._cards):
            self.ensureWidgetVisible(self._cards[row], 4, 4)
        self.currentRowChanged.emit(row)

    def set_segments(self, segments: list[tuple[float, float]], language: str,
                     select: int | None = None) -> None:
        """Rebuild the cards. Keeps the selected row (or sets ``select``) without emitting."""
        self._language = language
        row = self._current if select is None else select
        while len(self._cards) > len(segments):
            c = self._cards.pop()
            self._flow.removeWidget(c)
            c.hide()
            c.setParent(None)
            c.deleteLater()
        while len(self._cards) < len(segments):
            c = SegmentCard(len(self._cards), self.widget())
            c.clicked.connect(self._card_clicked)
            c.deleteRequested.connect(self.removeRequested)
            c.dragStarted.connect(self._drag_started)
            c.dragMoved.connect(self._drag_moved)
            c.dragFinished.connect(self._drag_finished)
            self._flow.addWidget(c)
            c.show()
            self._cards.append(c)
        for i, (s, e) in enumerate(segments):
            self._cards[i].set_segment(i, s, e, language)
            self._cards[i].set_selected(i == row)
            self._cards[i].delete_button.setEnabled(self._removable)
        self._current = row if 0 <= row < len(segments) else -1
        self._adjust_height()
        self.viewport().update()

    def update_segment(self, row: int, segment: tuple[float, float]) -> None:
        if 0 <= row < len(self._cards):
            self._cards[row].set_segment(row, segment[0], segment[1], self._language)

    def set_removable(self, removable: bool) -> None:
        self._removable = removable
        for c in self._cards:
            c.delete_button.setEnabled(removable)

    def _card_clicked(self, row: int) -> None:
        """A click selects a card; a click on the selected card selects nothing (draft mode)."""
        self.setCurrentRow(-1 if row == self._current else row)

    # ---- drag and drop reordering
    def is_dragging(self) -> bool:
        return self._drag_src >= 0

    def slot_at(self, global_pos: QPoint) -> int:
        """Insertion slot (0..count) for a global position: before the first card it precedes."""
        p = self.widget().mapFromGlobal(global_pos)
        for i, c in enumerate(self._cards):
            g = c.geometry()
            if p.y() < g.top():
                return i
            if p.y() <= g.bottom() and p.x() < g.center().x():
                return i
        return len(self._cards)

    def _show_indicator(self, slot: int) -> None:
        if not self._cards:
            return
        n = len(self._cards)
        if slot < n:
            g = self._cards[slot].geometry()
            x = g.left() - SPACING // 2 - INDICATOR_WIDTH // 2
        else:
            g = self._cards[-1].geometry()
            x = g.right() + 1 + SPACING // 2 - INDICATOR_WIDTH // 2
        x = max(x, 0)
        self.drop_indicator.setGeometry(QRect(x, g.top(), INDICATOR_WIDTH, g.height()))
        self.drop_indicator.show()
        self.drop_indicator.raise_()

    def _drag_started(self, row: int) -> None:
        self._drag_src, self._drag_slot = row, -1
        effect = QGraphicsOpacityEffect(self._cards[row])
        effect.setOpacity(0.55)
        self._cards[row].setGraphicsEffect(effect)

    def _drag_moved(self, global_pos: QPoint) -> None:
        if self._drag_src < 0:
            return
        self._drag_slot = self.slot_at(global_pos)
        self._show_indicator(self._drag_slot)
        vp = self.viewport().mapFromGlobal(global_pos)
        bar = self.verticalScrollBar()
        if vp.y() < 14:
            bar.setValue(bar.value() - 12)
        elif vp.y() > self.viewport().height() - 14:
            bar.setValue(bar.value() + 12)

    def _drag_finished(self, global_pos: QPoint, cancelled: bool) -> None:
        src = self._drag_src
        slot = self.slot_at(global_pos) if not cancelled else -1
        self._drag_src = self._drag_slot = -1
        self.drop_indicator.hide()
        if 0 <= src < len(self._cards):
            self._cards[src].setGraphicsEffect(None)
        if cancelled or src < 0 or slot < 0:
            return
        target = slot - 1 if slot > src else slot
        if target != src:
            self.moveRequested.emit(src, target)

    # ---- sizing
    def _extent(self) -> int:
        self.ensurePolished()
        return max(self.verticalScrollBar().sizeHint().width(), 10) + 4

    def _row_height(self) -> int:
        if self._cards:
            return self._cards[0].sizeHint().height()
        probe = SegmentCard(0, self.widget())      # measure a card without keeping it
        probe.ensurePolished()
        height = probe.sizeHint().height()
        probe.setParent(None)
        probe.deleteLater()
        return height

    def _max_height(self) -> int:
        return VISIBLE_ROWS * self._row_height() + (VISIBLE_ROWS - 1) * SPACING + 2 * MARGIN

    def _adjust_height(self) -> None:
        """Pick the area height for the current width (heightForWidth of the flow, capped)."""
        extent = self._extent()
        avail = self.width() - 2 * self.frameWidth() - extent
        self._flow.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        need = self._flow.heightForWidth(max(avail, 1)) if self._cards else 0
        top = self._max_height()
        scrolling = need > top
        right = MARGIN if scrolling else MARGIN + extent
        m = self._flow.contentsMargins()
        if m.right() != right:
            self._flow.setContentsMargins(MARGIN, MARGIN, right, MARGIN)
        height = min(max(need, self._row_height() + 2 * MARGIN), top)
        if self.height() != height or self.minimumHeight() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._adjust_height()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._minimum_width() + 200, self.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._minimum_width(), self.height())

    def _minimum_width(self) -> int:
        card_w = self._cards[0].sizeHint().width() if self._cards else 240
        return card_w + 2 * MARGIN + self._extent()

    # ---- keyboard
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.AltModifier:
            event.ignore()      # Alt+Left / Alt+Right reorder: handled by the main window
        elif event.key() in (Qt.Key_Left, Qt.Key_Up) and self._current > 0:
            self.setCurrentRow(self._current - 1)
        elif event.key() in (Qt.Key_Right, Qt.Key_Down) and self._current < len(self._cards) - 1:
            self.setCurrentRow(self._current + 1)
        else:
            super().keyPressEvent(event)

    # ---- painting: the glass "well" behind the cards
    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        p = QPainter(self.viewport())  # a scroll area paints on its viewport
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(with_alpha(th.input_bg, 0.55))
        p.setPen(QPen(with_alpha(th.input_border, 0.8), 1.0))
        p.drawRoundedRect(QRectF(self.viewport().rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        if not self._cards:  # a quiet hint instead of an empty well
            p.setPen(th.text_dim)
            rect = self.viewport().rect().adjusted(16, 0, -16, 0)
            text = p.fontMetrics().elidedText(i18n.tr(self._language, "segments_empty"),
                                              Qt.ElideRight, rect.width())
            p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, text)
