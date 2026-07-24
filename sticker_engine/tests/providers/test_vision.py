"""决策 K：VisionProvider 真实调 codex.exec_text（识图命名 + 介绍文案）。

本任务（Task K 补完）把 skeleton 接通真实 codex 文本能力：
- interpret() 拼大图 → codex.exec_text(识图 prompt, refs=[大图]) → 解析 JSON
- write_intro() codex.exec_text(介绍 prompt) → 截断 80 字
- 两者失败时优雅降级，管线不崩。

测试用 MagicMock 注入 codex，不真实调 codex（本机无 codex，决策 A1）。
"""
from unittest.mock import MagicMock

from PIL import Image

from sticker_engine.providers.vision import VisionProvider


def _make_panel(tmp_path, name="a.png"):
    p = tmp_path / name
    Image.new("RGBA", (10, 10)).save(p)
    return p


def test_interpret_parses_json_from_codex_text(tmp_path):
    """纯 JSON：codex 返回 '{"1":"开心","2":"难过"}'，解析为 int 键 dict。"""
    p1 = _make_panel(tmp_path, "a.png")
    p2 = _make_panel(tmp_path, "b.png")
    codex = MagicMock()
    codex.exec_text.return_value = '{"1":"开心","2":"难过"}'
    vision = VisionProvider(codex)
    result = vision.interpret([p1, p2])
    assert result == {1: "开心", 2: "难过"}


def test_interpret_handles_fenced_json(tmp_path):
    """```json 围栏：codex 返回带 markdown 围栏的 JSON，提取第一个 {...} 块。"""
    p1 = _make_panel(tmp_path, "a.png")
    codex = MagicMock()
    codex.exec_text.return_value = '```json\n{"1":"嘿嘿"}\n```'
    vision = VisionProvider(codex)
    assert vision.interpret([p1]) == {1: "嘿嘿"}


def test_intermit_handles_codex_prose_wrapping_json(tmp_path):
    """codex 前后带说明文字 + JSON 块（最常见真实输出）。"""
    p1 = _make_panel(tmp_path, "a.png")
    p2 = _make_panel(tmp_path, "b.png")
    codex = MagicMock()
    codex.exec_text.return_value = (
        '好的，这是每个表情的含义：\n'
        '{"1":"开心","2":"难过"}\n'
        '希望对你有帮助。'
    )
    vision = VisionProvider(codex)
    assert vision.interpret([p1, p2]) == {1: "开心", 2: "难过"}


def test_interpret_passes_contact_sheet_as_ref(tmp_path):
    """识图任务把拼图作为 -i 参考图传给 codex（refs=[大图路径]）。"""
    p1 = _make_panel(tmp_path, "a.png")
    p2 = _make_panel(tmp_path, "b.png")
    codex = MagicMock()
    codex.exec_text.return_value = '{"1":"x","2":"y"}'
    vision = VisionProvider(codex)
    vision.interpret([p1, p2])
    codex.exec_text.assert_called_once()
    _prompt, kwargs = codex.exec_text.call_args[0], codex.exec_text.call_args.kwargs
    refs = kwargs.get("refs") if "refs" in kwargs else (codex.exec_text.call_args[0][1]
              if len(codex.exec_text.call_args[0]) > 1 else None)
    assert refs and len(refs) == 1   # 传了拼图路径
    from pathlib import Path
    assert isinstance(refs[0], Path)


def test_interpret_degrades_when_codex_fails(tmp_path):
    """codex 失败（空串）→ 降级 含义N，不崩管线。"""
    p1 = _make_panel(tmp_path, "a.png")
    p2 = _make_panel(tmp_path, "b.png")
    codex = MagicMock()
    codex.exec_text.return_value = ""   # codex 失败
    vision = VisionProvider(codex)
    result = vision.interpret([p1, p2])
    assert result == {1: "含义1", 2: "含义2"}


def test_interpret_degrades_on_unparsable_text(tmp_path):
    """codex 返回非 JSON 文本 → 降级 含义N。"""
    p1 = _make_panel(tmp_path, "a.png")
    codex = MagicMock()
    codex.exec_text.return_value = "我无法识别这张图。"   # 无 JSON
    vision = VisionProvider(codex)
    result = vision.interpret([p1])
    assert result == {1: "含义1"}


def test_interpret_empty_panels_returns_empty(tmp_path):
    codex = MagicMock()
    vision = VisionProvider(codex)
    assert vision.interpret([]) == {}
    codex.exec_text.assert_not_called()


def test_write_intro_returns_codex_text_truncated(tmp_path):
    """codex 成功 → 返回 codex 文本，硬截断 80 字。"""
    codex = MagicMock()
    codex.exec_text.return_value = "软萌可爱的日常表情，适合聊天接梗。" + "x" * 100
    vision = VisionProvider(codex)
    intro = vision.write_intro(["开心", "难过"], episode_name="测试")
    assert len(intro) <= 80
    assert "软萌" in intro


def test_write_intro_degrades_when_codex_fails(tmp_path):
    """codex 失败 → 降级模板（基于含义词，非固定字面量），<=80 字。"""
    codex = MagicMock()
    codex.exec_text.return_value = ""
    vision = VisionProvider(codex)
    intro = vision.write_intro(["开心"], episode_name="测试")
    assert len(intro) <= 80
    assert len(intro) > 0
    # 降级模板应包含含义词或名字（不是固定字面量）
    assert "开心" in intro or "测试" in intro


def test_parse_meanings_from_text_helper(tmp_path):
    """直接测 _parse_meanings_from_text：纯 JSON / 围栏 / 散文包裹 / 不可解析。"""
    codex = MagicMock()
    vision = VisionProvider(codex)
    assert vision._parse_meanings_from_text('{"1":"a","2":"b"}', 2) == {1: "a", 2: "b"}
    assert vision._parse_meanings_from_text('```json\n{"1":"a"}\n```', 1) == {1: "a"}
    assert vision._parse_meanings_from_text('说明文字 {"2":"b"} 结尾', 2) == {2: "b"}
    assert vision._parse_meanings_from_text("不可解析", 2) == {1: "含义1", 2: "含义2"}
    assert vision._parse_meanings_from_text("", 1) == {1: "含义1"}
