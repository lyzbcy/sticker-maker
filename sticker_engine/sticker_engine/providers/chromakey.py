"""内置洋红/绿色抠图 provider（决策 H1）。

移植自现有 rechroma_test.py / remove_chroma_key.py 验证过的 hue-guard 算法。
**验收红线**：Task 13 会用真实素材做像素级 A/B 对齐测试（差异 <15%），
所以本模块的 key 判据必须和旧脚本 `_is_magenta_key` 一致：
    dh = min(|hue-300|, 360-|hue-300|) ≤ 20  且  s ≥ 0.85
（相对洋红 300°）。绿色 key 同构（相对 120°，容差 60）。

hue-guard 保护红衣的本质（数学保证，非额外逻辑）：
纯红 (255,0,0) 的 HSV hue=0°，相对洋红 300° 的 Δh=60° > 20，
所以天然不是洋红 key —— 红衣/肤色不会被抠掉。
"""
import colorsys
from typing import Tuple

import numpy as np
from PIL import Image


# 旧脚本 remove_chroma_key.py / rechroma_test.py 的判据常量（务必精确对齐）
_HUE_TOL_MAGENTA = 20.0   # 洋红 key hue 容差（相对 300°）
_HUE_TOL_GREEN = 60.0     # 绿色 key hue 容差（相对 120°）
_SAT_MIN = 0.85           # 饱和度下限
_MAGENTA_HUE = 300.0
_GREEN_HUE = 120.0


class ChromaKeyProvider:
    """
    内置洋红/绿色抠图（决策 H1）。

    - 洋红 key: HSV hue≈300°, Δh≤20, s≥0.85
    - 绿色 key: hue≈120°, Δh≤60, s≥0.85
    - 纯红(hue=0°)的 Δh 相对 300° = 60° > 20，天然不被当洋红 key → hue-guard 保护红衣

    洋红优先；冲突（角色偏洋红/偏红）回退绿色（决策 E1）。
    """

    HUE_TOL_MAGENTA = _HUE_TOL_MAGENTA
    HUE_TOL_GREEN = _HUE_TOL_GREEN
    SAT_MIN = _SAT_MIN

    # ------------------------------------------------------------------ #
    # 逐像素判定（colorsys 基准，绝对正确）
    # ------------------------------------------------------------------ #
    def _is_key_pixel(self, rgb: Tuple[int, int, int], key_color: str) -> bool:
        """单像素 key 判定。用 colorsys 精确换算 HSV，与旧脚本 _is_magenta_key 对齐。

        与 rechroma_test.py 的实现完全一致：mx==0 直接返回 False（避免除零）。
        """
        r8, g8, b8 = rgb
        r, g, b = r8 / 255.0, g8 / 255.0, b8 / 255.0
        mx = max(r, g, b)
        if mx == 0.0:
            return False
        h, s, _ = colorsys.rgb_to_hsv(r, g, b)
        hue_deg = h * 360.0
        kc = key_color.lower()
        if kc == "#ff00ff":
            dh = min(abs(hue_deg - _MAGENTA_HUE), 360.0 - abs(hue_deg - _MAGENTA_HUE))
            return dh <= self.HUE_TOL_MAGENTA and s >= self.SAT_MIN
        elif kc == "#00ff00":
            dh = min(abs(hue_deg - _GREEN_HUE), 360.0 - abs(hue_deg - _GREEN_HUE))
            return dh <= self.HUE_TOL_GREEN and s >= self.SAT_MIN
        return False

    # ------------------------------------------------------------------ #
    # 向量化抠图（性能路径，判定须与 _is_key_pixel 一致）
    # ------------------------------------------------------------------ #
    def remove_key(self, img: Image.Image, key_color: str) -> Image.Image:
        """对单张 RGBA 图抠掉 key 色，返回 RGBA。向量化实现（不逐像素 loop）。

        hue/sat 的计算路径刻意对齐 colorsys.rgb_to_hsv 的算术
        （h = (raw/6.0) % 1.0 → hue_deg = h*360；s = delta/maxc），
        以保证与 _is_key_pixel 的逐像素判定一致。
        """
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        arr = np.array(img)  # (H, W, 4) uint8
        rgb = arr[:, :, :3].astype(np.float64)
        a = arr[:, :, 3].copy()

        r = rgb[:, :, 0] / 255.0
        g = rgb[:, :, 1] / 255.0
        b = rgb[:, :, 2] / 255.0

        mx = np.maximum(np.maximum(r, g), b)
        mn = np.minimum(np.minimum(r, g), b)
        delta = mx - mn  # ≥0

        # --- 饱和度：s = delta / mx（mx==0 → s=0，非 key）---
        sat = np.zeros_like(mx)
        nz = mx > 0
        sat[nz] = delta[nz] / mx[nz]

        # --- 色相（对齐 colorsys 内部算术）---
        # colorsys: maxc==r → h = bc - gc；maxc==g → 2 + rc - bc；maxc==b → 4 + gc - rc
        # 其中 rc=(maxc-r)/delta, gc=(maxc-g)/delta, bc=(maxc-b)/delta
        # 最后 h = (raw_h / 6.0) % 1.0，hue_deg = h * 360
        hue_deg = np.zeros_like(mx)
        has_delta = delta > 0
        with np.errstate(divide="ignore", invalid="ignore"):
            rc = (mx - r) / delta
            gc = (mx - g) / delta
            bc = (mx - b) / delta
            # 优先级 r > g > b（与 colorsys 的 if/elif 一致，处理并列最大值）
            mask_r = has_delta & (mx == r)
            mask_g = has_delta & (mx == g) & ~mask_r
            mask_b = has_delta & (mx == b) & ~(mask_r | mask_g)
            raw_h = np.zeros_like(mx)
            raw_h[mask_r] = (bc - gc)[mask_r]
            raw_h[mask_g] = (2.0 + rc - bc)[mask_g]
            raw_h[mask_b] = (4.0 + gc - rc)[mask_b]
            h_unit = (raw_h / 6.0) % 1.0
            hue_deg = h_unit * 360.0

        # --- key 判定 ---
        kc = key_color.lower()
        if kc == "#ff00ff":
            dh = np.minimum(
                np.abs(hue_deg - _MAGENTA_HUE),
                360.0 - np.abs(hue_deg - _MAGENTA_HUE),
            )
            is_key = (dh <= self.HUE_TOL_MAGENTA) & (sat >= self.SAT_MIN)
        elif kc == "#00ff00":
            dh = np.minimum(
                np.abs(hue_deg - _GREEN_HUE),
                360.0 - np.abs(hue_deg - _GREEN_HUE),
            )
            is_key = (dh <= self.HUE_TOL_GREEN) & (sat >= self.SAT_MIN)
        else:
            is_key = np.zeros_like(mx, dtype=bool)

        a[is_key] = 0

        out = arr.copy()
        out[:, :, 3] = a
        return Image.fromarray(out)  # RGBA uint8 → 推断模式

    # ------------------------------------------------------------------ #
    # 去色边（defringe，2026-09-02 评分复盘：69 单"紫红色边框没有剔除干净"）
    # ------------------------------------------------------------------ #
    def remove_fringe(self, img: Image.Image, key_color: str = "#ff00ff",
                      hue_tol: float = 25.0, sat_min: float = 0.05,
                      radius: int = 3) -> Image.Image:
        """清掉白描边与 key 底抗锯齿混出的低饱和 key 色光环。

        根因：prompt 要求白描边 + 洋红底，两者边缘的混色（如 255,128,255）
        hue 仍在 300° 但饱和度 ~0.5 < SAT_MIN(0.85)，remove_key 判不中，
        成品贴纸轮廓外挂一圈剔不掉的粉紫边（用户原话"边框本身就有颜色，
        和洋红一叠加……只剔除了洋红色，这个叠加色就剔除不了"）。
        对策：只把「已透明区域向外 radius 圈内」的 key 色族像素清透明
        （放宽饱和度下限到 sat_min，纯白/纯灰 sat≈0 仍安全），不贴边的
        角色粉色（hue 多在 330-360°，不在洋红 ±25° 内）不受影响。
        remove_key 判据本身不动（A/B 对齐验收红线）。
        """
        import numpy as np
        from scipy import ndimage
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        arr = np.array(img)
        trans = arr[:, :, 3] == 0
        if not trans.any():
            return img
        rgb = arr[:, :, :3].astype(np.float64)
        r = rgb[:, :, 0] / 255.0
        g = rgb[:, :, 1] / 255.0
        b = rgb[:, :, 2] / 255.0
        mx = np.maximum(np.maximum(r, g), b)
        mn = np.minimum(np.minimum(r, g), b)
        delta = mx - mn
        sat = np.zeros_like(mx)
        nz = mx > 0
        sat[nz] = delta[nz] / mx[nz]
        hue_deg = np.zeros_like(mx)
        has_delta = delta > 0
        with np.errstate(divide="ignore", invalid="ignore"):
            rc = (mx - r) / delta
            gc = (mx - g) / delta
            bc = (mx - b) / delta
            mask_r = has_delta & (mx == r)
            mask_g = has_delta & (mx == g) & ~mask_r
            mask_b = has_delta & (mx == b) & ~(mask_r | mask_g)
            raw_h = np.zeros_like(mx)
            raw_h[mask_r] = (bc - gc)[mask_r]
            raw_h[mask_g] = (2.0 + rc - bc)[mask_g]
            raw_h[mask_b] = (4.0 + gc - rc)[mask_b]
            hue_deg = ((raw_h / 6.0) % 1.0) * 360.0
        kc = key_color.lower()
        if kc == "#00ff00":
            center, tol = _GREEN_HUE, 60.0
        else:
            center, tol = _MAGENTA_HUE, hue_tol
        dh = np.minimum(np.abs(hue_deg - center),
                        360.0 - np.abs(hue_deg - center))
        family = (dh <= tol) & (sat >= sat_min)
        near = ndimage.binary_dilation(trans, iterations=radius)
        kill = family & near & ~trans
        if not kill.any():
            return img
        out_arr = arr.copy()
        out_arr[kill] = (0, 0, 0, 0)
        return Image.fromarray(out_arr)

    # ------------------------------------------------------------------ #
    # 自动选 key（洋红优先；冲突回退绿色，决策 E1）+ 去色边收尾
    # ------------------------------------------------------------------ #
    def remove_key_auto(self, img: Image.Image) -> Image.Image:
        """洋红优先；如果洋红 key 几乎抠不掉任何东西（说明背景其实不是洋红，
        很可能是绿色），回退到绿色 key（决策 E1）。抠完接 remove_fringe
        清理描边混色光环（2026-09-02 复盘：紫红边框残留）。

        启发式：洋红抠图后透明占比 < 1%（背景不是洋红）→ 改用绿色重抠。
        阈值取 1% 而非 0%，是为了容忍极小尺寸/单像素图的数值边界。
        """
        out_mag = self.remove_key(img, "#ff00ff")
        arr = np.array(out_mag)
        total = arr.shape[0] * arr.shape[1]
        trans_pct = int((arr[:, :, 3] == 0).sum()) / total
        if trans_pct < 0.01:
            return self.remove_fringe(self.remove_key(img, "#00ff00"),
                                      "#00ff00")
        return self.remove_fringe(out_mag, "#ff00ff")
