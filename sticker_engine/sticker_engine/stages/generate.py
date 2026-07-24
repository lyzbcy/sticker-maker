import enum
import random
import shutil
from pathlib import Path
from typing import Optional
from ..pipeline.context import PipelineContext, LogEntry
from ..providers.codex import CodexProvider
from ..resources.prompts.templates import (
    REF_LIBRARY_TEMPLATE, STORY_TEMPLATE, KEYWORD_COMBO_TEMPLATE)


class GenerationMode(enum.Enum):
    REF_LIBRARY = "ref_library"
    STORY = "story"
    KEYWORD_COMBO = "keyword_combo"


class GenerateStage:
    """S1：三模式分派 → 拼 prompt → 调 codex → 捞图。"""

    def __init__(self, codex: CodexProvider, story_selector=None, keywords=None, seed=None):
        self.codex = codex
        self.story_selector = story_selector   # Task 5 的 StorySelector
        self.keywords = keywords               # dict: {emotions, actions, backgrounds}
        self.rng = random.Random(seed)

    def decide_mode(self, ctx: PipelineContext) -> GenerationMode:
        prefs = ctx.config.prefs
        grid = ctx.episode.grid_size
        n = grid * grid
        # 参考图库优先（且够数）
        if prefs.ref_lib_priority and self._count_refs(ctx) >= n:
            return GenerationMode.REF_LIBRARY
        # 故事模式（按 episode 意图决定；selector 缺失/池耗尽在 _build 阶段降级，决策 L）
        if ctx.episode.story_mode:
            return GenerationMode.STORY
        # 降级/默认：排列组合
        return GenerationMode.KEYWORD_COMBO

    def _count_refs(self, ctx) -> int:
        ref_lib = ctx.config.paths.reference_lib
        if not ref_lib.exists():
            return 0
        return len([p for p in ref_lib.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")])

    def run(self, ctx: PipelineContext) -> None:
        mode = self.decide_mode(ctx)
        prompt, refs = self._build_prompt_and_refs(ctx, mode)
        # 生图
        grid_image = self.codex.generate(prompt=prompt, refs=refs)
        if grid_image is None:
            ctx.log(LogEntry(stage="S1", status="FAIL", message=f"codex 生图失败（mode={mode.value}）"))
            ctx.grid_image = None
            return
        # 复制到 episode 目录
        dst = ctx.episode_dir / "原图" / f"grid_{ctx.episode.grid_size}x{ctx.episode.grid_size}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(grid_image, dst)
        ctx.grid_image = dst
        ctx.log(LogEntry(stage="S1", status="OK", message=f"生图完成 mode={mode.value} → {dst.name}"))

    def _build_prompt_and_refs(self, ctx: PipelineContext, mode: GenerationMode):
        grid = ctx.episode.grid_size
        n = grid * grid
        # base 图始终是第一个 ref
        base_path = self._pick_base(ctx)
        refs = [base_path] if base_path else []
        prompt = ""

        if mode == GenerationMode.REF_LIBRARY:
            n_img = n + 1
            prompt = REF_LIBRARY_TEMPLATE.format(grid=grid, n=n, n_img=n_img)
            refs += self._pick_refs(ctx, n)
        elif mode == GenerationMode.STORY:
            # selector 未注入或池耗尽 → 降级 combo（决策 L）
            if self.story_selector is None:
                ctx.log(LogEntry(stage="S1", status="WARN", message="未提供剧本选择器，降级到排列组合模式"))
                mode = GenerationMode.KEYWORD_COMBO
                stories = []
            else:
                stories = self.story_selector.pick(
                    n=grid, characters=ctx.episode.forced_characters, seed=self.rng.random())
            if mode == GenerationMode.STORY and not stories:
                # 池耗尽 → 降级 combo（决策 L）
                ctx.log(LogEntry(stage="S1", status="WARN", message="剧本池耗尽，降级到排列组合模式"))
                mode = GenerationMode.KEYWORD_COMBO
            else:
                desc = " | ".join(
                    f"Row{i+1}: " + " → ".join(p.cn for p in s.panels[:grid])
                    for i, s in enumerate(stories))
                prompt = STORY_TEMPLATE.format(grid=grid, stories_description=desc)
        if mode == GenerationMode.KEYWORD_COMBO:
            panels_desc = self._random_combo_panels(ctx, n)
            prompt = KEYWORD_COMBO_TEMPLATE.format(grid=grid, n=n, panels_description=panels_desc)
        return prompt, refs

    def _pick_base(self, ctx) -> Optional[Path]:
        # 从 config.characters 选第一个角色的第一个 base（简化；真实多 base 概率在 Prep 已决定）
        if not ctx.config.characters:
            return None
        char = next(iter(ctx.config.characters.values()))
        if not char.bases:
            return None
        base_rel = next(iter(char.bases.values()))
        # base 路径是相对 resources 的
        import sticker_engine as _se
        res_root = Path(_se.__file__).parent / "resources"
        return res_root / base_rel

    def _pick_refs(self, ctx, n) -> list:
        ref_lib = ctx.config.paths.reference_lib
        all_refs = [p for p in ref_lib.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
        self.rng.shuffle(all_refs)
        return all_refs[:n]

    def _random_combo_panels(self, ctx, n) -> str:
        kws = self.keywords or {"emotions": ["happy"], "actions": ["smiling"]}
        emos = kws.get("emotions", ["happy"])
        acts = kws.get("actions", ["smiling"])
        panels = []
        for _ in range(n):
            panels.append(f"{self.rng.choice(emos)} + {self.rng.choice(acts)}")
        return " | ".join(panels)
