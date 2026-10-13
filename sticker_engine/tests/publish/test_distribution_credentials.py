import pytest
from sticker_engine.publish import credentials

def test_no_plaintext_credentials_if_keyring_unavailable(tmp_path,monkeypatch):
    monkeypatch.setattr(credentials,'_keyring_ok',lambda:False)
    monkeypatch.setattr(credentials,'_fallback_file',lambda:tmp_path/'secret.json')
    with pytest.raises(RuntimeError,match='系统凭据库'):
        credentials.save_credentials('sample','fixture-password')
    assert not (tmp_path/'secret.json').exists()
