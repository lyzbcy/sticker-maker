import numpy as np
from PIL import Image
from sticker_engine.providers.chromakey import ChromaKeyProvider


def _solid(color, size=20):
    img = Image.new("RGB", (size, size), color)
    return img


def test_magenta_detection_pure_magenta_is_key():
    provider = ChromaKeyProvider()
    assert provider._is_key_pixel((255, 0, 255), "#ff00ff") is True


def test_magenta_detection_red_is_not_magenta_key():
    provider = ChromaKeyProvider()
    # 纯红 (255,0,0) 不该被判为洋红 key（hue-guard 保护红衣）
    assert provider._is_key_pixel((255, 0, 0), "#ff00ff") is False


def test_green_detection_pure_green_is_key():
    provider = ChromaKeyProvider()
    assert provider._is_key_pixel((0, 255, 0), "#00ff00") is True


def test_remove_magenta_makes_magenta_area_transparent():
    # 10x10：左半洋红，右半红
    arr = np.zeros((10, 20, 3), dtype=np.uint8)
    arr[:, :10] = (255, 0, 255)   # 洋红
    arr[:, 10:] = (255, 0, 0)     # 红（应保留）
    img = Image.fromarray(arr).convert("RGBA")  # (H,W,3) uint8 → 推断 RGB
    provider = ChromaKeyProvider()
    out = provider.remove_key(img, "#ff00ff")
    out_arr = np.array(out)
    # 左半透明
    assert (out_arr[:5, :5, 3] == 0).all()
    # 右半（红衣）不透明 —— hue-guard 保护
    assert (out_arr[:5, 15:, 3] > 0).all()


def test_auto_select_magenta_then_fallback_green():
    provider = ChromaKeyProvider()
    # 一张洋红底的图，magenta 应该有效
    img = Image.new("RGBA", (20, 20), (255, 0, 255, 255))
    img.putpixel((10, 10), (200, 50, 50, 255))   # 一个红衣像素
    out = provider.remove_key_auto(img)
    assert out.getpixel((0, 0))[3] == 0     # 洋红透明
    assert out.getpixel((10, 10))[3] > 0    # 红衣保留


def test_remove_key_auto_defringes_low_sat_magenta_halo():
    """2026-09-02 复盘（69 单"紫红色边框没有剔除干净"）：

    白描边与洋红底抗锯齿混出的 (255,128,255)（hue=300 但 sat≈0.5<0.85）
    remove_key 判不中 → 成品外圈残留粉紫光环。remove_key_auto 现在接
    remove_fringe：贴着透明区的低饱和洋红族像素要被清掉，白描边核心保留。
    """
    provider = ChromaKeyProvider()
    # 30x30（真实邻接布局：混色光环直接贴着洋红底，外面才是白描边核心）：
    # 左 10 列洋红底，第 10-12 列为抗锯齿混色光环，右侧为白描边/角色
    arr = np.zeros((30, 30, 4), dtype=np.uint8)
    arr[:, :10] = (255, 0, 255, 255)        # 洋红底
    arr[:, 10:13] = (255, 128, 255, 255)    # 低饱和洋红光环（抗锯齿混色）
    arr[:, 13:] = (255, 255, 255, 255)      # 白描边核心/角色
    img = Image.fromarray(arr)
    out = provider.remove_key_auto(img)
    out_arr = np.array(out)
    assert (out_arr[:, :10, 3] == 0).all()          # 洋红底已透明
    # 光环贴着透明区（distance<=3）→ 应被清掉
    assert (out_arr[:, 10:13, 3] == 0).all()
    # 白描边核心（不贴透明区、sat=0）→ 保留
    assert (out_arr[:, 13:, 3] > 0).all()           # 角色侧不受伤


def test_remove_fringe_leaves_inner_pink_alone():
    """不贴透明区的角色内部粉色（hue 330-360° 或远离边缘）不被误伤。"""
    provider = ChromaKeyProvider()
    arr = np.zeros((20, 20, 4), dtype=np.uint8)
    arr[:, :] = (255, 0, 255, 255)                   # 洋红底
    arr[5:15, 5:15] = (255, 200, 210, 255)           # 内部粉脸颊（hue≈349°）
    img = Image.fromarray(arr)
    out = provider.remove_key_auto(img)
    out_arr = np.array(out)
    assert out_arr[10, 10, 3] > 0                    # 粉脸颊完整保留
    assert (out_arr[:, 0, 3] == 0).all()             # 底照常抠掉


def test_vectorized_remove_key_matches_colorsys_baseline():
    """自证：向量化 remove_key 的 key 判定必须和逐像素 _is_key_pixel（colorsys 基准）一致。
    验收红线：Task 13 像素级 A/B 对齐依赖两者一致。"""
    rng = np.random.default_rng(42)
    provider = ChromaKeyProvider()
    # 随机生成 5000 个像素，覆盖洋红族 / 红 / 绿 / 灰 / 暗洋红阴影等
    h, w = 50, 100
    arr = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    # 注入一批洋红族 + 红衣 + 暗洋红边缘像素，确保边界用例有覆盖
    arr[0, 0] = (255, 0, 255)        # 纯洋红
    arr[0, 1] = (255, 0, 0)          # 纯红（红衣）
    arr[0, 2] = (220, 30, 220)       # 略偏暗洋红
    arr[0, 3] = (200, 200, 200)      # 灰（非 key）
    arr[0, 4] = (0, 0, 0)            # 纯黑（mx==0，非 key）
    arr[0, 5] = (255, 150, 255)      # 粉色低 sat（非 key）
    img = Image.fromarray(arr).convert("RGBA")  # (H,W,3) uint8 → 推断 RGB
    for key_color in ("#ff00ff", "#00ff00"):
        out = provider.remove_key(img, key_color)
        out_a = np.array(out)[:, :, 3]
        # 逐像素基准
        expected_transparent = np.zeros((h, w), dtype=bool)
        for y in range(h):
            for x in range(w):
                if provider._is_key_pixel(tuple(int(c) for c in arr[y, x]), key_color):
                    expected_transparent[y, x] = True
        mismatches = (out_a == 0) != expected_transparent
        assert mismatches.sum() == 0, (
            f"key={key_color}: 向量化与 colorsys 基准不一致，{int(mismatches.sum())} 像素不符"
        )
