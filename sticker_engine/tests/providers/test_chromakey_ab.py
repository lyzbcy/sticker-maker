"""抠图 A/B 像素级对齐测试（Task 13 验收红线）。

用真实洋红底素材验证：内置 ChromaKeyProvider 的抠图结果，
必须与旧 codex 脚本（remove_chroma_key.py / rechroma_test.py）产出的
透明参考图，在透明通道上差异 < 15%。阈值允许边缘处理细节差异，但主体
抠图区域必须一致——确保新引擎抠图质量不退化于线上脚本。

样本来源：tests/data/ab_chromakey/{src_NN.png, ref_NN.png}，按同名配对。
src = 带洋红底的原图；ref = 旧脚本抠图后的透明图。两者必须是同一张图。
"""
import numpy as np
from PIL import Image
from pathlib import Path
import pytest
from sticker_engine.providers.chromakey import ChromaKeyProvider

DATA = Path(__file__).parent.parent / "data" / "ab_chromakey"

# 验收红线阈值：透明通道差异 < 15%。
# 实测 5 组真实样本 diff 在 0.86% ~ 9.94% 之间（主体几乎完全一致，
# 差异集中在洋红/红衣边缘的半透明羽化处理）。15% 是宽松上限，
# 既能捕捉真正的抠图回归（背景没抠干净 / 红衣被误抠），又允许边缘细节差异。
THRESHOLD = 0.15


def _diff_pct(a: Image.Image, b: Image.Image) -> float:
    """两张 RGBA 图透明通道差异比例（0=完全一致，1=完全相反）。

    只比透明位（a==0）而非完整 alpha 值：旧脚本可能用羽化/二值化等
    不同方式处理边缘 alpha 值，逐值比较会被这些细节噪声主导；
    而透明/不透明二分对比能稳定反映主体抠图区域是否一致。
    """
    if a.size != b.size:
        a = a.resize(b.size)
    aa = np.array(a.convert("RGBA"))
    bb = np.array(b.convert("RGBA"))
    a_trans = aa[:, :, 3] == 0
    b_trans = bb[:, :, 3] == 0
    diff = (a_trans != b_trans).sum() / (aa.shape[0] * aa.shape[1])
    return float(diff)


@pytest.mark.skipif(not DATA.exists() or not list(DATA.glob("src_*")),
                    reason="无 A/B 样本数据")
@pytest.mark.parametrize("sample", sorted(DATA.glob("src_*")))
def test_chromakey_matches_reference_within_threshold(sample):
    provider = ChromaKeyProvider()
    src = Image.open(sample).convert("RGBA")
    ref_name = sample.name.replace("src_", "ref_")
    ref = Image.open(DATA / ref_name).convert("RGBA")
    result = provider.remove_key(src, "#ff00ff")
    diff = _diff_pct(result, ref)
    assert diff < THRESHOLD, (
        f"{sample.name} 抠图与参考差异 {diff:.1%} 超过 {THRESHOLD:.0%} 阈值"
    )
