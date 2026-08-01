"""Clipboard handling.

The Windows clipboard is a shared resource any process can hold open, so a
write can simply fail. That used to surface as an unexplained crash with the
dictation lost.
"""

import pytest

from voxkey import inserter


class FlakyClipboard:
    """Fails the first `failures` writes, then succeeds."""

    def __init__(self, failures):
        self.failures = failures
        self.attempts = 0
        self.value = None

    def copy(self, text):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError('OpenClipboard failed')
        self.value = text


@pytest.fixture()
def no_sleep(monkeypatch):
    monkeypatch.setattr(inserter.time, 'sleep', lambda _seconds: None)


def test_a_clean_write_happens_once(monkeypatch, no_sleep):
    clipboard = FlakyClipboard(failures=0)
    monkeypatch.setattr(inserter.pyperclip, 'copy', clipboard.copy)

    inserter.copy_with_retry('hello')

    assert clipboard.value == 'hello'
    assert clipboard.attempts == 1


def test_a_transient_lock_is_retried(monkeypatch, no_sleep):
    clipboard = FlakyClipboard(failures=3)
    monkeypatch.setattr(inserter.pyperclip, 'copy', clipboard.copy)

    inserter.copy_with_retry('the dictation')

    assert clipboard.value == 'the dictation', 'the text was lost to a temporary lock'
    assert clipboard.attempts == 4


def test_a_permanent_lock_raises_something_nameable(monkeypatch, no_sleep):
    clipboard = FlakyClipboard(failures=99)
    monkeypatch.setattr(inserter.pyperclip, 'copy', clipboard.copy)

    with pytest.raises(inserter.ClipboardBusy):
        inserter.copy_with_retry('lost text', attempts=3)

    assert clipboard.attempts == 3


def test_empty_text_never_touches_the_clipboard(monkeypatch):
    def explode(_text):
        raise AssertionError('the clipboard should not be touched for empty text')

    monkeypatch.setattr(inserter.pyperclip, 'copy', explode)
    assert inserter.insert_text('', hwnd=None) == inserter.PASTED


def test_no_target_window_leaves_the_text_on_the_clipboard(monkeypatch, no_sleep):
    clipboard = FlakyClipboard(failures=0)
    monkeypatch.setattr(inserter.pyperclip, 'copy', clipboard.copy)
    monkeypatch.setattr(inserter, '_wait_for_modifiers_released', lambda: None)
    monkeypatch.setattr(inserter, '_focus_window', lambda _hwnd: False)

    outcome = inserter.insert_text('spoken words', hwnd=None)

    assert outcome == inserter.CLIPBOARD_ONLY
    assert clipboard.value == 'spoken words'
