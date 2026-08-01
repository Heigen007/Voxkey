"""Microphone capture into an in-memory 16 kHz mono WAV.

Speech models want mono; 16 kHz 16-bit keeps a five-minute take under 10 MB
with no quality loss for speech, well inside every provider's upload limit.
"""

from __future__ import annotations

import io
import threading
import time
import wave
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

from .strings import ERROR_NO_MIC, ERROR_NOTHING_RECORDED


class RecorderError(Exception):
    """Raised when the microphone cannot be opened or produced nothing."""


@dataclass(frozen=True)
class TakeStats:
    """What actually happened during one take.

    `audio_seconds` counts samples that really arrived; `wall_seconds` is how
    long the recording was open. A gap between them means the stream died or
    dropped audio while the UI still said "recording" - which is the one
    failure that silently eats half a dictation.
    """

    audio_seconds: float
    wall_seconds: float
    xruns: int
    last_status: str

    @property
    def gap(self) -> float:
        return max(0.0, self.wall_seconds - self.audio_seconds)


class Recorder:
    """Non-blocking microphone recorder with a live level readout."""

    def __init__(self, sample_rate: int, max_seconds: int) -> None:
        self._sample_rate = sample_rate
        self._max_frames = sample_rate * max_seconds
        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._frames = 0
        self._level = 0.0
        self._overrun = False
        self._stream: sd.InputStream | None = None
        self._started_at = 0.0
        self._stopped_at = 0.0
        self._xruns = 0
        self._last_status = ''

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Open the default input device and begin buffering audio."""
        if self._stream is not None:
            return
        with self._lock:
            self._chunks = []
            self._frames = 0
            self._level = 0.0
            self._overrun = False
            self._xruns = 0
            self._last_status = ''
            self._started_at = time.monotonic()
            self._stopped_at = 0.0
        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype='int16',
                blocksize=1024,
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as error:  # sounddevice raises a family of errors
            self._stream = None
            raise RecorderError(ERROR_NO_MIC.format(reason=error)) from error

    def stop(self) -> bytes:
        """Close the stream and return the take as WAV bytes."""
        self._close()
        with self._lock:
            chunks = list(self._chunks)
        if not chunks:
            raise RecorderError(ERROR_NOTHING_RECORDED)
        return _to_wav(np.concatenate(chunks), self._sample_rate)

    def cancel(self) -> None:
        """Close the stream and throw the audio away."""
        self._close()
        with self._lock:
            self._chunks = []
            self._frames = 0

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        with self._lock:
            self._stopped_at = time.monotonic()
        try:
            stream.stop()
            stream.close()
        except Exception:  # noqa: BLE001 - closing a dead device must not crash the app
            pass

    # -- live state ------------------------------------------------------

    @property
    def level(self) -> float:
        """Smoothed input loudness, 0.0 .. 1.0, for the meter."""
        with self._lock:
            return self._level

    @property
    def seconds(self) -> float:
        with self._lock:
            return self._frames / self._sample_rate

    @property
    def overrun(self) -> bool:
        """True once the take hit the maximum length and must be stopped."""
        with self._lock:
            return self._overrun

    @property
    def stats(self) -> TakeStats:
        with self._lock:
            end = self._stopped_at or time.monotonic()
            return TakeStats(
                audio_seconds=self._frames / self._sample_rate,
                wall_seconds=max(0.0, end - self._started_at) if self._started_at else 0.0,
                xruns=self._xruns,
                last_status=self._last_status,
            )

    # -- audio thread ----------------------------------------------------

    def _on_audio(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        """PortAudio callback. Must stay cheap - it runs on the audio thread."""
        if status:
            with self._lock:
                self._xruns += 1
                self._last_status = str(status)

        block = indata.copy().reshape(-1)
        rms = float(np.sqrt(np.mean(np.square(block.astype(np.float32)))))
        # Perceptual-ish curve so quiet speech still moves the meter.
        level = min(1.0, (rms / 32768.0 * 14.0) ** 0.6)
        with self._lock:
            self._chunks.append(block)
            self._frames += frames
            # Fast attack, slow release reads better than raw RMS.
            self._level = max(level, self._level * 0.82)
            if self._frames >= self._max_frames:
                self._overrun = True


def _to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())
    return buffer.getvalue()
