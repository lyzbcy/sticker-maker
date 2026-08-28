"""推广配置测试：个人推广页新增链接字段。"""
from sticker_engine.promotion.config import PromotionConfig


def test_promotion_defaults_include_profile_links():
    c = PromotionConfig()
    assert c.studio_name == "捞鱼工作室"
    assert c.homepage_url.startswith("https://")
    assert c.avatar_url.startswith("https://")
    assert "github.com" in c.repo_url
    assert "discussions" in c.discussions_url


def test_promotion_json_override_survives():
    # load_promotion 用 dict.update 合并用户 promotion.json，新字段可被覆盖
    data = {
        "reward_qr": str(PromotionConfig().reward_qr),
        "group_qr": str(PromotionConfig().group_qr),
        "sticker_qr": str(PromotionConfig().sticker_qr),
        "author_name": PromotionConfig().author_name,
        "studio_name": PromotionConfig().studio_name,
        "homepage_url": PromotionConfig().homepage_url,
        "avatar_url": PromotionConfig().avatar_url,
        "repo_url": PromotionConfig().repo_url,
        "discussions_url": PromotionConfig().discussions_url,
    }
    override = {"homepage_url": "https://example.com/"}
    merged = {**data, **override}
    assert merged["homepage_url"] == "https://example.com/"
    assert merged["repo_url"] == data["repo_url"]
