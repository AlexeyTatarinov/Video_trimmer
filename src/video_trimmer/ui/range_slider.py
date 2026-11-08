"""Two-handle range slider over [0, maximum] in seconds."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from video_trimmer.ui import theme

HANDLE_W = 24  # horizontal room reserved at each end (handle diameter is 20)
HANDLE_R = 10.0


class RangeSlider(QWidget):
    rangeChanged = Signal(float, float)  # low, high
    # v0.2: which handle ("start" or "end") changed and its new value in seconds.
    # Emitted for every change of that handle (mouse drag and programmatic setters).
    handleMoved = Signal(str, float)
    dragStarted = Signal(str)   # "start" | "end": the user pressed that handle
    dragFinished = Signal(str)  # "start" | "end": the user released it

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._max = 1.0
        self._low = 0.0
        self._high = 1.0
        self._active: str | None = None
        self._hover = False
        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumHeight(40)
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
            if self._low != old[0]:
                self.handleMoved.emit("start", self._low)
            if self._high != old[1]:
                self.handleMoved.emit("end", self._high)

    def is_dragging(self) -> bool:
        return self._active is not None

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
        self.dragStarted.emit(self._active_name())
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._active:
            self._drag_to(event.position().x())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._active is None:
            return
        name = self._active_name()
        self._active = None
        self.update()
        self.dragFinished.emit(name)

    def _active_name(self) -> str:
        return "start" if self._active == "low" else "end"

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def _drag_to(self, x: float) -> None:
        value = self.x_to_value(x)
        if self._active == "low":
            self.setLow(value)
        elif self._active == "high":
            self.setHigh(value)

    # ---- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        th = theme.current()
        p = QPainter(self)
        cy = self.height() / 2
        xl, xh = self.value_to_x(self._low), self.value_to_x(self._high)
        left, right = self._track()
        enabled = self.isEnabled()
        theme.paint_groove(p, left, right, cy, th, enabled, height=8.0)
        theme.paint_fill(p, xl, xh, cy, th, enabled, height=8.0)
        for name, x in (("low", xl), ("high", xh)):
            hot = self._active == name or (self._hover and self._active is None)
            theme.paint_handle(p, QPointF(x, cy), th, HANDLE_R, hot=self._active == name or hot,
                               enabled=enabled)
