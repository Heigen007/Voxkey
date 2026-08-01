"""Global keyboard hooks.

Three keys matter:

* the dictation hotkey - always suppressed, so the app underneath never sees
  it and no autocomplete pops up mid-dictation;
* Enter - stops the recording, suppressed ONLY while recording. If it reached
  the app it would submit the still-empty input a second before the text gets
  pasted into it;
* Esc - cancels, suppressed ONLY while recording, for the same reason: it
  would otherwise close whatever dialog is in front.

Outside a recording, Enter and Esc pass through untouched.

Callbacks fire on the hook thread and must return immediately, so they only
push onto the app's event queue.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import keyboard

from .strings import ERROR_HOTKEY

logger = logging.getLogger(__name__)

STOP_KEYS = ('enter',)
CANCEL_KEYS = ('esc', 'escape')


class HotkeyError(Exception):
    """Raised when the hotkey combination cannot be registered."""


class HotkeyListener:
    """Owns the global hooks for the lifetime of the app."""

    def __init__(
        self,
        combo: str,
        on_toggle: Callable[[], None],
        on_cancel: Callable[[], None],
        is_recording: Callable[[], bool],
    ) -> None:
        self._combo = combo
        self._on_toggle = on_toggle
        self._on_cancel = on_cancel
        self._is_recording = is_recording
        self._swallowed_down: set[str] = set()
        self._handles: list[object] = []

    def start(self) -> None:
        try:
            self._handles.append(
                keyboard.add_hotkey(
                    self._combo, self._on_toggle, suppress=True, trigger_on_release=False
                )
            )
        except Exception as error:  # noqa: BLE001 - bad combo strings raise a few types
            raise HotkeyError(ERROR_HOTKEY.format(hotkey=self._combo, reason=error)) from error

        # A blocking hook: returning False swallows the event.
        self._handles.append(keyboard.hook(self._on_event, suppress=True))
        logger.info('hotkey: listening on %s (suppressed) + enter/esc while recording', self._combo)

    def stop(self) -> None:
        for handle in self._handles:
            try:
                keyboard.unhook(handle)
            except Exception:  # noqa: BLE001 - unhooking a dead handle is harmless
                pass
        self._handles = []
        self._swallowed_down.clear()

    def _on_event(self, event) -> bool:
        """Decide whether a key reaches the focused app. Runs on the hook thread."""
        name = event.name
        if name not in STOP_KEYS and name not in CANCEL_KEYS:
            return True

        if event.event_type == keyboard.KEY_UP:
            # Swallow the release of a press we already ate, so the app never
            # sees a key-up without its key-down.
            if name in self._swallowed_down:
                self._swallowed_down.discard(name)
                return False
            return True

        if not self._is_recording():
            return True

        self._swallowed_down.add(name)
        if name in STOP_KEYS:
            self._on_toggle()
        else:
            self._on_cancel()
        return False
