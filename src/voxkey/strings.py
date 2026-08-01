"""Every user-visible string, in one place.

Kept together so a translation is a single-file pull request rather than a
hunt through the codebase. English is the source language.
"""

from __future__ import annotations

APP_NAME = 'Voxkey'

# --- overlay --------------------------------------------------------------
HINT_RECORDING = '{hotkey} / Enter - stop   ·   Esc - cancel'
HINT_AFTER = '{hotkey} - record again'
HINT_BUSY = 'one moment'
STATUS_TRANSCRIBING = 'Transcribing...'
STATUS_CANCELLED = 'Cancelled'
STATUS_TOO_SHORT = 'Too short'
STATUS_IN_CLIPBOARD = 'In clipboard - press Ctrl+V'

# --- tray -----------------------------------------------------------------
TRAY_TITLE = '{app} - {hotkey}'
TRAY_DICTATION = 'Dictation: {hotkey}'
TRAY_SETTINGS = 'Settings...'
TRAY_AUTOSTART = 'Start with Windows'
TRAY_CONFIG_FOLDER = 'Open config folder'
TRAY_LOG = 'Log'
TRAY_QUIT = 'Quit'

# --- errors ---------------------------------------------------------------
ERROR_NO_MIC = 'No microphone: {reason}'
ERROR_NOTHING_RECORDED = 'Nothing was recorded'
ERROR_TIMEOUT = 'Request timed out'
ERROR_OFFLINE = 'Cannot reach {provider}'
ERROR_BAD_KEY = 'Invalid API key'
ERROR_NO_ACCESS = 'This key has no access to that model'
ERROR_NO_MODEL = 'Model not found: {model}'
ERROR_TOO_LONG = 'Recording too long'
ERROR_RATE_LIMIT = 'Rate limit or quota reached'
ERROR_SERVER = '{provider} is unavailable ({status})'
ERROR_NO_SPEECH = 'No speech detected'
ERROR_GENERIC = 'Error {status}: {message}'
ERROR_CRASH = 'Something went wrong'
ERROR_ALREADY_RUNNING = '{app} is already running - look for the microphone icon in the tray.'
ERROR_HOTKEY = 'Could not register the hotkey "{hotkey}": {reason}'

# --- settings window ------------------------------------------------------
SETTINGS_TITLE = '{app} settings'
SETTINGS_WELCOME = (
    'Set up dictation. Pick a provider, paste an API key, then press Test - '
    'it records three seconds and shows you what came back.'
)
SETTINGS_PROVIDER = 'Provider'
SETTINGS_API_KEY = 'API key'
SETTINGS_GET_KEY = 'Get a key'
SETTINGS_SHOW_KEY = 'Show'
SETTINGS_BASE_URL = 'Endpoint URL'
SETTINGS_MODEL = 'Model'
SETTINGS_LANGUAGE = 'Language'
SETTINGS_LANGUAGE_HELP = 'ISO code such as en, ru, de. Leave empty to auto-detect.'
SETTINGS_VOCABULARY = 'Vocabulary'
SETTINGS_VOCABULARY_HELP = 'Names and terms the model keeps getting wrong. Optional.'
SETTINGS_HOTKEY = 'Hotkey'
SETTINGS_HOTKEY_HELP = 'Suppressed while running, so the app underneath never sees it.'
SETTINGS_CLEANUP = 'Tidy up the text with an LLM (removes filler words, adds punctuation)'
SETTINGS_AUTOSTART = 'Start with Windows'
SETTINGS_TEST = 'Test'
SETTINGS_TESTING = 'Recording 3 seconds - say something...'
SETTINGS_TEST_SENDING = 'Sending to {provider}...'
SETTINGS_TEST_OK = 'Works. Heard: "{text}"'
SETTINGS_TEST_EMPTY = 'Connected, but no speech was detected. Check your microphone.'
SETTINGS_TEST_FAILED = 'Failed: {reason}'
SETTINGS_TEST_NEEDS_KEY = 'Enter an API key first.'
SETTINGS_SAVE = 'Save'
SETTINGS_CANCEL = 'Cancel'
SETTINGS_SAVED = 'Saved.'
SETTINGS_NEEDS_KEY = 'An API key is required before dictation will work.'
