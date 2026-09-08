"""Compatibility facade for the legacy view API, implemented with PySide6.

The project view/controller boundary predates the Qt migration.  Keeping this
facade local to the GUI package lets the view retain that stable boundary while
all actual windows, widgets, dialogs and timers are native Qt objects.
"""

# Tk-compatible method names intentionally override a few Qt method names with
# different signatures (for example ``geometry`` and ``destroy``).
# pyright: reportIncompatibleMethodOverride=false

from __future__ import annotations

import re
import sys
import threading
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal, QSize, Slot
from PySide6.QtGui import QColor, QFont, QImage, QPalette, QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


_appearance_mode = "Dark"
_widgets: "weakref.WeakSet[Any]" = weakref.WeakSet()
_qt_app: QApplication | None = None
_image_cache: dict[tuple[str, tuple[int, int] | None, str], QPixmap] = {}


def _app() -> QApplication:
    global _qt_app
    app = cast(QApplication | None, QApplication.instance())
    if app is None:
        app = QApplication(sys.argv)
    _qt_app = app
    app.setStyle("Fusion")
    default_font = QFont("Segoe UI")
    default_font.setPixelSize(13)
    app.setFont(default_font)
    return app


def _color(value: Any, default: str = "transparent") -> str:
    if value is None:
        return default
    if isinstance(value, (tuple, list)):
        return str(value[0] if _appearance_mode == "Light" else value[-1])
    if value == "transparent":
        return "transparent"
    return str(value)


def set_appearance_mode(mode: str) -> None:
    global _appearance_mode
    _appearance_mode = "Light" if str(mode).lower() == "light" else "Dark"
    for widget in list(_widgets):
        try:
            widget._refresh_style()
        except (RuntimeError, AttributeError):
            pass


def get_appearance_mode() -> str:
    return _appearance_mode


def set_default_color_theme(_theme: str) -> None:
    """The original application uses the built-in dark-blue palette."""


class _Invoker(QObject):
    call = Signal(int, object)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.call.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    @Slot(int, object)
    def _dispatch(self, ms: int, callback: Callable[[], Any]) -> None:
        """Run callbacks in the invoker's (GUI) thread."""
        if ms <= 0:
            callback()
        else:
            QTimer.singleShot(ms, callback)


_invoker: _Invoker | None = None


def _ensure_gui_invoker() -> _Invoker:
    global _invoker
    if _invoker is None:
        # Ownership by QApplication guarantees destruction in the GUI thread,
        # before Python tears down module globals.
        _invoker = _Invoker(_app())
    return _invoker


def _invoke_later(ms: int, callback: Callable[[], Any]) -> None:
    invoker = _ensure_gui_invoker()
    delay = max(0, int(ms))
    if threading.current_thread() is threading.main_thread():
        QTimer.singleShot(delay, callback)
    else:
        invoker.call.emit(delay, callback)


class Variable:
    def __init__(self, value: Any = None) -> None:
        self._value = value
        self._traces: list[Callable[..., Any]] = []

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        if self._value == value:
            return
        self._value = value
        for callback in list(self._traces):
            callback("", "", "write")

    def trace_add(self, _mode: str, callback: Callable[..., Any]) -> str:
        self._traces.append(callback)
        return str(id(callback))


class StringVar(Variable):
    def __init__(self, value: str = "") -> None:
        super().__init__(value)


class BooleanVar(Variable):
    def __init__(self, value: bool = False) -> None:
        super().__init__(bool(value))


class IntVar(Variable):
    def __init__(self, value: int = 0) -> None:
        super().__init__(int(value))


@dataclass(frozen=True)
class CTkFont:
    family: str = "Segoe UI"
    size: int = 13
    weight: str = "normal"
    slant: str = "roman"

    def to_qfont(self) -> QFont:
        # CustomTkinter interprets positive CTkFont sizes as screen pixels.
        # QFont(family, size) treats them as typographic points, which grows
        # with Windows DPI and made text overflow the original controls.
        font = QFont(self.family)
        font.setPixelSize(self.size)
        font.setBold(self.weight == "bold")
        font.setItalic(self.slant == "italic")
        return font


class CTkImage:
    def __init__(self, light_image: Any, dark_image: Any = None, size: tuple[int, int] | None = None) -> None:
        self.light_image = light_image
        self.dark_image = dark_image or light_image
        self.size = size

    def pixmap(self) -> QPixmap:
        image = self.light_image if _appearance_mode == "Light" else self.dark_image
        source = str(getattr(image, "filename", id(image)))
        cache_key = (source, self.size, _appearance_mode)
        cached = _image_cache.get(cache_key)
        if cached is not None:
            return cached
        rgba = image.convert("RGBA")
        data = rgba.tobytes("raw", "RGBA")
        qimage = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()
        pixmap = QPixmap.fromImage(qimage)
        if self.size:
            pixmap = pixmap.scaled(*self.size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        _image_cache[cache_key] = pixmap
        return pixmap


def _pair(value: Any) -> tuple[int, int]:
    if isinstance(value, (tuple, list)):
        return int(value[0]), int(value[-1])
    n = int(value or 0)
    return n, n


def _alignment(anchor: str | None) -> Qt.AlignmentFlag:
    mapping = {
        "w": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        "e": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        "n": Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        "s": Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        "center": Qt.AlignmentFlag.AlignCenter,
    }
    return mapping.get(anchor or "center", Qt.AlignmentFlag.AlignCenter)


class _LayoutHost:
    def _init_host(self) -> None:
        self._layout_kind: str | None = None
        self._layout: QLayout | None = None
        self._children: list[Any] = []
        self._pack_right_count = 0

    def _layout_target(self) -> QWidget:
        target: QWidget = cast(QWidget, self)
        return target

    def _child_parent(self) -> QWidget:
        return self._layout_target()

    def _register_child(self, child: Any) -> None:
        if child not in self._children:
            self._children.append(child)

    def _invalidate_layout_chain(self) -> None:
        current: Any = self
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            layout = getattr(current, "_layout", None)
            if layout is not None:
                layout.invalidate()
            current.updateGeometry()
            wrapper = getattr(current, "_layout_wrapper", None)
            if wrapper is not None:
                if wrapper.layout() is not None:
                    wrapper.layout().invalidate()
                wrapper.updateGeometry()
            current = getattr(current, "master", None)

    def _ensure_pack(self, horizontal: bool) -> QHBoxLayout | QVBoxLayout:
        if self._layout is None:
            self._layout_kind = "pack"
            self._layout = QHBoxLayout() if horizontal else QVBoxLayout()
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            if isinstance(self._layout, QVBoxLayout):
                self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            else:
                self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            if getattr(self, "_unconstrained_layout", False):
                self._layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            self._layout_target().setLayout(self._layout)
        return cast(QHBoxLayout | QVBoxLayout, self._layout)

    def _ensure_grid(self) -> QGridLayout:
        if self._layout is None:
            self._layout_kind = "grid"
            self._layout = QGridLayout()
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            if getattr(self, "_unconstrained_layout", False):
                self._layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            self._layout_target().setLayout(self._layout)
        if not isinstance(self._layout, QGridLayout):
            raise RuntimeError("Nie można mieszać pack i grid w jednym kontenerze")
        return self._layout

    def _wrapper(self, child: QWidget, padx: Any, pady: Any) -> QWidget:
        existing_wrapper = getattr(child, "_layout_wrapper", None)
        if isinstance(existing_wrapper, QWidget):
            return existing_wrapper
        left, right = _pair(padx)
        top, bottom = _pair(pady)
        wrapper = QWidget(self._layout_target())
        wrapper.setObjectName("layoutWrapper")
        wrapper.setStyleSheet("QWidget#layoutWrapper { background: transparent; }")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(left, top, right, bottom)
        layout.setSpacing(0)
        child_alignment = Qt.AlignmentFlag(0)
        if isinstance(child, QLabel):
            anchor = getattr(child, "_options", {}).get("anchor")
            justify = getattr(child, "_options", {}).get("justify", "center")
            if anchor:
                child_alignment = _alignment(anchor)
            elif justify == "center":
                child_alignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            elif justify == "right":
                child_alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            else:
                child_alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        layout.addWidget(child, 0, child_alignment)
        setattr(child, "_layout_wrapper", wrapper)
        return wrapper

    def _add_pack(self, child: QWidget, **kwargs: Any) -> None:
        side = kwargs.get("side", "top")
        horizontal = side in ("left", "right")
        layout = self._ensure_pack(horizontal)
        wrapper = self._wrapper(child, kwargs.get("padx", 0), kwargs.get("pady", 0))
        expand = bool(kwargs.get("expand"))
        fill = kwargs.get("fill")
        if fill in ("x", "both"):
            wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, wrapper.sizePolicy().verticalPolicy())
        if fill in ("y", "both"):
            wrapper.setSizePolicy(wrapper.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)
        if isinstance(layout, QVBoxLayout) and not expand and fill not in ("y", "both"):
            wrapper.setSizePolicy(wrapper.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Fixed)
        if isinstance(layout, QHBoxLayout) and not expand and fill not in ("x", "both"):
            wrapper.setSizePolicy(QSizePolicy.Policy.Fixed, wrapper.sizePolicy().verticalPolicy())
        stretch = 1 if expand else 0
        if isinstance(layout, QHBoxLayout) and side == "right":
            if self._pack_right_count == 0:
                layout.addStretch(1)
            index = max(0, layout.count() - self._pack_right_count)
            layout.insertWidget(index, wrapper, stretch)
            self._pack_right_count += 1
        elif side == "bottom" and isinstance(layout, QVBoxLayout):
            layout.addWidget(wrapper, stretch, Qt.AlignmentFlag.AlignBottom)
        else:
            alignment = Qt.AlignmentFlag(0)
            anchor = kwargs.get("anchor")
            if anchor:
                alignment = _alignment(anchor)
            layout.addWidget(wrapper, stretch, alignment)
        wrapper.show()
        child.show()
        self._invalidate_layout_chain()

    def _add_grid(self, child: QWidget, **kwargs: Any) -> None:
        layout = self._ensure_grid()
        wrapper = self._wrapper(child, kwargs.get("padx", 0), kwargs.get("pady", 0))
        sticky = str(kwargs.get("sticky", ""))
        alignment = Qt.AlignmentFlag(0)
        if "w" in sticky and "e" not in sticky:
            alignment |= Qt.AlignmentFlag.AlignLeft
        if "e" in sticky and "w" not in sticky:
            alignment |= Qt.AlignmentFlag.AlignRight
        if "n" in sticky and "s" not in sticky:
            alignment |= Qt.AlignmentFlag.AlignTop
        if "s" in sticky and "n" not in sticky:
            alignment |= Qt.AlignmentFlag.AlignBottom
        if "ew" in sticky or ("e" in sticky and "w" in sticky):
            wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, wrapper.sizePolicy().verticalPolicy())
        if "ns" in sticky or ("n" in sticky and "s" in sticky):
            wrapper.setSizePolicy(wrapper.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)
        layout.addWidget(
            wrapper,
            int(kwargs.get("row", 0)),
            int(kwargs.get("column", 0)),
            int(kwargs.get("rowspan", 1)),
            int(kwargs.get("columnspan", 1)),
            alignment,
        )
        wrapper.show()
        child.show()
        self._invalidate_layout_chain()

    def _add_place(self, child: QWidget, **kwargs: Any) -> None:
        layout = self._ensure_grid()
        wrapper = self._wrapper(child, kwargs.get("padx", 0), kwargs.get("pady", 0))
        layout.addWidget(wrapper, 0, 0, _alignment(kwargs.get("anchor", "center")))
        wrapper.show()
        child.show()
        self._invalidate_layout_chain()


class _WidgetMixin:
    master: Any

    if TYPE_CHECKING:
        # Concrete widgets combine this mixin with QWidget subclasses. This
        # hook describes that runtime composition to static type checkers.
        def __getattr__(self, name: str) -> Any: ...

    def _init_widget(self, master: Any, **kwargs: Any) -> None:
        self.master = master
        self._options = dict(kwargs)
        self._layout_wrapper: QWidget | None = None
        self._manager = ""
        self._last_layout: tuple[str, dict[str, Any]] | None = None
        if master is not None and hasattr(master, "_register_child"):
            master._register_child(self)
        _widgets.add(self)
        self._apply_dimensions(kwargs)

    def _apply_dimensions(self, options: dict[str, Any]) -> None:
        width = options.get("width")
        height = options.get("height")
        if width is not None:
            self.setMinimumWidth(int(width))
        if height is not None:
            self.setMinimumHeight(int(height))
            if options.get("height") and getattr(self, "_propagate", True) is False:
                self.setFixedHeight(int(height))

    def pack(self, **kwargs: Any) -> None:
        if not kwargs and self._last_layout and self._last_layout[0] == "pack":
            self._show_placement()
            return
        self._manager = "pack"
        self._last_layout = ("pack", dict(kwargs))
        self.master._add_pack(self, **kwargs)

    def grid(self, **kwargs: Any) -> None:
        if not kwargs and self._last_layout and self._last_layout[0] == "grid":
            self._show_placement()
            return
        self._manager = "grid"
        self._last_layout = ("grid", dict(kwargs))
        self.master._add_grid(self, **kwargs)

    def place(self, **kwargs: Any) -> None:
        self._manager = "place"
        self._last_layout = ("place", dict(kwargs))
        self.master._add_place(self, **kwargs)

    def _show_placement(self) -> None:
        self.show()
        if self._layout_wrapper:
            self._layout_wrapper.show()
        self._manager = self._last_layout[0] if self._last_layout else ""

    def pack_forget(self) -> None:
        self._hide_placement()

    def grid_remove(self) -> None:
        self._hide_placement()

    def grid_forget(self) -> None:
        self._hide_placement()

    def _hide_placement(self) -> None:
        self.hide()
        if self._layout_wrapper:
            self._layout_wrapper.hide()
        self._manager = ""

    def pack_propagate(self, enabled: bool) -> None:
        self._propagate = bool(enabled)
        if enabled:
            self.setMaximumHeight(16777215)
        elif self._options.get("height"):
            self.setFixedHeight(int(self._options["height"]))

    def grid_columnconfigure(self, column: int, weight: int = 0, minsize: int = 0) -> None:
        layout = self._ensure_grid()
        layout.setColumnStretch(column, weight)
        if minsize:
            layout.setColumnMinimumWidth(column, minsize)

    def grid_rowconfigure(self, row: int, weight: int = 0, minsize: int = 0) -> None:
        layout = self._ensure_grid()
        layout.setRowStretch(row, weight)
        if minsize:
            layout.setRowMinimumHeight(row, minsize)

    def configure(self, **kwargs: Any) -> None:
        self._options.update(kwargs)
        self._apply_dimensions(kwargs)
        if "height" in kwargs:
            self.setFixedHeight(int(kwargs["height"]))
        if "state" in kwargs:
            state = kwargs["state"]
            self.setEnabled(state not in ("disabled", "readonly"))
        self._refresh_style()

    config = configure

    def register(self, callback: Callable[..., Any]) -> Callable[..., Any]:
        return callback

    def focus_set(self) -> None:
        self.setFocus()

    def after(self, ms: int, callback: Callable[[], Any]) -> None:
        _invoke_later(ms, callback)

    def bind(self, event: str, callback: Callable[..., Any]) -> None:
        if event == "<Button-1>":
            old = self.mousePressEvent

            def pressed(qevent: Any) -> None:
                callback(qevent)
                try:
                    old(qevent)
                except TypeError:
                    pass

            self.mousePressEvent = pressed
        elif event == "<Return>" and hasattr(self, "returnPressed"):
            self.returnPressed.connect(lambda: callback(None))

    def winfo_children(self) -> list[Any]:
        return [child for child in getattr(self, "_children", []) if child.winfo_exists()]

    def winfo_exists(self) -> bool:
        try:
            self.objectName()
            return not getattr(self, "_destroyed", False)
        except RuntimeError:
            return False

    def winfo_manager(self) -> str:
        return self._manager

    def winfo_width(self) -> int:
        return self.width()

    def winfo_height(self) -> int:
        return self.height()

    def winfo_reqheight(self) -> int:
        return self.sizeHint().height()

    def winfo_rootx(self) -> int:
        return self.mapToGlobal(self.rect().topLeft()).x()

    def winfo_rooty(self) -> int:
        return self.mapToGlobal(self.rect().topLeft()).y()

    def winfo_toplevel(self) -> Any:
        window = self.window()
        return window

    def update_idletasks(self) -> None:
        _app().processEvents()

    def tkraise(self) -> None:
        self.raise_()

    def lift(self) -> None:
        self.raise_()

    def focus_force(self) -> None:
        self.activateWindow()
        self.setFocus()

    def destroy(self) -> None:
        self._destroyed = True
        if isinstance(self, QDialog):
            # A hidden/deferred-delete application-modal QDialog can continue
            # blocking the main window until Qt processes deleteLater().
            self.hide()
            self.setWindowModality(Qt.WindowModality.NonModal)
        if self.master is not None and hasattr(self.master, "_children"):
            try:
                self.master._children.remove(self)
            except ValueError:
                pass
        if self._layout_wrapper is not None:
            self._layout_wrapper.hide()
            self._layout_wrapper.deleteLater()
        self.close()
        self.deleteLater()

    def _refresh_style(self) -> None:
        pass


class CTk(_WidgetMixin, _LayoutHost, QWidget):
    def __init__(self, **kwargs: Any) -> None:
        _app()
        _ensure_gui_invoker()
        QWidget.__init__(self)
        self.master = None
        self._unconstrained_layout = True
        self._init_host()
        self._init_widget(None, **kwargs)
        self._refresh_style()

    def title(self, value: str) -> None:
        self.setWindowTitle(value)

    def geometry(self, value: str) -> None:
        if re.match(r"^\d+x\d+", value):
            self._explicit_geometry = True
        _set_geometry(self, value)

    def minsize(self, width: int, height: int) -> None:
        self.setMinimumSize(width, height)

    def resizable(self, horizontal: bool, vertical: bool) -> None:
        if not horizontal:
            self.setFixedWidth(self.width())
        if not vertical:
            self.setFixedHeight(self.height())

    def mainloop(self) -> int:
        self.show()
        return _app().exec()

    def wait_window(self, window: Any) -> None:
        if isinstance(window, QDialog):
            window.exec()

    def _refresh_style(self) -> None:
        bg = "#f2f2f2" if _appearance_mode == "Light" else "#242424"
        self.setStyleSheet(f"CTk {{ background-color: {bg}; }}")


class CTkToplevel(_WidgetMixin, _LayoutHost, QDialog):
    def __init__(self, master: Any = None, **kwargs: Any) -> None:
        _app()
        QDialog.__init__(self, master)
        self._unconstrained_layout = True
        self._init_host()
        self._init_widget(master, **kwargs)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._refresh_style()
        QTimer.singleShot(0, self.show)

    def title(self, value: str) -> None:
        self.setWindowTitle(value)

    def geometry(self, value: str) -> None:
        if re.match(r"^\d+x\d+", value):
            self._explicit_geometry = True
        _set_geometry(self, value)

    def minsize(self, width: int, height: int) -> None:
        self.setMinimumSize(width, height)

    def resizable(self, horizontal: bool, vertical: bool) -> None:
        self.setSizeGripEnabled(horizontal or vertical)
        self._requested_resizable = (horizontal, vertical)
        self._size_locked = False

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if hasattr(self, "_requested_resizable") and not self._size_locked:
            # One short turn lets Qt polish nested layouts before we freeze a
            # non-resizable dialog at its requested content size.
            QTimer.singleShot(10, self._apply_requested_size)

    def _apply_requested_size(self) -> None:
        if self._size_locked:
            return
        horizontal, vertical = self._requested_resizable
        if getattr(self, "_explicit_geometry", False) and hasattr(self, "_explicit_size"):
            self.resize(self._explicit_size)
        else:
            window_layout = self.layout()
            if window_layout is not None:
                window_layout.invalidate()
                window_layout.activate()
                hint = window_layout.sizeHint()
            else:
                hint = self.sizeHint()
            width = max(200, min(hint.width(), 780))
            height = max(80, min(hint.height(), 720))
            self.resize(width, height)
        size = QSize(self.size())
        if not horizontal:
            self.setFixedWidth(size.width())
        if not vertical:
            self.setFixedHeight(size.height())
        self._size_locked = True

    def transient(self, parent: Any) -> None:
        # QDialog already receives ``parent`` in its constructor. Repeating
        # setParent() after the window has been scheduled for display hides it
        # on Windows and is illegal when called from a worker thread.
        # Keeping this method as a compatibility no-op preserves the existing
        # view code without changing Qt ownership.
        return None

    def grab_set(self) -> None:
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

    def grab_release(self) -> None:
        # Qt applies a changed windowModality reliably only while the window is
        # hidden. Every current caller releases the grab immediately before
        # destroying the dialog, so keeping it hidden is also flicker-free.
        self.hide()
        self.setWindowModality(Qt.WindowModality.NonModal)

    def attributes(self, name: str, value: Any) -> None:
        if name == "-topmost":
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(value))

    def protocol(self, name: str, callback: Callable[[], Any]) -> None:
        if name == "WM_DELETE_WINDOW":
            self._close_callback = callback

    def closeEvent(self, event: Any) -> None:
        callback = getattr(self, "_close_callback", None)
        if callback:
            callback()
            if self.isVisible():
                event.ignore()
                return
        self._destroyed = True
        self.hide()
        self.setWindowModality(Qt.WindowModality.NonModal)
        if self.master is not None and hasattr(self.master, "_children"):
            try:
                self.master._children.remove(self)
            except ValueError:
                pass
        event.accept()
        self.deleteLater()

    def _refresh_style(self) -> None:
        bg = _color(self._options.get("fg_color"), "#f2f2f2" if _appearance_mode == "Light" else "#242424")
        self.setStyleSheet(f"CTkToplevel {{ background-color: {bg}; }}")


def _set_geometry(widget: QWidget, value: str) -> None:
    size_match = re.match(r"^(\d+)x(\d+)", value)
    pos_match = re.search(r"\+(-?\d+)\+(-?\d+)$", value)
    if size_match:
        size = QSize(int(size_match.group(1)), int(size_match.group(2)))
        setattr(widget, "_explicit_size", size)
        widget.resize(size)
    if pos_match:
        widget.move(int(pos_match.group(1)), int(pos_match.group(2)))


class CTkFrame(_WidgetMixin, _LayoutHost, QFrame):
    def __init__(self, master: Any, **kwargs: Any) -> None:
        QFrame.__init__(self, master._child_parent())
        self._init_host()
        self._propagate = True
        self._init_widget(master, **kwargs)
        self._refresh_style()

    def _refresh_style(self) -> None:
        bg = _color(self._options.get("fg_color"), "#e5e5e5" if _appearance_mode == "Light" else "#2b2b2b")
        radius = int(self._options.get("corner_radius", 6))
        self.setStyleSheet(f"CTkFrame {{ background-color: {bg}; border-radius: {radius}px; }}")


class CTkScrollableFrame(_WidgetMixin, _LayoutHost, QScrollArea):
    def __init__(self, master: Any, **kwargs: Any) -> None:
        QScrollArea.__init__(self, master._child_parent())
        self._content = QWidget()
        self._init_host()
        self._init_widget(master, **kwargs)
        self.setWidget(self._content)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._refresh_style()

    def _layout_target(self) -> QWidget:
        return self._content

    def scroll_to_widget(self, widget: QWidget) -> None:
        self.ensureWidgetVisible(widget, 0, 12)

    def _refresh_style(self) -> None:
        bg = _color(self._options.get("fg_color"), "#e5e5e5" if _appearance_mode == "Light" else "#2b2b2b")
        self.setStyleSheet(
            f"QScrollArea {{ background: {bg}; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: {bg}; }}"
            "QScrollBar:vertical { width: 10px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #666; border-radius: 5px; min-height: 24px; }"
        )
        self._content.setStyleSheet(f"background: {bg};")


class CTkLabel(_WidgetMixin, QLabel):
    def __init__(self, master: Any, text: str = "", **kwargs: Any) -> None:
        QLabel.__init__(self, master._child_parent())
        kwargs["text"] = text
        self._variable: Variable | None = kwargs.get("textvariable")
        self._image = kwargs.get("image")
        self._init_widget(master, **kwargs)
        self.setMinimumHeight(int(kwargs.get("height", 28)))
        self.setText(str(self._variable.get() if self._variable else text))
        variable = self._variable
        if variable:
            variable.trace_add("write", lambda *_: self.setText(str(variable.get())))
        self.setAlignment(_alignment(kwargs.get("anchor") or ("w" if kwargs.get("justify") == "left" else "center")))
        self.setWordWrap(bool(kwargs.get("wraplength")))
        if kwargs.get("wraplength"):
            self.setFixedWidth(int(kwargs["wraplength"]))
        self._refresh_style()

    def configure(self, **kwargs: Any) -> None:
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))
        super().configure(**kwargs)

    def _refresh_style(self) -> None:
        color = _color(self._options.get("text_color"), "#1f1f1f" if _appearance_mode == "Light" else "#dce4ee")
        font = self._options.get("font")
        if isinstance(font, CTkFont):
            self.setFont(font.to_qfont())
        self.setStyleSheet(f"CTkLabel {{ color: {color}; background: transparent; }}")
        if self._image:
            self.setPixmap(self._image.pixmap())


class CTkButton(_WidgetMixin, QPushButton):
    def __init__(self, master: Any, text: str = "", command: Callable[[], Any] | None = None, **kwargs: Any) -> None:
        QPushButton.__init__(self, text, master._child_parent())
        kwargs.update(text=text, command=command)
        self._init_widget(master, **kwargs)
        if command:
            self.clicked.connect(command)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_style()

    def configure(self, **kwargs: Any) -> None:
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))
        super().configure(**kwargs)

    def sizeHint(self) -> QSize:
        return QSize(int(self._options.get("width", 140)), int(self._options.get("height", 28)))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _refresh_style(self) -> None:
        bg = _color(self._options.get("fg_color"), "#1f6aa5")
        hover = _color(self._options.get("hover_color"), "#144870")
        text = _color(self._options.get("text_color"), "#ffffff")
        radius = int(self._options.get("corner_radius", 6))
        font = self._options.get("font")
        if isinstance(font, CTkFont):
            self.setFont(font.to_qfont())
        self.setMinimumHeight(int(self._options.get("height", 28)))
        self.setStyleSheet(
            f"CTkButton {{ background: {bg}; color: {text}; border: none; border-radius: {radius}px; padding: 5px 10px; }}"
            f"CTkButton:hover {{ background: {hover}; }} CTkButton:pressed {{ background: {hover}; }}"
        )


class CTkEntry(_WidgetMixin, QLineEdit):
    def __init__(self, master: Any, **kwargs: Any) -> None:
        QLineEdit.__init__(self, master._child_parent())
        self._variable = kwargs.get("textvariable")
        validatecommand = kwargs.get("validatecommand")
        callback = validatecommand[0] if isinstance(validatecommand, tuple) else validatecommand
        self._validator_callback: Callable[[str], bool] | None = (
            cast(Callable[[str], bool], callback) if callable(callback) else None
        )
        self._syncing = False
        self._init_widget(master, **kwargs)
        self.setPlaceholderText(str(kwargs.get("placeholder_text", "")))
        if self._variable:
            self.setText(str(self._variable.get()))
            self.textChanged.connect(self._to_variable)
            self._variable.trace_add("write", lambda *_: self._from_variable())
        self._last_valid_text = self.text()
        if self._validator_callback:
            self.textEdited.connect(self._validate_edit)
        self._refresh_style()

    def _validate_edit(self, value: str) -> None:
        callback = self._validator_callback
        if callback is not None and callback(value):
            self._last_valid_text = value
            return
        cursor = self.cursorPosition()
        self._syncing = True
        self.setText(self._last_valid_text)
        self.setCursorPosition(max(0, cursor - 1))
        self._syncing = False

    def _to_variable(self, value: str) -> None:
        if self._variable and not self._syncing:
            self._variable.set(value)

    def _from_variable(self) -> None:
        variable = self._variable
        if variable is None:
            return
        value = str(variable.get())
        if value != self.text():
            self._syncing = True
            self.setText(value)
            self._syncing = False

    def get(self) -> str:
        return self.text()

    def delete(self, start: Any, end: Any = None) -> None:
        self.clear()

    def insert(self, index: Any, text: Any) -> None:
        if str(index) in ("0", "0.0"):
            self.setText(str(text))
        else:
            QLineEdit.insert(self, str(text))

    def register(self, callback: Callable[..., Any]) -> Callable[..., Any]:
        return callback

    def _refresh_style(self) -> None:
        bg = "#ffffff" if _appearance_mode == "Light" else "#343638"
        fg = "#1f1f1f" if _appearance_mode == "Light" else "#ffffff"
        border = "#b0b0b0" if _appearance_mode == "Light" else "#565b5e"
        self.setMinimumHeight(int(self._options.get("height", 28)))
        self.setStyleSheet(
            f"CTkEntry {{ background: {bg}; color: {fg}; border: 1px solid {border}; border-radius: 6px; padding: 4px 8px; }}"
        )


class CTkCheckBox(_WidgetMixin, QCheckBox):
    def __init__(self, master: Any, text: str = "", variable: Variable | None = None, **kwargs: Any) -> None:
        QCheckBox.__init__(self, text, master._child_parent())
        self._variable = variable
        self._syncing = False
        self._init_widget(master, text=text, variable=variable, **kwargs)
        if variable:
            self.setChecked(bool(variable.get()))
            self.toggled.connect(self._to_variable)
            variable.trace_add("write", lambda *_: self._from_variable())
        self._refresh_style()

    def _to_variable(self, checked: bool) -> None:
        if self._variable and not self._syncing:
            self._variable.set(bool(checked))

    def _from_variable(self) -> None:
        variable = self._variable
        if variable is None:
            return
        self._syncing = True
        self.setChecked(bool(variable.get()))
        self._syncing = False

    def select(self) -> None:
        self.setChecked(True)

    def deselect(self) -> None:
        self.setChecked(False)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if not self.isChecked():
            return

        option = QStyleOptionButton()
        self.initStyleOption(option)
        indicator = self.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, option, self,
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(Qt.GlobalColor.white, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        x, y, width, height = indicator.x(), indicator.y(), indicator.width(), indicator.height()
        painter.drawLine(
            x + int(width * 0.23), y + int(height * 0.52),
            x + int(width * 0.43), y + int(height * 0.72),
        )
        painter.drawLine(
            x + int(width * 0.43), y + int(height * 0.72),
            x + int(width * 0.78), y + int(height * 0.30),
        )
        painter.end()

    def _refresh_style(self) -> None:
        fg = "#1f1f1f" if _appearance_mode == "Light" else "#dce4ee"
        self.setStyleSheet(
            f"CTkCheckBox {{ color: {fg}; spacing: 7px; background: transparent; }}"
            "CTkCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #949a9f; border-radius: 4px; }"
            "CTkCheckBox::indicator:checked { background: #1f6aa5; border-color: #1f6aa5; }"
        )


_radio_groups: "weakref.WeakKeyDictionary[Any, dict[int, QButtonGroup]]" = weakref.WeakKeyDictionary()


class CTkRadioButton(_WidgetMixin, QRadioButton):
    def __init__(self, master: Any, text: str = "", variable: Variable | None = None, value: Any = None, **kwargs: Any) -> None:
        QRadioButton.__init__(self, text, master._child_parent())
        self._variable = variable
        self._value = value
        self._init_widget(master, text=text, variable=variable, value=value, **kwargs)
        # Stan zaznaczony używa grubszej niebieskiej obwódki. Wszystkie opcje
        # rezerwują tę samą wysokość, aby pierścień nie był przycinany po
        # przełączeniu z opcji, która początkowo była niezaznaczona.
        self.setMinimumHeight(int(kwargs.get("height", 28)))
        if variable:
            key = id(variable)
            groups = _radio_groups.setdefault(master.window(), {})
            group = groups.setdefault(key, QButtonGroup(master.window()))
            group.addButton(self)
            self.setChecked(variable.get() == value)
            self.toggled.connect(lambda checked: checked and variable.set(value))
            variable.trace_add("write", lambda *_: self.setChecked(variable.get() == value))
        self._refresh_style()

    def _refresh_style(self) -> None:
        fg = "#1f1f1f" if _appearance_mode == "Light" else "#dce4ee"
        center = "#f2f2f2" if _appearance_mode == "Light" else "#2b2b2b"
        self.setStyleSheet(
            f"CTkRadioButton {{ color: {fg}; background: transparent; spacing: 7px; }}"
            "CTkRadioButton::indicator { width: 18px; height: 18px; "
            "border: 2px solid #9aa0a6; border-radius: 10px; background: transparent; }"
            f"CTkRadioButton::indicator:checked {{ border: 5px solid #1f6aa5; "
            f"border-radius: 14px; background: {center}; }}"
            "CTkRadioButton::indicator:hover { border-color: #3b8ed0; }"
        )


class _ComboBoxItemDelegate(QStyledItemDelegate):
    """Draw popup focus like a selection instead of a Windows focus frame."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)

        highlighted_states = (
            QStyle.StateFlag.State_Selected
            | QStyle.StateFlag.State_MouseOver
            | QStyle.StateFlag.State_HasFocus
        )
        if styled_option.state & highlighted_states:
            styled_option.state |= QStyle.StateFlag.State_Selected
            styled_option.palette.setColor(QPalette.ColorRole.Highlight, QColor("#1f6aa5"))
            styled_option.palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

        # Qt's native Windows style draws a dotted focus rectangle on top of
        # the item.  The blue selection already provides a clear focus cue.
        styled_option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, styled_option, index)


class CTkComboBox(_WidgetMixin, QComboBox):
    def __init__(self, master: Any, values: list[str] | None = None, variable: Variable | None = None, **kwargs: Any) -> None:
        QComboBox.__init__(self, master._child_parent())
        self._variable = variable
        self._init_widget(master, values=values or [], variable=variable, **kwargs)
        self.addItems([str(v) for v in values or []])
        if variable:
            self.setCurrentText(str(variable.get()))
            self.currentTextChanged.connect(variable.set)
            variable.trace_add("write", lambda *_: self.setCurrentText(str(variable.get())))
        self._popup_delegate = _ComboBoxItemDelegate(self.view())
        self.view().setItemDelegate(self._popup_delegate)
        self._refresh_style()

    def get(self) -> str:
        return self.currentText()

    def set(self, value: str) -> None:
        self.setCurrentText(value)

    def _refresh_style(self) -> None:
        bg = "#ffffff" if _appearance_mode == "Light" else "#343638"
        fg = "#1f1f1f" if _appearance_mode == "Light" else "#ffffff"

        self.setStyleSheet(f"""
            CTkComboBox {{ 
                background: {bg}; 
                color: {fg}; 
                border: 1px solid #565b5e; 
                border-radius: 6px; 
                padding: 4px 8px; 
            }}
            
            /* Główne okno listy rozwijanej */
            CTkComboBox QAbstractItemView {{
                background-color: {bg};
                color: {fg};
                border: 1px solid #565b5e;
                outline: 0px; /* Wyłącza systemową ramkę focusu na całym widoku */
            }}
            
            /* KLUCZOWE: Nadajemy styl bazowy wierszom. 
               To wyłącza systemowego delegata Windows i aktywuje pełne wsparcie CSS dla listy. */
            CTkComboBox QAbstractItemView::item {{
                background-color: transparent;
                padding: 6px 4px;
            }}
            
            /* Teraz podświetlenie zadziała bez problemu */
            CTkComboBox QAbstractItemView::item:selected, 
            CTkComboBox QAbstractItemView::item:hover {{
                background-color: #1f6aa5;
                color: #ffffff;
            }}
        """)

        # QComboBox displays its items in a separate popup window.  On Windows
        # the popup can therefore inherit the system palette instead of the
        # application's palette.  Style the view itself (rather than relying
        # only on the descendant selector above) and explicitly set the
        # selection palette used by Qt's item delegate.
        popup_view = self.view()
        popup_view.setMouseTracking(True)
        popup_view.setStyleSheet(f"""
            QAbstractItemView {{
                background-color: {bg};
                color: {fg};
                border: 1px solid #565b5e;
                outline: 0px;
                selection-background-color: #1f6aa5;
                selection-color: #ffffff;
            }}
            QAbstractItemView::item {{
                background-color: transparent;
                padding: 6px 4px;
            }}
            QAbstractItemView::item:selected,
            QAbstractItemView::item:hover {{
                background-color: #1f6aa5;
                color: #ffffff;
            }}
        """)
        palette = popup_view.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(bg))
        palette.setColor(QPalette.ColorRole.Text, QColor(fg))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#1f6aa5"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        popup_view.setPalette(palette)


class CTkTextbox(_WidgetMixin, QTextEdit):
    def __init__(self, master: Any, **kwargs: Any) -> None:
        QTextEdit.__init__(self, master._child_parent())
        self._init_widget(master, **kwargs)
        if kwargs.get("wrap") == "none":
            self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._refresh_style()

    def get(self, start: Any = None, end: Any = None) -> str:
        return self.toPlainText()

    def delete(self, start: Any, end: Any = None) -> None:
        self.clear()

    def insert(self, index: Any, text: Any) -> None:
        if str(index) in ("0", "0.0", "1.0"):
            self.setPlainText(str(text))
        else:
            self.moveCursor(self.textCursor().MoveOperation.End)
            self.insertPlainText(str(text))

    def see(self, _index: Any) -> None:
        self.moveCursor(self.textCursor().MoveOperation.End)
        self.ensureCursorVisible()

    def _refresh_style(self) -> None:
        bg = "#ffffff" if _appearance_mode == "Light" else "#1e1e1e"
        fg = "#1f1f1f" if _appearance_mode == "Light" else "#ffffff"
        font = self._options.get("font")
        if isinstance(font, CTkFont):
            self.setFont(font.to_qfont())
        elif isinstance(font, tuple):
            qfont = QFont(str(font[0]))
            qfont.setPixelSize(int(font[1]))
            self.setFont(qfont)
        self.setStyleSheet(f"CTkTextbox {{ background: {bg}; color: {fg}; border: 1px solid #565b5e; border-radius: 6px; padding: 6px; }}")


class CTkProgressBar(_WidgetMixin, QProgressBar):
    def __init__(self, master: Any, **kwargs: Any) -> None:
        QProgressBar.__init__(self, master._child_parent())
        self._init_widget(master, **kwargs)
        self.setRange(0, 1000)
        self.setTextVisible(False)
        self._refresh_style()

    def set(self, value: float) -> None:
        self.setValue(int(max(0.0, min(1.0, value)) * 1000))

    def _refresh_style(self) -> None:
        self.setStyleSheet("CTkProgressBar { background: #343638; border: none; border-radius: 4px; height: 8px; } CTkProgressBar::chunk { background: #1f6aa5; border-radius: 4px; }")


class CTkTabview(_WidgetMixin, QTabWidget):
    def __init__(self, master: Any, command: Callable[[], Any] | None = None, **kwargs: Any) -> None:
        QTabWidget.__init__(self, master._child_parent())
        self._init_widget(master, command=command, **kwargs)
        if command:
            self.currentChanged.connect(lambda _index: command())
        self._refresh_style()

    def add(self, name: str) -> CTkFrame:
        page = CTkFrame(self, fg_color="transparent")
        page.master = self
        self.addTab(page, name)
        return page

    def _child_parent(self) -> QWidget:
        return self

    def get(self) -> str:
        return self.tabText(self.currentIndex())

    def _refresh_style(self) -> None:
        bg = "#e5e5e5" if _appearance_mode == "Light" else "#2b2b2b"
        fg = "#1f1f1f" if _appearance_mode == "Light" else "#ffffff"
        self.setStyleSheet(
            f"CTkTabview::pane {{ background: {bg}; border: none; border-radius: 6px; }}"
            f"QTabBar::tab {{ background: {bg}; color: {fg}; padding: 8px 14px; }}"
            "QTabBar::tab:selected { background: #1f6aa5; color: white; }"
        )


class _MessageBox:
    @staticmethod
    def showerror(title: str, message: str) -> None:
        QMessageBox.critical(QApplication.activeWindow(), title, message)

    @staticmethod
    def showwarning(title: str, message: str) -> None:
        QMessageBox.warning(QApplication.activeWindow(), title, message)

    @staticmethod
    def showinfo(title: str, message: str) -> None:
        QMessageBox.information(QApplication.activeWindow(), title, message)

    @staticmethod
    def askyesno(title: str, message: str) -> bool:
        box = QMessageBox(QApplication.activeWindow())
        box.setWindowTitle(title)
        box.setText(message)

        box.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)

        box.button(QMessageBox.StandardButton.Yes).setText("Tak")
        box.button(QMessageBox.StandardButton.No).setText("Nie")

        box.exec()

        return (
            box.standardButton(box.clickedButton())
            == QMessageBox.StandardButton.Yes
        )


class _FileDialog:
    _settings = QSettings("ProductionCounter", "ProductionCounter")
    _last_open_directory_key = "filedialog/last_open_directory"

    @classmethod
    def _last_open_directory(cls) -> str:
        saved_directory = cls._settings.value(cls._last_open_directory_key, "")
        if saved_directory:
            directory = Path(str(saved_directory))
            if directory.is_dir():
                return str(directory)
        return ""

    @staticmethod
    def askopenfilename(title: str = "", filetypes: list[Any] | None = None) -> str:
        filters = []
        for label, patterns in filetypes or []:
            if isinstance(patterns, (tuple, list)):
                patterns = " ".join(patterns)
            filters.append(f"{label} ({patterns})")
        path, _ = QFileDialog.getOpenFileName(
            QApplication.activeWindow(),
            title,
            _FileDialog._last_open_directory(),
            ";;".join(filters),
        )
        if path:
            _FileDialog._settings.setValue(
                _FileDialog._last_open_directory_key,
                str(Path(path).parent),
            )
            _FileDialog._settings.sync()
        return path


messagebox = _MessageBox()
filedialog = _FileDialog()
