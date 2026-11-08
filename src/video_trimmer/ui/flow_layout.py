"""Flow layout: items go left to right and wrap onto the next row (heightForWidth)."""
from __future__ import annotations

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_spacing = spacing
        self._v_spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    # ---- QLayout API
    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)
        self.invalidate()

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            self.invalidate()
            return item
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    # ---- spacing
    def setSpacings(self, horizontal: int, vertical: int) -> None:  # noqa: N802
        self._h_spacing, self._v_spacing = horizontal, vertical
        self.invalidate()

    def horizontalSpacing(self) -> int:  # noqa: N802
        return self._h_spacing

    def verticalSpacing(self) -> int:  # noqa: N802
        return self._v_spacing

    # ---- geometry
    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m: QMargins = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, row_h = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > area.right() + 1 and row_h > 0:
                x = area.x()
                y += row_h + self._v_spacing
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._h_spacing
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y() + m.bottom()
