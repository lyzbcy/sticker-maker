"""shelf + batch + config 单测（mock playwright）。"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from sticker_engine.publish.config import PublishConfig, _default_tip_guide
from sticker_engine.publish.shelf import Shelf, ShelfResult
from sticker_engine.publish.batch import BatchState, BatchPublisher


# ---- config ----

def test_publish_config_defaults():
    cfg = PublishConfig()
    assert cfg.copyright == "捞鱼真不吃鱼"
    assert cfg.thanks_text == "谢谢你喜欢我~"
    assert cfg.theme == "万能通用"
    assert cfg.region == "全球"
    assert "软萌可爱" in cfg.style


def test_validate_tips_images_returns_missing(tmp_path):
    cfg = PublishConfig(tip_guide_img=tmp_path / "no.png", tip_thanks_img=tmp_path / "no2.png")
    missing = cfg.validate_tips_images()
    assert len(missing) == 2


def test_config_from_env_reads_account(tmp_path):
    env = tmp_path / ".env"
    import base64
    pwd_b64 = base64.b64encode("secret123".encode()).decode()
    env.write_text(f"WECHAT_STICKER_ACCOUNT=test@qq.com\nWECHAT_STICKER_PASSWORD_ENCODED={pwd_b64}\n", encoding="utf-8")
    cfg = PublishConfig.from_env(env)
    assert cfg.account == "test@qq.com"
    assert cfg.password == "secret123"


# ---- shelf ----

def test_shelf_summarize_counts():
    from sticker_engine.publish.shelf import Shelf
    cfg = PublishConfig()
    session = MagicMock()
    shelf = Shelf(cfg, session)
    results = [ShelfResult("a", "OK"), ShelfResult("b", "FAIL"),
               ShelfResult("c", "SKIP"), ShelfResult("d", "UNKNOWN"), ShelfResult("e", "OK")]
    s = shelf._summarize(results)
    assert s == {"ok": 2, "fail": 1, "skip": 1, "unknown": 1}


def test_shelve_one_returns_skip_when_no_detail():
    cfg = PublishConfig()
    session = MagicMock()
    shelf = Shelf(cfg, session)
    row = MagicMock()
    row.query_selector.return_value = None   # 无详情链接
    status, reason = shelf._shelve_one(MagicMock(), row)
    assert status == "SKIP"


def test_is_shelved_success_detects_keywords():
    cfg = PublishConfig()
    session = MagicMock()
    shelf = Shelf(cfg, session)
    page = MagicMock()
    page.inner_text.return_value = "操作成功，已预约今日上架"
    assert shelf._is_shelved_success(page) is True
    page.inner_text.return_value = "随便别的文案"
    # 无弹窗信息时返回 False
    page.query_selector.return_value = None
    assert shelf._is_shelved_success(page) is False


# ---- batch ----

def test_batch_state_save_load_roundtrip(tmp_path):
    state_path = tmp_path / "state.json"
    state = BatchState(results={"episode_1": "ok", "episode_2": "fail"})
    state.save(state_path)
    loaded = BatchState.load(state_path)
    assert loaded.results == {"episode_1": "ok", "episode_2": "fail"}
    assert loaded.is_done("episode_1") is True
    assert loaded.is_done("episode_2") is False


def test_batch_state_load_missing_returns_empty(tmp_path):
    loaded = BatchState.load(tmp_path / "nope.json")
    assert loaded.results == {}


def test_batch_publisher_list_episodes(tmp_path):
    # 造几个 episode 目录
    for n in [1, 2, 3]:
        (tmp_path / f"episode_20260101_120000_{n:02d}").mkdir()
    cfg = PublishConfig()
    batch = BatchPublisher(cfg, tmp_path)
    episodes = batch.list_episodes(1, 3)
    assert len(episodes) == 3
    nums = [n for n, _ in episodes]
    assert nums == [1, 2, 3]


def test_batch_run_skips_done_on_resume(tmp_path):
    # 造 episode
    ep = tmp_path / "episode_20260101_120000_01"
    ep.mkdir()
    (ep / "最终版").mkdir()
    (ep / "最终版" / "开心.png").write_bytes(b"x")
    cfg = PublishConfig(tip_guide_img=tmp_path / "g.png", tip_thanks_img=tmp_path / "t.png")
    # 造赞赏图（绕过校验）
    cfg.tip_guide_img.write_bytes(b"x")
    cfg.tip_thanks_img.write_bytes(b"x")
    batch = BatchPublisher(cfg, tmp_path)
    # mock _publish_one_with_retry 返回 ok
    batch._publish_one_with_retry = MagicMock(return_value="ok")
    # 先正常跑
    result = batch.run(start=1, end=1, resume=False)
    assert result["summary"]["ok"] == 1
    # 再 resume：应跳过已成功的
    batch._publish_one_with_retry.reset_mock()
    result2 = batch.run(start=1, end=1, resume=True)
    assert batch._publish_one_with_retry.call_count == 0   # 跳过，不重发
    assert "skipped" in result2["results"][ep.name]
