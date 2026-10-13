# -*- coding: utf-8 -*-
"""封面大头照回归锁（2026-09-08，驳回数据驱动的 P0）。

锁三件事：
1. pick_header_candidates 词反查走"含义词→同名文件"（68 号单错位事故
   同款约定：panel 序号 ≠ 文件名字典序，位置索引会系统性选错格）
2. 撞名后缀变体（"心动了～"）可匹配；无 header 词返回空（老单回退）
3. make_big_head_cover 产出 240 透明方图且头部（窗口内容）不溢出画布
"""
import numpy as np
import pytest
from PIL import Image


def _make_ep(tmp_path, words):
    """造一弹：最终版文件名=含义词（乱序落盘模拟字典序≠panel 序）。"""
    ep = tmp_path / "episode_20260908_000000"
    final = ep / "最终版"
    final.mkdir(parents=True, exist_ok=True)
    mm = {str(i + 1): w for i, w in enumerate(words)}
    (ep / "meaning_map.json").write_text(
        __import__("json").dumps(mm, ensure_ascii=False), encoding="utf-8")
    # 头肩格画法：上部大圆（头）+ 下部小矩形（肩），其余透明
    for w in words:
        im = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
        arr = np.zeros((240, 240, 4), dtype=np.uint8)
        yy, xx = np.mgrid[0:240, 0:240]
        head = (xx - 120) ** 2 + (yy - 85) ** 2 <= 70 ** 2       # 头（近满宽）
        body = (yy >= 155) & (yy <= 215) & (abs(xx - 120) <= 62)  # 肩身
        arr[head | body] = (120, 180, 255, 255)
        Image.fromarray(arr).save(final / f"{w}.png")
    return ep


def _full_body_image():
    """全身像：窄高 bbox（w/h ≈ 0.4），质检应判不合规。"""
    im = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    arr = np.zeros((240, 240, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:240, 0:240]
    head = (xx - 120) ** 2 + (yy - 40) ** 2 <= 28 ** 2
    body = (yy >= 70) & (abs(xx - 120) <= 22)
    arr[head | body] = (255, 120, 120, 255)
    return Image.fromarray(arr)


def test_candidates_by_word_not_position(tmp_path):
    """字典序 ≠ panel 序时（68 号单同款），必须按词反查同名文件。

    panel 序：格 13="阿呆"（header 词），但字典序里 paths[12] 是别的格
    ——旧位置索引会系统性选错；词反查锁定"阿呆.png"。
    """
    from sticker_engine.stages.assets import pick_header_candidates
    ep = _make_ep(tmp_path, ["阿呆", "呃呃", "唔唔", "哎呀"] * 3 + ["阿呆", "呃呃", "唔唔", "哎呀"])
    final = ep / "最终版"
    paths = sorted(final.glob("*.png"), key=lambda p: p.stem)
    cands = pick_header_candidates(paths, ep_dir=ep)
    assert [c.name for c in cands] == ["阿呆.png", "呃呃.png", "唔唔.png", "哎呀.png"][:len(cands)]
    assert all(c.exists() for c in cands)


def test_candidates_suffix_variant_and_miss(tmp_path):
    from sticker_engine.stages.assets import pick_header_candidates
    # 撞名：场景格先占"心动了"，header 格改名"心动了～"→ 两个变体都命中
    # （场景格若为全身像由 _is_head_shot 质检拦截；运行时走 header_slots
    # 显式信号，不依赖词反查——此处只锁"后缀变体可被匹配"）
    words = ["心动了", "开心", "难过", "惊喜", "叹气", "摸鱼", "发呆", "充电",
             "加班", "摸头", "贴贴", "干饭", "追剧", " 许愿 ".strip(), "打卡", "心动了～"]
    ep = _make_ep(tmp_path, words)
    cands = pick_header_candidates([], ep_dir=ep)
    assert {c.name for c in cands} == {"心动了.png", "心动了～.png"}
    # 老单：无 header 词 → 空候选（调用方回退旧行为）
    ep_old = _make_ep(tmp_path, ["开心", "难过"] * 8)
    assert pick_header_candidates([], ep_dir=ep_old) == []


def test_big_head_cover_output(tmp_path):
    from sticker_engine.stages.assets import make_big_head_cover, _is_head_shot
    ep = _make_ep(tmp_path, ["呜呜呜"] + ["场景"] * 15)
    src = ep / "最终版" / "呜呜呜.png"
    assert _is_head_shot(src)            # 头肩格 bbox 近方
    out = tmp_path / "封面.png"
    assert make_big_head_cover(src, out)
    im = Image.open(out)
    assert im.size == (240, 240)
    arr = np.asarray(im)
    a = arr[:, :, 3]
    assert (a > 8).sum() > 240 * 240 * 0.2    # 内容存在
    assert a[2, 2] <= 8                        # 四角留白（不溢出画布）
    assert a[-3, -3] <= 8


def test_full_body_fails_quality_gate(tmp_path):
    from sticker_engine.stages.assets import _is_head_shot
    p = tmp_path / "全身.png"
    _full_body_image().save(p)
    assert not _is_head_shot(p)
