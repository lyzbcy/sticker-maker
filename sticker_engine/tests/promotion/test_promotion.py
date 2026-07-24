"""E 推广系统测试：featured + config。"""
from pathlib import Path
from sticker_engine.promotion.featured import list_featured, sample_featured, featured_count
from sticker_engine.promotion.config import PromotionConfig


def test_list_featured_returns_pngs():
    """精选目录有内容（138 张内置）。"""
    featured = list_featured()
    assert len(featured) > 0
    assert all(p.suffix == ".png" for p in featured)


def test_featured_count_is_positive():
    assert featured_count() > 0


def test_sample_featured_returns_subset():
    all_count = featured_count()
    sample = sample_featured(n=8)
    # n 小于总数时返回 n 张；n 大于时返回全部
    assert len(sample) == min(8, all_count)


def test_sample_featured_n_larger_than_total():
    all_count = featured_count()
    sample = sample_featured(n=all_count + 100)
    assert len(sample) == all_count


def test_sample_featured_seed_reproducible():
    """相同 seed 返回相同结果。"""
    s1 = sample_featured(n=5, seed=42)
    s2 = sample_featured(n=5, seed=42)
    assert [p.name for p in s1] == [p.name for p in s2]


def test_promotion_config_defaults_empty():
    cfg = PromotionConfig()
    assert cfg.reward_qr is None
    assert cfg.group_qr is None
    assert cfg.sticker_qr is None
    assert cfg.has_any() is False


def test_promotion_config_has_any():
    cfg = PromotionConfig(reward_qr=Path("/tmp/x.png"))
    assert cfg.has_any() is True


def test_promotion_config_validate_missing(tmp_path):
    cfg = PromotionConfig(reward_qr=tmp_path / "no.png")
    missing = cfg.validate()
    assert "reward" in missing


def test_promotion_config_validate_existing(tmp_path):
    p = tmp_path / "qr.png"
    p.write_bytes(b"x")
    cfg = PromotionConfig(reward_qr=p)
    assert cfg.validate() == []
