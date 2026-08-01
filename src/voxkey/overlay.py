"""The floating recording bar.

A small always-on-top strip near the bottom of the screen. Two properties
matter more than looks:

* It is created WS_EX_NOACTIVATE, so showing it never pulls focus away from
  the input the user is dictating into.
* The process is made DPI-aware and every coordinate is scaled by hand.
  Without that, Windows bitmap-stretches the window on a 125%+ display and
  the text turns to mush.

Layout constants are in base pixels at 96 dpi and get multiplied by the
monitor scale at draw time.
"""

from __future__ import annotations

import ctypes
import tkinter as tk
from collections.abc import Callable
from ctypes import wintypes

from . import strings

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

WIDTH = 380
HEIGHT = 84
MARGIN_BOTTOM = 150
TRANSPARENT_KEY = '#010203'

BG = '#16181d'
BORDER = '#2c3038'
TEXT = '#f2f4f8'
DIM = '#767c88'
RED = '#f2545b'
AMBER = '#e0a33e'
GREEN = '#3fbf7f'
METER_ON = '#5b8def'
METER_OFF = '#292d35'

BAR_COUNT = 22
BAR_X0 = 96
BAR_WIDTH = 5
BAR_GAP = 3
ROW_Y = 32
HINT_Y = 64
STOP_CENTER = (320, ROW_Y)
CANCEL_CENTER = (352, ROW_Y)
HIT_RADIUS = 15

FONT = 'Segoe UI'
FONT_TIMER = 16
FONT_MESSAGE = 15
FONT_HINT = 11
FONT_CANCEL = 17

user32 = ctypes.windll.user32
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long


def enable_dpi_awareness() -> None:
    """Opt out of Windows' bitmap scaling. Must run before the first window."""
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
        user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        )
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def pretty_hotkey(combo: str) -> str:
    """'ctrl+alt+space' -> 'Ctrl+Alt+Space' for display."""
    return '+'.join(part.strip().capitalize() for part in combo.split('+') if part.strip())


class Overlay:
    """Renders the recording bar. All methods must be called on the Tk thread."""

    def __init__(
        self,
        root: tk.Tk,
        on_stop: Callable[[], None],
        on_cancel: Callable[[], None],
        hotkey: str,
    ) -> None:
        self._root = root
        self._on_stop = on_stop
        self._on_cancel = on_cancel
        self._hotkey_label = pretty_hotkey(hotkey)
        self._state = 'hidden'
        self._message = ''
        self._level = 0.0
        self._seconds = 0.0
        self._visible = False
        self._scale = 1.0

        root.overrideredirect(True)
        root.attributes('-topmost', True)
        root.configure(bg=TRANSPARENT_KEY)
        root.attributes('-transparentcolor', TRANSPARENT_KEY)

        self._canvas = tk.Canvas(root, bg=TRANSPARENT_KEY, highlightthickness=0, bd=0)
        self._canvas.pack()
        self._canvas.bind('<Button-1>', self._on_click)

        root.update_idletasks()
        self._make_non_activating()
        self._apply_scale()
        root.withdraw()

    # -- public API ------------------------------------------------------

    def set_hotkey(self, combo: str) -> None:
        self._hotkey_label = pretty_hotkey(combo)

    def show_recording(self) -> None:
        self._state = 'recording'
        self._level = 0.0
        self._seconds = 0.0
        self._show()

    def update_meter(self, level: float, seconds: float) -> None:
        if self._state != 'recording':
            return
        self._level = level
        self._seconds = seconds
        self._render()

    def show_busy(self, message: str) -> None:
        self._state = 'busy'
        self._message = message
        self._show()

    def show_ok(self, message: str) -> None:
        self._state = 'ok'
        self._message = message
        self._show()

    def show_error(self, message: str) -> None:
        self._state = 'error'
        self._message = message
        self._show()

    def hide(self) -> None:
        self._state = 'hidden'
        if self._visible:
            self._root.withdraw()
            self._visible = False

    # -- geometry --------------------------------------------------------

    def _hwnd(self) -> int:
        return user32.GetParent(self._root.winfo_id()) or self._root.winfo_id()

    def _p(self, value: float) -> int:
        """Base pixels -> device pixels for the current monitor."""
        return round(value * self._scale)

    def _font(self, base_px: int, *styles: str) -> tuple:
        # Negative Tk font sizes are pixels, which keeps us out of the
        # point/scaling guesswork entirely.
        return (FONT, -self._p(base_px), *styles)

    def _apply_scale(self) -> None:
        try:
            dpi = user32.GetDpiForWindow(self._hwnd()) or 96
        except (AttributeError, OSError):
            dpi = 96
        scale = dpi / 96.0
        if scale == self._scale and self._canvas.winfo_reqwidth() > 1:
            return
        self._scale = scale
        self._canvas.configure(width=self._p(WIDTH), height=self._p(HEIGHT))
        self._root.geometry(self._geometry())

    def _geometry(self) -> str:
        width, height = self._p(WIDTH), self._p(HEIGHT)
        x = (self._root.winfo_screenwidth() - width) // 2
        y = self._root.winfo_screenheight() - self._p(MARGIN_BOTTOM)
        return f'{width}x{height}+{x}+{y}'

    def _make_non_activating(self) -> None:
        """Add WS_EX_NOACTIVATE so the bar can never steal keyboard focus."""
        hwnd = self._hwnd()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

    def _show(self) -> None:
        if not self._visible:
            self._apply_scale()
            self._root.geometry(self._geometry())
            self._root.deiconify()
            self._root.attributes('-topmost', True)
            self._visible = True
        self._render()

    def _on_click(self, event: tk.Event) -> None:
        if self._state != 'recording':
            return
        radius = self._p(HIT_RADIUS)
        if _near(event.x, event.y, self._point(CANCEL_CENTER), radius):
            self._on_cancel()
        elif _near(event.x, event.y, self._point(STOP_CENTER), radius):
            self._on_stop()

    def _point(self, base: tuple[int, int]) -> tuple[int, int]:
        return self._p(base[0]), self._p(base[1])

    # -- drawing ---------------------------------------------------------

    def _render(self) -> None:
        canvas = self._canvas
        canvas.delete('all')
        _rounded_rect(
            canvas, self._p(2), self._p(2), self._p(WIDTH - 2), self._p(HEIGHT - 2),
            self._p(14), fill=BG, outline=BORDER,
        )
        if self._state == 'recording':
            self._render_recording()
        else:
            self._render_status()

    def _render_status(self) -> None:
        colors = {'busy': AMBER, 'ok': GREEN, 'error': RED}
        self._dot(colors.get(self._state, DIM))
        self._canvas.create_text(
            self._p(44), self._p(ROW_Y), text=self._message, anchor='w',
            fill=TEXT, font=self._font(FONT_MESSAGE),
        )
        hint = strings.HINT_BUSY if self._state == 'busy' else strings.HINT_AFTER.format(
            hotkey=self._hotkey_label
        )
        self._hint(hint)

    def _render_recording(self) -> None:
        canvas = self._canvas
        self._dot(RED)
        minutes, seconds = divmod(int(self._seconds), 60)
        canvas.create_text(
            self._p(44), self._p(ROW_Y), text=f'{minutes}:{seconds:02d}', anchor='w',
            fill=TEXT, font=self._font(FONT_TIMER, 'bold'),
        )

        lit = int(self._level * BAR_COUNT)
        center_y = self._p(ROW_Y)
        for index in range(BAR_COUNT):
            x = self._p(BAR_X0 + index * (BAR_WIDTH + BAR_GAP))
            half = self._p((5 + 19 * (index + 1) / BAR_COUNT) / 2)
            color = METER_ON if index < lit else METER_OFF
            canvas.create_rectangle(
                x, center_y - half, x + self._p(BAR_WIDTH), center_y + half, fill=color, outline=''
            )

        sx, sy = self._point(STOP_CENTER)
        side = self._p(5)
        canvas.create_rectangle(sx - side, sy - side, sx + side, sy + side, fill=TEXT, outline='')
        cx, cy = self._point(CANCEL_CENTER)
        canvas.create_text(cx, cy, text='✕', fill=DIM, font=self._font(FONT_CANCEL))

        self._hint(strings.HINT_RECORDING.format(hotkey=self._hotkey_label))

    def _hint(self, text: str) -> None:
        self._canvas.create_text(
            self._p(WIDTH / 2), self._p(HINT_Y), text=text, fill=DIM, font=self._font(FONT_HINT)
        )

    def _dot(self, color: str) -> None:
        self._canvas.create_oval(
            self._p(20), self._p(ROW_Y - 6), self._p(32), self._p(ROW_Y + 6), fill=color, outline=''
        )


def _near(x: int, y: int, center: tuple[int, int], radius: int) -> bool:
    return abs(x - center[0]) <= radius and abs(y - center[1]) <= radius


def _rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, r: float, **kwargs):
    """A rounded rectangle built from a smoothed polygon (tk has no native one)."""
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)
