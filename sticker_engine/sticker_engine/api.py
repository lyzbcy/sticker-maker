from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
import threading


@dataclass
class Episode:
    """一次 run 的产出。"""
    episode_dir: Optional[Path] = None
    stickers: list = field(default_factory=list)
    meaning_map: dict = field(default_factory=dict)
    assets: object = None
    production_log: list = field(default_factory=list)


class StickerEngine:
    """表情包一键制作 · 核心引擎门面。"""

    def __init__(self, config):
        self.config = config

    def run(
        self,
        progress_callback: Optional[Callable] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Episode:
        # 骨架：后续 Task 3 接入 PipelineRunner
        return Episode()
