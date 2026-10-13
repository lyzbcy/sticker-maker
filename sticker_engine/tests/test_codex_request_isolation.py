"""独立回归：仅使用本地临时 PNG，不调用真实生图或历史用户图。"""
import os
import json
import io
import threading
import subprocess
from types import SimpleNamespace
from sticker_engine.providers.codex import CodexProvider

SESSION_A = '11111111-1111-1111-1111-111111111111'
SESSION_B = '22222222-2222-2222-2222-222222222222'

def image(root, session, name, mtime):
    path = root / session / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'fixture-not-real-image')
    os.utime(path, (mtime, mtime))
    return path

def output(session):
    return json.dumps({'type': 'thread.started', 'thread_id': session})

def test_current_request_does_not_harvest_another_concurrent_session(tmp_path):
    provider = CodexProvider(output_dir=tmp_path)
    own = image(tmp_path, SESSION_A, 'own.png', 1100)
    image(tmp_path, SESSION_B, 'other.png', 1200)
    assert provider._image_for_request(1000, output(SESSION_A)) == own

def test_historical_image_in_own_session_is_not_fresh(tmp_path):
    provider = CodexProvider(output_dir=tmp_path)
    image(tmp_path, SESSION_A, 'history.png', 900)
    image(tmp_path, SESSION_B, 'concurrent.png', 1100)
    assert provider._image_for_request(1000, output(SESSION_A)) is None

def test_success_exit_without_thread_identity_must_not_claim_an_image(tmp_path):
    provider = CodexProvider(output_dir=tmp_path)
    image(tmp_path, SESSION_A, 'new.png', 1100)
    assert provider._image_for_request(1000, 'tool failed or no thread.started') is None

def test_choose_latest_fresh_image_only_in_current_session(tmp_path):
    provider = CodexProvider(output_dir=tmp_path)
    image(tmp_path, SESSION_A, 'draft.png', 1001)
    final = image(tmp_path, SESSION_A, 'final.png', 1002)
    image(tmp_path, SESSION_B, 'other.png', 1003)
    assert provider._image_for_request(1000, output(SESSION_A)) == final

def test_process_exit_waits_for_final_thread_identity_before_snapshot(tmp_path, monkeypatch):
    """确定性模拟进程已退出但 reader 仅在 join 时读到最后 JSON 行。"""
    own = image(tmp_path, SESSION_A, 'final.png', 1100)
    provider = CodexProvider(output_dir=tmp_path)
    class DeferredPump:
        def __init__(self, target, args, daemon):
            self.target, self.args, self.done = target, args, False
        def start(self):
            pass
        def join(self, timeout=None):
            if not self.done:
                self.target(*self.args)
                self.done = True
    monkeypatch.setattr(threading, 'Thread', DeferredPump)
    monkeypatch.setattr('sticker_engine.providers.codex.time.time', lambda: 1000)
    proc = SimpleNamespace(stdout=io.StringIO(output(SESSION_A)+'\n'), stderr=io.StringIO(''), returncode=0, poll=lambda:0)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: proc)
    assert provider.generate('isolated fake generation, no network') == own
