"""Speech-to-text providers.

Every provider here speaks the OpenAI audio API, so one HTTP client covers all
of them and adding another is a row in PROVIDERS plus, at most, a base URL.
That is deliberate: the point is to let people use whichever service they
already pay for - or a self-hosted endpoint - not to build an abstraction
layer over unrelated APIs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    """Everything the settings window needs to present a provider."""

    key: str
    label: str
    base_url: str
    default_model: str
    models: tuple[str, ...]
    default_cleanup_model: str
    signup_url: str
    notes: str
    editable_base_url: bool = False


PROVIDERS: dict[str, ProviderInfo] = {
    'openai': ProviderInfo(
        key='openai',
        label='OpenAI',
        base_url='https://api.openai.com/v1',
        default_model='whisper-1',
        models=('whisper-1', 'gpt-4o-transcribe', 'gpt-4o-mini-transcribe'),
        default_cleanup_model='gpt-4o-mini',
        signup_url='https://platform.openai.com/api-keys',
        notes=(
            'whisper-1 is the safe default: it never cuts a recording short. '
            'gpt-4o-transcribe is more accurate but, being a language model, '
            'can end a transcript early on a long pause.'
        ),
    ),
    'groq': ProviderInfo(
        key='groq',
        label='Groq',
        base_url='https://api.groq.com/openai/v1',
        default_model='whisper-large-v3-turbo',
        models=('whisper-large-v3-turbo', 'whisper-large-v3'),
        default_cleanup_model='llama-3.3-70b-versatile',
        signup_url='https://console.groq.com/keys',
        notes='Whisper large, much cheaper than OpenAI and usually faster. Has a free tier.',
    ),
    'custom': ProviderInfo(
        key='custom',
        label='Custom (OpenAI-compatible)',
        base_url='',
        default_model='whisper-1',
        models=(),
        default_cleanup_model='',
        signup_url='',
        notes=(
            'Any endpoint that implements POST /audio/transcriptions the way OpenAI does - '
            'a self-hosted Whisper server, a proxy, or another vendor.'
        ),
        editable_base_url=True,
    ),
}

DEFAULT_PROVIDER = 'openai'


def get(key: str) -> ProviderInfo:
    """Provider by key, falling back to the default for an unknown value."""
    return PROVIDERS.get(key, PROVIDERS[DEFAULT_PROVIDER])


def resolve_base_url(provider_key: str, custom_base_url: str) -> str:
    """The endpoint root to call, honouring a custom URL where allowed."""
    info = get(provider_key)
    url = custom_base_url.strip() if info.editable_base_url else info.base_url
    return (url or info.base_url).rstrip('/')


def resolve_model(provider_key: str, model: str) -> str:
    return model.strip() or get(provider_key).default_model


def resolve_cleanup_model(provider_key: str, model: str) -> str:
    return model.strip() or get(provider_key).default_cleanup_model


def labels() -> list[str]:
    return [info.label for info in PROVIDERS.values()]


def key_for_label(label: str) -> str:
    for info in PROVIDERS.values():
        if info.label == label:
            return info.key
    return DEFAULT_PROVIDER
