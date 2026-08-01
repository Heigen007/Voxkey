"""Request shape and error mapping, with no network involved."""

import dataclasses

import pytest

from voxkey import config, strings, transcriber

WAV = b'RIFF....fake'


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ''

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


@pytest.fixture()
def captured(monkeypatch):
    """Capture the outgoing request instead of sending it."""
    calls = {}

    def fake_post(url, **kwargs):
        calls['url'] = url
        calls.update(kwargs)
        return calls.get('response') or FakeResponse(payload={'text': 'hello there'})

    monkeypatch.setattr(transcriber.requests, 'post', fake_post)
    return calls


def settings(**overrides):
    return dataclasses.replace(config.Settings(api_key='sk-test'), **overrides)


def test_posts_to_the_provider_endpoint(captured):
    transcriber.transcribe(WAV, settings())
    assert captured['url'] == 'https://api.openai.com/v1/audio/transcriptions'
    assert captured['headers']['Authorization'] == 'Bearer sk-test'
    assert captured['data']['model'] == 'whisper-1'


def test_groq_goes_to_groq(captured):
    transcriber.transcribe(WAV, settings(provider='groq'))
    assert captured['url'] == 'https://api.groq.com/openai/v1/audio/transcriptions'
    assert captured['data']['model'] == 'whisper-large-v3-turbo'


def test_optional_fields_are_omitted_when_empty(captured):
    transcriber.transcribe(WAV, settings())
    assert 'language' not in captured['data']
    assert 'prompt' not in captured['data']


def test_optional_fields_are_sent_when_set(captured):
    transcriber.transcribe(WAV, settings(language='ru', vocabulary='Astana, ORA'))
    assert captured['data']['language'] == 'ru'
    assert captured['data']['prompt'] == 'Astana, ORA'


def test_a_keyless_local_endpoint_sends_no_auth_header(captured):
    transcriber.transcribe(
        WAV, dataclasses.replace(config.Settings(), provider='custom', base_url='http://localhost:8000/v1')
    )
    assert 'Authorization' not in captured['headers']
    assert captured['url'] == 'http://localhost:8000/v1/audio/transcriptions'


def test_returns_the_transcript(captured):
    assert transcriber.transcribe(WAV, settings()) == 'hello there'


def test_empty_transcript_is_an_error(captured):
    captured['response'] = FakeResponse(payload={'text': '   '})
    with pytest.raises(transcriber.TranscriptionError) as error:
        transcriber.transcribe(WAV, settings())
    assert str(error.value) == strings.ERROR_NO_SPEECH


@pytest.mark.parametrize(
    ('status', 'expected'),
    [
        (401, strings.ERROR_BAD_KEY),
        (403, strings.ERROR_NO_ACCESS),
        (413, strings.ERROR_TOO_LONG),
        (429, strings.ERROR_RATE_LIMIT),
    ],
)
def test_http_errors_become_readable_messages(captured, status, expected):
    captured['response'] = FakeResponse(status_code=status, payload={})
    with pytest.raises(transcriber.TranscriptionError) as error:
        transcriber.transcribe(WAV, settings())
    assert str(error.value) == expected


def test_missing_model_names_the_model(captured):
    captured['response'] = FakeResponse(status_code=404, payload={})
    with pytest.raises(transcriber.TranscriptionError) as error:
        transcriber.transcribe(WAV, settings(model='nope-1'))
    assert 'nope-1' in str(error.value)


def test_server_error_names_the_provider(captured):
    captured['response'] = FakeResponse(status_code=503, payload={})
    with pytest.raises(transcriber.TranscriptionError) as error:
        transcriber.transcribe(WAV, settings(provider='groq'))
    assert 'Groq' in str(error.value)


def test_timeout_is_reported_not_raised_raw(monkeypatch):
    def boom(*_args, **_kwargs):
        raise transcriber.requests.Timeout()

    monkeypatch.setattr(transcriber.requests, 'post', boom)
    with pytest.raises(transcriber.TranscriptionError) as error:
        transcriber.transcribe(WAV, settings())
    assert str(error.value) == strings.ERROR_TIMEOUT


def test_cleanup_returns_the_original_text_when_the_call_fails(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError('down')

    monkeypatch.setattr(transcriber.requests, 'post', boom)
    assert transcriber.cleanup('raw dictation', settings(cleanup=True)) == 'raw dictation'
