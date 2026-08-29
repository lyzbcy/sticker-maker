"""平台状态抓取测试（「一键更新」，2026-08-27）。

夹具来自真实平台管理页 inner_text（2026-08-27 预检抓取）。
"""
import json

from sticker_engine.publish.status import (
    PlatformRow, match_episode, normalize_name, parse_rows_from_text)
from sticker_engine.config.series import EpisodeMeta

# 真实页面文本片段（名称+数据行交错，含多页作品）
REAL_PAGE_TEXT = """
作品	下载次数	发送次数	赞赏金额	状态	原创类型	最后更新	操作
周三涵做表情 63
-	-	-	待审核	原创	2026-08-27	详情
episode202608251
-	-	-	待审核	原创	2026-08-27	详情
episode202608251
-	-	-	已保存	原创	2026-08-25	详情
周三涵做表情58
-	-	-	未通过审核	原创	2026-07-07	详情
周三涵做表情32
68	214	-	已上架
原创	2026-07-01	详情
周三涵做表情43
63	172	-	已上架
原创	2026-07-01	详情
1 / 7 下一页  跳转
"""


def test_parse_rows_from_real_page_text():
    rows = parse_rows_from_text(REAL_PAGE_TEXT)
    names = {r.name for r in rows}
    assert "周三涵做表情 63" in names
    assert "周三涵做表情32" in names
    assert len(rows) >= 6
    by_name = {r.name: r for r in rows}
    r63 = by_name["周三涵做表情 63"]
    assert r63.status == "待审核" and r63.updated == "2026-08-27"
    assert r63.downloads == "-" and r63.sends == "-"
    r32 = by_name["周三涵做表情32"]
    assert r32.status == "已上架" and r32.downloads == "68" and r32.sends == "214"
    r58 = by_name["周三涵做表情58"]
    assert r58.status == "未通过审核"


def test_normalize_name_strips_punct():
    assert normalize_name("episode_2026-08-25_180912") == "episode20260825180912"
    assert normalize_name("周三涵做表情 63") == "周三涵做表情63"


def test_match_exact_album_name():
    row = match_episode("周三涵做表情 63", [
        {"album_name": "周三涵做表情 63", "name": "episode_20260827_205842"},
        {"album_name": "周三涵做表情 61", "name": "episode_20260825_180912"},
    ])
    assert row and row["album_name"] == "周三涵做表情 63"


def test_match_truncated_platform_name():
    """平台把长目录名截断显示（episode202608251）——前缀匹配要能对上。"""
    row = match_episode("episode202608251", [
        {"album_name": "", "name": "episode_20260825_180912"},
    ])
    assert row is not None


def test_match_returns_none_for_unknown():
    assert match_episode("别人的作品", [
        {"album_name": "周三涵做表情 63", "name": "episode_x"}]) is None


def test_meta_platform_fields_roundtrip(tmp_path):
    """平台状态字段要能落盘 + 读回。"""
    m = EpisodeMeta(album_name="周三涵做表情 63")
    m.platform_status = "已上架"
    m.platform_downloads = "68"
    m.platform_sends = "214"
    m.platform_tips = "-"
    m.platform_updated_at = "2026-08-27 23:59:00"
    from sticker_engine.config.series import save_meta, load_meta
    save_meta(tmp_path, m)
    m2 = load_meta(tmp_path)
    assert m2.platform_status == "已上架"
    assert m2.platform_downloads == "68"
    assert m2.platform_updated_at == "2026-08-27 23:59:00"


def test_old_meta_without_platform_fields_loads(tmp_path):
    """历史 meta（无平台字段）加载不炸，字段取默认值。"""
    (tmp_path / "meta.json").write_text(
        json.dumps({"album_name": "旧作品", "published": True}), encoding="utf-8")
    from sticker_engine.config.series import load_meta
    m = load_meta(tmp_path)
    assert m.album_name == "旧作品"
    assert m.platform_status == ""
    assert m.platform_downloads == "-"


# ---------------- 驳回理由（2026-08-29：详情页→未通过审核→表情驳回理由） ----------------

# 真实理由页文本（2026-08-29 实测抓取：聊天页图标驳回）
REAL_REASON_TEXT = """微信表情开放平台
我的表情
常见问题
公告
3
表情驳回理由
聊天页图标
聊天页图标在手机上展示位置较小，请去除不必要的文字信息和装饰图案。"""


def test_extract_reason_from_real_page():
    from sticker_engine.publish.status import _extract_reason
    r = _extract_reason(REAL_REASON_TEXT)
    assert "聊天页图标在手机上展示位置较小" in r
    assert "表情驳回理由" not in r          # 标题不混入
    assert "微信表情开放平台" not in r       # 页头导航不混入


def test_extract_reason_missing_key_returns_empty():
    from sticker_engine.publish.status import _extract_reason
    assert _extract_reason("页面里没有关键词") == ""


def test_reject_reason_persisted_in_meta():
    """reject_reason 写进 meta 且 to_dict 带出（前端字段链路）。"""
    m = EpisodeMeta(album_name="周三涵做表情 65")
    m.platform_status = "未通过审核"
    m.platform_reject_reason = "聊天页图标在手机上展示位置较小，请去除不必要的文字信息和装饰图案。"
    d = m.to_dict()
    assert d["platform_reject_reason"].startswith("聊天页图标在手机上")
    # 旧 meta（无该字段）反序列化兼容
    m2 = EpisodeMeta.from_dict({"album_name": "x", "platform_status": "已上架"})
    assert m2.platform_reject_reason == ""
