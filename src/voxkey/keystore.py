"""Per-user encryption for the API key, using Windows DPAPI.

`CryptProtectData` ties the ciphertext to the current Windows account: another
user on the machine, or the same file copied to another machine, cannot read
it. This is not protection against someone who already has your session - it
is protection against your key sitting in plain text in a JSON file that then
gets synced to cloud storage, swept into a backup, or shared by accident.

If DPAPI is unavailable the key is stored unencrypted and labelled as such, so
the situation is visible rather than silently insecure.
"""

from __future__ import annotations

import base64
import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger(__name__)

SCHEME_DPAPI = 'dpapi'
SCHEME_PLAIN = 'plain'


class _DataBlob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _crypt32():
    return ctypes.windll.crypt32


def is_available() -> bool:
    """True when DPAPI can be used on this machine."""
    try:
        _crypt32()
    except (AttributeError, OSError):
        return False
    return True


def protect(plaintext: str) -> dict[str, str]:
    """Encrypt a secret for storage. Returns a {scheme, value} record."""
    if not plaintext:
        return {'scheme': SCHEME_PLAIN, 'value': ''}
    try:
        return {'scheme': SCHEME_DPAPI, 'value': _dpapi_protect(plaintext)}
    except Exception as error:  # noqa: BLE001 - fall back visibly, never lose the key
        logger.warning('keystore: DPAPI unavailable, storing in plain text: %s', error)
        return {'scheme': SCHEME_PLAIN, 'value': plaintext}


def unprotect(record: object) -> str:
    """Read a secret back. Tolerates a bare string from a hand-edited config."""
    if isinstance(record, str):
        return record
    if not isinstance(record, dict):
        return ''

    value = str(record.get('value') or '')
    if not value or record.get('scheme') != SCHEME_DPAPI:
        return value
    try:
        return _dpapi_unprotect(value)
    except Exception as error:  # noqa: BLE001
        logger.error('keystore: could not decrypt the stored key: %s', error)
        return ''


def _dpapi_protect(plaintext: str) -> str:
    data = plaintext.encode('utf-8')
    buffer = ctypes.create_string_buffer(data, len(data))
    source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    result = _DataBlob()

    if not _crypt32().CryptProtectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    ):
        raise OSError(ctypes.GetLastError(), 'CryptProtectData failed')

    try:
        encrypted = ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)
    return base64.b64encode(encrypted).decode('ascii')


def _dpapi_unprotect(encoded: str) -> str:
    data = base64.b64decode(encoded)
    buffer = ctypes.create_string_buffer(data, len(data))
    source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    result = _DataBlob()

    if not _crypt32().CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    ):
        raise OSError(ctypes.GetLastError(), 'CryptUnprotectData failed')

    try:
        decrypted = ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)
    return decrypted.decode('utf-8')
