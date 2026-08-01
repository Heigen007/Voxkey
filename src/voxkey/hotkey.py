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

## Why there is a watchdog

Windows silently removes a low-level keyboard hook whose callback overruns
`LowLevelHooksTimeout` - 300 ms by default. There is no error and no
notification: the process keeps running, the tray icon stays put, and the
hotkey just stops working. A Python callback on a machine under heavy load
can absolutely overrun that, and the app has no way to notice.

The blocking hook sees every keystroke, so silence is the signal. If no key
event has arrived for a while, either nobody is typing or the hook is gone -
and re-registering is safe in both cases, precisely because nobody is typing
at that moment. No synthetic input, and no gap during real work.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import keyboard

from .strings import ERROR_HOTKEY

logger = logging.getLogger(__name__)

STOP_KEYS = ('enter',)
CANCEL_KEYS = ('esc', 'escape')

REARM_AFTER_SECONDS = 60.0
WATCHDOG_INTERVAL_SECONDS = 10.0


class HotkeyError(Exception):
    """Raised when the hotkey combination cannot be registered."""


def _drop(kind: str, remover, handle) -> None:
    """Remove one registration, complaining if it did not come off.

    A leaked registration is not cosmetic: the next install stacks a second
    one on top and every key press fires the callback twice.
    """
    try:
        remover(handle)
    except Exception as error:  # noqa: BLE001
        logger.error('hotkey: could not remove the %s registration: %r', kind, error)


class HotkeyListener:
    """Owns the global hooks for the lifetime of the app, and keeps them alive."""

    def __init__(
        self,
        combo: str,
        on_toggle: Callable[[], None],
        on_cancel: Callable[[], None],
        is_recording: Callable[[], bool],
        rearm_after: float = REARM_AFTER_SECONDS,
    ) -> None:
        self._combo = combo
        self._on_toggle = on_toggle
        self._on_cancel = on_cancel
        self._is_recording = is_recording
        self._rearm_after = rearm_after
        self._swallowed_down: set[str] = set()
        # Two registrations, two different removal functions - see _remove().
        self._hotkey_handle: object | None = None
        self._hook_handle: object | None = None
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._watchdog: threading.Thread | None = None
        self._last_event = 0.0
        self.rearm_count = 0

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        self._install()
        self._stopping.clear()
        self._watchdog = threading.Thread(target=self._watch, daemon=True, name='hotkey-watchdog')
        self._watchdog.start()
        logger.info(
            'hotkey: listening on %s (suppressed) + enter/esc while recording, '
            're-arming after %.0fs of silence',
            self._combo, self._rearm_after,
        )

    def stop(self) -> None:
        self._stopping.set()
        with self._lock:
            self._remove()
        self._swallowed_down.clear()

    # -- registration ----------------------------------------------------

    def _install(self) -> None:
        try:
            self._hotkey_handle = keyboard.add_hotkey(
                self._combo, self._on_toggle, suppress=True, trigger_on_release=False
            )
        except Exception as error:  # noqa: BLE001 - bad combo strings raise a few types
            raise HotkeyError(ERROR_HOTKEY.format(hotkey=self._combo, reason=error)) from error

        # A blocking hook: returning False swallows the event.
        self._hook_handle = keyboard.hook(self._on_event, suppress=True)
        self._last_event = time.monotonic()

    def _remove(self) -> None:
        """Undo _install().

        The two registrations live in different registries inside the keyboard
        library and need different removal calls: `remove_hotkey` for the
        hotkey, `unhook` for the blocking hook. Using the wrong one raises
        KeyError and leaves the registration in place - which, on a re-arm,
        means two hotkeys firing the callback twice for one key press. So a
        failure here is logged loudly rather than swallowed.
        """
        if self._hotkey_handle is not None:
            _drop('hotkey', keyboard.remove_hotkey, self._hotkey_handle)
            self._hotkey_handle = None
        if self._hook_handle is not None:
            _drop('hook', keyboard.unhook, self._hook_handle)
            self._hook_handle = None

    # -- watchdog --------------------------------------------------------

    def _should_rearm(self, now: float) -> bool:
        """True once the hook has been silent long enough to be suspect."""
        return now - self._last_event > self._rearm_after

    def _watch(self) -> None:
        while not self._stopping.wait(WATCHDOG_INTERVAL_SECONDS):
            if self._should_rearm(time.monotonic()):
                self._rearm()

    def _rearm(self) -> None:
        """Take the hooks down and put them straight back up."""
        with self._lock:
            if self._stopping.is_set():
                return
            self._remove()
            try:
                self._install()
            except HotkeyError as error:
                # Something else may hold the combination at this instant.
                # Refresh the stamp so we retry next cycle rather than spin.
                self._last_event = time.monotonic()
                logger.error('hotkey: re-arm failed: %s', error)
                return
        self.rearm_count += 1
        logger.info('hotkey: re-armed after %.0fs of silence (#%d)', self._rearm_after, self.rearm_count)

    # -- the hook itself -------------------------------------------------

    def _on_event(self, event) -> bool:
        """Decide whether a key reaches the focused app. Runs on the hook thread."""
        # Proof of life for the watchdog, stamped for every key, not just ours.
        self._last_event = time.monotonic()

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
