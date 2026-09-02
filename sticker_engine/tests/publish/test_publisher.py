"""Publisher 单测。

- EpisodeAssets.from_dir：纯文件解析，用 tmp_path 构造 episode。
- Publisher.publish：用 MagicMock 模拟 page/session，断言步骤调用序列、早退、提交判定。

不启动真实浏览器。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from sticker_engine.publish import publisher as pub_mod
from sticker_engine.publish.publisher import EpisodeAssets, Publisher
from sticker_engine.publish.config import PublishConfig
from sticker_engine.publish import selectors as S


# ---------------------------------------------------------------------------
# 测试夹具：构造 episode 目录
# ---------------------------------------------------------------------------


def _write_png(path: Path) -> None:
    """写一个最小合法 PNG（8 字节签名 + IHDR 不强求，用最小 1x1）。"""
    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1x1 8bit RGBA
    idat_raw = b"\x00" + b"\x00\x00\x00\xff"  # filter byte + 1 RGBA pixel
    idat = zlib.compress(idat_raw)
    iend = b""
    path.write_bytes(sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", iend))


def make_episode(tmp_path: Path, *, meanings=None, has_char_card=True,
                 contains_laoyu=False, with_meaning_map=True,
                 with_assets=True, intro="这是介绍", n=16,
                 characters=None) -> Path:
    """构造一个 episode 目录。返回 episode 路径。

    meanings: 16 个含义词列表（默认 meaning_01..）。若 with_meaning_map 且 meanings
    非默认顺序，会写 meaning_map.json 打乱顺序验证排序逻辑。
    """
    ep = tmp_path / "episode_test"
    final = ep / "最终版"
    final.mkdir(parents=True)
    if meanings is None:
        meanings = [f"meaning_{i:02d}" for i in range(1, n + 1)]

    for m in meanings:
        _write_png(final / f"{m}.png")

    if with_meaning_map:
        # 故意打乱 key 顺序，验证按 int key 升序
        shuffled = {}
        for i, m in enumerate(meanings, start=1):
            shuffled[str(n - i + 1)] = m  # key 倒序
        (ep / "meaning_map.json").write_text(
            json.dumps(shuffled, ensure_ascii=False), encoding="utf-8"
        )

    if with_assets:
        (ep / "横幅").mkdir()
        _write_png(ep / "横幅" / "横幅.png")
        (ep / "封面").mkdir()
        _write_png(ep / "封面" / "封面.png")
        (ep / "图标").mkdir()
        _write_png(ep / "图标" / "图标.png")

    if intro is not None:
        (ep / "介绍.txt").write_text(intro, encoding="utf-8")

    if has_char_card:
        line = "含捞鱼：是" if contains_laoyu else "含捞鱼：否"
        default_role = "捞鱼" if contains_laoyu else "星星布丁"
        roles = "、".join(characters) if characters else default_role
        (ep / "本次制作角色.md").write_text(
            f"# 角色\n角色：{roles}\n{line}\n", encoding="utf-8")

    return ep


# ===========================================================================
# EpisodeAssets.from_dir
# ===========================================================================


def test_from_dir_orders_stickers_by_meaning_map_int_key(tmp_path):
    """meaning_map.json 的 key 按 int 升序，而非文件名字母序。"""
    ep = make_episode(tmp_path, meanings=["zeta", "alpha", "mid"])
    # meaning_map key 故意倒序：{"3":"zeta","2":"alpha","1":"mid"}
    assets = EpisodeAssets.from_dir(ep)
    # 期望按 key 1→3：mid, alpha, zeta
    assert [a.stem for a in assets.stickers] == ["mid", "alpha", "zeta"]
    assert assets.meanings == ["mid", "alpha", "zeta"]


def test_from_dir_falls_back_to_filename_sort_without_map(tmp_path):
    """无 meaning_map 时按文件名排序。"""
    ep = make_episode(tmp_path, meanings=["charlie", "alpha", "bravo"],
                      with_meaning_map=False)
    assets = EpisodeAssets.from_dir(ep)
    assert [a.stem for a in assets.stickers] == ["alpha", "bravo", "charlie"]
    assert assets.meanings == ["alpha", "bravo", "charlie"]


def test_from_dir_detects_laoyu_yes(tmp_path):
    ep = make_episode(tmp_path, contains_laoyu=True)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.contains_laoyu is True


def test_from_dir_detects_laoyu_no(tmp_path):
    ep = make_episode(tmp_path, contains_laoyu=False)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.contains_laoyu is False


def test_from_dir_no_char_card_means_no_laoyu(tmp_path):
    ep = make_episode(tmp_path, has_char_card=False)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.contains_laoyu is False


def test_from_dir_resolves_asset_paths(tmp_path):
    ep = make_episode(tmp_path)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.banner == ep / "横幅" / "横幅.png"
    assert assets.cover == ep / "封面" / "封面.png"
    assert assets.icon == ep / "图标" / "图标.png"


def test_from_dir_missing_assets_are_none(tmp_path):
    ep = make_episode(tmp_path, with_assets=False)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.banner is None
    assert assets.cover is None
    assert assets.icon is None


def test_from_dir_reads_intro_and_truncates_to_80(tmp_path):
    long_intro = "啊" * 200
    ep = make_episode(tmp_path, intro=long_intro)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.intro == "啊" * 80


def test_from_dir_album_name_is_dir_name(tmp_path):
    ep = make_episode(tmp_path)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.album_name == "episode_test"


def test_from_dir_empty_final_returns_empty_stickers(tmp_path):
    """最终版/ 不存在或为空 → stickers 空。"""
    ep = tmp_path / "empty_episode"
    ep.mkdir()
    (ep / "本次制作角色.md").write_text("含捞鱼：否", encoding="utf-8")
    assets = EpisodeAssets.from_dir(ep)
    assert assets.stickers == []
    assert assets.meanings == []


def test_from_dir_corrupt_meaning_map_falls_back_to_filename(tmp_path):
    """meaning_map.json 损坏 → 回退文件名排序。"""
    ep = make_episode(tmp_path, meanings=["bravo", "alpha"],
                      with_meaning_map=False)
    # 写一个非法 JSON
    (ep / "meaning_map.json").write_text("{not valid json", encoding="utf-8")
    assets = EpisodeAssets.from_dir(ep)
    assert [a.stem for a in assets.stickers] == ["alpha", "bravo"]


def test_validate_flags_empty_stickers(tmp_path):
    ep = tmp_path / "no_stickers"
    ep.mkdir()
    assets = EpisodeAssets.from_dir(ep)
    problems = assets.validate()
    assert any("无表情图" in p for p in problems)


def test_validate_passes_when_stickers_align(tmp_path):
    ep = make_episode(tmp_path)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.validate() == []


def test_from_dir_meaning_map_in_yuantu_subdir(tmp_path):
    """meaning_map.json 在 原图/ 子目录（A 产出位置）也能读到。"""
    ep = tmp_path / "episode_yt"
    final = ep / "最终版"
    final.mkdir(parents=True)
    (ep / "原图").mkdir()
    for m in ["first", "second"]:
        _write_png(final / f"{m}.png")
    # key 倒序
    (ep / "原图" / "_meaning_map.json").write_text(
        json.dumps({"2": "first", "1": "second"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (ep / "本次制作角色.md").write_text("含捞鱼：否", encoding="utf-8")
    assets = EpisodeAssets.from_dir(ep)
    assert [a.stem for a in assets.stickers] == ["second", "first"]


# ===========================================================================
# Publisher.publish（mock page/session）
# ===========================================================================


def _make_publisher(tmp_path) -> tuple[Publisher, MagicMock, MagicMock]:
    """造一个 Publisher，session/page 全 mock。config 的赞赏图指向真实文件。"""
    # 赞赏图存在（避免校验早退）
    tips_dir = tmp_path / "赞赏页"
    tips_dir.mkdir()
    guide = tips_dir / "赞赏引导图.png"
    thanks = tips_dir / "赞赏致谢图.png"
    _write_png(guide)
    _write_png(thanks)

    config = PublishConfig(
        tip_guide_img=guide, tip_thanks_img=thanks,
        account="a@b.com", password="secret",
    )
    session = MagicMock(name="session")
    page = MagicMock(name="page")
    # 默认 inner_text 返回含"提交成功"以走 happy path
    page.inner_text.return_value = "提交成功"
    # session.start 返回 page
    session.start.return_value = page
    session.ensure_login.return_value = True
    publisher = Publisher(config, session)
    return publisher, session, page


def _patch_all_steps(publisher: Publisher) -> dict:
    """把所有 _step_* 换成 spy，返回 {name: mock}。"""
    spies = {}
    for name in dir(publisher):
        if name.startswith("_step_") or name in (
            "_select_role", "_confirm_crop", "_upload_uploader_at",
            "_upload_tip_images",
        ):
            m = MagicMock(name=name)
            spies[name] = m
            setattr(publisher, name, m)
    return spies


def test_publish_happy_path_calls_steps_in_order_and_closes(tmp_path):
    """happy path：ensure_login 后各 _step_* 被调，session.close 被调，返回 success。"""
    ep = make_episode(tmp_path)
    publisher, session, page = _make_publisher(tmp_path)
    # _step_submit 直接返回 True（不进真实 page.click）
    publisher._step_submit = MagicMock(return_value=True)
    publisher._verify_form = MagicMock(return_value=[])
    # 其余 step 用 spy（不抛），用 manager 记录调用顺序
    manager = MagicMock(name="manager")
    for name in ("_step_open_submit_form", "_step_tips", "_step_upload_assets",
                 "_step_upload_stickers", "_step_fill_meanings",
                 "_step_fill_album_info", "_step_fill_copyright",
                 "_step_select_categories", "_step_select_price"):
        m = getattr(manager, name)
        setattr(publisher, name, m)

    result = publisher.publish(ep)

    assert result["success"] is True
    assert result["step"] == "done"
    assert result["album_name"] == "episode_test"
    # 登录、开表单、上传表情图都应被调用
    session.ensure_login.assert_called_once()
    session.ensure_login.assert_called_once_with(page, on_status=ANY)
    for name in ("_step_open_submit_form", "_step_tips", "_step_upload_assets",
                 "_step_upload_stickers", "_step_fill_meanings",
                 "_step_fill_album_info", "_step_fill_copyright",
                 "_step_select_categories", "_step_select_price"):
        getattr(manager, name).assert_called_once()
    publisher._step_submit.assert_called_once()
    session.close.assert_called_once()


def test_publish_new_mode_uploads_assets_before_stickers(tmp_path):
    """2026-09-02 顺序重构（71-89 批量失败事故）：新建模式素材图（赞赏/
    横幅/封面/图标）必须先于 16 张表情图上传——表情图 set 后占满平台
    异步上传队列，紧随其后的素材 set 会被吞（提交时红字"横幅不能为空"）。"""
    ep = make_episode(tmp_path)
    publisher, session, page = _make_publisher(tmp_path)
    publisher._step_submit = MagicMock(return_value=True)
    publisher._verify_form = MagicMock(return_value=[])
    order = []
    for name in ("_step_tips", "_step_upload_assets", "_step_upload_stickers",
                 "_step_fill_meanings", "_step_fill_album_info"):
        def _spy(*_a, _name=name, **_k):
            order.append(_name)
            return True   # tips 先行成功，不触发兜底
        setattr(publisher, name, _spy)

    result = publisher.publish(ep)

    assert result["success"] is True
    assert order == ["_step_tips", "_step_upload_assets",
                     "_step_upload_stickers", "_step_fill_meanings",
                     "_step_fill_album_info"]


def test_publish_tips_fallback_reruns_after_categories(tmp_path):
    """赞赏区先前未就绪（_step_tips 返回 False）→ 分类/价格之后兜底重跑。"""
    ep = make_episode(tmp_path)
    publisher, session, page = _make_publisher(tmp_path)
    publisher._step_submit = MagicMock(return_value=True)
    publisher._verify_form = MagicMock(return_value=[])
    calls = []
    state = {"tips": 0}

    def _tips(page, assets):
        state["tips"] += 1
        calls.append(f"_step_tips#{state['tips']}")
        return state["tips"] >= 2   # 第一次 False（区未渲染），第二次 True

    publisher._step_tips = _tips
    for name in ("_step_upload_assets", "_step_upload_stickers",
                 "_step_fill_meanings", "_step_fill_album_info",
                 "_step_select_categories", "_step_select_price"):
        def _spy(*_a, _name=name, **_k):
            calls.append(_name)
        setattr(publisher, name, _spy)

    result = publisher.publish(ep)

    assert result["success"] is True
    assert calls.count("_step_tips#1") == 1 and calls.count("_step_tips#2") == 1
    # 第二次赞赏兜底必须发生在分类之后
    assert calls.index("_step_tips#2") > calls.index("_step_select_categories")


def test_publish_early_exit_when_no_stickers(tmp_path):
    """无表情图 → step=prepare，不启动浏览器。"""
    ep = tmp_path / "empty"
    ep.mkdir()
    publisher, session, page = _make_publisher(tmp_path)
    result = publisher.publish(ep)
    assert result["success"] is False
    assert result["step"] == "prepare"
    assert "无表情图" in result["error"]
    # 不应启动浏览器
    session.start.assert_not_called()


def test_publish_early_exit_when_tips_images_missing(tmp_path):
    """赞赏图缺失 → step=prepare，不启动浏览器。"""
    ep = make_episode(tmp_path)
    config = PublishConfig(
        tip_guide_img=tmp_path / "no_guide.png",
        tip_thanks_img=tmp_path / "no_thanks.png",
    )
    session = MagicMock(name="session")
    page = MagicMock()
    session.start.return_value = page
    publisher = Publisher(config, session)

    result = publisher.publish(ep)
    assert result["success"] is False
    assert result["step"] == "prepare"
    assert "赞赏图缺失" in result["error"]
    session.start.assert_not_called()


def test_publish_early_exit_on_login_failure(tmp_path):
    """登录失败 → step=login，后续步骤不执行。"""
    ep = make_episode(tmp_path)
    publisher, session, page = _make_publisher(tmp_path)
    session.ensure_login.return_value = False
    step_calls = []
    for name in ("_step_open_submit_form", "_step_upload_stickers"):
        def _spy(_name=name):
            step_calls.append(_name)
        setattr(publisher, name, _spy)

    result = publisher.publish(ep)
    assert result["success"] is False
    assert result["step"] == "login"
    assert result["error"].startswith("登录超时")
    # 后续步骤不应执行
    assert step_calls == []
    session.close.assert_called_once()


def test_publish_submit_failure_returns_submit_step(tmp_path):
    """_step_submit 返回 False → step=submit, success=False。"""
    ep = make_episode(tmp_path)
    publisher, session, page = _make_publisher(tmp_path)
    page.inner_text.return_value = "完全无关的文案"
    page.url = "https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=form/apply"
    publisher._step_submit = MagicMock(return_value=False)

    result = publisher.publish(ep)
    assert result["success"] is False
    assert result["step"] == "submit"


def test_publish_exception_screenshots_and_closes(tmp_path):
    """步骤抛异常 → 截图、close、返回 step=unknown。"""
    ep = make_episode(tmp_path)
    publisher, session, page = _make_publisher(tmp_path)

    def boom(*a, **kw):
        raise RuntimeError("boom")
    publisher._step_open_submit_form = boom

    result = publisher.publish(ep)
    assert result["success"] is False
    assert result["step"] == "unknown"
    assert "RuntimeError: boom" in result["error"]
    page.screenshot.assert_called_once()
    session.close.assert_called_once()


def test_publish_passes_headless_to_session(tmp_path):
    """headless 参数透传给 session.start。"""
    ep = make_episode(tmp_path)
    publisher, session, page = _make_publisher(tmp_path)
    publisher._step_submit = MagicMock(return_value=True)
    publisher._verify_form = MagicMock(return_value=[])
    for name in ("_step_open_submit_form", "_step_upload_stickers",
                 "_step_fill_meanings", "_step_fill_album_info",
                 "_step_fill_copyright", "_step_upload_assets",
                 "_step_select_categories", "_step_select_price",
                 "_step_tips"):
        setattr(publisher, name, MagicMock(name=name))

    publisher.publish(ep, headless=True)
    session.start.assert_called_once_with(headless=True)


def test_step_fill_meanings_passes_meanings_and_selector(tmp_path):
    """步骤7：evaluate(script, [meanings, MEANING_INPUT])。
    2026-09-02 加固后填完会做数量验证（多一次 evaluate 检查）——填充
    调用要从 call_args_list 里按 payload 形状找。"""
    ep = make_episode(tmp_path, meanings=["aa", "bb"], with_meaning_map=False)
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    # 检查 evaluate 返回 {n, filled} 满足条件 → 一轮成功
    page.evaluate.side_effect = [None, {"n": 2, "filled": 2}]
    publisher._step_fill_meanings(page, assets)
    fill_calls = [c for c in page.evaluate.call_args_list
                  if len(c.args) > 1 and isinstance(c.args[1], list)]
    assert fill_calls, "应至少有一次填充 evaluate"
    payload = fill_calls[0].args[1]
    assert payload[0] == ["aa", "bb"]
    assert payload[1] == S.MEANING_INPUT
    # 验证通过后不重填
    assert len(fill_calls) == 1


def test_step_fill_meanings_retries_when_cells_not_rendered(tmp_path):
    """2026-09-02（71 单实测）：含义词格子逐个渲染——首轮只有 1/2 格有值
    时必须重填，直到全部有值。"""
    ep = make_episode(tmp_path, meanings=["aa", "bb"], with_meaning_map=False)
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    page.evaluate.side_effect = [
        None, {"n": 2, "filled": 1},          # 第 1 轮：只填上 1 格
        None, {"n": 2, "filled": 2},          # 第 2 轮：全填上
    ]
    publisher._step_fill_meanings(page, assets)
    fill_calls = [c for c in page.evaluate.call_args_list
                  if isinstance(c.args[1], list)]
    assert len(fill_calls) == 2
    assert any("重填" in w for w in publisher.warnings)


def test_step_open_submit_form_uses_selector_constants(tmp_path):
    """步骤3-4 用常量按钮；步骤5 改为点「静态表情」label（平台隐藏了 radio input）。"""
    publisher, session, page = _make_publisher(tmp_path)
    publisher._step_open_submit_form(page)
    click_selectors = [c.args[0] for c in page.click.call_args_list]
    assert any(S.SUBMIT_WORK_BUTTON_TEXT in c for c in click_selectors)
    assert any(S.ALBUM_TYPE_TEXT in c for c in click_selectors)
    # 静态表情走 evaluate label 点击：payload 首参是 ["静态表情", True]
    payloads = [c.args[1] for c in page.evaluate.call_args_list if len(c.args) > 1]
    assert any(p and p[0] == "静态表情" for p in payloads)


def test_step_fill_album_info_uses_constants_and_intro(tmp_path):
    ep = make_episode(tmp_path, intro="你好表情")
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    # 选后验证版：fill 带 timeout kwarg；mock input_value 返回非空
    page.locator.return_value.input_value.return_value = "你好表情"
    publisher._step_fill_album_info(page, assets)
    page.fill.assert_any_call(S.ALBUM_NAME_INPUT, "episode_test")
    page.fill.assert_any_call(S.INTRO_TEXTAREA, "你好表情", timeout=5000)


def test_step_fill_copyright_uses_config(tmp_path):
    publisher, session, page = _make_publisher(tmp_path)
    publisher._step_fill_copyright(page)
    page.fill.assert_called_once_with(S.COPYRIGHT_INPUT, publisher.config.copyright)


def test_step_select_categories_clicks_all_constants(tmp_path):
    """2026-08 实测改版：所有选项点可见 label（input 被隐藏），不再用 input 选择器。"""
    publisher, session, page = _make_publisher(tmp_path)
    page.evaluate.return_value = True
    ep = make_episode(tmp_path)
    assets = EpisodeAssets.from_dir(ep)
    publisher._step_select_categories(page, assets)
    payloads = [c.args[1] for c in page.evaluate.call_args_list if len(c.args) > 1]
    texts = [p[0] if isinstance(p, list) else p for p in payloads]
    for expected in ("卡通表情/其他", "软萌可爱", "日常", "万能通用"):
        assert any(t == expected for t in texts), f"应点过 label「{expected}」, 实际: {texts}"
    # 两组地区（全球）走 _click_label_all_unchecked（payload 不是 list）
    assert any(not isinstance(p, list) and p == "全球" for p in payloads)

def _mock_dt(page, word):
    """mock 角色 dt 的 inner_text（选后验证用）。"""
    page.locator.return_value.inner_text.return_value = f"人物角色{word}"


def _picked_word(page):
    """新版 _select_role 通过 get_by_text(exact) 点文本叶子——取其入参。"""
    for c in page.get_by_text.call_args_list:
        if c.args and isinstance(c.args[0], str):
            return c.args[0]
    return None


def test_select_role_single_character_uses_gender_not_compilation(tmp_path):
    """2026-08-29（69 驳回）：单角色男性（捞鱼）→【男人】（评审F1：按性别不按合辑）。"""
    ep = make_episode(tmp_path, contains_laoyu=True, characters=["捞鱼"])
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    _mock_dt(page, S.ROLE_MALE_TITLE)
    publisher._select_role(page, assets)
    assert _picked_word(page) == S.ROLE_MALE_TITLE
    forbidden = S.ROLE_WITH_LAOYU_TITLE.split("(")[0]
    assert _picked_word(page) != forbidden


def test_select_role_single_female_uses_woman(tmp_path):
    """单角色女性（星星布丁）→【女人】。"""
    ep = make_episode(tmp_path, contains_laoyu=False, characters=["星星布丁"])
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    expected = S.ROLE_WITHOUT_LAOYU_TITLE.split("(")[0]
    _mock_dt(page, expected)
    publisher._select_role(page, assets)
    assert _picked_word(page) == expected


def test_select_role_multi_character_uses_compilation(tmp_path):
    """多角色（2 个及以上）→ 人物合辑。"""
    ep = make_episode(tmp_path, contains_laoyu=True,
                      characters=["捞鱼", "星星布丁"])
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    expected = S.ROLE_WITH_LAOYU_TITLE.split("(")[0]
    _mock_dt(page, expected)
    publisher._select_role(page, assets)
    assert _picked_word(page) == expected


def test_select_role_uses_woman_title_when_no_laoyu(tmp_path):
    ep = make_episode(tmp_path, contains_laoyu=False)
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    expected = S.ROLE_WITHOUT_LAOYU_TITLE.split("(")[0]
    _mock_dt(page, expected)
    publisher._select_role(page, assets)
    assert _picked_word(page) == expected


def test_step_tips_fills_thanks_text_and_clicks_accept(tmp_path):
    publisher, session, page = _make_publisher(tmp_path)
    page.evaluate.return_value = True
    # 让 _upload_tip_images 不真跑（避免 mock query 复杂度）
    publisher._upload_tip_images = MagicMock()
    publisher._step_tips(page, EpisodeAssets.from_dir(make_episode(tmp_path)))
    # 接受赞赏走 evaluate label 点击（防 toggle 取消）
    payloads = [c.args[1] for c in page.evaluate.call_args_list if len(c.args) > 1]
    assert any(p and p[0] == "接受赞赏" for p in payloads)
    page.fill.assert_called_once_with(
        S.TIPS_TEXT_INPUT, publisher.config.thanks_text, timeout=3000
    )
    publisher._upload_tip_images.assert_called_once()


def test_step_select_price_prefers_free_label(tmp_path):
    publisher, session, page = _make_publisher(tmp_path)
    page.evaluate.return_value = True
    publisher._step_select_price(page)
    # 改版后点可见 label「免费」（已选跳过）
    payloads = [c.args[1] for c in page.evaluate.call_args_list if len(c.args) > 1]
    assert any(p and p[0] == "免费" and p[1] is True for p in payloads)


def test_step_submit_returns_true_on_success_text(tmp_path):
    publisher, session, page = _make_publisher(tmp_path)
    page.inner_text.return_value = "提交成功，等待审核"
    assert publisher._step_submit(page) is True


def test_step_submit_returns_true_on_auditing_text(tmp_path):
    """提交成功后管理页出现"审核中"（含 home/index URL）→ 成功。"""
    publisher, session, page = _make_publisher(tmp_path)
    page.inner_text.return_value = "表情包审核中"
    page.url = "https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=home/index"
    assert publisher._step_submit(page) is True


def test_step_submit_returns_true_when_url_leaves_form(tmp_path):
    """回到管理首页（home/index）→ 成功。"""
    publisher, session, page = _make_publisher(tmp_path)
    page.inner_text.return_value = "无关文案"
    page.url = "https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=home/index"
    assert publisher._step_submit(page) is True


def test_step_submit_rejects_unknown_url_now(tmp_path):
    """回归守护（修复假提交成功）：不再是"URL 不含 login/readtemplate 就成功"——
    未知 URL（错误页/空白页）不得判成功。"""
    publisher, session, page = _make_publisher(tmp_path)
    page.inner_text.return_value = "无关文案"
    page.url = "https://sticker.weixin.qq.com/some/unknown/page"
    assert publisher._step_submit(page) is False


def test_step_submit_detects_validation_error(tmp_path):
    """表单校验错误（必填提示）→ 明确失败并记录告警。"""
    publisher, session, page = _make_publisher(tmp_path)
    page.inner_text.return_value = "请填写必填项"
    page.url = "https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=form/apply"
    assert publisher._step_submit(page) is False
    assert any("平台校验未通过" in w for w in publisher.warnings)


def test_step_submit_returns_false_when_stuck_on_form(tmp_path):
    publisher, session, page = _make_publisher(tmp_path)
    page.inner_text.return_value = "无关文案"
    page.url = "https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=form/apply"
    assert publisher._step_submit(page) is False


def test_confirm_crop_swallows_failure(tmp_path):
    """裁剪框确定失败（无裁剪框）应静默忽略。"""
    publisher, session, page = _make_publisher(tmp_path)
    page.click.side_effect = Exception("timeout")
    # 不应抛
    publisher._confirm_crop(page)


def test_step_upload_assets_uses_visible_file_inputs(tmp_path):
    """2026-08 改版：横幅/封面/图标按可见 file input 槽位打标上传。"""
    ep = make_episode(tmp_path)
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    page.evaluate.return_value = True

    publisher._step_upload_assets(page, assets)

    # 三张素材各上传一次（打标后 set_input_files('._asset_target', path)）
    calls = [c.args for c in page.set_input_files.call_args_list]
    assert any(c[0] == '._asset_target' and c[1] == str(assets.banner) for c in calls)
    assert any(c[0] == '._asset_target' and c[1] == str(assets.cover) for c in calls)
    assert any(c[0] == '._asset_target' and c[1] == str(assets.icon) for c in calls)


def test_step_upload_assets_only_english_keys(tmp_path):
    """2026-09-02 破案（71-89 全军覆没根因）：主流程传英文键
    only=["banner","cover","icon"]，内部曾用中文标签匹配导致 pairs 被过滤
    成空——素材上传整体空转、零告警。英文键/中文标签都必须生效。"""
    ep = make_episode(tmp_path)
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    page.evaluate.return_value = {"ok": True, "zone": True, "srcs": []}

    publisher._step_upload_assets(page, assets, only=["banner", "icon"])

    calls = [c.args for c in page.set_input_files.call_args_list]
    assert any(c[1] == str(assets.banner) for c in calls)
    assert any(c[1] == str(assets.icon) for c in calls)
    assert not any(c[1] == str(assets.cover) for c in calls)

    # 中文标签同样生效
    page.set_input_files.reset_mock()
    publisher._step_upload_assets(page, assets, only=["封面"])
    calls = [c.args for c in page.set_input_files.call_args_list]
    assert len(calls) == 1 and calls[0][1] == str(assets.cover)


def test_step_upload_assets_retries_when_thumbnail_missing(tmp_path):
    """2026-09-02：槽位级缩略图确认失败（wait_for_function 超时）→ 重传一次；
    两次都失败 → 记两条 warning，不抛异常。"""
    ep = make_episode(tmp_path)
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    page.evaluate.return_value = {"ok": True, "zone": True, "srcs": []}
    page.wait_for_function.side_effect = TimeoutError("wait_for_function: timeout")

    publisher._step_upload_assets(page, assets)

    # 横幅重试：每张素材 set_input_files 2 次（首轮 + 重传）
    calls = [c.args for c in page.set_input_files.call_args_list]
    assert sum(1 for c in calls if c[1] == str(assets.banner)) == 2
    assert any("第 1 次" in w for w in publisher.warnings)
    assert any("均未确认缩略图" in w for w in publisher.warnings)


def test_step_upload_assets_second_attempt_succeeds(tmp_path):
    """重传后缩略图出现 → 不再记「均未确认」告警。"""
    ep = make_episode(tmp_path)
    assets = EpisodeAssets.from_dir(ep)
    publisher, session, page = _make_publisher(tmp_path)
    page.evaluate.return_value = {"ok": True, "zone": True, "srcs": []}
    calls = {"n": 0}

    def _wff(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("first attempt timeout")

    page.wait_for_function.side_effect = _wff

    publisher._step_upload_assets(page, assets)

    assert not any("均未确认缩略图" in w for w in publisher.warnings)
    assert any("第 1 次" in w for w in publisher.warnings)


# ---------------------------------------------------------------------------
# 含义词查重 + 变体词（2026-09-01，56/58 驳回：含义词重复）
# ---------------------------------------------------------------------------


def test_meaning_variant_not_numeric_suffix():
    """变体词用语气词/标点，不用平台明令禁止的 XX1/XX2 数字后缀。"""
    p = Publisher(MagicMock(), MagicMock())
    used = ["来啦"]
    v = p._meaning_variant("来啦", used)
    assert v not in used
    assert v.startswith("来啦")
    assert not v[-1].isdigit()


def test_meaning_variant_skips_existing_words():
    """已有词撞车时逐个后缀往后找，直到不重复。"""
    p = Publisher(MagicMock(), MagicMock())
    used = ["哼", "哼~", "哼！", "哼呢"]
    assert p._meaning_variant("哼", used) not in used


def _make_editor_page(values):
    """mock 编辑器 page：evaluate 直读/直写含义词输入框（模拟 DOM input）。"""
    page = MagicMock()

    def evaluate(script, arg=None):
        if isinstance(arg, list):   # 写格 [idx, word]
            idx, word = arg
            while len(values) < idx:
                values.append("")
            values[idx - 1] = word
            return None
        if isinstance(arg, str):    # 读全部
            return list(values)
        return None

    page.evaluate.side_effect = evaluate
    page.wait_for_timeout = MagicMock()
    return page


def test_fix_meanings_dedupes_after_fill():
    """识图重填后读回查重：重复格自动换变体词，最终全部唯一。"""
    p = Publisher(MagicMock(), MagicMock())
    values = ["来啦", "开心", "来啦", "", "开心"]
    page = _make_editor_page(values)
    # 绕过识图：直接测 _step_fix_meanings_by_vision 的填格+查重段不现实，
    # 这里按同款流程手动驱动 publisher 的公共原语
    for i in range(1, 6):
        p._set_meaning_value(page, i, values[i - 1])
    read = p._read_meanings(page, 5)
    assert read == ["来啦", "开心", "来啦", "", "开心"]
    # 查重（与 _step_fix_meanings_by_vision 内联逻辑同款）
    seen, dup = set(), []
    for i, v in enumerate(read, start=1):
        v = (v or "").strip()
        if v and v in seen:
            dup.append(i)
        seen.add(v)
    used = [v.strip() for v in read if (v or "").strip()]
    for i in dup:
        variant = p._meaning_variant(read[i - 1].strip(), used)
        p._set_meaning_value(page, i, variant)
        used.append(variant)
    final = [v for v in p._read_meanings(page, 5) if v.strip()]
    assert len(final) == len(set(final))            # 无重复
    assert values[2] != "来啦" and values[2].startswith("来啦")
