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


# ---------------- 匹配器错配回归（2026-09-01 历史 60 弹导入事故） ----------------

def _cands():
    """模拟目录序：episode_2026xxx 在前，import_001-060 在后（5 在 57 前）。"""
    real = [{"album_name": "周三涵做表情61", "name": "episode_20260825_180912"}]
    imports = [{"album_name": f"周三涵做表情{n}", "name": f"episode_import_{n:03d}"}
               for n in range(1, 61)]
    return real + imports


def test_no_prefix_hijack_between_numbered_series():
    """57 的平台行绝不能抢走 5 的本地单（前缀互含在编号场景必须拒绝）。"""
    hit = match_episode("周三涵做表情57", _cands())
    assert hit and hit["album_name"] == "周三涵做表情57"


def test_exact_match_first_for_every_number():
    """1-60 每个编号的平台行都精确归属到同号本地单。"""
    cands = _cands()
    for n in (1, 5, 9, 16, 59, 60):
        hit = match_episode(f"周三涵做表情 {n}", cands)   # 平台名带空格也归一
        assert hit and hit["album_name"] == f"周三涵做表情{n}", n


def test_truncated_timestamp_still_matches():
    """时间戳长名被平台截断（episode202608251）仍能容错匹配。"""
    hit = match_episode("episode202608251", [
        {"album_name": "episode_20260825_180912", "name": "episode_20260825_180912"},
        {"album_name": "周三涵做表情5", "name": "episode_import_005"},
    ])
    assert hit and hit["album_name"] == "episode_20260825_180912"


def test_five_not_matched_when_only_longer_exists():
    """只有 57 本地单时，5 的平台行不得错配到它。"""
    hit = match_episode("周三涵做表情5", [
        {"album_name": "周三涵做表情57", "name": "episode_import_057"}])
    assert hit is None


# ---------------- 评审加固回归（2026-09-01 无上下文子 Agent 对抗评审） ----------------

def test_base_album_not_hijacked_by_numbered_row():
    """高危：57 的行不得命中无编号基础专辑（单侧无尾守卫）。"""
    assert match_episode("周三涵做表情57", [
        {"album_name": "周三涵做表情", "name": "episode_x"}]) is None


def test_base_album_row_not_hijacked_to_numbered_local():
    """高危：基础专辑的行不得命中 周三涵做表情1（5/57 复活口）。"""
    assert match_episode("周三涵做表情", [
        {"album_name": "周三涵做表情1", "name": "episode_import_001"},
        {"album_name": "周三涵做表情2", "name": "episode_import_002"}]) is None


def test_letter_suffix_cannot_bypass_guard():
    """字母后缀（尾数字取不到）不得绕过守卫。"""
    assert match_episode("episode20260825180912", [
        {"album_name": "episode_20260825_180912_extra",
         "name": "episode_20260825_180912_extra"}]) is None


def test_ambiguous_truncation_rejected():
    """中危：同小时两个时间戳作品截断歧义 → 拒配（不按目录序先到先得）。"""
    cands = [
        {"album_name": "episode_20260825_180958", "name": "episode_20260825_180958"},
        {"album_name": "episode_20260825_180912", "name": "episode_20260825_180912"},
    ]
    assert match_episode("episode202608251", cands) is None


def test_unambiguous_truncation_still_ok():
    """唯一真身截断（18 点档只有一单）仍匹配。"""
    assert match_episode("episode20260825180", [
        {"album_name": "episode_20260825_180912", "name": "episode_20260825_180912"},
    ])["album_name"] == "episode_20260825_180912"


def test_fullwidth_digits_normalized():
    """全角数字（平台表单手输事故高频）折叠后正常匹配。"""
    hit = match_episode("周三涵做表情５７", [
        {"album_name": "周三涵做表情57", "name": "episode_import_057"}])
    assert hit and hit["album_name"] == "周三涵做表情57"


def test_case_insensitive():
    assert match_episode("Episode202608251", [
        {"album_name": "episode_20260825_180912", "name": "episode_20260825_180912"}])


def test_unrelated_names_no_match():
    """无数字尾的行名（星星布丁）对无关候选（星星）不得互配。"""
    assert match_episode("星星布丁", [
        {"album_name": "星星", "name": "episode_y"}]) is None
