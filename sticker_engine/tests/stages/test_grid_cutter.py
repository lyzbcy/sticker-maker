"""内容感知宫格切图测试（2026-08-27 切图越界修复）。

场景覆盖：
- 规则网格（沟干净）→ 沟中下刀
- 不均匀网格（列宽差 40%）→ 切线自适应实际沟位，不再等分
- 贴纸跨界（bbox 超出格子）→ 连通域整块归属原格，不被切半
- 无沟（贴纸粘连/满铺）→ 等分兜底 + note
- 空格（某格无内容）→ 格子矩形兜底
"""
import numpy as np
from PIL import Image

from sticker_engine.stages.grid_cutter import cut_grid, _find_gutters

MAGENTA = (255, 0, 255)


def _canvas(w, h, bg=MAGENTA):
    return Image.new("RGB", (w, h), bg)


def _draw_sticker(img, x0, y0, x1, y1, outline=(255, 255, 255), fill=None):
    """画一个带白描边的方块贴纸（模拟 die-cut）。fill 可指定主体色。"""
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill=outline)
    d.rectangle([x0, y0, x1, y1], fill=fill or (120, 200, 80))


def test_regular_grid_cuts_at_gutters(tmp_path):
    img = _canvas(400, 400)
    for r in range(4):
        for c in range(4):
            _draw_sticker(img, 20 + c * 100, 20 + r * 100, 80 + c * 100, 80 + r * 100)
    p = tmp_path / "grid.png"; img.save(p)
    panels, notes = cut_grid(p, 4, tmp_path / "out")
    assert len(panels) == 16
    assert any("沟中下刀" in n for n in notes)
    # 每张 panel 都应是正方形且只含一个贴纸（非空）
    for pan in panels:
        im = Image.open(pan)
        assert abs(im.width - im.height) <= 12, f"{pan} 尺寸 {im.size}"
        # 单贴纸内容裁剪：60px 主体 + 描边 + 外扩 ≈ 76px，绝不该超过半张图
        assert im.width <= 120, f"{pan} 宽 {im.width} —— 归属/裁剪异常"


def test_each_panel_contains_its_own_sticker(tmp_path):
    """归属回归（2026-08-27 气鼓鼓事故）：16 个贴纸每格一个、各具颜色，
    切出的 panel 主色必须等于自己那格的颜色——质心算错时 16 个贴纸会
    全部归到第一格，此测试立刻爆炸。"""
    img = _canvas(400, 400)
    colors = {}
    for r in range(4):
        for c in range(4):
            fill = (30 + r * 60, 30 + c * 60, 90)
            colors[(r, c)] = fill
            _draw_sticker(img, 20 + c * 100, 20 + r * 100, 80 + c * 100, 80 + r * 100,
                          fill=fill)
    p = tmp_path / "grid.png"; img.save(p)
    panels, notes = cut_grid(p, 4, tmp_path / "out")
    import numpy as np
    for r in range(4):
        for c in range(4):
            im = Image.open(panels[r * 4 + c]).convert("RGB")
            a = np.asarray(im).reshape(-1, 3)
            # 排除背景色与白描边后的众数应接近该格主体色
            non_bg = a[(a != MAGENTA).all(axis=1) & (a != (255, 255, 255)).all(axis=1)]
            dom = non_bg[non_bg.sum(axis=1).argmax()]
            expect = colors[(r, c)]
            assert abs(int(dom[0]) - expect[0]) <= 8 and abs(int(dom[1]) - expect[1]) <= 8, \
                f"panel({r},{c}) 主色 {tuple(dom)} ≠ 期望 {expect} —— 贴纸归属错格"


def test_uneven_grid_adapts_to_actual_gutters(tmp_path):
    """列宽故意不均（40/60 分割），切线应跟实际沟走而非等分。"""
    img = _canvas(500, 400)
    # 行方向 4 等分，列方向分割线在 x=150/260/380（不等分）
    xs = [0, 150, 260, 380, 500]
    for r in range(4):
        y0, y1 = 12 + r * 100, 88 + r * 100
        for c in range(4):
            pad = 14
            _draw_sticker(img, xs[c] + pad, y0, xs[c + 1] - pad, y1)
    p = tmp_path / "grid.png"; img.save(p)
    from sticker_engine.stages.grid_cutter import _content_mask, _detect_background
    arr = np.asarray(img)
    mask = _content_mask(arr, _detect_background(arr))
    col = mask.mean(axis=0)
    cuts = _find_gutters(col, 4)
    assert cuts is not None
    # 切线必须落在实际沟里（贴纸之间的空带），且与等分位置不同
    assert cuts != [125, 250, 375]
    for cut in cuts:
        assert col[max(0, cut - 2):cut + 3].max() <= 0.02


def test_overflow_sticker_kept_whole(tmp_path):
    """第 1 格贴纸越过等分线 x=100 伸进第 2 格（但不与邻格贴纸粘连）——
    应整块归第 1 格，不被切半。

    注意：若越界部分与邻格贴纸的白描边粘连（连通域合并），质心归属会把
    合并块判给质心所在格——真粘连是内容感知切割的已知边界（ImageMint
    也承认无自动解），靠 gutter 不被阻塞 + 邻格矩形兜底保证不崩。
    """
    img = _canvas(400, 400)
    for r in range(4):
        for c in range(4):
            x0, x1 = 20 + c * 100, 80 + c * 100
            y0, y1 = 20 + r * 100, 80 + r * 100
            if r == 0 and c == 0:
                x1 = 110   # 越过等分线 x=100，描边到 114，与邻格描边(116 起)留缝不粘连
            _draw_sticker(img, x0, y0, x1, y1)
    p = tmp_path / "grid.png"; img.save(p)
    panels, notes = cut_grid(p, 4, tmp_path / "out")
    assert len(panels) == 16
    assert any("整块归属" in n for n in notes)
    # 第 1 张 panel 应含越界部分（主体 60 + 越界 30 + 描边/外扩 ≈ 110px）
    p1 = Image.open(panels[0])
    assert p1.width >= 100, f"panel_01 宽 {p1.width}，越界贴纸被切半了"
    # 第 2 张 panel 不应包含第 1 格贴纸的残留
    p2 = Image.open(panels[1])
    assert p2.width <= 100


def test_no_gutters_falls_back_to_equal_division(tmp_path):
    """整图铺满内容（无沟）→ 等分兜底，仍出 16 张。"""
    arr = np.zeros((400, 400, 3), dtype=np.uint8)
    for r in range(4):
        for c in range(4):
            arr[r*100:(r+1)*100, c*100:(c+1)*100] = (r * 60 + 10, c * 60 + 10, 90)
    p = tmp_path / "grid.png"; Image.fromarray(arr).save(p)
    panels, notes = cut_grid(p, 4, tmp_path / "out")
    assert len(panels) == 16
    assert any("等分兜底" in n for n in notes)


def test_empty_cell_falls_back_to_rect(tmp_path):
    """某格完全空白 → 用格子矩形兜底（尺寸≈格宽）。"""
    img = _canvas(400, 400)
    for r in range(4):
        for c in range(4):
            if r == 0 and c == 1:
                continue   # 第 2 格留空
            _draw_sticker(img, 20 + c * 100, 20 + r * 100, 80 + c * 100, 80 + r * 100)
    p = tmp_path / "grid.png"; img.save(p)
    panels, notes = cut_grid(p, 4, tmp_path / "out")
    assert len(panels) == 16
    p2 = Image.open(panels[1])
    assert p2.width >= 80   # 格子矩形兜底（接近整格宽）


def test_white_background_also_works(tmp_path):
    """白底网格（codex 偶尔画白底）同样能切。"""
    img = _canvas(400, 400, bg=(255, 255, 255))
    for r in range(4):
        for c in range(4):
            _draw_sticker(img, 20 + c * 100, 20 + r * 100, 80 + c * 100, 80 + r * 100,
                          outline=(200, 60, 200))
    p = tmp_path / "grid.png"; img.save(p)
    panels, notes = cut_grid(p, 4, tmp_path / "out")
    assert len(panels) == 16
    assert any("沟中下刀" in n for n in notes)
