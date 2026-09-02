# -*- coding: utf-8 -*-
"""「修复并重新提交」命令测试：repolish+去空格（不触发发布/codex）。"""
import json
from pathlib import Path

from PIL import Image

import sticker_engine.cli as cli
from sticker_engine.cli import cmd_fix_and_republish, cmd_repolish_finals


def _call(handler, args):
    results = []
    orig = cli._result
    cli._result = lambda req_id, status, data=None, **kw: results.append(
        (status, data if data is not None else kw))
    try:
        handler("req-test", args)
    finally:
        cli._result = orig
    return results[0]


def _make_rejected_ep(tmp_path, album="周三涵做表情 61"):
    ep = tmp_path / "episode_x"
    final = ep / "最终版"; final.mkdir(parents=True)
    # 品红边框的"成品"（带边框线形态）
    im = Image.new("RGBA", (240, 240), (255, 0, 255, 255))
    im.paste(Image.new("RGBA", (180, 180), (250, 220, 200, 255)), (30, 30))
    im.save(final / "欢呼.png")
    from sticker_engine.config.series import load_meta, save_meta
    m = load_meta(ep); m.album_name = album
    m.platform_status = "未通过审核"
    m.platform_reject_reason = "表情名称应避免出现空格"
    save_meta(ep, m)
    return ep


def test_repolish_removes_border_and_backs_up(tmp_path):
    ep = _make_rejected_ep(tmp_path)
    st, data = _call(cmd_repolish_finals, {"episode_dir": str(ep)})
    assert st == "ok" and data["count"] == 1
    out = Image.open(ep / "最终版" / "欢呼.png").convert("RGBA")
    assert out.getpixel((3, 3))[3] == 0            # 品红边框被抠
    bak = Image.open(ep / "原图" / "_finals_backup" / "欢呼.png")
    assert bak.getpixel((3, 3))[3] == 255          # 备份是原图
    # 重跑不叠加（备份第一手）
    _call(cmd_repolish_finals, {"episode_dir": str(ep)})
    assert Image.open(ep / "最终版" / "欢呼.png").convert("RGBA").getpixel((3, 3))[3] == 0


def test_fix_strips_album_spaces_without_publish(tmp_path, monkeypatch):
    """publish=False：只修复（含改名），绝不触发发布/浏览器。"""
    ep = _make_rejected_ep(tmp_path)
    st, data = _call(cmd_fix_and_republish, {"episode_dir": str(ep), "publish": False})
    assert st == "ok" and data["published"] is False
    from sticker_engine.config.series import load_meta
    m = load_meta(ep)
    assert m.album_name == "周三涵做表情61"          # 空格已去
    # 精准化：61 的理由只提名称空格 → 只改 album，不跑去边框
    assert data["fields"] == ["album"]
    joined = "；".join(data["actions"])
    assert "去空格" in joined
    assert "去边框" not in joined


def test_fix_fields_from_border_reason(tmp_path):
    """边框线理由 → repolish 跑 + stickers/cover 进编辑字段。"""
    ep = _make_rejected_ep(tmp_path)
    from sticker_engine.config.series import load_meta, save_meta
    m = load_meta(ep)
    m.platform_reject_reason = "总体驳回理由\n表情图中含有多余边框线，需要去除。"
    save_meta(ep, m)
    st, data = _call(cmd_fix_and_republish, {"episode_dir": str(ep), "publish": False})
    assert st == "ok"
    assert "stickers" in data["fields"] and "cover" in data["fields"]
    joined = "；".join(data["actions"])
    assert "去边框" in joined
    # 品红边框被抠
    out = Image.open(ep / "最终版" / "欢呼.png").convert("RGBA")
    assert out.getpixel((3, 3))[3] == 0


def test_fix_fields_explicit_override(tmp_path):
    """args.fix_fields 显式指定 → 覆盖驳回理由推断（运维场景：只重传表情图）。"""
    ep = _make_rejected_ep(tmp_path)
    from sticker_engine.config.series import load_meta, save_meta
    m = load_meta(ep)
    m.platform_reject_reason = "表情图中含有多余边框线，需要去除。"
    save_meta(ep, m)
    st, data = _call(cmd_fix_and_republish, {
        "episode_dir": str(ep), "publish": False,
        "fix_fields": ["stickers"]})
    assert st == "ok"
    assert data["fields"] == ["stickers"]          # 显式覆盖：不再带 cover


def test_fix_banner_field_rebuilds_banner(tmp_path):
    """横幅变形驳回 → banner 进 fields + 本地用新版拼贴重做横幅。"""
    ep = _make_rejected_ep(tmp_path)
    from sticker_engine.config.series import load_meta, save_meta
    m = load_meta(ep)
    m.platform_reject_reason = (
        "详情页横幅\n图中元素不能被拉伸或压扁导致变形，需要调整。")
    save_meta(ep, m)
    st, data = _call(cmd_fix_and_republish, {"episode_dir": str(ep), "publish": False})
    assert st == "ok"
    assert "banner" in data["fields"]
    joined = "；".join(data["actions"])
    assert "横幅" in joined
    assert (ep / "横幅" / "横幅.png").exists()
    from PIL import Image as _Im
    assert _Im.open(ep / "横幅" / "横幅.png").size == (750, 400)
