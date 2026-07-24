import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .pipeline.context import PipelineContext, EpisodeSpec
from .pipeline.runner import PipelineRunner
from .pipeline.gates import Gate0PreGenerate, Gate1PostGenerateRaw, Gate2PostGenerate
from .stages.prep import PrepStage
from .stages.generate import GenerateStage
from .stages.postprocess import PostprocessStage
from .stages.assets import AssetsStage
from .providers.codex import CodexProvider, CodexStatus
from .providers.chromakey import ChromaKeyProvider
from .providers.vision import VisionProvider
from .story.library import LinkageLibrary
from .story.selector import StorySelector
import sticker_engine as _se


@dataclass
class Episode:
    """一次 run 的产出。"""
    episode_dir: Optional[Path] = None
    stickers: list = field(default_factory=list)
    meaning_map: dict = field(default_factory=dict)
    assets: object = None
    production_log: list = field(default_factory=list)


class _S2Adapter:
    """把 PostprocessStage.run(ctx, gen_mode, transparent) 适配成单参 run(ctx)。"""

    def __init__(self, stage):
        self.stage = stage
        self.name = "S2"

    def run(self, ctx):
        self.stage.run(
            ctx,
            gen_mode="story",
            transparent=ctx.episode.transparent_default,
        )


class _FailingCodex:
    """测试用：check() 总是失败。"""

    def check(self):
        return CodexStatus(
            installed=False, logged_in=False, image_ready=False,
            guidance_msg="测试：codex 不可用")

    def generate(self, *a, **kw):
        return None


class StickerEngine:
    """表情包一键制作 · 核心引擎门面。"""

    def __init__(self, config):
        self.config = config
        self._test_mocks = None

    def _inject_test_mocks(self, codex_ready=True, **kw):
        """测试专用：注入 mock providers，绕过真实 codex。"""
        self._test_mocks = {"codex_ready": codex_ready, **kw}

    def _build_providers(self):
        from unittest.mock import MagicMock
        if self._test_mocks is not None:
            if self._test_mocks.get("codex_ready"):
                codex = MagicMock()

                def _fake_gen(prompt, refs=None, timeout=None):
                    import os
                    import tempfile
                    fd, p = tempfile.mkstemp(
                        suffix=".png", dir=str(self.config.paths.user_data))
                    os.close(fd)
                    from PIL import Image
                    Image.new("RGBA", (400, 400), (255, 0, 255, 255)).save(p)
                    return Path(p)

                codex.generate.side_effect = _fake_gen
                codex.check.return_value = CodexStatus(True, True, True, "")
            else:
                codex = _FailingCodex()
            chromakey = ChromaKeyProvider()
            vision = MagicMock()
            vision.interpret.return_value = {i: f"含义{i}" for i in range(1, 17)}
            vision.write_intro.return_value = "测试介绍，软萌可爱。"
            return codex, chromakey, vision

        # 真实模式：未配置 paths（骨架调用）时退化为 _FailingCodex，
        # 让 runner 在 Gate0 早停，仍返回一个合法 Episode。
        if self.config.paths is None:
            return _FailingCodex(), ChromaKeyProvider(), _FailingCodex()

        paths = self.config.paths
        codex = CodexProvider(codex_exec=paths.codex_exec, output_dir=paths.codex_output_dir)
        chromakey = ChromaKeyProvider()
        vision = VisionProvider(codex)
        return codex, chromakey, vision

    def run(
        self,
        progress_callback: Optional[Callable] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Episode:
        codex, chromakey, vision = self._build_providers()
        res = Path(_se.__file__).parent / "resources"
        lib = LinkageLibrary.load(res / "linkage_scripts.json")
        import json
        keywords = {}
        kw_path = res / "keywords.json"
        if kw_path.exists():
            keywords = json.loads(kw_path.read_text(encoding="utf-8"))
        story_selector = StorySelector(lib.scripts, used=set())
        self._ensure_characters()
        ctx = PipelineContext(config=self.config, episode=EpisodeSpec.placeholder())
        runner = PipelineRunner(steps=[
            ("S0", PrepStage()),
            (Gate0PreGenerate(codex), "Gate0"),
            ("S1", GenerateStage(
                codex=codex, story_selector=story_selector, keywords=keywords)),
            (Gate1PostGenerateRaw(), "Gate1"),
            ("S2", _S2Adapter(PostprocessStage(vision=vision, chromakey=chromakey))),
            (Gate2PostGenerate(), "Gate2"),
            ("S3", AssetsStage(vision=vision)),
        ])
        try:
            runner.run(ctx, progress_callback=progress_callback, stop_event=stop_event)
        except Exception:
            pass
        ep = Episode(
            episode_dir=ctx.episode_dir, stickers=ctx.stickers,
            meaning_map=ctx.meaning_map, assets=ctx.assets)
        ep.production_log = list(ctx.production_log)
        return ep

    def _ensure_characters(self):
        if self.config.characters:
            return
        res = Path(_se.__file__).parent / "resources" / "default_config.yaml"
        if res.exists():
            import yaml
            data = yaml.safe_load(res.read_text(encoding="utf-8"))
            from .config.schema import Character
            chars = {}
            for name, info in data.get("characters", {}).items():
                chars[name] = Character(
                    name=name,
                    bases=info.get("bases", {}),
                    base_probs=info.get("base_probs", {}),
                )
            self.config.characters = chars
