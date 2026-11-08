"""Two-handle range slider over [0, maximum] in seconds."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

HANDLE_W = 12


class RangeSlider(QWidget):
    rangeChanged = Signal(float, float)  # low, high

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._max = 1.0
        self._low = 0.0
        self._high = 1.0
        self._active: str | None = None
        self.setMinimumHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ---- value logic (pure clamping)
    def maximum(self) -> float:
        return self._max

    def low(self) -> float:
        return self._low

    def high(self) -> float:
        return self._high

    def setMaximum(self, value: float) -> None:
        old = (self._low, self._high)
        was_full = self._high >= self._max
        self._max = max(float(value), 0.0)
        self._high = self._max if was_full else min(self._high, self._max)
        self._low = min(self._low, self._high)
        self._after_change(old)

    def setValues(self, low: float, high: float) -> None:
        old = (self._low, self._high)
        self._high = min(max(float(high), 0.0), self._max)
        self._low = min(max(float(low), 0.0), self._high)
        self._after_change(old)

    def setLow(self, value: float) -> None:
        self.setValues(value, self._high)

    def setHigh(self, value: float) -> None:
        old = (self._low, self._high)
        self._high = min(max(float(value), self._low), self._max)
        self._after_change(old)

    def _after_change(self, old: tuple[float, float]) -> None:
        self.update()
        if (self._low, self._high) != old:
            self.rangeChanged.emit(self._low, self._high)

    # ---- geometry
    def _track(self) -> tuple[float, float]:
        return HANDLE_W / 2, max(self.width() - HANDLE_W / 2, HANDLE_W / 2 + 1)

    def value_to_x(self, value: float) -> float:
        left, right = self._track()
        frac = value / self._max if self._max > 0 else 0.0
        return left + frac * (right - left)

    def x_to_value(self, x: float) -> float:
        left, right = self._track()
        frac = (x - left) / (right - left)
        return min(max(frac, 0.0), 1.0) * self._max

    # ---- mouse
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        x = event.position().x()
        dl, dh = abs(x - self.value_to_x(self._low)), abs(x - self.value_to_x(self._high))
        if dl == dh:
            self._active = "low" if x < self.value_to_x(self._low) else "high"
        else:
            self._active = "low" if dl < dh else "high"
        self._drag_to(x)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._active:
            self._drag_to(event.position().x())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._active = None

    def _drag_to(self, x: float) -> None:
        value = self.x_to_value(x)
        if self._active == "low":
            self.setLow(value)
        elif self._active == "high":
            self.setHigh(value)

    # ---- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        cy = self.height() / 2
        xl, xh = self.value_to_x(self._low), self.value_to_x(self._high)
        left, right = self._track()
        p.setPen(Qt.NoPen)
        p.setBrush(pal.mid())
        p.drawRoundedRect(QRectF(left, cy - 3, right - left, 6), 3, 3)
        p.setBrush(pal.highlight())
        p.drawRect(QRectF(xl, cy - 3, max(xh - xl, 0), 6))
        p.setPen(QColor(0, 0, 0, 90))
        p.setBrush(pal.button() if not self.isEnabled() else pal.light())
        for x in (xl, xh):
            p.drawRoundedRect(QRectF(x - HANDLE_W / 2, 4, HANDLE_W, self.height() - 8), 3, 3)
