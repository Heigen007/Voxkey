import dataclasses
import json

from voxkey import config


def test_defaults_when_nothing_saved(config_dir):
    settings = config.load()
    assert settings.provider == 'openai'
    assert settings.api_key == ''
    assert settings.hotkey == config.DEFAULT_HOTKEY
    assert settings.is_configured is False


def test_roundtrip(config_dir):
    original = dataclasses.replace(
        config.Settings(),
        api_key='sk-test-123',
        provider='groq',
        language='ru',
        hotkey='ctrl+alt+d',
        cleanup=True,
    )
    config.save(original)
    loaded = config.load()

    assert loaded.api_key == 'sk-test-123'
    assert loaded.provider == 'groq'
    assert loaded.language == 'ru'
    assert loaded.hotkey == 'ctrl+alt+d'
    assert loaded.cleanup is True
    assert loaded.is_configured is True


def test_key_is_not_written_in_plain_text(config_dir):
    config.save(dataclasses.replace(config.Settings(), api_key='sk-super-secret-value'))
    raw = config.config_path().read_text(encoding='utf-8')
    assert 'sk-super-secret-value' not in raw


def test_env_key_overrides_the_file(config_dir, monkeypatch):
    config.save(dataclasses.replace(config.Settings(), api_key='from-file'))
    monkeypatch.setenv('VOXKEY_API_KEY', 'from-env')
    assert config.load().api_key == 'from-env'


def test_broken_file_falls_back_to_defaults(config_dir):
    config.config_path().write_text('{ this is not json', encoding='utf-8')
    assert config.load().provider == 'openai'


def test_hand_edited_wrong_types_are_coerced_not_fatal(config_dir):
    config.config_path().write_text(
        json.dumps({'max_seconds': '120', 'cleanup': 1, 'language': 'de'}), encoding='utf-8'
    )
    settings = config.load()
    assert settings.max_seconds == 120
    assert settings.cleanup is True
    assert settings.language == 'de'


def test_custom_provider_with_url_but_no_key_counts_as_configured(config_dir):
    settings = dataclasses.replace(
        config.Settings(), provider='custom', base_url='http://localhost:8000/v1'
    )
    assert settings.is_configured is True
    assert settings.resolved_base_url == 'http://localhost:8000/v1'
