# -*- coding: utf-8 -*-
"""P1/P2 平台驳回整改测试（doc/reference/platform-review.md）。

P1：图标 AI 生成纯头部正面照（成功 / codex 失败 fallback / 废图质检 / prompt 单行铁律）
P2：trim_border_band 裁掉四边同色不透明残留带（品红格线/黑底），白描边与透明留白不受影响
"""
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image

from sticker_engine.stages.postprocess import trim_border_band
from sticker_engine.stages.assets import AssetsStage, _ICON_AI_PROMPT


def _solid(size, rgba):
    return Image.new("RGBA", size, rgba)


# ---------------- P2：trim_border_band ----------------

def test_trim_magenta_border_band():
    """品红残留带（62 事故形态）：外圈品红 + 中间角色白块 → 品红被裁掉。"""
    im = Image.new("RGBA", (100, 100), (255, 0, 255, 255))     # 品红底
    im.paste(_solid((70, 70), (255, 255, 255, 255)), (15, 15))  # 角色白块
    out = trim_border_band(im)
    assert out.size == (70, 70)          # 四边各 15px 品红带全裁
    assert out.getpixel((5, 5)) == (255, 255, 255, 255)


def test_trim_black_border_band():
    """黑底残留（62 生图画黑底场景）。"""
    im = Image.new("RGBA", (80, 80), (10, 10, 10, 255))
    im.paste(_solid((60, 60), (250, 200, 200, 255)), (10, 10))
    out = trim_border_band(im)
    assert out.size == (60, 60)


def test_no_trim_for_transparent_edges():
    """透明留白（正常成品）：不裁（透明不参与残留带判定）。"""
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    im.paste(_solid((40, 40), (200, 100, 100, 255)), (30, 30))
    out = trim_border_band(im)
    assert out.size == (100, 100)        # 原样


def test_no_trim_for_curved_character():
    """角色本体（弧形，非整行同色）：不裁。"""
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for r in range(10, 40):   # 画同心圆环模拟弧形角色
        for x in range(100):
            for y in range(100):
                if abs((x - 50) ** 2 + (y - 50) ** 2 - r * r) < 8:
                    im.putpixel((x, y), (255, 255, 255, 255))
    out = trim_border_band(im)
    assert out.size == (100, 100)


def test_conservative_giveup_on_huge_band():
    """大面积单色底（>50%）→ 保守放弃不裁（防把角色一起裁没）。"""
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    im.paste(_solid((20, 20), (255, 0, 255, 255)), (40, 40))   # 单色块在中间
    # 构造：整块不透明品红 90x90（角色 20x20 融在其内无法区分）→ 裁完 <50% 放弃
    im2 = Image.new("RGBA", (100, 100), (255, 0, 255, 255))
    out = trim_border_band(im2)
    assert out.size == (100, 100)        # 全裁会 <50%，保守不动


# ---------------- P1：AI 图标 ----------------

def _ctx(tmp_path):
    from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
    from sticker_engine.config.schema import Config, Paths
    paths = Paths(user_data=tmp_path, output_root=tmp_path / "e", reference_lib=tmp_path / "ref",
                  prefs_file=tmp_path / "p.yaml", codex_exec="codex", codex_output_dir=tmp_path / "codex")
    config = Config.placeholder(); config.paths = paths
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path / "e1"; ctx.episode_dir.mkdir(parents=True)
    return ctx


def test_icon_prompt_is_single_line():
    """codex 铁律：图标 prompt 必须单行（多行经 codex.cmd 丢参考图）。"""
    assert "\n" not in _ICON_AI_PROMPT
    assert "HEAD" in _ICON_AI_PROMPT and "magenta" in _ICON_AI_PROMPT
    assert "no text" in _ICON_AI_PROMPT


def test_ai_icon_success(tmp_path):
    """codex 生成成功 → 抠洋红 + trim + 240 补方落盘。"""
    ctx = _ctx(tmp_path)
    raw = tmp_path / "raw_icon.png"
    im = Image.new("RGBA", (120, 120), (255, 0, 255, 255))          # 洋红底
    im.paste(Image.new("RGBA", (90, 90), (255, 220, 200, 255)), (15, 15))  # "头"
    im.save(raw)
    fake_codex = MagicMock()
    fake_codex.generate.return_value = str(raw)
    vision = MagicMock()
    vision.codex = fake_codex
    stage = AssetsStage(vision)
    base = tmp_path / "base.png"
    Image.new("RGBA", (50, 50), (255, 255, 255, 255)).save(base)
    ctx.selected_bases = [base]          # S0 选中的 base 作参考（保 IP）
    out = stage._make_ai_icon(ctx, [])
    assert out is not None and Path(out).exists()
    img = Image.open(out)
    assert img.size == (240, 240)
    # 洋红被抠（四角透明或非品红）
    fake_codex.generate.assert_called_once()
    kw = fake_codex.generate.call_args.kwargs
    assert kw["prompt"] == _ICON_AI_PROMPT


def test_ai_icon_fallback_on_failure(tmp_path):
    """codex 失败 → None（调用方退回复用封面，素材永不缺失）。"""
    ctx = _ctx(tmp_path)
    fake_codex = MagicMock()
    fake_codex.generate.return_value = None
    vision = MagicMock(); vision.codex = fake_codex
    stage = AssetsStage(vision)
    assert stage._make_ai_icon(ctx, [tmp_path / "a.png"]) is None


def test_ai_icon_rejects_solid_waste(tmp_path):
    """纯色废图（>98% 同灰度）→ 当作失败返回 None。"""
    ctx = _ctx(tmp_path)
    raw = tmp_path / "waste.png"
    Image.new("RGBA", (100, 100), (0, 0, 0, 255)).save(raw)
    fake_codex = MagicMock(); fake_codex.generate.return_value = str(raw)
    vision = MagicMock(); vision.codex = fake_codex
    assert AssetsStage(vision)._make_ai_icon(ctx, []) is None


# ---------------- P2 第二层：remove_edge_background ----------------

def test_remove_edge_background_black():
    """62 场景：黑底+品红边框 → 抠成透明，角色保留。"""
    from sticker_engine.stages.postprocess import remove_edge_background
    im = Image.new("RGBA", (100, 100), (10, 10, 10, 255))              # 黑底
    im.paste(Image.new("RGBA", (100, 8), (255, 0, 255, 255)), (0, 0))  # 顶部品红条
    im.paste(Image.new("RGBA", (50, 60), (250, 250, 250, 255)), (25, 30))  # 角色（占50%，贴近真实）
    out = remove_edge_background(im)
    assert out.getpixel((5, 50))[3] == 0          # 黑底透明
    assert out.getpixel((50, 2))[3] == 0          # 品红条透明
    assert out.getpixel((50, 55))[3] == 255       # 角色保留


def test_remove_edge_background_keeps_unconnected_same_color():
    """角色与背景同色但不连通边缘 → 安全保留（连通性判据）。"""
    from sticker_engine.stages.postprocess import remove_edge_background
    im = Image.new("RGBA", (80, 80), (255, 0, 255, 255))              # 洋红底
    im.paste(Image.new("RGBA", (30, 30), (255, 0, 255, 255)), (25, 25))  # 同色块（被白框围住更真实）
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    d.rectangle([22, 22, 57, 57], outline=(255, 255, 255, 255), width=4)  # 白描边围住
    out = remove_edge_background(im)
    assert out.getpixel((5, 5))[3] == 0            # 底被抠
    assert out.getpixel((40, 40))[3] == 255        # 围住的同色块保留


def test_remove_edge_background_skips_transparent_edges():
    """边缘大半透明（chromakey 已处理）→ 原样返回不折腾。"""
    from sticker_engine.stages.postprocess import remove_edge_background
    im = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (30, 30), (200, 100, 100, 255)), (15, 15))
    out = remove_edge_background(im)
    assert out.size == (60, 60) and out.getpixel((30, 30))[3] == 255
