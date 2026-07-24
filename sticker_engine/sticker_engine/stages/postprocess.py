"""S2 后处理阶段：裁切宫格图 → 含义预检 → 条件抠图 → 按含义词重命名 → 写最终版。

**抠图条件矩阵（spec 3.3，本模块核心纪律）**：
    | mode            | transparent | 抠图? |
    |-----------------|-------------|-------|
    | ref_library     | False       | 否    |  ← 保留参考图原有背景
    | story / combo   | *           | 是    |  ← prompt 模式抠洋红/绿底
    | ref_library     | True        | 是    |  ← 用户显式要透明
    | grid_size==1    | —           | 不切图（should_crop=False）|
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List

from PIL import Image

from ..pipeline.context import PipelineContext, LogEntry
from ..providers.chromakey import ChromaKeyProvider
from ..providers.vision import VisionProvider

# 微信表情主图目标尺寸（spec：240×240）
_TARGET_SIZE = 240


def should_crop(grid_size: int) -> bool:
    """1×1 不切图；其余 grid（2/3/4）需裁切。"""
    return grid_size > 1


def should_chromakey(mode: str, transparent: bool) -> bool:
    """抠图条件矩阵（spec 3.3）。

    - 参考图库模式 + transparent=False → 不抠（保留参考图原有背景）
    - prompt 模式（story/combo）→ 抠（洋红/绿底）
    - ref_library + transparent=True → 抠（用户显式要透明）
    """
    if mode == "ref_library" and not transparent:
        return False   # 参考图库模式默认保留背景
    return True        # prompt 模式默认抠；ref_library + transparent=True 也抠


@dataclass
class Sticker:
    """单张成品贴纸。"""
    path: Path
    meaning: str
    panel_index: int


class PostprocessStage:
    """S2：裁切 → 含义预检 → 条件抠图 → 重命名 → 写最终版。"""

    def __init__(self, vision: VisionProvider, chromakey: ChromaKeyProvider):
        self.vision = vision
        self.chromakey = chromakey

    def run(self, ctx: PipelineContext, gen_mode: str = "story",
            transparent: bool = True) -> None:
        grid_size = ctx.episode.grid_size
        # 1) 裁切（或 1×1 直接用）
        if should_crop(grid_size):
            panels = self._crop_grid(
                ctx.grid_image, grid_size,
                ctx.episode_dir / "原图" / "_panels")
        else:
            panels = [ctx.grid_image]
        # 2) 含义预检
        if len(panels) > 1:
            meanings = self.vision.interpret(panels)
        else:
            meanings = {1: Path(panels[0]).stem}
        ctx.meaning_map = meanings
        # 3) 条件抠图 + 重命名 → 写最终版
        final_dir = ctx.episode_dir / "最终版"
        final_dir.mkdir(exist_ok=True)
        need_key = should_chromakey(gen_mode, transparent)
        seen_names = set()
        for idx, panel in enumerate(panels, start=1):
            img = Image.open(panel).convert("RGBA")
            if need_key:
                img = self.chromakey.remove_key_auto(img)
            meaning = meanings.get(idx, f"表情{idx}")
            # 含义词去重（同名加后缀 2/3/...）
            name = meaning
            i = 2
            while name in seen_names:
                name = f"{meaning}{i}"
                i += 1
            seen_names.add(name)
            # 尺寸校验/缩放（微信要求 240×240）
            img = self._ensure_size(img)
            out = final_dir / f"{name}.png"
            img.save(out)
            ctx.stickers.append(Sticker(path=out, meaning=name, panel_index=idx))
        ctx.log(LogEntry(
            stage="S2", status="OK",
            message=f"后处理完成：{len(ctx.stickers)} 张，抠图={need_key}"))

    def _crop_grid(self, grid_image: Path, grid: int, out_dir: Path) -> List[Path]:
        """按行优先（r*grid+c+1）裁切宫格图，返回 panel 路径列表。"""
        out_dir.mkdir(parents=True, exist_ok=True)
        img = Image.open(grid_image)
        w, h = img.size
        cell_w, cell_h = w // grid, h // grid
        panels: List[Path] = []
        for r in range(grid):
            for c in range(grid):
                idx = r * grid + c + 1
                cell = img.crop(
                    (c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h))
                out = out_dir / f"panel_{idx:02d}.png"
                cell.save(out)
                panels.append(out)
        return panels

    def _ensure_size(self, img: Image.Image, target: int = _TARGET_SIZE) -> Image.Image:
        """尺寸校验：非 target×target 则缩放（LANCZOS）。"""
        if img.width != target or img.height != target:
            img = img.resize((target, target), Image.LANCZOS)
        return img
