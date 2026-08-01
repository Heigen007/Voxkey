"""Settings, stored per user in %APPDATA%\\Voxkey\\config.json.

Deliberately not next to the executable: installed under Program Files there
is no write access, and a config that travels with the binary gets shared by
accident. The API key inside is encrypted per Windows account - see keystore.

Two environment variables exist for development and testing:
  VOXKEY_CONFIG_DIR  point the whole config elsewhere
  VOXKEY_API_KEY     supply the key without writing it to disk at all
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from . import keystore, providers

logger = logging.getLogger(__name__)

APP_NAME = 'Voxkey'
SAMPLE_RATE = 16_000
MIN_SECONDS = 0.4
DEFAULT_HOTKEY = 'ctrl+alt+space'


def config_dir() -> Path:
    override = os.environ.get('VOXKEY_CONFIG_DIR')
    if override:
        return Path(override)
    appdata = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
    return Path(appdata) / APP_NAME


def config_path() -> Path:
    return config_dir() / 'config.json'


def log_path() -> Path:
    return config_dir() / 'voxkey.log'


@dataclass(frozen=True)
class Settings:
    """Immutable settings snapshot. Change with dataclasses.replace()."""

    provider: str = providers.DEFAULT_PROVIDER
    api_key: str = ''
    base_url: str = ''
    model: str = ''
    language: str = ''
    vocabulary: str = ''
    hotkey: str = DEFAULT_HOTKEY
    cleanup: bool = False
    cleanup_model: str = ''
    autostart: bool = False
    max_seconds: int = 300
    request_timeout: int = 90
    log: bool = False

    @property
    def is_configured(self) -> bool:
        """Enough to attempt a transcription.

        A self-hosted endpoint may legitimately need no key at all, so a
        custom provider counts as configured once it has a URL.
        """
        if self.api_key.strip():
            return True
        return providers.get(self.provider).editable_base_url and bool(self.base_url.strip())

    @property
    def resolved_model(self) -> str:
        return providers.resolve_model(self.provider, self.model)

    @property
    def resolved_base_url(self) -> str:
        return providers.resolve_base_url(self.provider, self.base_url)

    @property
    def resolved_cleanup_model(self) -> str:
        return providers.resolve_cleanup_model(self.provider, self.cleanup_model)


_FIELD_TYPES = {f: type(v) for f, v in asdict(Settings()).items()}


def load() -> Settings:
    """Read settings from disk. A missing or broken file yields defaults."""
    raw: dict = {}
    path = config_path()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            logger.error('config: %s is unreadable, falling back to defaults: %s', path, error)
            raw = {}

    values: dict[str, object] = {}
    for name, expected in _FIELD_TYPES.items():
        if name == 'api_key' or name not in raw:
            continue
        value = raw[name]
        # Tolerate a hand-edited file: coerce rather than crash on a wrong type.
        try:
            values[name] = expected(value) if not isinstance(value, expected) else value
        except (TypeError, ValueError):
            logger.warning('config: ignoring %s=%r, expected %s', name, value, expected.__name__)

    api_key = os.environ.get('VOXKEY_API_KEY', '').strip() or keystore.unprotect(raw.get('api_key'))
    return Settings(api_key=api_key, **values)  # type: ignore[arg-type]


def save(settings: Settings) -> Path:
    """Write settings to disk with the API key encrypted. Returns the path."""
    payload = asdict(settings)
    payload['api_key'] = keystore.protect(settings.api_key.strip())

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    logger.info('config: saved to %s', path)
    return path
