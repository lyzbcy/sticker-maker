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




def _magenta_family(arr):
    """洋红族像素掩码（与 chromakey.remove_fringe 判据对齐）。

    hue 300°±30° 且 sat≥0.05：覆盖纯洋红底与白描边混色出的粉紫抗锯齿
    （72 驳回形态：品红格线碎片 hue≈313-327°/sat≈0.6）。白描边
    hue≈0/sat≈0、纯红 hue=0° Δh=60°、粉红衣 hue≈333° Δh=33°——都不在
    族内，天然安全。
    """
    import numpy as np
    rgb = arr[:, :, :3].astype(np.float64)
    r, g, b = rgb[:, :, 0] / 255.0, rgb[:, :, 1] / 255.0, rgb[:, :, 2] / 255.0
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    delta = mx - mn
    sat = np.zeros_like(mx)
    nz = mx > 0
    sat[nz] = delta[nz] / mx[nz]
    hue_deg = np.zeros_like(mx)
    has_delta = delta > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        rc = (mx - r) / delta
        gc = (mx - g) / delta
        bc = (mx - b) / delta
        mask_r = has_delta & (mx == r)
        mask_g = has_delta & (mx == g) & ~mask_r
        mask_b = has_delta & (mx == b) & ~(mask_r | mask_g)
        raw_h = np.zeros_like(mx)
        raw_h[mask_r] = (bc - gc)[mask_r]
        raw_h[mask_g] = (2.0 + rc - bc)[mask_g]
        raw_h[mask_b] = (4.0 + gc - rc)[mask_b]
        hue_deg = ((raw_h / 6.0) % 1.0) * 360.0
    dh = np.minimum(np.abs(hue_deg - 300.0), 360.0 - np.abs(hue_deg - 300.0))
    return (dh <= 30.0) & (sat >= 0.05)


def remove_edge_background(img, dist_thresh: int = 60, max_frac: float = 0.80,
                          on_note=None, max_rounds: int = 3):
    """把"与边缘连通的背景色"抠成透明（P2 第二层：62 黑底+格线场景）。

    原理：背景（洋红底/黑底/格线）总是从画布边缘连入；角色本体被白描边
    包裹、不接触边缘。取边缘前 2 种不透明主色为背景色，从四边 flood，
    色距 < dist_thresh 的连通像素透明化——即使角色黑发与黑底同色，也因
    不连通边缘而安全。抠掉面积 > max_frac 判异常（整图废图），原样返回。

    迭代抠边（2026-09-01，72 驳回"第 5/15 格品红细框"）：单轮 flood 只能
    抠"与画布边缘连通"的背景；抠掉外圈后**新暴露**的边缘色（贴着白描边
    外侧、已与外区隔断的封闭格线环）第一轮够不到。因此抠完外圈后再跑
    内层清理（最多 max_rounds 轮，一轮即收敛）：把「从透明区可达」的
    洋红族残留清透明（判据对齐 chromakey.remove_fringe）。
    内层**不做一般背景色 flood**：新暴露边界里角色轮廓占大头，"边界色=
    背景色"的语义不再成立（白角色会被当背景整片啃掉——实测复现），
    必须依赖"洋红族 + 白描边不在族内"这个正确性锚点。正常"透明留白+
    角色"成品（角色非洋红族）不被折腾。
    """
    import numpy as np
    from scipy import ndimage
    src = img.convert("RGBA")
    arr = np.asarray(src).astype(np.int16)
    h, w = arr.shape[:2]
    edge = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    opaque_edge = edge[edge[:, 3] > 200]
    if len(opaque_edge) < 2 * (h + w) * 0.5:
        # 边缘大半透明：chromakey 已处理过、无外层背景可抠——但仍可能
        # 有"与外区隔断的封闭格线残留"（72 形态），走内层洋红清理
        return _strip_enclosed_magenta(src, on_note=on_note)
    # F3（评审）：白/近白底豁免——所有 prompt 强制"白描边"，白底时描边即
    # 背景色，连通性安全论证反转（白描边+浅肤色脸会被整片吃掉）。白底也
    # 不属于"多余边框线"驳回形态（62 是黑底+格线），不抠。
    if opaque_edge[:, :3].mean(axis=0).sum() > 3 * 240:
        if on_note:
            on_note("检测到白/近白底，跳过边缘背景抠除（防误伤白描边角色）")
        return _strip_enclosed_magenta(src, on_note=on_note)

    def _edge_bg_colors(opaque_pixels):
        # R1（评审）：背景色候选必须占边缘不透明像素 >=15%——角色少量贴边
        # （评审复现 ~3.5%）时其颜色会混成桶 #2 啃食角色；15% 挡住它，同时
        # 不误伤真实格线（四边细线占比 ~10-25%）
        q = (opaque_pixels[:, :3] // 32).astype(np.int32)
        keys, counts = np.unique(q, axis=0, return_counts=True)
        colors = []
        for idx in np.argsort(-counts)[:2]:
            if counts[idx] < len(opaque_pixels) * 0.15:
                break
            mask = (q == keys[idx]).all(axis=1)
            if mask.sum():
                colors.append(opaque_pixels[mask][:, :3].mean(axis=0))
        return colors

    a_mask = arr[:, :, 3] > 200
    dist = np.full((h, w), 1e9, dtype=np.float32)
    for c in _edge_bg_colors(opaque_edge):
        d = np.abs(arr[:, :, :3] - c).sum(axis=2)
        dist = np.minimum(dist, d)
    near = a_mask & (dist < dist_thresh)
    seed = np.zeros((h, w), dtype=bool)
    seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
    reach = ndimage.binary_propagation(seed, mask=near)
    if reach.sum() == 0:
        return _strip_enclosed_magenta(src, on_note=on_note)
    frac = reach.sum() / max(1, a_mask.sum())
    if frac > max_frac:
        if on_note:
            on_note(f"边缘连通背景占比 {frac:.0%} 超上限，保守放弃抠除")
        return _strip_enclosed_magenta(src, on_note=on_note)
    px = np.asarray(src).copy()
    px[reach] = (0, 0, 0, 0)

    # ---- 迭代轮：抠掉外圈后，新暴露边界处的洋红族残留继续清（72 品红
    # 细框）——flood 整个"从透明区可达"的洋红族连通域；白描边不在族内，
    # 传播到此为止——角色本体安全。多轮直到不再有新增（实际一轮收敛）。
    for _ in range(max(1, max_rounds - 1)):
        trans = px[:, :, 3] <= 200
        fam = _magenta_family(px) & (px[:, :, 3] > 200)
        if not fam.any():
            break
        seed3 = ndimage.binary_dilation(trans) & fam
        if not seed3.any():
            break   # 透明边界没有贴着的洋红残留 → 收敛
        reach3 = ndimage.binary_propagation(seed3, mask=fam)
        if reach3.sum() == 0:
            break
        px[reach3] = (0, 0, 0, 0)
    return Image.fromarray(px, "RGBA")


def _strip_enclosed_magenta(img, on_note=None):
    """内层清理：透明邻域内的洋红族残留直接清透明（72 封闭格线环形态）。

    用于"边缘已大半透明/白底豁免"的抠图产物——外层背景色 flood 不适用，
    但贴着白描边外侧的封闭品红格线环仍在。判据同 chromakey.remove_fringe
    （hue 300±30、sat≥0.05），只清「从透明区可达」的洋红族连通域：白描边
    （sat≈0）与角色本体不在族内，不被侵蚀。
    """
    import numpy as np
    from scipy import ndimage
    px = np.asarray(img.convert("RGBA")).copy()
    trans = px[:, :, 3] <= 200
    if not trans.any():
        return img
    fam = _magenta_family(px) & (px[:, :, 3] > 200)
    if not fam.any():
        return img
    seed = ndimage.binary_dilation(trans) & fam
    if not seed.any():
        return img
    reach = ndimage.binary_propagation(seed, mask=fam)
    if reach.sum() == 0:
        return img
    if on_note:
        on_note(f"内层洋红残留清理 {int(reach.sum())} px")
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
        # 2) 含义预检（0 token 模式：S1 已把选定词条预置到 ctx，直接用
        # ——切图格序 = prompt 格序；曾靠识图命名，每单喂 1 张大图给
        # 最强模型，token 开销把周额度吃光强制卡停）
        preset = getattr(ctx, "preset_meanings", None)
        use_vision = bool(getattr(ctx.config.prefs, "vision_calls", False))
        if preset and len(preset) == len(panels) and not use_vision:
            meanings = {i + 1: w for i, w in enumerate(preset)}
        elif len(panels) > 1 and use_vision:
            meanings = self.vision.interpret(panels)
        elif len(panels) > 1 and not use_vision:
            # 无预置（ref/story 等模式）且 0 token：退用文件名序（ref 模式
            # 文件名即含义；不完美但不烧 token）
            meanings = {i + 1: Path(p).stem for i, p in enumerate(panels)}
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

