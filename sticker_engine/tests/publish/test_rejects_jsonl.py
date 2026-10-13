# -*- coding: utf-8 -*-
"""一键复制驳回理由（JSONL 导出）的收集逻辑测试。"""
from sticker_engine.cli import collect_reject_records
from sticker_engine.config.series import EpisodeMeta, save_meta


def test_collect_reject_records_filters_and_maps(tmp_path):
    """未通过+有理由 → 收集；已上架/无理由 → 过滤；字段映射正确。"""
    save_meta(tmp_path / "episode_a", EpisodeMeta(
        album_name="周三涵做表情207", platform_status="未通过审核",
        platform_reject_reason="图标不是纯头部正面图像"))
    save_meta(tmp_path / "episode_b", EpisodeMeta(
        album_name="周三涵做表情208", platform_status="已上架"))
    save_meta(tmp_path / "episode_c", EpisodeMeta(
        album_name="周三涵做表情209", platform_status="未通过审核",
        platform_reject_reason="名称中不能含有空格"))

    recs = collect_reject_records(tmp_path)

    assert [r["album_name"] for r in recs] == ["周三涵做表情207", "周三涵做表情209"]
    assert recs[0]["reject_reason"] == "图标不是纯头部正面图像"
    assert recs[0]["episode_dir"].endswith("episode_a")
    assert "platform_status" in recs[0] and "prompt_head" in recs[0]


def test_collect_reject_records_empty_root(tmp_path):
    assert collect_reject_records(tmp_path) == []
