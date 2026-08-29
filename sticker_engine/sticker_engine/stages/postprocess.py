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
from .grid_cutter import cut_grid

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




def remove_edge_background(img, dist_thresh: int = 60, max_frac: float = 0.80,
                          on_note=None):
    """把"与边缘连通的背景色"抠成透明（P2 第二层：62 黑底+格线场景）。

    原理：背景（洋红底/黑底/格线）总是从画布边缘连入；角色本体被白描边
    包裹、不接触边缘。取边缘前 2 种不透明主色为背景色，从四边 flood，
    色距 < dist_thresh 的连通像素透明化——即使角色黑发与黑底同色，也因
    不连通边缘而安全。抠掉面积 > max_frac 判异常（整图废图），原样返回。
    """
    import numpy as np
    from scipy import ndimage
    src = img.convert("RGBA")
    arr = np.asarray(src).astype(np.int16)
    h, w = arr.shape[:2]
    edge = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    opaque_edge = edge[edge[:, 3] > 200]
    if len(opaque_edge) < 2 * (h + w) * 0.5:
        return src   # 边缘大半透明：chromakey 已处理过，无背景可抠
    # F3（评审）：白/近白底豁免——所有 prompt 强制"白描边"，白底时描边即
    # 背景色，连通性安全论证反转（白描边+浅肤色脸会被整片吃掉）。白底也
    # 不属于"多余边框线"驳回形态（62 是黑底+格线），不抠。
    if opaque_edge[:, :3].mean(axis=0).sum() > 3 * 240:
        if on_note:
            on_note("检测到白/近白底，跳过边缘背景抠除（防误伤白描边角色）")
        return src
    # R1（评审）：背景色候选必须占边缘不透明像素 >=15%——角色少量贴边
    # （评审复现 ~3.5%）时其颜色会混成桶 #2 啃食角色；15% 挡住它，同时
    # 不误伤真实格线（四边细线占比 ~10-25%）
    q = (opaque_edge[:, :3] // 32).astype(np.int32)
    keys, counts = np.unique(q, axis=0, return_counts=True)
    bg_colors = []
    for idx in np.argsort(-counts)[:2]:
        if counts[idx] < len(opaque_edge) * 0.15:
            break
        mask = (q == keys[idx]).all(axis=1)
        if mask.sum():
            bg_colors.append(opaque_edge[mask][:, :3].mean(axis=0))
    if not bg_colors:
        if on_note:
            on_note("边缘无稳定背景色（角色贴边？），跳过抠除")
        return src
    a_mask = arr[:, :, 3] > 200
    dist = np.full((h, w), 1e9, dtype=np.float32)
    for c in bg_colors:
        d = np.abs(arr[:, :, :3] - c).sum(axis=2)
        dist = np.minimum(dist, d)
    near = a_mask & (dist < dist_thresh)
    seed = np.zeros((h, w), dtype=bool)
    seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
    reach = ndimage.binary_propagation(seed, mask=near)
    if reach.sum() == 0:
        return src
    frac = reach.sum() / max(1, a_mask.sum())
    if frac > max_frac:
        if on_note:
            on_note(f"边缘连通背景占比 {frac:.0%} 超上限，保守放弃抠除")
        return src
    px = np.asarray(src).copy()
    px[reach] = (0, 0, 0, 0)
    return Image.fromarray(px, "RGBA")


def trim_border_band(img, max_frac: float = 0.25):
    """裁掉四边的"同色不透明残留带"（P2：62 边框线事故，模块级供图标流程复用）。

    判定：某一行/列 >=95% 像素为同一不透明颜色（色距和 < 40）且连续向内
    -> 残留带（品红格线/黑底/补方色）。逐边向内收缩，单边最多裁 max_frac
    防误杀。角色白描边不受影响：描边贴角色轮廓呈弧形，不会构成"整行同色"。
    大量透明的边（正常留白）不参与判定。裁完过小（<50%）保守放弃。
    """
    import numpy as np
    arr = np.asarray(img.convert("RGBA"), dtype=np.int16)
    h, w = arr.shape[:2]
    if h == 0 or w == 0:
        return img

    def _band_ok(pixels) -> bool:
        n = len(pixels)
        if n == 0:
            return False
        opaque = pixels[pixels[:, 3] > 200]
        if len(opaque) < n * 0.95:
            return False   # 大量透明 -> 正常留白
        ref = opaque[0]
        dist = np.abs(opaque[:, :3] - ref[:3]).sum(axis=1)
        return bool((dist < 40).mean() >= 0.95)

    def _trim_edges(slices, max_trim: int):
        lo_n = 0
        for px in slices[0][:max_trim]:
            if not _band_ok(px):
                break
            lo_n += 1
        hi_n = 0
        for px in slices[1][:max_trim]:
            if not _band_ok(px):
                break
            hi_n += 1
        return lo_n, hi_n

    rows = [arr[i] for i in range(h)]
    cols = [arr[:, j] for j in range(w)]
    top, bot = _trim_edges((rows, list(reversed(rows))), int(h * max_frac))
    left, right = _trim_edges((cols, list(reversed(cols))), int(w * max_frac))
    if top + bot >= h * 0.5 or left + right >= w * 0.5:
        return img   # 判定失真（大面积单色底），保守放弃
    if (top, bot, left, right) == (0, 0, 0, 0):
        return img
    return img.crop((left, top, w - right, h - bot))


def ensure_size(img, target: int = _TARGET_SIZE):
    """补方（不拉伸）+ 等比缩放到 target（S2 成品与图标共用）。"""
    if img.width != img.height:
        corners = [img.getpixel(p) for p in
                   [(0, 0), (img.width - 1, 0), (0, img.height - 1),
                    (img.width - 1, img.height - 1)]]
        same = all(c[:3] == corners[0][:3] and c[3] == corners[0][3] for c in corners)
        fill = corners[0] if (same and corners[0][3] > 0) else (0, 0, 0, 0)
        side = max(img.width, img.height)
        canvas = Image.new("RGBA", (side, side), fill)
        canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        img = canvas
    if img.width != target or img.height != target:
        img = img.resize((target, target), Image.LANCZOS)
    return img


class PostprocessStage:
    """S2：裁切 → 含义预检 → 条件抠图 → 重命名 → 写最终版。"""

    name = "S2"

    def __init__(self, vision: VisionProvider, chromakey: ChromaKeyProvider):
        self.vision = vision
        self.chromakey = chromakey

    def run(self, ctx: PipelineContext, gen_mode: str = None,
            transparent: bool = None) -> None:
        # C1 修复：单参契约下从 ctx 读模式；双参调用（旧测试）显式传值优先
        if gen_mode is None:
            gen_mode = ctx.gen_mode or "story"
        if transparent is None:
            transparent = ctx.episode.transparent_default
        grid_size = ctx.episode.grid_size
        # 1) 裁切（或 1×1 直接用）
        # 2026-08-27：等分切割 → 内容感知切割（投影找沟 + 连通域归属），
        # 解决 codex 网格不齐/贴纸越界时"切到邻格内容、自己被切半"的问题
        if should_crop(grid_size):
            panels, cut_notes = cut_grid(
                ctx.grid_image, grid_size,
                ctx.episode_dir / "原图" / "_panels")
            for note in cut_notes:
                ctx.log(LogEntry(stage="S2", status="OK", message=f"切图：{note}"))
        else:
            panels = [ctx.grid_image]
        # 2) 含义预检
        if len(panels) > 1:
            meanings = self.vision.interpret(panels)
        else:
            meanings = {1: Path(panels[0]).stem}
        ctx.meaning_map = meanings
        # C3 修复：把含义词顺序落盘到 meaning_map.json
        # （初心第44行：发布时要按故事线顺序，C 的 publisher 读此文件排序上传）
        import json
        (ctx.episode_dir / "meaning_map.json").write_text(
            json.dumps({str(k): v for k, v in meanings.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        # 3) 条件抠图 + 重命名 → 写最终版
        final_dir = ctx.episode_dir / "最终版"
        final_dir.mkdir(exist_ok=True)
        need_key = should_chromakey(gen_mode, transparent)
        seen_names = set()
        for idx, panel in enumerate(panels, start=1):
            img = Image.open(panel).convert("RGBA")
            if need_key:
                img = self.chromakey.remove_key_auto(img)
                # P2（62 边框线事故）双层防御：①抠掉与边缘连通的背景色
                # （黑底/格线，chromakey 漏网时兜底；角色被白描边包裹不
                # 连通，安全）。仅抠图单执行——ref_library 保背景模式
                # （need_key=False）明文不抠，两层防御不得越界（评审F2）
                img = remove_edge_background(
                    img, on_note=lambda m: ctx.log(
                        LogEntry(stage="S2", status="WARN", message="抠背景：" + m)))
                # ②裁掉四边同色不透明残留带（薄层格线/补方色泄漏）
                img = self._trim_border_band(img)
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

    def _trim_border_band(self, img, max_frac: float = 0.25):
        return trim_border_band(img, max_frac)


    def _ensure_size(self, img: Image.Image, target: int = _TARGET_SIZE) -> Image.Image:
        return ensure_size(img, target)

