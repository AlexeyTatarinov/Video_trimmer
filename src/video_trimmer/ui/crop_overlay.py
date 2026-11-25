"""Red crop frame over the video picture (v0.4.0).

``CropOverlay`` is a transparent child widget that covers its host (the preview surface of the
main window or the full-screen window). Both hosts paint the video frames themselves (QVideoSink
-> QImage), so this ordinary, non-native widget is always painted on top of the picture, on every
platform.

Coordinates:
* the area is kept in integer **source pixels** (``Crop``), even width/height, at least 32x32,
  always inside the picture; the full frame is reported as ``None`` (no crop);
* the *base rectangle* is the letterboxed picture inside the widget (aspect ratio kept);
* the *view* (Ctrl+wheel zoom and pan) scales the picture around a normalised centre; it never
  changes the area. The host paints the frame into ``picture_rect()``.

Mouse: drag inside the frame = move; drag one of the 8 handles = resize (free proportions);
wheel over the frame = zoom the area around the cursor; Ctrl+wheel = zoom the view; middle drag
or Space+drag = pan the view; double middle click = fit the view. A left double click that is not
on a handle is passed on to the host (full screen toggle).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from video_trimmer.ui.crop_types import Crop, even_floor, is_full, min_size

HANDLES = ("tl", "t", "tr", "r", "br", "b", "bl", "l")

_CURSORS = {
    "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
    "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
    "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
    "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
}


def fit_rectf(src: QSize, dst: QRect) -> QRectF:
    """Largest rectangle of the aspect of ``src`` inside ``dst``, centred (same rounding as
    fullscreen.fit_rect, so both hosts agree pixel for pixel)."""
    if src.width() <= 0 or src.height() <= 0 or dst.width() <= 0 or dst.height() <= 0:
        return QRectF()
    scale = min(dst.width() / src.width(), dst.height() / src.height())
    w = max(1, min(dst.width(), round(src.width() * scale)))
    h = max(1, min(dst.height(), round(src.height() * scale)))
    return QRectF(dst.left() + (dst.width() - w) // 2, dst.top() + (dst.height() - h) // 2, w, h)


class CropOverlay(QWidget):
    areaChanged = Signal(object)   # Crop, or None for the full frame (only on user actions)
    viewChanged = Signal()         # the host repaints the picture

    FRAME_COLOR = QColor(235, 38, 38)
    SHADE = QColor(0, 0, 0, 115)
    HANDLE = 9            # drawn handle size, px
    GRAB = 9              # handle hit radius, px
    AREA_STEP = 0.8       # one "Zoom in" press: the area becomes 80% as large
    WHEEL_STEP = 0.85     # one wheel notch over the frame
    VIEW_STEP = 1.25      # one Ctrl+wheel notch
    MAX_VIEW_ZOOM = 8.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cropOverlay")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self._src = QSize()          # source size (VideoInfo width x height, displayed)
        self._frame = QSize()        # size of the frames being painted (aspect fallback)
        self._area = (0, 0, 0, 0)    # x, y, w, h in source pixels
        self._zoom = 1.0
        self._cx, self._cy = 0.5, 0.5
        self._interactive = True
        self._space = False
        self._drag: dict | None = None

    # ------------------------------------------------------------------ source / state
    def source_size(self) -> QSize:
        return QSize(self._src)

    def has_source(self) -> bool:
        return self._src.width() > 0 and self._src.height() > 0

    def set_source_size(self, width: int, height: int) -> None:
        """A new video: full frame, fitted view."""
        new = QSize(max(int(width), 0), max(int(height), 0))
        if new != self._src:
            self._frame = QSize()      # frames of the previous video say nothing about this one
        self._src = new
        self._area = (0, 0, self._src.width(), self._src.height())
        self._drag = None
        self._zoom, self._cx, self._cy = 1.0, 0.5, 0.5
        self.viewChanged.emit()
        self.update()

    def set_frame_size(self, size: QSize) -> None:
        if size.isValid() and size != self._frame:
            self._frame = QSize(size)
            self.viewChanged.emit()
            self.update()

    def set_interactive(self, on: bool) -> None:
        self._interactive = bool(on)
        if not on:
            self._drag = None
            self.unsetCursor()

    def is_interactive(self) -> bool:
        return self._interactive and self.has_source()

    def area(self):
        """The area to save, or None for the full frame."""
        if not self.has_source():
            return None
        x, y, w, h = self._area
        if is_full(x, y, w, h, self._src.width(), self._src.height()):
            return None
        return Crop(x, y, w, h)

    def area_rect(self):
        """The area as a Crop, also for the full frame."""
        return Crop(*self._area)

    def set_area(self, crop, emit: bool = False) -> None:
        """Put ``crop`` (or None = full frame) into the frame, clamped and evened."""
        if not self.has_source():
            return
        W, H = self._src.width(), self._src.height()
        if crop is None:
            new = (0, 0, W, H)
        else:
            lo = min_size(W, H)
            w = min(max(even_floor(int(crop.w)), lo), even_floor(W))
            h = min(max(even_floor(int(crop.h)), lo), even_floor(H))
            x = min(max(int(crop.x), 0), W - w)
            y = min(max(int(crop.y), 0), H - h)
            new = (0, 0, W, H) if is_full(x, y, w, h, W, H) else (x, y, w, h)
        self._apply(new, emit)

    def reset_area(self) -> None:
        """"Full frame"."""
        self.set_area(None, emit=True)

    def _apply(self, new: tuple, emit: bool) -> None:
        changed = tuple(new) != self._area
        self._area = tuple(int(v) for v in new)
        self.update()
        if emit and changed:
            self.areaChanged.emit(self.area())

    # ------------------------------------------------------------------ geometry
    def _display_size(self) -> QSize:
        """Aspect of the painted picture: the frames being painted, else the source size."""
        if self._frame.isValid() and not self._frame.isEmpty():
            return self._frame
        return self._src

    def base_rect(self) -> QRectF:
        """The letterboxed picture at view zoom 1."""
        return fit_rectf(self._display_size(), self.rect())

    def picture_rect(self) -> QRectF:
        """Where the picture is painted (view zoom and pan applied)."""
        base = self.base_rect()
        if base.isEmpty() or self._zoom == 1.0:
            return base
        w, h = base.width() * self._zoom, base.height() * self._zoom
        c = base.center()
        return QRectF(c.x() - self._cx * w, c.y() - self._cy * h, w, h)

    def _scale(self) -> tuple[float, float]:
        pic = self.picture_rect()
        if pic.isEmpty() or not self.has_source():
            return 0.0, 0.0
        return pic.width() / self._src.width(), pic.height() / self._src.height()

    def source_to_widget(self, p: QPointF) -> QPointF:
        pic = self.picture_rect()
        sx, sy = self._scale()
        return QPointF(pic.left() + p.x() * sx, pic.top() + p.y() * sy)

    def widget_to_source(self, p: QPointF) -> QPointF:
        pic = self.picture_rect()
        sx, sy = self._scale()
        if sx <= 0 or sy <= 0:
            return QPointF()
        return QPointF((p.x() - pic.left()) / sx, (p.y() - pic.top()) / sy)

    def frame_rect(self) -> QRectF:
        x, y, w, h = self._area
        a = self.source_to_widget(QPointF(x, y))
        b = self.source_to_widget(QPointF(x + w, y + h))
        return QRectF(a, b)

    def _handle_center(self, name: str) -> QPointF:
        r = self.frame_rect()
        xs = {"l": r.left(), "c": r.center().x(), "r": r.right()}
        ys = {"t": r.top(), "c": r.center().y(), "b": r.bottom()}
        hx = "l" if "l" in name else "r" if "r" in name else "c"
        hy = "t" if "t" in name else "b" if "b" in name else "c"
        return QPointF(xs[hx], ys[hy])

    def handle_rect(self, name: str) -> QRectF:
        c = self._handle_center(name)
        s = self.HANDLE
        return QRectF(c.x() - s / 2, c.y() - s / 2, s, s)

    def handle_at(self, pos: QPointF):
        """Name of the handle under ``pos`` (corners win over edges), or None."""
        if not self.has_source():
            return None
        pos = QPointF(pos)
        best, best_d = None, None
        for name in HANDLES:
            c = self._handle_center(name)
            d = max(abs(c.x() - pos.x()), abs(c.y() - pos.y()))
            if d <= self.GRAB:
                rank = (d, 0 if len(name) == 2 else 1)
                if best_d is None or rank < best_d:
                    best, best_d = name, rank
        return best

    def in_frame(self, pos: QPointF) -> bool:
        return self.frame_rect().contains(QPointF(pos))

    # ------------------------------------------------------------------ area zoom
    def zoom_in(self) -> None:
        self._zoom_area(self.AREA_STEP, None)

    def zoom_out(self) -> None:
        self._zoom_area(1.0 / self.AREA_STEP, None)

    def _zoom_area(self, factor: float, anchor: QPointF | None) -> None:
        """Scale the area by ``factor`` keeping ``anchor`` (source px; default: centre) in place."""
        if not self.has_source():
            return
        W, H = self._src.width(), self._src.height()
        x, y, w, h = self._area
        lo = min_size(W, H)
        s = max(factor, lo / w, lo / h)
        s = min(s, W / w, H / h)
        if anchor is None:
            anchor = QPointF(x + w / 2, y + h / 2)
        ax = min(max(anchor.x(), 0.0), float(W))
        ay = min(max(anchor.y(), 0.0), float(H))
        nw = min(max(even_floor(round(w * s)), lo), even_floor(W))
        nh = min(max(even_floor(round(h * s)), lo), even_floor(H))
        if nw >= even_floor(W) and nh >= even_floor(H):
            self._apply((0, 0, W, H), True)
            return
        fx = (ax - x) / w if w else 0.5
        fy = (ay - y) / h if h else 0.5
        nx = int(round(ax - fx * nw))
        ny = int(round(ay - fy * nh))
        nx = min(max(nx, 0), W - nw)
        ny = min(max(ny, 0), H - nh)
        self._apply((nx, ny, nw, nh), True)

    # ------------------------------------------------------------------ view zoom / pan
    def view_zoom(self) -> float:
        return self._zoom

    def set_view_zoom(self, zoom: float, anchor: QPointF | None = None) -> None:
        """Zoom the view keeping the widget point ``anchor`` (default: the centre) still."""
        base = self.base_rect()
        z = min(max(float(zoom), 1.0), self.MAX_VIEW_ZOOM)
        if base.isEmpty():
            self._zoom = z
            return
        pic = self.picture_rect()
        if anchor is None:
            anchor = base.center()
        ux = (anchor.x() - pic.left()) / pic.width()
        uy = (anchor.y() - pic.top()) / pic.height()
        self._zoom = z
        nw, nh = base.width() * z, base.height() * z
        left, top = anchor.x() - ux * nw, anchor.y() - uy * nh
        self._cx = (base.center().x() - left) / nw
        self._cy = (base.center().y() - top) / nh
        self._clamp_view()
        self.viewChanged.emit()
        self.update()

    def fit_view(self) -> None:
        self._zoom, self._cx, self._cy = 1.0, 0.5, 0.5
        self.viewChanged.emit()
        self.update()

    def pan_view(self, dx: float, dy: float) -> None:
        pic = self.picture_rect()
        if pic.isEmpty() or self._zoom <= 1.0:
            return
        self._cx -= dx / pic.width()
        self._cy -= dy / pic.height()
        self._clamp_view()
        self.viewChanged.emit()
        self.update()

    def _clamp_view(self) -> None:
        if self._zoom <= 1.0:
            self._zoom, self._cx, self._cy = 1.0, 0.5, 0.5
            return
        m = 0.5 / self._zoom
        self._cx = min(max(self._cx, m), 1.0 - m)
        self._cy = min(max(self._cy, m), 1.0 - m)

    def set_space_held(self, held: bool) -> None:
        """Space + drag pans the view (the full-screen window forwards its Space key)."""
        self._space = bool(held)

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self.is_interactive():
            event.ignore()
            return
        pos = event.position()
        btn = event.button()
        if btn == Qt.MiddleButton or (btn == Qt.LeftButton and self._space):
            self._drag = {"kind": "pan", "last": QPointF(pos)}
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if btn != Qt.LeftButton:
            event.ignore()
            return
        handle = self.handle_at(pos)
        if handle is None and not self.in_frame(pos):
            event.ignore()                     # outside the frame: nothing to drag
            return
        self._drag = {"kind": handle or "move", "start": self.widget_to_source(pos), "area": self._area}
        if handle is None:
            self.setCursor(Qt.SizeAllCursor)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        if self._drag is None:
            if self.is_interactive():
                self._hover_cursor(pos)
            event.ignore()
            return
        if self._drag["kind"] == "pan":
            last = self._drag["last"]
            self.pan_view(pos.x() - last.x(), pos.y() - last.y())
            self._drag["last"] = QPointF(pos)
        else:
            p = self.widget_to_source(pos)
            start = self._drag["start"]
            self._drag_to(self._drag["kind"], self._drag["area"], p.x() - start.x(), p.y() - start.y())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            event.ignore()
            return
        self._drag = None
        self._hover_cursor(event.position())
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MiddleButton and self.is_interactive():
            self.fit_view()
            event.accept()
            return
        if (event.button() == Qt.LeftButton and self.is_interactive()
                and self.handle_at(event.position()) is not None):
            event.accept()                     # a double click on a handle does nothing
            return
        event.ignore()                         # the host toggles full screen

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self.is_interactive():
            event.ignore()
            return
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            event.ignore()
            return
        pos = event.position()
        if event.modifiers() & Qt.ControlModifier:
            self.set_view_zoom(self._zoom * (self.VIEW_STEP ** steps), anchor=pos)
            event.accept()
        elif self.in_frame(pos):
            self._zoom_area(self.WHEEL_STEP ** steps, self.widget_to_source(pos))
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.handle_key(event):
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def handle_key(self, event, space: bool = True) -> bool:
        """+/- zoom the area; Space (held) arms panning. Returns True when the key was used."""
        if not self.is_interactive():
            return False
        k = event.key()
        if k in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_in()
        elif k in (Qt.Key_Minus, Qt.Key_Underscore):
            self.zoom_out()
        elif space and k == Qt.Key_Space:
            if not event.isAutoRepeat():
                self._space = True
        else:
            return False
        event.accept()
        return True

    def _hover_cursor(self, pos: QPointF) -> None:
        if not self.is_interactive():
            self.unsetCursor()
            return
        handle = self.handle_at(pos)
        if handle is not None:
            self.setCursor(_CURSORS[handle])
        elif self._space and self._zoom > 1.0:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()                 # the host's cursor (also the hidden one)

    def _drag_to(self, kind: str, area: tuple, dx: float, dy: float) -> None:
        W, H = self._src.width(), self._src.height()
        x, y, w, h = area
        if kind == "move":
            nx = min(max(int(round(x + dx)), 0), W - w)
            ny = min(max(int(round(y + dy)), 0), H - h)
            self._apply((nx, ny, w, h), True)
            return
        lo = min_size(W, H)
        nx, nw = self._resize_axis(x, w, dx, "l" in kind, "r" in kind, W, lo)
        ny, nh = self._resize_axis(y, h, dy, "t" in kind, "b" in kind, H, lo)
        if is_full(nx, ny, nw, nh, W, H):
            self._apply((0, 0, W, H), True)
        else:
            self._apply((nx, ny, nw, nh), True)

    @staticmethod
    def _resize_axis(pos: int, size: int, d: float, low_edge: bool, high_edge: bool,
                     limit: int, lo: int) -> tuple[int, int]:
        """One axis of a resize: the moving edge follows ``d``; the other edge stays put."""
        start, end = pos, pos + size
        if low_edge:
            new = min(max(start + d, 0.0), end - lo)
            size = max(even_floor(end - int(round(new))), lo)
            start = end - size
            if start < 0:
                start, size = end - even_floor(end), even_floor(end)
            return start, size
        if high_edge:
            new = min(max(end + d, start + lo), float(limit))
            size = max(even_floor(int(round(new)) - start), lo)
            if start + size > limit:
                size = even_floor(limit - start)
            return start, size
        if size % 2:
            size -= 1                              # an odd full side becomes even once edited
        return start, size

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:  # noqa: N802
        if not self.has_source():
            return
        pic = self.picture_rect()
        if pic.isEmpty():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        fr = self.frame_rect()
        full = self.area() is None
        if not full:                            # shade the part that will not be saved
            shade = QPainterPath()
            shade.addRect(pic.intersected(QRectF(self.rect())))
            hole = QPainterPath()
            hole.addRect(fr)
            p.fillPath(shade.subtracted(hole), self.SHADE)
        inner = fr.adjusted(1.5, 1.5, -1.5, -1.5) if full else fr
        p.setBrush(Qt.NoBrush)
        outline = QPen(QColor(0, 0, 0, 150), 4.0)      # keeps the red line visible on red pictures
        outline.setJoinStyle(Qt.MiterJoin)
        p.setPen(outline)
        p.drawRect(inner)
        pen = QPen(self.FRAME_COLOR, 2.0)
        pen.setJoinStyle(Qt.MiterJoin)
        p.setPen(pen)
        p.drawRect(inner)
        p.setPen(QPen(QColor(255, 255, 255), 1.2))
        p.setBrush(self.FRAME_COLOR)
        for name in HANDLES:
            r = self.handle_rect(name)
            if full:   # keep the handles of the full frame inside the picture
                c = self._handle_center(name)
                c.setX(min(max(c.x(), fr.left() + self.HANDLE / 2), fr.right() - self.HANDLE / 2))
                c.setY(min(max(c.y(), fr.top() + self.HANDLE / 2), fr.bottom() - self.HANDLE / 2))
                r.moveCenter(c)
            p.drawRect(r)
        if not full:                            # the size of the area, inside its top-left corner
            text = f"{self._area[2]}x{self._area[3]}"
            f = QFont(self.font())
            f.setPointSizeF(max(f.pointSizeF() * 0.85, 7.0))
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            fm = p.fontMetrics()
            tw, th = fm.horizontalAdvance(text) + 10, fm.height() + 2
            if fr.width() > tw + 2 * self.HANDLE and fr.height() > th + 2 * self.HANDLE:
                box = QRectF(fr.left() + self.HANDLE, fr.top() + self.HANDLE, tw, th)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 150))
                p.drawRoundedRect(box, 4, 4)
                p.setPen(QColor(255, 255, 255))
                p.drawText(box, Qt.AlignCenter, text)
