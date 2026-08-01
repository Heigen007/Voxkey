"""Put transcribed text into whatever input had focus before recording.

Two Windows quirks drive the design:

1. A window that takes focus steals it from the user's input. The overlay is
   created WS_EX_NOACTIVATE so it never does - but we still remember the
   foreground HWND and restore it defensively before pasting.
2. Typing Unicode with synthetic key events is slow and unreliable for
   non-Latin scripts in some apps. Clipboard + Ctrl+V works everywhere, so we
   borrow the clipboard and hand it back afterwards.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes

import keyboard
import pyperclip

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Explicit signatures: HWND is pointer-sized, and the default int32 restype
# silently truncates handles on 64-bit Windows.
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL

MODIFIERS = ('ctrl', 'shift', 'alt', 'windows')
CLIPBOARD_RESTORE_DELAY = 0.6
CLIPBOARD_ATTEMPTS = 6
SW_RESTORE = 9

PASTED = 'pasted'
CLIPBOARD_ONLY = 'clipboard'


class ClipboardBusy(Exception):
    """Raised when another application held the clipboard open for too long."""


def copy_with_retry(text: str, attempts: int = CLIPBOARD_ATTEMPTS) -> None:
    """Put text on the clipboard, surviving another app holding it.

    The Windows clipboard is a single shared resource that any process can
    hold open - browsers, Office, clipboard managers all do it routinely. A
    write during that window simply fails. The lock is momentary, so retry
    rather than lose a dictation the user has already spoken.
    """
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            pyperclip.copy(text)
            return
        except Exception as error:  # noqa: BLE001 - pyperclip raises its own family
            last_error = error
            time.sleep(0.05 * (attempt + 1))
    logger.error('insert: clipboard locked after %d attempts: %r', attempts, last_error)
    raise ClipboardBusy('another application is holding the clipboard') from last_error


def current_window() -> int | None:
    """HWND of the window that currently owns the keyboard focus."""
    return user32.GetForegroundWindow() or None


def insert_text(text: str, hwnd: int | None) -> str:
    """Paste `text` into `hwnd`, leaving the clipboard as we found it.

    Returns PASTED, or CLIPBOARD_ONLY when the original window is gone or
    refuses to come back. In that case the text is left on the clipboard and
    nothing is typed anywhere: pasting a dictation into whatever window
    happens to be in front - a chat, a terminal - is far worse than making
    the user press Ctrl+V.
    """
    if not text:
        return PASTED

    _wait_for_modifiers_released()

    if not _focus_window(hwnd):
        logger.warning('insert: target window unavailable, leaving text on the clipboard')
        copy_with_retry(text)
        return CLIPBOARD_ONLY

    previous = _read_clipboard()
    copy_with_retry(text)
    time.sleep(0.06)  # give the target a beat to settle after the focus change
    keyboard.send('ctrl+v')

    if previous is not None:
        _restore_clipboard_later(previous, text)
    return PASTED


def _focus_window(hwnd: int | None) -> bool:
    """Ensure `hwnd` is the foreground window.

    The happy path is a no-op: the overlay is WS_EX_NOACTIVATE, so focus never
    left. This only does real work when something stole focus mid-dictation,
    and Windows deliberately makes that hard - so it may legitimately fail.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.GetForegroundWindow() == hwnd:
        return True

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    # Windows refuses foreground changes from background processes unless the
    # caller shares an input queue with the current foreground thread.
    foreground = user32.GetForegroundWindow()
    our_thread = kernel32.GetCurrentThreadId()
    their_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    attached = [
        thread for thread in {their_thread, target_thread}
        if thread and thread != our_thread and user32.AttachThreadInput(our_thread, thread, True)
    ]
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        for thread in attached:
            user32.AttachThreadInput(our_thread, thread, False)

    restored = user32.GetForegroundWindow() == hwnd
    if not restored:
        logger.warning('insert: could not restore focus to %s', hwnd)
    return restored


def _wait_for_modifiers_released(timeout: float = 1.0) -> None:
    """Hold off until Ctrl/Shift/Alt are physically up.

    The hotkey contains modifiers; pasting while one is still held turns our
    Ctrl+V into whatever the app maps Ctrl+Shift+V (or worse) to.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(keyboard.is_pressed(key) for key in MODIFIERS):
            return
        time.sleep(0.02)


def _read_clipboard() -> str | None:
    """Current clipboard text, or None if it holds something we cannot keep."""
    try:
        return pyperclip.paste()
    except Exception as error:  # noqa: BLE001 - a locked clipboard is not fatal
        logger.warning('insert: clipboard read failed: %s', error)
        return None


def _restore_clipboard_later(previous: str, pasted: str) -> None:
    """Hand the clipboard back once the target has finished reading it."""

    def restore() -> None:
        time.sleep(CLIPBOARD_RESTORE_DELAY)
        try:
            # Only restore if nothing else claimed the clipboard meanwhile.
            if pyperclip.paste() == pasted:
                copy_with_retry(previous)
        except Exception as error:  # noqa: BLE001 - a failed restore is not worth an error
            logger.warning('insert: clipboard restore failed: %s', error)

    threading.Thread(target=restore, daemon=True).start()
