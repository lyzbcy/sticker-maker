import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional

from .pipeline.context import PipelineContext, EpisodeSpec
from .pipeline.runner import PipelineRunner, StopRequested
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
    """一次 run 的产出。success=False 表示关卡 FAIL 或被取消，调用方应查 errors/gate_errors。"""
    episode_dir: Optional[Path] = None
    stickers: list = field(default_factory=list)
    meaning_map: dict = field(default_factory=dict)
    assets: object = None
    production_log: list = field(default_factory=list)
    success: bool = True
    errors: list = field(default_factory=list)   # list[GateError]，关卡失败记录
    aborted_reason: str = ""   # 非空表示被取消/异常中止的原因
    # S3 图标降级（AI 大头照失败退回复用封面）：批量自动发布路径据此跳过该单
    icon_fallback: bool = False
    # S3 封面降级（header 格缺失/裁剪失败退回旧缩放）：批量自动发布据此跳过
    cover_fallback: bool = False


class _FailingCodex:
    """测试用：check() 总是失败。"""

    def check(self):
        return CodexStatus(
            installed=False, logged_in=False, image_ready=False,
            guidance_msg="测试：codex 不可用")

    def generate(self, *a, **kw):
        return None


# 系列取号互斥（2026-09-10 批量双生图工位）：occupied 扫描→take_number→
# save_series 必须原子，否则双工位并发会重号/漏号。
_SERIES_NUMBER_LOCK = threading.Lock()


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

                def _fake_gen(prompt, refs=None, timeout=None, on_wait=None):
                    import os
                    import tempfile
                    fd, p = tempfile.mkstemp(
                        suffix=".png", dir=str(self.config.paths.user_data))
                    os.close(fd)
                    from PIL import Image
                    # 洋红底 + 深洋红方块：不能是纯色图（S1 废图质检会拦），
                    # 且两种色都在洋红键控范围内，不影响后续抠图
                    im = Image.new("RGBA", (400, 400), (255, 0, 255, 255))
                    for i in range(0, 400, 100):
                        for j in range(0, 400, 100):
                            if (i + j) // 100 % 2 == 0:
                                im.paste((220, 0, 220, 255), (i + 25, j + 25, i + 75, j + 75))
                    im.save(p)
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

    def _build_episode_spec(self) -> EpisodeSpec:
        """M3 修复：从 config.prefs 构造 EpisodeSpec，而非用 placeholder 忽略用户偏好。"""
        prefs = self.config.prefs
        return EpisodeSpec(
            grid_size=prefs.grid_size,
            transparent_default=prefs.transparent_default,
            story_mode=prefs.story_mode,
            ref_lib_priority=prefs.ref_lib_priority,
        )

    def run(self, progress_callback=None, stop_event=None, prefs_override=None) -> Episode:
        """Persist every generated item, including direct scheduler/agent calls."""
        from .library.hooks import runtime_for
        from .library.commands import LOCK, batch_lock_held
        runtime = runtime_for(self)
        if runtime is None:
            return self._run_with_overrides(progress_callback, stop_event, prefs_override)
        # 批量流水线的工作线程豁免：锁由 run_batch 命令线程持有（RLock
        # 跨线程不可重入，2026-09-09 流水线事故）。max_age 让批量内连续
        # 多弹共享 refresh 缓存，不再每弹冷跑全量扫描（此前每弹多 ~100s）
        need_release = False
        if not batch_lock_held():
            if not LOCK.acquire(blocking=False):
                return Episode(success=False, aborted_reason="资源任务正在进行，请稍后重试")
            need_release = True
        try:
            status = runtime.refresh(max_age=600)
            if isinstance(status, dict) and status.get('offline'):
                return Episode(success=False,
                               aborted_reason='共享资源库当前不可用，已停止生成；请恢复同步目录后重试')
            from .library.hooks import reload_engine_config
            reload_engine_config(self, runtime)
            episode = self._run_with_overrides(progress_callback, stop_event, prefs_override)
            if episode.episode_dir and Path(episode.episode_dir).is_dir():
                try:
                    runtime.capture(episode.episode_dir)
                    from .library.settings import SharedSettings
                    SharedSettings(runtime).capture()
                except Exception as exc:
                    episode.success = False
                    episode.aborted_reason = f"作品保留在本机，但写入资源库失败：{exc}"
            return episode
        finally:
            if need_release:
                LOCK.release()

    def _run_with_overrides(self, progress_callback, stop_event, overrides):
        """One generation's experiment settings never overwrite shared defaults."""
        if overrides is None:
            return self._run_impl(progress_callback=progress_callback, stop_event=stop_event)
        allowed = {'prompt_set_id', 'background_mode', 'sticker_text',
                   'ref_lib_priority', 'story_mode', 'vision_calls'}
        if not isinstance(overrides, dict) or set(overrides) - allowed:
            raise ValueError('单弹参数只接受方案、背景、配字及生图模式')
        for key in ('sticker_text', 'ref_lib_priority', 'story_mode', 'vision_calls'):
            if key in overrides and type(overrides[key]) is not bool:
                raise ValueError(f'{key} 必须是布尔值')
        if 'background_mode' in overrides and overrides['background_mode'] not in ('solid', 'transparent'):
            raise ValueError('背景必须为solid或transparent')
        if 'prompt_set_id' in overrides:
            set_id = overrides['prompt_set_id']
            if set_id is not None:
                from .config.prompts import list_sets
                paths = self.config.paths
                root = (getattr(paths, 'assets_root', None) or getattr(paths, 'user_data', None))
                if not isinstance(set_id, str) or root is None or not any(s.id == set_id for s in list_sets(root)):
                    raise ValueError('指定的Prompt方案不存在')
        original = self.config
        self.config = replace(original, prefs=replace(original.prefs, **overrides))
        try:
            return self._run_impl(progress_callback=progress_callback, stop_event=stop_event)
        finally:
            self.config = original

    def _run_impl(
        self,
        progress_callback: Optional[Callable] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Episode:
        codex, chromakey, vision = self._build_providers()
        res = _se.resources_path()
        lib = LinkageLibrary.load(res / "linkage_scripts.json")
        import json
        keywords = {}
        kw_path = res / "keywords.json"
        if kw_path.exists():
            keywords = json.loads(kw_path.read_text(encoding="utf-8"))
        story_selector = StorySelector(lib.scripts, used=set())
        self._ensure_characters()
        ctx = PipelineContext(config=self.config, episode=self._build_episode_spec())
        runner = PipelineRunner(steps=[
            ("S0", PrepStage()),
            (Gate0PreGenerate(codex), "Gate0"),
            ("S1", GenerateStage(
                codex=codex, story_selector=story_selector, keywords=keywords)),
            (Gate1PostGenerateRaw(), "Gate1"),
            ("S2", PostprocessStage(vision=vision, chromakey=chromakey)),
            (Gate2PostGenerate(), "Gate2"),
            ("S3", AssetsStage(vision=vision)),
        ])
        aborted_reason = ""
        try:
            runner.run(ctx, progress_callback=progress_callback, stop_event=stop_event)
        except StopRequested:
            aborted_reason = "用户取消（stop_event）"
        except Exception as e:
            # C2 修复：真实 bug 不再静默吞掉，记进 aborted_reason 暴露给调用方
            aborted_reason = f"运行异常：{type(e).__name__}: {e}"
        # C2 修复：success 由关卡 errors / 异常决定，调用方可据 success 区分成功失败
        success = not ctx.errors and not aborted_reason
        # 成功后自动按默认系列编号命名（prefs.default_series_id）：
        # 「周思涵做表情系列」起始 60 → 专辑名「周思涵做表情 60」，同系列下一个 61
        if success and ctx.episode_dir is not None:
            try:
                from .config.series import (find_series, assign_to_series,
                                            load_series, save_series)
                sid = getattr(self.config.prefs, "default_series_id", None)
                target = find_series(sid) if sid else None
                if target is not None:
                    # 2026-09-10 批量双生图工位：取号段全程持锁——occupied
                    # 扫描/take_number/save_series 三步在两线程并发时会
                    # 互相覆盖 next_number（重号）或漏扫对方（同号）。锁只
                    # 包命名段（~1s），生图主体仍在双工位并行。
                    with _SERIES_NUMBER_LOCK:
                        # 跳过已占号（历史偶数空缺自动补齐；occupied=本地全部
                        # 已用编号。批量双重取号事故的补救能力）
                        _occupied = set()
                        try:
                            _root = self.config.paths.output_root
                            from pathlib import Path as _P
                            from .config.series import load_meta as _lm0
                            for _d in _P(_root).iterdir() if _P(_root).exists() else []:
                                if _d.is_dir() and _d.name.startswith("episode"):
                                    _m = _lm0(_d)
                                    if _m.number:
                                        _occupied.add(_m.number)
                        except Exception:
                            _occupied = set()
                        target = find_series(sid) if sid else None
                        if target is not None:
                            assign_to_series(ctx.episode_dir, target,
                                             occupied=_occupied)
                            all_series = load_series()
                            for s in all_series:
                                if s.id == target.id:
                                    s.next_number = target.next_number
                            save_series(all_series)
            except Exception:
                pass   # 命名失败不影响作品产出
            # 命名后重写介绍（2026-09-04：S3 生成介绍在命名之前，《》里
            # 只能写目录名——156-160 五单带着《episode_20260903_xxx》简介
            # 上了平台。这里用最终专辑名重写本地介绍.txt）
            if success and ctx.episode_dir is not None:
                try:
                    from .config.series import load_meta as _lm
                    from .stages.assets import rewrite_intro_with_album
                    _album = _lm(ctx.episode_dir).album_name
                    if _album and not _album.startswith("episode_"):
                        rewrite_intro_with_album(ctx.episode_dir, _album)
                except Exception:
                    pass
        ep = Episode(
            episode_dir=ctx.episode_dir, stickers=ctx.stickers,
            meaning_map=ctx.meaning_map, assets=ctx.assets,
            success=success, errors=list(ctx.errors), aborted_reason=aborted_reason,
            icon_fallback=bool(getattr(ctx, "icon_fallback", False)),
            cover_fallback=bool(getattr(ctx, "cover_fallback", False)))
        ep.production_log = list(ctx.production_log)
        return ep

    def _ensure_characters(self):
        if self.config.characters:
            return
        res = _se.resources_path() / "default_config.yaml"
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
