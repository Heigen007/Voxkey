import os

import pytest


@pytest.fixture()
def config_dir(tmp_path, monkeypatch):
    """Point the whole config at a throwaway directory for one test."""
    monkeypatch.setenv('VOXKEY_CONFIG_DIR', str(tmp_path))
    monkeypatch.delenv('VOXKEY_API_KEY', raising=False)
    yield tmp_path
    os.environ.pop('VOXKEY_CONFIG_DIR', None)
