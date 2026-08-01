"""Start-at-logon registration.

Uses a plain shortcut in the user's Startup folder rather than a registry Run
entry: it needs no admin rights, the user can see and delete it by hand, and
it does not look like malware persistence to antivirus heuristics - which
matters for a tool that already hooks the keyboard for a living.

The shortcut is created through PowerShell's WScript.Shell, because building a
.lnk from Python otherwise means hand-rolling IShellLink over COM.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
LINK_NAME = 'Voxkey.lnk'


def link_path() -> Path:
    appdata = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
    return Path(appdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup' / LINK_NAME


def is_enabled() -> bool:
    return link_path().exists()


def apply(enabled: bool) -> bool:
    """Make autostart match `enabled`. Returns the resulting state."""
    return enable() if enabled else disable()


def enable() -> bool:
    target, arguments, workdir = _shortcut_target()
    command = '; '.join([
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps(str(link_path()))})',
        f'$s.TargetPath = {_ps(target)}',
        f'$s.Arguments = {_ps(arguments)}',
        f'$s.WorkingDirectory = {_ps(workdir)}',
        f'$s.IconLocation = {_ps(target)}',
        "$s.Description = 'Voxkey - hotkey dictation'",
        '$s.Save()',
    ])
    try:
        link_path().parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error('autostart: powershell failed: %s', result.stderr[:400])
    except Exception as error:  # noqa: BLE001 - never let this crash the app
        logger.exception('autostart: could not create the shortcut: %s', error)

    enabled = is_enabled()
    logger.info('autostart: enable -> %s (%s)', enabled, link_path())
    return enabled


def disable() -> bool:
    try:
        link_path().unlink(missing_ok=True)
    except OSError as error:
        logger.error('autostart: could not remove the shortcut: %s', error)
    still_there = is_enabled()
    logger.info('autostart: disable -> %s', not still_there)
    return still_there


def _shortcut_target() -> tuple[str, str, str]:
    """(target, arguments, working directory) for the shortcut."""
    if getattr(sys, 'frozen', False):
        exe = Path(sys.executable).resolve()
        return str(exe), '', str(exe.parent)

    package = Path(__file__).resolve().parent
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    return str(runner), '-m voxkey', str(package.parents[1])


def _ps(value: str) -> str:
    """Quote a value as a PowerShell single-quoted literal."""
    return "'" + value.replace("'", "''") + "'"
