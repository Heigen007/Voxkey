"""Voxkey - press a hotkey anywhere in Windows, speak, get text.

Flow: hotkey -> the overlay bar appears (without taking focus) and recording
starts -> Enter, the same hotkey, or the stop button ends it -> audio goes to
the configured provider -> the transcript is pasted into whatever input had
focus. Esc cancels.

Threads:
  main    - Tk mainloop, owns all UI, drains the event queue every tick
  hook    - keyboard hooks, only push events onto the queue
  tray    - pystray message loop
  worker  - one per dictation: network call + paste
"""

from __future__ import annotations

import ctypes
import logging
import logging.handlers
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

from . import config, strings
from .hotkey import HotkeyError, HotkeyListener
from .inserter import CLIPBOARD_ONLY, current_window, insert_text
from .overlay import Overlay, enable_dpi_awareness
from .recorder import Recorder, RecorderError
from .settings_window import SettingsWindow
from .transcriber import TranscriptionError, cleanup, transcribe
from .tray import Tray

logger = logging.getLogger('voxkey')

IDLE = 'idle'
RECORDING = 'recording'
BUSY = 'busy'

TICK_MS = 40
FLASH_MS = 1400
ERROR_MS = 4000
CANCEL_MS = 900


class VoxkeyApp:
    """The state machine tying hotkey, recorder, provider and paste together."""

    def __init__(self, settings: config.Settings) -> None:
        self._settings = settings
        self._events: queue.Queue[tuple] = queue.Queue()
        self._state = IDLE
        self._target_hwnd: int | None = None
        self._hide_job: str | None = None
        self._hotkeys: HotkeyListener | None = None

        self._recorder = Recorder(config.SAMPLE_RATE, settings.max_seconds)
        self._root = tk.Tk()
        self._root.title(strings.APP_NAME)
        self._overlay = Overlay(
            self._root,
            on_stop=lambda: self._post('toggle'),
            on_cancel=lambda: self._post('cancel'),
            hotkey=settings.hotkey,
        )
        self._tray = Tray(
            settings.hotkey,
            on_settings=lambda: self._post('settings'),
            on_quit=lambda: self._post('quit'),
        )

    # -- lifecycle -------------------------------------------------------

    def run(self) -> None:
        self._tray.start()
        self._start_hotkeys()
        logger.info(
            'app: ready, hotkey=%s provider=%s model=%s',
            self._settings.hotkey, self._settings.provider, self._settings.resolved_model,
        )
        if not self._settings.is_configured:
            self._post('settings')
        self._root.after(TICK_MS, self._tick)
        self._root.mainloop()

    def _start_hotkeys(self) -> None:
        listener = HotkeyListener(
            self._settings.hotkey,
            on_toggle=lambda: self._post('toggle'),
            on_cancel=lambda: self._post('cancel'),
            is_recording=lambda: self._state == RECORDING,
        )
        try:
            listener.start()
        except HotkeyError as error:
            logger.error('app: %s', error)
            messagebox.showerror(strings.APP_NAME, str(error))
            self._post('settings')
            return
        self._hotkeys = listener

    def _stop_hotkeys(self) -> None:
        if self._hotkeys is not None:
            self._hotkeys.stop()
            self._hotkeys = None

    def _shutdown(self) -> None:
        logger.info('app: shutting down')
        self._stop_hotkeys()
        self._recorder.cancel()
        self._tray.stop()
        self._root.destroy()

    # -- event loop ------------------------------------------------------

    def _post(self, kind: str, payload: object = None) -> None:
        """Queue an event. Called from any thread; never blocks the caller."""
        self._events.put((kind, payload))

    def _tick(self) -> None:
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            self._handle(kind, payload)

        if self._state == RECORDING:
            if self._recorder.overrun:
                logger.info('app: hit the maximum length, stopping automatically')
                self._stop_recording()
            else:
                self._overlay.update_meter(self._recorder.level, self._recorder.seconds)

        self._root.after(TICK_MS, self._tick)

    def _handle(self, kind: str, payload: object) -> None:
        if kind == 'toggle':
            if self._state == IDLE:
                self._start_recording()
            elif self._state == RECORDING:
                self._stop_recording()
        elif kind == 'cancel':
            if self._state == RECORDING:
                self._cancel_recording()
        elif kind == 'done':
            self._state = IDLE
            if payload:
                # Only worth a message when the text did NOT land in the input.
                self._overlay.show_ok(str(payload))
                self._schedule_hide(FLASH_MS)
            else:
                # The pasted text is its own confirmation - just get out of the way.
                self._cancel_hide()
                self._overlay.hide()
        elif kind == 'error':
            self._state = IDLE
            self._overlay.show_error(str(payload))
            self._schedule_hide(ERROR_MS)
        elif kind == 'settings':
            self._open_settings()
        elif kind == 'quit':
            self._shutdown()

    # -- states ----------------------------------------------------------

    def _start_recording(self) -> None:
        if not self._settings.is_configured:
            self._open_settings()
            return

        self._target_hwnd = current_window()
        try:
            self._recorder.start()
        except RecorderError as error:
            logger.error('app: %s', error)
            self._overlay.show_error(str(error))
            self._schedule_hide(ERROR_MS)
            return
        self._state = RECORDING
        self._cancel_hide()
        self._overlay.show_recording()
        self._tray.set_recording(True)

    def _stop_recording(self) -> None:
        duration = self._recorder.seconds
        self._tray.set_recording(False)

        if duration < config.MIN_SECONDS:
            self._recorder.cancel()
            self._state = IDLE
            self._overlay.show_error(strings.STATUS_TOO_SHORT)
            self._schedule_hide(CANCEL_MS)
            return

        try:
            wav = self._recorder.stop()
        except RecorderError as error:
            self._state = IDLE
            logger.error('app: %s (stats: %s)', error, self._recorder.stats)
            self._overlay.show_error(str(error))
            self._schedule_hide(ERROR_MS)
            return

        stats = self._recorder.stats
        logger.info(
            'app: take %.1fs audio / %.1fs open, %.0f KB, xruns=%d %s',
            stats.audio_seconds, stats.wall_seconds, len(wav) / 1024, stats.xruns, stats.last_status,
        )
        if stats.gap > 1.0:
            # The mic stream died or dropped audio while the overlay still
            # showed "recording". Everything after the gap is lost.
            logger.warning(
                'app: CAPTURE GAP %.1fs - only %.1fs of audio for %.1fs of recording',
                stats.gap, stats.audio_seconds, stats.wall_seconds,
            )

        self._state = BUSY
        self._overlay.show_busy(strings.STATUS_TRANSCRIBING)
        threading.Thread(
            target=self._process, args=(wav, self._target_hwnd), daemon=True, name='worker'
        ).start()

    def _cancel_recording(self) -> None:
        self._recorder.cancel()
        self._state = IDLE
        self._tray.set_recording(False)
        self._overlay.show_ok(strings.STATUS_CANCELLED)
        self._schedule_hide(CANCEL_MS)

    def _process(self, wav: bytes, hwnd: int | None) -> None:
        """Worker thread: transcribe, optionally clean up, paste."""
        settings = self._settings
        try:
            started = time.monotonic()
            text = transcribe(wav, settings)
            logger.info(
                'app: %s -> %d chars in %.1fs | tail: %s',
                settings.resolved_model, len(text), time.monotonic() - started, _tail(text),
            )
            if settings.cleanup:
                text = cleanup(text, settings)
            outcome = insert_text(text, hwnd)
            logger.info('app: %d chars -> %s', len(text), outcome)
            # No payload on success: the pasted text speaks for itself.
            self._post('done', strings.STATUS_IN_CLIPBOARD if outcome == CLIPBOARD_ONLY else None)
        except TranscriptionError as error:
            logger.error('app: %s', error)
            self._post('error', str(error))
        except Exception:  # noqa: BLE001 - a worker crash must not kill the app
            logger.exception('app: unexpected failure while processing a dictation')
            self._post('error', strings.ERROR_CRASH)

    # -- settings --------------------------------------------------------

    def _open_settings(self) -> None:
        SettingsWindow.show(self._root, self._settings, self._apply_settings)

    def _apply_settings(self, settings: config.Settings) -> None:
        """Adopt saved settings without a restart."""
        hotkey_changed = settings.hotkey != self._settings.hotkey
        self._settings = settings
        self._recorder = Recorder(config.SAMPLE_RATE, settings.max_seconds)
        self._overlay.set_hotkey(settings.hotkey)
        self._tray.set_hotkey(settings.hotkey)
        if hotkey_changed or self._hotkeys is None:
            self._stop_hotkeys()
            self._start_hotkeys()
        logger.info('app: settings applied, hotkey=%s provider=%s', settings.hotkey, settings.provider)

    # -- overlay timers --------------------------------------------------

    def _schedule_hide(self, delay_ms: int) -> None:
        self._cancel_hide()
        self._hide_job = self._root.after(delay_ms, self._overlay.hide)

    def _cancel_hide(self) -> None:
        if self._hide_job is not None:
            self._root.after_cancel(self._hide_job)
            self._hide_job = None


def _tail(text: str, size: int = 60) -> str:
    """Last words of the transcript - enough to spot a cut-off mid-sentence
    without writing the whole dictation to disk."""
    flat = ' '.join(text.split())
    return flat if len(flat) <= size else '...' + flat[-size:]


def _setup_logging(enabled: bool) -> None:
    """Wire up the log file, or make every logging call a no-op.

    When disabled nothing is written and no file is created: the NullHandler
    keeps Python from falling back to stderr, and the CRITICAL level makes the
    logger calls throughout the app cost a single comparison.
    """
    root = logging.getLogger()
    if not enabled:
        root.addHandler(logging.NullHandler())
        root.setLevel(logging.CRITICAL)
        return

    path = config.log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=512_000, backupCount=1, encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _acquire_single_instance() -> bool:
    """Refuse to start twice - two keyboard hooks would paste everything twice."""
    error_already_exists = 183
    kernel32 = ctypes.windll.kernel32
    # Handle is intentionally leaked: Windows frees the mutex when we exit.
    kernel32.CreateMutexW(None, False, 'Voxkey_SingleInstance')
    return kernel32.GetLastError() != error_already_exists


def _fatal(message: str) -> None:
    """Report a startup failure. There is no console in a windowed build."""
    logger.error('startup: %s', message)
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(strings.APP_NAME, message)
    root.destroy()


def main() -> int:
    settings = config.load()
    _setup_logging(settings.log)

    if not _acquire_single_instance():
        logger.info('startup: another instance is already running')
        _fatal(strings.ERROR_ALREADY_RUNNING.format(app=strings.APP_NAME))
        return 1

    enable_dpi_awareness()
    try:
        VoxkeyApp(settings).run()
    except Exception as error:  # noqa: BLE001
        logger.exception('app: crashed')
        _fatal(f'{strings.ERROR_CRASH}: {error}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
