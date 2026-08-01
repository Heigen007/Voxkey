"""Enter/Esc suppression, checked without installing real keyboard hooks.

A bug here is expensive: get it wrong and Enter is swallowed system-wide, or
it reaches the app and submits an empty form a second before the transcript
gets pasted into it.
"""

import time
from types import SimpleNamespace

import pytest

from voxkey import hotkey
from voxkey.hotkey import HotkeyListener

DOWN = 'down'
UP = 'up'


@pytest.fixture()
def listener():
    state = {'recording': False, 'calls': []}
    instance = HotkeyListener(
        'ctrl+alt+space',
        on_toggle=lambda: state['calls'].append('toggle'),
        on_cancel=lambda: state['calls'].append('cancel'),
        is_recording=lambda: state['recording'],
    )
    instance.state = state  # type: ignore[attr-defined]
    return instance


def press(listener, name, event_type=DOWN):
    """Returns (reached_the_app, callbacks_fired)."""
    listener.state['calls'].clear()
    allowed = listener._on_event(SimpleNamespace(name=name, event_type=event_type))
    return allowed, list(listener.state['calls'])


@pytest.mark.parametrize('key', ['enter', 'esc', 'a', 'f4'])
def test_idle_lets_everything_through(listener, key):
    assert press(listener, key) == (True, [])


def test_enter_stops_the_recording_and_is_swallowed(listener):
    listener.state['recording'] = True
    assert press(listener, 'enter') == (False, ['toggle'])


def test_esc_cancels_the_recording_and_is_swallowed(listener):
    listener.state['recording'] = True
    assert press(listener, 'esc') == (False, ['cancel'])


def test_the_matching_key_up_is_swallowed_too(listener):
    listener.state['recording'] = True
    press(listener, 'enter')
    # By now the app has moved on to transcribing, but the key-up still
    # belongs to a press the focused window never saw.
    listener.state['recording'] = False
    assert press(listener, 'enter', UP) == (False, [])


def test_an_unpaired_key_up_reaches_the_app(listener):
    assert press(listener, 'enter', UP) == (True, [])


def test_other_keys_pass_through_while_recording(listener):
    listener.state['recording'] = True
    assert press(listener, 'a') == (True, [])
    assert press(listener, 'backspace') == (True, [])


# --- the watchdog ---------------------------------------------------------
#
# Windows drops a low-level hook whose callback overruns its timeout, without
# telling anyone: the process lives on and the hotkey silently stops working.
# Silence from the hook is the only available signal.


def test_silence_is_what_triggers_a_re_arm(listener):
    listener._last_event = time.monotonic()
    assert listener._should_rearm(time.monotonic()) is False

    listener._last_event = time.monotonic() - (hotkey.REARM_AFTER_SECONDS + 1)
    assert listener._should_rearm(time.monotonic()) is True


def test_any_key_counts_as_proof_of_life(listener):
    """Even keys the app passes straight through must reset the clock."""
    listener._last_event = time.monotonic() - 10_000
    assert listener._should_rearm(time.monotonic()) is True

    press(listener, 'a')
    assert listener._should_rearm(time.monotonic()) is False


def test_watchdog_reinstalls_the_hooks_after_silence(monkeypatch):
    """The real loop, with the keyboard module stubbed out."""
    installs = []
    monkeypatch.setattr(hotkey.keyboard, 'add_hotkey', lambda *a, **k: installs.append('hotkey') or 'h1')
    monkeypatch.setattr(hotkey.keyboard, 'hook', lambda *a, **k: installs.append('hook') or 'h2')
    monkeypatch.setattr(hotkey.keyboard, 'unhook', lambda handle: None)
    monkeypatch.setattr(hotkey, 'WATCHDOG_INTERVAL_SECONDS', 0.05)

    listener = HotkeyListener(
        'ctrl+alt+space',
        on_toggle=lambda: None,
        on_cancel=lambda: None,
        is_recording=lambda: False,
        rearm_after=0.1,
    )
    listener.start()
    try:
        deadline = time.monotonic() + 5
        while listener.rearm_count < 1 and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        listener.stop()

    assert listener.rearm_count >= 1, 'the watchdog never re-armed'
    assert installs.count('hook') >= 2, 'the blocking hook was not re-installed'
    assert installs.count('hotkey') >= 2, 'the hotkey was not re-registered'


def test_stopping_ends_the_watchdog(monkeypatch):
    monkeypatch.setattr(hotkey.keyboard, 'add_hotkey', lambda *a, **k: 'h1')
    monkeypatch.setattr(hotkey.keyboard, 'hook', lambda *a, **k: 'h2')
    monkeypatch.setattr(hotkey.keyboard, 'unhook', lambda handle: None)
    monkeypatch.setattr(hotkey, 'WATCHDOG_INTERVAL_SECONDS', 0.05)

    listener = HotkeyListener(
        'ctrl+alt+space', lambda: None, lambda: None, lambda: False, rearm_after=0.1
    )
    listener.start()
    listener.stop()
    time.sleep(0.4)

    assert listener.rearm_count == 0
    assert not listener._watchdog.is_alive()
