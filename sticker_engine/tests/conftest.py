"""Keep every test off the developer's real artwork, accounts and credentials."""
import pytest

@pytest.fixture(autouse=True)
def isolated_user_data(tmp_path, monkeypatch, request):
    if request.path.name != 'test_paths.py':
        monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path / 'isolated-device'))
    monkeypatch.setenv('STICKER_ENGINE_NO_LOCK', '1')
