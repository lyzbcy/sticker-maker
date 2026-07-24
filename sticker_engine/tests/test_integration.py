import threading
from pathlib import Path
from unittest.mock import MagicMock

from sticker_engine import StickerEngine, Config
from sticker_engine.config.schema import Paths, Prefs, ModeProbsConfig
from sticker_engine.pipeline.context import EpisodeSpec


def _build_config(tmp_path):
    config = Config.placeholder()
    config.paths = Paths(
        user_data=tmp_path, output_root=tmp_path / "e", reference_lib=tmp_path / "ref",
        prefs_file=tmp_path / "p.yaml", codex_exec="codex", codex_output_dir=tmp_path / "c")
    config.prefs = Prefs()
    return config


def test_engine_run_emits_progress_events_in_order(tmp_path):
    config = _build_config(tmp_path)
    engine = StickerEngine(config)
    engine._inject_test_mocks()
    events = []
    episode = engine.run(progress_callback=lambda ev: events.append(ev))
    stages = [e.stage for e in events]
    assert any("S0" in s for s in stages)
    assert any("S3" in s for s in stages)
    assert events[-1].percent == 1.0


def test_engine_run_stops_when_stop_event_set(tmp_path):
    config = _build_config(tmp_path)
    engine = StickerEngine(config)
    engine._inject_test_mocks()
    stop = threading.Event()
    stop.set()
    episode = engine.run(stop_event=stop)
    assert episode is not None


def test_gate0_fails_when_codex_not_ready(tmp_path):
    config = _build_config(tmp_path)
    engine = StickerEngine(config)
    engine._inject_test_mocks(codex_ready=False)
    episode = engine.run()
    assert len(episode.production_log) > 0
