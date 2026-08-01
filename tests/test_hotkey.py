"""Enter/Esc suppression, checked without installing real keyboard hooks.

A bug here is expensive: get it wrong and Enter is swallowed system-wide, or
it reaches the app and submits an empty form a second before the transcript
gets pasted into it.
"""

from types import SimpleNamespace

import pytest

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
