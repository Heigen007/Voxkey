"""Speech-to-text over the OpenAI audio API, plus an optional clean-up pass."""

from __future__ import annotations

import logging

import requests

from . import providers, strings
from .config import Settings

logger = logging.getLogger(__name__)

CLEANUP_INSTRUCTION = (
    'You are an editor of spoken text. Turn the transcript into clean written '
    'prose: drop filler words and false starts, fix punctuation and paragraphs, '
    'correct obvious mis-hearings. Do not add anything, do not shorten the '
    'meaning, do not answer the text. Reply with the edited version only, in '
    'the same language as the input.'
)


class TranscriptionError(Exception):
    """Raised with a short, user-facing message when the API call fails."""


def transcribe(wav_bytes: bytes, settings: Settings) -> str:
    """Send WAV audio to the configured provider and return the text."""
    info = providers.get(settings.provider)
    data = {'model': settings.resolved_model, 'response_format': 'json'}
    if settings.language.strip():
        data['language'] = settings.language.strip()
    if settings.vocabulary.strip():
        data['prompt'] = settings.vocabulary.strip()

    try:
        response = requests.post(
            f'{settings.resolved_base_url}/audio/transcriptions',
            headers=_auth(settings),
            files={'file': ('speech.wav', wav_bytes, 'audio/wav')},
            data=data,
            timeout=settings.request_timeout,
        )
    except requests.Timeout as error:
        raise TranscriptionError(strings.ERROR_TIMEOUT) from error
    except requests.RequestException as error:
        raise TranscriptionError(strings.ERROR_OFFLINE.format(provider=info.label)) from error

    if response.status_code != 200:
        raise TranscriptionError(_describe_http_error(response, settings))

    try:
        text = (response.json().get('text') or '').strip()
    except ValueError as error:
        raise TranscriptionError(
            strings.ERROR_GENERIC.format(status=response.status_code, message='bad response')
        ) from error

    if not text:
        raise TranscriptionError(strings.ERROR_NO_SPEECH)
    return text


def cleanup(text: str, settings: Settings) -> str:
    """Tidy the transcript with a chat model.

    Best-effort by design: any failure returns the original text, because
    losing a dictation to a clean-up hiccup is far worse than filler words.
    """
    model = settings.resolved_cleanup_model
    if not model:
        return text
    try:
        response = requests.post(
            f'{settings.resolved_base_url}/chat/completions',
            headers={**_auth(settings), 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': CLEANUP_INSTRUCTION},
                    {'role': 'user', 'content': text},
                ],
            },
            timeout=settings.request_timeout,
        )
        if response.status_code != 200:
            logger.warning('cleanup: HTTP %s: %s', response.status_code, response.text[:300])
            return text
        cleaned = (response.json()['choices'][0]['message']['content'] or '').strip()
        return cleaned or text
    except Exception as error:  # noqa: BLE001 - clean-up must never break the flow
        logger.warning('cleanup: failed, using the raw transcript: %s', error)
        return text


def _auth(settings: Settings) -> dict[str, str]:
    key = settings.api_key.strip()
    return {'Authorization': f'Bearer {key}'} if key else {}


def _describe_http_error(response: requests.Response, settings: Settings) -> str:
    """Turn an API error into something readable on a 360 px overlay."""
    info = providers.get(settings.provider)
    status = response.status_code

    if status == 401:
        return strings.ERROR_BAD_KEY
    if status == 403:
        return strings.ERROR_NO_ACCESS
    if status == 404:
        return strings.ERROR_NO_MODEL.format(model=settings.resolved_model)
    if status == 413:
        return strings.ERROR_TOO_LONG
    if status == 429:
        return strings.ERROR_RATE_LIMIT
    if status >= 500:
        return strings.ERROR_SERVER.format(provider=info.label, status=status)

    message = ''
    try:
        message = str(response.json().get('error', {}).get('message', ''))
    except ValueError:
        message = response.text[:120]
    logger.error('transcribe: HTTP %s: %s', status, response.text[:500])
    return strings.ERROR_GENERIC.format(status=status, message=message[:90] or 'unknown')
