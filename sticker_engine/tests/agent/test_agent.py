"""D agent 测试：server 端点 + scheduler + 认证。"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sticker_engine.agent.server import _create_app
from sticker_engine.agent.scheduler import Scheduler, ScheduledJob


@pytest.fixture
def client():
    app = _create_app(token="test-token-123", scheduler=None)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _auth_headers():
    return {"Authorization": "Bearer test-token-123"}


# ---- 认证 ----

def test_no_token_returns_401(client):
    r = client.get("/status")
    assert r.status_code == 401


def test_wrong_token_returns_401(client):
    r = client.get("/status", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_health_no_auth_needed(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_agent_prompt_no_auth_needed(client):
    r = client.get("/agent-prompt")
    assert r.status_code == 200
    assert b"AI Agent" in r.data or b"agent" in r.data


# ---- status ----

def test_status_returns_codex_and_episodes(client, monkeypatch):
    # mock CodexProvider.check
    from sticker_engine.providers.codex import CodexStatus
    mock_status = CodexStatus(installed=True, logged_in=True, image_ready=True)
    monkeypatch.setattr("sticker_engine.providers.codex.CodexProvider.check",
                        lambda self: mock_status, raising=False)
    # mock resolve_paths 到临时
    r = client.get("/status", headers=_auth_headers())
    assert r.status_code == 200
    data = r.get_json()
    assert "codex_ready" in data
    assert "episodes" in data


# ---- run（SSE）----

def test_run_returns_sse_stream(client, monkeypatch):
    """run 返回 text/event-stream，含 progress + result。"""
    from sticker_engine import Episode
    from sticker_engine.pipeline.context import ProgressEvent
    fake_episode = Episode(success=True, episode_dir="/tmp/fake", stickers=[1]*16)

    def fake_run(self, progress_callback=None, stop_event=None):
        progress_callback(ProgressEvent(stage="S1", phase="x", message="m", percent=0.5))
        return fake_episode
    monkeypatch.setattr("sticker_engine.api.StickerEngine.run", fake_run)

    r = client.post("/run", headers=_auth_headers())
    assert r.status_code == 200
    assert "text/event-stream" in r.content_type
    # 解析 SSE
    text = r.get_data(as_text=True)
    assert "progress" in text
    assert "result" in text
    assert '"success": true' in text or '"success":true' in text


def test_stop_sets_stop_events(client, monkeypatch):
    r = client.post("/stop", headers=_auth_headers())
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


# ---- scheduler ----

def test_scheduler_add_list_remove(tmp_path):
    state = tmp_path / "schedules.json"
    sched = Scheduler(state_file=state)
    job = sched.add(cron="0 9 * * *", action="run")
    assert job.job_id in [j.job_id for j in sched.list()]
    assert job.cron == "0 9 * * *"
    # 删除
    assert sched.remove(job.job_id) is True
    assert sched.remove(job.job_id) is False   # 已删


def test_scheduler_persists_across_instances(tmp_path):
    state = tmp_path / "schedules.json"
    sched1 = Scheduler(state_file=state)
    sched1.add(cron="0 9 * * *", action="run")
    # 新实例加载持久化
    sched2 = Scheduler(state_file=state)
    jobs = sched2.list()
    assert len(jobs) == 1
    assert jobs[0].cron == "0 9 * * *"


def test_scheduler_trigger_fn_called(tmp_path):
    """trigger_fn 在定时触发时被调用。"""
    called = []
    sched = Scheduler(state_file=tmp_path / "s.json",
                      trigger_fn=lambda action, args: called.append((action, args)))
    sched._on_trigger("run", {"k": "v"}, "job1")
    assert called == [("run", {"k": "v"})]
