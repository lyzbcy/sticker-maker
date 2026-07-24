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
    img = Image.fromarray(arr, "RGB").convert("RGBA")
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
    img = Image.fromarray(arr, "RGB").convert("RGBA")
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
