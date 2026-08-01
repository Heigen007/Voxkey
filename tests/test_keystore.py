from voxkey import keystore


def test_roundtrip():
    record = keystore.protect('sk-secret')
    assert record['value'] != 'sk-secret'
    assert keystore.unprotect(record) == 'sk-secret'


def test_empty_key_stays_empty():
    record = keystore.protect('')
    assert keystore.unprotect(record) == ''


def test_plain_record_is_read_back():
    assert keystore.unprotect({'scheme': 'plain', 'value': 'sk-plain'}) == 'sk-plain'


def test_bare_string_from_a_hand_edited_config():
    assert keystore.unprotect('sk-typed-by-hand') == 'sk-typed-by-hand'


def test_garbage_does_not_raise():
    assert keystore.unprotect(None) == ''
    assert keystore.unprotect(42) == ''
    assert keystore.unprotect({'scheme': 'dpapi', 'value': 'not-base64!!'}) == ''
