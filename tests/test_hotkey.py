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


class FakeKeyboard:
    """Counts live registrations, so a leak is visible rather than implied."""

    def __init__(self):
        self.live_hotkeys = 0
        self.live_hooks = 0
        self.installs = 0

    def add_hotkey(self, *_args, **_kwargs):
        self.live_hotkeys += 1
        self.installs += 1
        return f'hotkey-{self.installs}'

    def hook(self, *_args, **_kwargs):
        self.live_hooks += 1
        return f'hook-{self.installs}'

    def remove_hotkey(self, _handle):
        self.live_hotkeys -= 1

    def unhook(self, _handle):
        self.live_hooks -= 1

    def install(self, monkeypatch):
        for name in ('add_hotkey', 'hook', 'remove_hotkey', 'unhook'):
            monkeypatch.setattr(hotkey.keyboard, name, getattr(self, name))


def _run_until_rearmed(listener, rounds=2, timeout=6.0):
    listener.start()
    try:
        deadline = time.monotonic() + timeout
        while listener.rearm_count < rounds and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        listener.stop()


def test_watchdog_reinstalls_the_hooks_after_silence(monkeypatch):
    fake = FakeKeyboard()
    fake.install(monkeypatch)
    monkeypatch.setattr(hotkey, 'WATCHDOG_INTERVAL_SECONDS', 0.05)

    listener = HotkeyListener(
        'ctrl+alt+space', lambda: None, lambda: None, lambda: False, rearm_after=0.1
    )
    _run_until_rearmed(listener, rounds=2)

    assert listener.rearm_count >= 2, 'the watchdog never re-armed'
    assert fake.installs >= 3, 'the hotkey was not re-registered'


def test_a_re_arm_never_stacks_a_second_registration(monkeypatch):
    """The regression that shipped in 0.1.1.

    `unhook` cannot remove an `add_hotkey` registration - that needs
    `remove_hotkey`. With the wrong call the old hotkey stayed alive, so after
    one re-arm a single key press fired the callback twice: the recording
    started and stopped instantly.
    """
    fake = FakeKeyboard()
    fake.install(monkeypatch)
    monkeypatch.setattr(hotkey, 'WATCHDOG_INTERVAL_SECONDS', 0.05)

    listener = HotkeyListener(
        'ctrl+alt+space', lambda: None, lambda: None, lambda: False, rearm_after=0.1
    )
    _run_until_rearmed(listener, rounds=3)

    assert listener.rearm_count >= 3
    # stop() removed the last pair, so nothing at all should be left behind.
    assert fake.live_hotkeys == 0, f'{fake.live_hotkeys} hotkey registrations leaked'
    assert fake.live_hooks == 0, f'{fake.live_hooks} hook registrations leaked'


def test_install_and_remove_leave_the_real_library_clean():
    """Against the actual keyboard library, not a stub.

    This is what proves the removal APIs are the right ones: a stub would
    happily agree with whichever call we chose.
    """
    listener = HotkeyListener(
        'ctrl+alt+f24', lambda: None, lambda: None, lambda: False
    )
    before = (len(hotkey.keyboard._hooks), len(hotkey.keyboard._hotkeys))
    try:
        listener._install()
        during = (len(hotkey.keyboard._hooks), len(hotkey.keyboard._hotkeys))
        assert during > before, 'nothing was registered'

        listener._remove()
        assert (len(hotkey.keyboard._hooks), len(hotkey.keyboard._hotkeys)) == before, (
            'a registration survived removal'
        )

        # And doing it twice must not accumulate either.
        for _ in range(3):
            listener._install()
            listener._remove()
        assert (len(hotkey.keyboard._hooks), len(hotkey.keyboard._hotkeys)) == before
    finally:
        hotkey.keyboard.unhook_all()


def test_stopping_ends_the_watchdog(monkeypatch):
    fake = FakeKeyboard()
    fake.install(monkeypatch)
    monkeypatch.setattr(hotkey, 'WATCHDOG_INTERVAL_SECONDS', 0.05)

    listener = HotkeyListener(
        'ctrl+alt+space', lambda: None, lambda: None, lambda: False, rearm_after=0.1
    )
    listener.start()
    listener.stop()
    time.sleep(0.4)

    assert listener.rearm_count == 0
    assert not listener._watchdog.is_alive()
    assert fake.live_hotkeys == 0
    assert fake.live_hooks == 0
