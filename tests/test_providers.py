from voxkey import providers


def test_every_provider_has_what_the_settings_window_needs():
    for key, info in providers.PROVIDERS.items():
        assert info.key == key
        assert info.label
        assert info.notes
        assert info.default_model or info.editable_base_url


def test_unknown_provider_falls_back_to_the_default():
    assert providers.get('nope').key == providers.DEFAULT_PROVIDER


def test_label_roundtrip():
    for info in providers.PROVIDERS.values():
        assert providers.key_for_label(info.label) == info.key


def test_model_defaults_when_empty():
    assert providers.resolve_model('groq', '') == 'whisper-large-v3-turbo'
    assert providers.resolve_model('groq', 'custom-model') == 'custom-model'


def test_base_url_is_fixed_for_hosted_providers():
    assert providers.resolve_base_url('openai', 'http://evil.example') == 'https://api.openai.com/v1'


def test_custom_provider_accepts_a_url_and_strips_the_slash():
    assert providers.resolve_base_url('custom', 'http://localhost:9000/v1/') == 'http://localhost:9000/v1'


def test_custom_provider_without_a_url_is_not_a_crash():
    assert providers.resolve_base_url('custom', '') == ''
