"""System tray icon: proof the app is alive, and the way into settings.

pystray owns a Win32 message loop, so it runs on its own thread while Tk keeps
the main one.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable

import pystray

from . import autostart, config, strings
from .icon import IDLE_COLOR, RECORDING_COLOR, mic_image
from .overlay import pretty_hotkey

logger = logging.getLogger(__name__)


class Tray:
    """Tray icon with a small menu. Safe to call from any thread."""

    def __init__(
        self,
        hotkey: str,
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._icon = pystray.Icon(
            'voxkey',
            icon=mic_image(IDLE_COLOR),
            title=_title(hotkey),
            menu=pystray.Menu(
                pystray.MenuItem(
                    strings.TRAY_DICTATION.format(hotkey=pretty_hotkey(hotkey)), None, enabled=False
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(strings.TRAY_SETTINGS, self._on_settings, default=True),
                pystray.MenuItem(
                    strings.TRAY_AUTOSTART,
                    self._toggle_autostart,
                    checked=lambda item: autostart.is_enabled(),
                ),
                pystray.MenuItem(strings.TRAY_CONFIG_FOLDER, _open_config_folder),
                # Only worth showing when logging is actually turned on.
                pystray.MenuItem(
                    strings.TRAY_LOG, _open_log, visible=lambda item: config.log_path().exists()
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(strings.TRAY_QUIT, self._quit),
            ),
        )
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name='tray')
        self._thread.start()

    def set_recording(self, recording: bool) -> None:
        try:
            self._icon.icon = mic_image(RECORDING_COLOR if recording else IDLE_COLOR)
        except Exception as error:  # noqa: BLE001 - a stale icon is cosmetic
            logger.warning('tray: icon update failed: %s', error)

    def set_hotkey(self, hotkey: str) -> None:
        try:
            self._icon.title = _title(hotkey)
            self._icon.update_menu()
        except Exception as error:  # noqa: BLE001
            logger.warning('tray: title update failed: %s', error)

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:  # noqa: BLE001
            pass

    def _toggle_autostart(self) -> None:
        autostart.apply(not autostart.is_enabled())
        self._icon.update_menu()

    def _quit(self) -> None:
        self._on_quit()


def _title(hotkey: str) -> str:
    return strings.TRAY_TITLE.format(app=strings.APP_NAME, hotkey=pretty_hotkey(hotkey))


def _open_config_folder() -> None:
    folder = config.config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    os.startfile(folder)


def _open_log() -> None:
    path = config.log_path()
    os.startfile(path if path.exists() else config.config_dir())
