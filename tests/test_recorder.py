"""WAV framing and the capture-gap diagnostic. No microphone required."""

import io
import wave

import numpy as np

from voxkey.recorder import TakeStats, _to_wav


def test_wav_is_16khz_mono_16bit():
    samples = np.zeros(16_000, dtype=np.int16)
    data = _to_wav(samples, 16_000)

    assert data[:4] == b'RIFF'
    with wave.open(io.BytesIO(data)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 16_000
        assert handle.getsampwidth() == 2
        assert handle.getnframes() == 16_000


def test_a_healthy_take_has_no_gap():
    stats = TakeStats(audio_seconds=30.0, wall_seconds=30.2, xruns=0, last_status='')
    assert stats.gap < 1.0


def test_a_dead_stream_shows_up_as_a_gap():
    stats = TakeStats(audio_seconds=4.0, wall_seconds=31.0, xruns=0, last_status='')
    assert stats.gap == 27.0


def test_gap_is_never_negative():
    stats = TakeStats(audio_seconds=5.1, wall_seconds=5.0, xruns=0, last_status='')
    assert stats.gap == 0.0
