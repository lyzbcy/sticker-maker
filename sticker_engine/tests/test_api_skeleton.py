import threading
from sticker_engine import StickerEngine, Config


def test_sticker_engine_can_be_constructed_with_config():
    engine = StickerEngine(Config.placeholder())
    assert engine is not None


def test_run_returns_episode_object_and_supports_callbacks():
    engine = StickerEngine(Config.placeholder())
    events = []
    stop = threading.Event()
    episode = engine.run(progress_callback=lambda ev: events.append(ev), stop_event=stop)
    # 骨架阶段：run 立即返回空 Episode，不发事件
    assert episode is not None
    assert hasattr(episode, "episode_dir")
    assert hasattr(episode, "stickers")
    assert hasattr(episode, "meaning_map")
    assert hasattr(episode, "assets")
    assert hasattr(episode, "production_log")
