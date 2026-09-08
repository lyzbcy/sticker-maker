# -*- coding: utf-8 -*-
"""发布凭据读取：旧版 password_b64 格式必须兼容（2026-09-07 真机事故）。"""
import base64
import json

from sticker_engine.publish import credentials as cred


def _write_file(tmp_path, payload):
    f = tmp_path / "publish_credentials.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    return f


def test_legacy_password_b64_is_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(cred, "_keyring_ok", lambda: False)
    monkeypatch.setattr(cred, "_fallback_file", lambda: tmp_path / "publish_credentials.json")
    _write_file(tmp_path, {"account": "a@b.c", "password_b64":
                           base64.b64encode("秘密123".encode()).decode()})
    account, password = cred.load_credentials()
    assert account == "a@b.c" and password == "秘密123"


def test_plain_password_still_preferred(tmp_path, monkeypatch):
    monkeypatch.setattr(cred, "_keyring_ok", lambda: False)
    monkeypatch.setattr(cred, "_fallback_file", lambda: tmp_path / "publish_credentials.json")
    _write_file(tmp_path, {"account": "a@b.c", "password": "plain"})
    assert cred.load_credentials() == ("a@b.c", "plain")


def test_corrupt_b64_falls_back_to_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cred, "_keyring_ok", lambda: False)
    monkeypatch.setattr(cred, "_fallback_file", lambda: tmp_path / "publish_credentials.json")
    _write_file(tmp_path, {"account": "a@b.c", "password_b64": "!!!not-b64!!!"})
    account, password = cred.load_credentials()
    assert account == "a@b.c" and password is None
