"""内容感知宫格切图（2026-08-27 切图越界修复）。

背景（为什么不等分切割）：
    codex/GPT-image 画 4×4 网格时，只有约 85-90% 概率格子尺寸画对
    （mikeesto 实测）。实际常见两类偏差：
    a. 格线不齐/格子大小不一 → 等分切割切到邻格内容；
    b. 角色跨越格线 → 等分切割把一个角色切成两半。
    旧实现 `_crop_grid` 纯等分，无法应对。

方法（调研 GitHub 后融合，参考文献见模块底部注释）：
    1. 背景色检测（采样边框中位色）→ 前景 mask（颜色距离）；
    2. 投影 profile 找"空带"（gutter）：行列方向上前景密度≈0 的连续带，
       在带中点下刀 → 自适应不均匀网格（ImageMint / 数独投影法）；
    3. 连通域归属：每个贴纸连通域按质心分配到所属格子，裁剪取该格子
       全部连通域的联合 bbox（外扩边距）——越界贴纸整块归属原格，
       不会被切成两半（sugarcookie / Max Halford 连通域思路）；
    4. 兜底：某方向找不到干净 gutter（贴纸粘连）→ 该方向等分 + WARN。

不引入 OpenCV：scipy.ndimage.label 做连通域（依赖已在环境内）。
"""
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage

# ---- 可调参数 ----
_BG_DIST_THRESH = 60      # 与背景色的逐通道绝对差之和，超过视为前景
_EMPTY_LINE_EPS = 0.02    # 某行/列前景占比低于此值视为"空线"
_MIN_BAND_PX = 3          # 空带最小宽度（像素），过滤反锯齿杂线
_SPECK_AREA = 30          # 小于该面积的连通域视为噪点
_EXPAND_PX = 6            # 裁剪 bbox 外扩像素（保住白描边）


def _detect_background(arr: np.ndarray) -> np.ndarray:
    """采样图像四周边框（内缩 3px）的每通道中位色作为背景色。"""
    h, w = arr.shape[:2]
    ring = np.concatenate([
        arr[3:6, :, :3].reshape(-1, 3),
        arr[h-6:h-3, :, :3].reshape(-1, 3),
        arr[:, 3:6, :3].reshape(-1, 3),
        arr[:, w-6:w-3, :3].reshape(-1, 3),
    ])
    return np.median(ring, axis=0)


def _content_mask(arr: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """前景 mask：与背景色的逐通道绝对差之和超过阈值。"""
    dist = np.abs(arr[:, :, :3].astype(np.int16) - bg.astype(np.int16)).sum(axis=2)
    return dist > _BG_DIST_THRESH


def _find_gutters(profile: np.ndarray, n_cells: int) -> Optional[List[int]]:
    """在投影 profile（每线前景像素数）上找 n_cells-1 条内部空带，返回切线坐标。

    找不到（带数量不足/位置不合理）返回 None，调用方等分兜底。
    """
    total = profile.shape[0]
    # profile 是每线前景"占比"（0~1）：空线 = 占比 <= eps（容忍杂点）
    empty = profile <= _EMPTY_LINE_EPS
    # 找连续空带
    bands = []
    start = None
    for i, e in enumerate(empty):
        if e and start is None:
            start = i
        elif not e and start is not None:
            if i - start >= _MIN_BAND_PX:
                bands.append((start, i - 1))
            start = None
    if start is not None and len(empty) - start >= _MIN_BAND_PX:
        bands.append((start, len(empty) - 1))
    # 只保留内部带（不贴图像边缘：带完全在 [cell*0.25, total-cell*0.25] 内）
    cell = total / n_cells
    internal = [b for b in bands
                if b[0] > cell * 0.25 and b[1] < total - cell * 0.25]
    if len(internal) < n_cells - 1:
        return None
    # 期望切线位置 i*cell，各取最近的带中点；要求有序且互不相同
    cuts = []
    used = set()
    for i in range(1, n_cells):
        expect = int(i * cell)
        best, best_d = None, None
        for bi, (s, e) in enumerate(internal):
            if bi in used:
                continue
            mid = (s + e) // 2
            d = abs(mid - expect)
            if best_d is None or d < best_d:
                best, best_d = bi, d
        if best is None or best_d > cell * 0.55:   # 离期望太远视为不合理
            return None
        used.add(best)
        cuts.append((internal[best][0] + internal[best][1]) // 2)
    if cuts != sorted(cuts) or len(set(cuts)) != len(cuts):
        return None
    return cuts


def _cell_bounds(cuts: Optional[List[int]], total: int, n_cells: int) -> List[Tuple[int, int]]:
    """由切线（或等分兜底）得到每格的 [start, end) 区间。"""
    if cuts:
        edges = [0] + cuts + [total]
    else:
        edges = [int(i * total / n_cells) for i in range(n_cells + 1)]
    return [(edges[i], edges[i + 1]) for i in range(n_cells)]


def _strip_grid_lines(mask: np.ndarray, max_thick: int = 10,
                      min_span: float = 0.80) -> int:
    """清除宫格格线：横/纵方向"贯穿 ≥80% 且厚度 ≤10px"的前景条带。

    根因（2026-09-09 panel_09 240×97 事故）：codex 偶发在宫格上画
    白/浅色网格线——白线与角色白描边同色相连，把跨行内容连成覆盖
    整图的巨型连通域，被 _components 的巨块过滤整块剔除（角色跟着
    丢失，只剩感叹号碎块 → 联合 bbox 切出扁条）；同时白线填平行沟
    导致 gutter 检测失败退等分。
    格线特征实测（092455 单）：厚 6-7px、横纵各 3 条正好 4 格 3 沟；
    角色密集带最薄 58px → 10px 阈值安全。返回清除条带数（诊断用）。
    """
    removed = 0
    for axis in ("row", "col"):
        dense = mask.mean(axis=1 if axis == "row" else 0)
        idx = np.where(dense >= min_span)[0]
        if len(idx) == 0:
            continue
        runs = []
        s = p = int(idx[0])
        for v in idx[1:]:
            v = int(v)
            if v == p + 1:
                p = v
            else:
                runs.append((s, p))
                s = p = v
        runs.append((s, p))
        for a, b in runs:
            if (b - a + 1) <= max_thick:
                if axis == "row":
                    mask[a:b + 1, :] = False
                else:
                    mask[:, a:b + 1] = False
                removed += 1
    return removed


def _components(mask: np.ndarray):
    """4-连通域：返回 [(centroid_y, centroid_x, y0, y1, x0, x1, area)]，过滤噪点。

    同时剔除"结构性杂块"（实测 codex 偶发画整图边框线/大面积残留）：
    - 覆盖 >35% 画面的巨块；
    - 横贯 >85% 宽且高 <5% 的水平线（边框/分隔线）；
    - 纵贯 >85% 高且宽 <5% 的垂直线。
    """
    labeled, n = ndimage.label(mask)
    if n == 0:
        return []
    h, w = mask.shape
    objs = ndimage.find_objects(labeled)
    comps = []
    for idx, sl in enumerate(objs, start=1):
        if sl is None:
            continue
        m = labeled[sl] == idx
        area = int(m.sum())
        if area < _SPECK_AREA:
            continue
        by0, by1, bx0, bx1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        bw, bh = bx1 - bx0, by1 - by0
        if bw * bh > 0.35 * w * h:
            continue
        if bw > 0.85 * w and bh < 0.05 * h:
            continue
        if bh > 0.85 * h and bw < 0.05 * w:
            continue
        # 质心必须加切片原点偏移：np.where 返回的是切片内局部坐标，
        # 不加偏移时每个组件的"质心"都是自己 bbox 的中心（都≈格内坐标），
        # 16 个贴纸会全部被归属到第一格（2026-08-27 气鼓鼓裁剪事故）
        ys, xs = np.where(m)
        cy = float(ys.mean()) + by0
        cx = float(xs.mean()) + bx0
        comps.append((cy, cx, by0, by1, bx0, bx1, area))
    return comps


def _solid_bounds(arr, grid, axis):
    """Detect near-grid, full-span color transitions, not character silhouettes.

    A solid tile can have the same color as the global sampled background.
    Foreground gutters and component bboxes therefore cannot define its frame.
    Only a strong transition across >=90% of the sheet near the nominal cut is
    accepted; otherwise equal-grid framing preserves the complete caption band.
    """
    colors = arr[:, :, :3].astype(np.int16)
    delta = np.abs(np.diff(colors, axis=axis)).sum(axis=2)
    support = (delta >= 40).mean(axis=1 if axis == 0 else 0)
    total = arr.shape[axis]
    cell = total / grid
    cuts = []
    for i in range(1, grid):
        expected = int(i * cell)
        radius = max(1, int(cell * .12))
        candidates = [(float(support[pos - 1]), -abs(pos - expected), pos)
                      for pos in range(max(1, expected - radius), min(total, expected + radius + 1))
                      if support[pos - 1] >= .90]
        cuts.append(max(candidates)[2] if candidates else expected)
    return _trim_solid_gutters(arr, _cell_bounds(cuts, total, grid), axis)


def _trim_solid_gutters(arr, bounds, axis):
    """Trim only thin, globally proven white gutters, not local silhouettes.

    A nearly full-sheet white core anchors a >=70% near-white run touching a
    cell boundary. Thick white regions and bands crossed by dark foreground
    are retained. At most one bright adjacent antialias pixel is included.
    The full grid is essential: a white sleeve in one cell is not evidence.
    """
    rgb = arr[:, :, :3].astype(np.int16)
    white = (rgb.min(axis=2) > 230) & (rgb.max(axis=2)-rgb.min(axis=2) <= 20)
    support = white.mean(axis=0 if axis == 1 else 1)
    dark = (rgb.min(axis=2) < 180).any(axis=0 if axis == 1 else 1)
    result = []
    for start, end in bounds:
        lo, hi = start, end
        limit = max(1, int((end-start)*.04))
        for left in (True, False):
            edge = start if left else end-1
            step = 1 if left else -1
            positions = []
            pos = edge
            if (support[pos] < .7 and not dark[pos]
                    and start <= pos+step < end and support[pos+step] >= .7):
                positions.append(pos);pos += step
            while start <= pos < end and support[pos] >= .7:
                positions.append(pos);pos += step
            outside = start-1 if left else end
            if (not positions and 0 <= outside < len(support)
                    and support[outside] >= .98 and not dark[edge]):
                # The transition detector can already put the white core
                # outside the crop, leaving only its one-pixel bright fringe.
                positions = [edge]
                if left:
                    lo = edge+1
                else:
                    hi = edge
                continue
            if (not positions or len(positions) > limit
                    or max(support[x] for x in positions) < .98
                    or any(dark[x] for x in positions)):
                continue
            # An adjacent bright pixel can be a colored gutter AA fringe;
            # never extend through dark hair/outline, and never exceed 4%.
            if start <= pos < end and not dark[pos] and len(positions) < limit:
                positions.append(pos)
            if left:
                lo = max(positions)+1
            else:
                hi = min(positions)
        result.append((lo, hi) if lo < hi else (start, end))
    return result


def solid_cell_boxes(arr, grid):
    """Row-major source boxes shared by solid S2 and explicit grid recovery."""
    if grid not in (2, 3, 4) or min(arr.shape[:2]) < grid * 8:
        raise ValueError('彩底网格尺寸或格数无效')
    xs, ys = _solid_bounds(arr, grid, 1), _solid_bounds(arr, grid, 0)
    return [(x0, y0, x1, y1) for y0, y1 in ys for x0, x1 in xs]


def cut_grid(grid_image: Path, grid: int, out_dir: Path, *, preserve_cell: bool = False
             ) -> Tuple[List[Path], List[str]]:
    """把宫格图切成 grid×grid 张 panel（行优先编号），返回 (paths, notes)。

    notes 是给人看的切图诊断（gutter 是否命中、是否兜底、越界归属等），
    调用方写进日志方便排查。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(grid_image).convert("RGB")
    arr = np.asarray(img)
    h, w = arr.shape[:2]
    notes: List[str] = []

    if preserve_cell:
        xs = _solid_bounds(arr, grid, 1)
        ys = _solid_bounds(arr, grid, 0)
        panels = []
        for row, (y0, y1) in enumerate(ys):
            for col, (x0, x1) in enumerate(xs):
                out = out_dir / f'panel_{row * grid + col + 1:02d}.png'
                img.crop((x0, y0, x1, y1)).save(out)
                panels.append(out)
        notes.append(f'彩底整格保留（含底部字幕留白）：X={xs}；Y={ys}；不按人物框收紧')
        return panels, notes

    bg = _detect_background(arr)
    mask = _content_mask(arr, bg)
    lines = _strip_grid_lines(mask)
    if lines:
        notes.append(f"检测并清除 {lines} 条宫格格线（白线粘连防护）")

    col_profile = mask.mean(axis=0)   # 每列前景占比 0~1
    row_profile = mask.mean(axis=1)   # 每行前景占比 0~1
    xs = _find_gutters(col_profile, grid)
    ys = _find_gutters(row_profile, grid)
    notes.append(f"切线检测：X={'沟中下刀 ' + str(xs) if xs else '未检出，等分兜底'}；"
                 f"Y={'沟中下刀 ' + str(ys) if ys else '未检出，等分兜底'}")

    x_bounds = _cell_bounds(xs, w, grid)
    y_bounds = _cell_bounds(ys, h, grid)

    comps = _components(mask)
    panels: List[Path] = []
    overflow_count = 0
    for r in range(grid):
        ry0, ry1 = y_bounds[r]
        for c in range(grid):
            rx0, rx1 = x_bounds[c]
            idx = r * grid + c + 1
            # 归属：质心落在该格内的连通域，联合 bbox
            own = [cm for cm in comps if ry0 <= cm[0] < ry1 and rx0 <= cm[1] < rx1]
            if own:
                y0 = max(0, min(cm[2] for cm in own) - _EXPAND_PX)
                y1 = min(h, max(cm[3] for cm in own) + _EXPAND_PX)
                x0 = max(0, min(cm[4] for cm in own) - _EXPAND_PX)
                x1 = min(w, max(cm[5] for cm in own) + _EXPAND_PX)
                # 钳制：贴纸允许越界，但最多超出格子边界 45% 格宽/高
                # （防杂块把 panel 撑成整图；正常贴纸越界都在这个量级内）
                m_y = int(0.45 * (ry1 - ry0))
                m_x = int(0.45 * (rx1 - rx0))
                y0, y1 = max(ry0 - m_y, y0), min(ry1 + m_y, y1)
                x0, x1 = max(rx0 - m_x, x0), min(rx1 + m_x, x1)
                # 健全性兜底（2026-09-09 panel_09 240×97 事故第二层防线）：
                # 联合 bbox 任一维 <55% 格高/宽 = 只捕到装饰碎块、角色主体
                # 丢失（粘连巨块被剔除等未知形态）——退回格子矩形，等分
                # 位置至少不切脸。实测正常贴纸两维都 ≥75%。
                if ((y1 - y0) < 0.55 * (ry1 - ry0)
                        or (x1 - x0) < 0.55 * (rx1 - rx0)):
                    notes.append(f"panel_{idx:02d} 归属 bbox 异常偏小，退格子矩形兜底")
                    y0, y1, x0, x1 = ry0, ry1, rx0, rx1
                # 越界诊断：bbox 超出格子范围 → 贴纸跨线，已整块归属
                elif y0 < ry0 or y1 > ry1 or x0 < rx0 or x1 > rx1:
                    overflow_count += 1
            else:
                # 空格（该格无内容连通域）：用格子矩形兜底
                y0, y1, x0, x1 = ry0, ry1, rx0, rx1
            out = out_dir / f"panel_{idx:02d}.png"
            img.crop((x0, y0, x1, y1)).save(out)
            panels.append(out)
    if overflow_count:
        notes.append(f"{overflow_count} 张贴纸越过格线，已按连通域整块归属原格裁剪")
    return panels, notes


# ---- 调研参考（实现依据）----
# 投影 profile 找格线：Stack Overflow 数独网格检测（比霍夫变换稳）
#   https://stackoverflow.com/questions/48954246/
# 沟中下刀 + bbox 收紧：ImageMint "Slice uneven AI sprite sheet"
#   https://imagemint.net/tutorials/slice-uneven-ai-sprite-sheet
# 连通域归属 + bbox：sugarcookie（PIL flood-fill）/ Max Halford 漫画分格教程
#   https://sethmlarson.dev/cutting-spritesheets-like-cookies-with-python-and-pillow
#   https://maxhalford.github.io/blog/comic-book-panel-segmentation/
# GPT-4o 网格 85-90% 尺寸正确率实测：mikeesto
#   https://mikeesto.com/posts/animating-gpt4o-image-grids/
