import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from sticker_engine.publish.browser import BrowserSession
from sticker_engine.publish.config import PublishConfig


def test_unverified_cached_session_is_not_reused_for_bound_account(tmp_path, monkeypatch):
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path))
    state = tmp_path / 'resource_library/device.json'; state.parent.mkdir()
    state.write_text(json.dumps({'account_id': 'a', 'account_label': 'a@example.com', 'library_id':'lib'}))
    cfg = PublishConfig(); cfg.storage_state.parent.mkdir(parents=True, exist_ok=True)
    cfg.storage_state.write_text('{}')
    pw = MagicMock()
    session = BrowserSession(cfg, playwright=pw)
    monkeypatch.setattr(session, '_load_credentials', lambda: ('a@example.com', 'pw'))
    session.start(headless=False)
    assert 'storage_state' not in pw.chromium.launch.return_value.new_context.call_args.kwargs


def test_bound_account_mismatch_blocks_browser_before_launch(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path))
    state = tmp_path / 'resource_library/device.json'; state.parent.mkdir()
    state.write_text(json.dumps({'account_id':'a','account_label':'a@example.com','library_id':'lib'}))
    pw = MagicMock(); session = BrowserSession(PublishConfig(), playwright=pw)
    monkeypatch.setattr(session, '_load_credentials', lambda: ('b@example.com', 'pw'))
    with pytest.raises(ValueError, match='账号'):
        session.start(headless=False)
    pw.chromium.launch.assert_not_called()
