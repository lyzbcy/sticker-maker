#!/usr/bin/env python3
"""A/B 测试：对比旧硬阈值抠图 vs config 新参数抠图，以及 hue-guard 红衣保护开关。

对单张图分别用不同参数抠图，统计：
- 全透明像素比例（阴影区被抠掉 → 比例升高）
- 半透明像素比例（边缘过渡）
- 残留的"接近洋红"像素数（粉边指标）
- 红衣误伤率（被抠透明但 HSV 不属于洋红的像素 = 角色/衣服被误删）

hue-guard 验证：对比 --no-hue-guard（旧行为，红衣被误抠）vs 默认（hue-guard 开，红衣应保留）。
"""
import subprocess, sys, os, colorsys
from collections import Counter
from PIL import Image
import numpy as np

SCRIPT = os.path.expanduser("~/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py")
KEY = "#ff00ff"


def run_chroma(inp, out, params):
    cmd = f'python "{SCRIPT}" --input "{inp}" --out "{out}" --key-color {KEY} --force {params}'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ❌ {r.stderr.strip()}")
        return False
    return True


def _is_magenta_key(r, g, b, hue_tol=20.0, sat_min=0.85):
    """判定像素 HSV 是否属于洋红 key 族（与 remove_chroma_key.py 的 _is_magenta_key 对齐）。"""
    mx = max(r, g, b)
    if mx == 0:
        return False
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue_deg = h * 360.0
    dh = min(abs(hue_deg - 300.0), 360.0 - abs(hue_deg - 300.0))
    return dh <= hue_tol and s >= sat_min


def stats(path, src_path=None):
    """统计抠图结果。若提供 src_path（带洋红背景的源图），额外算红衣误伤率。

    红衣误伤 = 抠图后 alpha=0，但源图该像素 HSV 不属于洋红（dH300>20 或 S<0.85）。
    这些是被误删的前景（红衣/肤色），越少越好。
    """
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    total = w * h
    a = Counter(im.getchannel("A").getdata())
    trans = a.get(0, 0)
    partial = sum(v for k, v in a.items() if 0 < k < 255)
    near_magenta = 0
    px = im.load()
    for y in range(h):
        for x in range(w):
            r, g, b, al = px[x, y]
            if al == 0:
                continue
            # 洋红偏暗阴影: R/B 高 G 低, dominance>=16
            if min(r, b) - g >= 16 and min(r, b) >= 100:
                near_magenta += 1
    result = {
        "trans_pct": round(trans * 100 / total, 2),
        "partial_pct": round(partial * 100 / total, 2),
        "near_magenta": near_magenta,
    }
    # 红衣误伤率（需要源图对照）
    if src_path and os.path.exists(src_path):
        src = np.array(Image.open(src_path).convert("RGBA"))
        chroma = np.array(im)
        alpha = chroma[:, :, 3]
        rgb = src[:, :, :3].astype(int)
        # 被抠成透明 但源图该像素不是洋红 key → 误伤
        cut = (alpha == 0)
        # 向量化计算是否洋红
        is_mag = np.zeros(rgb.shape[:2], dtype=bool)
        h_arr, s_arr, _ = np.vectorize(lambda r, g, b: colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0))(
            rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2])
        hue_deg = h_arr * 360.0
        dh = np.minimum(np.abs(hue_deg - 300.0), 360.0 - np.abs(hue_deg - 300.0))
        is_mag = (dh <= 20.0) & (s_arr >= 0.85)
        misprotect = cut & (~is_mag)
        result["misprotect_pct"] = round(misprotect.sum() * 100 / total, 2)
    return result


def hue_guard_test(img_path, label):
    """对比 --no-hue-guard（旧行为）vs 默认 hue-guard 开（新行为）。"""
    print(f"\n{'='*60}\nHSV hue-guard 对比: {label}\n  源图: {img_path}\n{'='*60}")
    base = os.path.dirname(img_path)
    name = os.path.splitext(os.path.basename(img_path))[0]
    out_off = os.path.join(base, f"_test_{name}_GUARD_OFF.png")
    out_on = os.path.join(base, f"_test_{name}_GUARD_ON.png")
    common = "--auto-key none --soft-matte --transparent-threshold 150 --opaque-threshold 155 --edge-contract 1"

    print("\n[OFF] --no-hue-guard (旧行为,红衣会被误抠):")
    run_chroma(img_path, out_off, f"{common} --no-hue-guard")
    s_off = stats(out_off, img_path)
    print(f"    透明={s_off['trans_pct']}%  红衣误伤={s_off.get('misprotect_pct','N/A')}%  近洋红残留={s_off['near_magenta']}px")

    print("\n[ON] hue-guard 默认开 (新行为,红衣应保留):")
    run_chroma(img_path, out_on, f"{common}")
    s_on = stats(out_on, img_path)
    print(f"    透明={s_on['trans_pct']}%  红衣误伤={s_on.get('misprotect_pct','N/A')}%  近洋红残留={s_on['near_magenta']}px")

    mp_off = s_off.get("misprotect_pct", 0)
    mp_on = s_on.get("misprotect_pct", 0)
    print(f"\n对比:")
    print(f"  红衣误伤率: {mp_off}% → {mp_on}%  ({'✅改善' if mp_on < mp_off else '⚠️注意'})")
    print(f"  透明像素:   {s_off['trans_pct']}% → {s_on['trans_pct']}%")
    print(f"  粉边残留:   {s_off['near_magenta']}px → {s_on['near_magenta']}px  ({'✅' if s_on['near_magenta'] < s_off['near_magenta'] * 3 else '⚠️'})")
    print(f"  OFF图: {out_off}")
    print(f"  ON图:  {out_on}")
    return s_off, s_on


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="chroma-key 抠图质量 A/B 测试（含 hue-guard 红衣保护对照）")
    ap.add_argument("--hue-guard", action="store_true", help="只跑 hue-guard OFF vs ON 对照")
    ap.add_argument("--image", help="指定单张图测试（默认跑预设对照集）")
    args = ap.parse_args()

    # 预设对照测试集：红衣图（应低误伤）+ 正常图（应零退化）
    testset = [
        (r"E:\星星布丁\微信表情包\周三涵做表情32\原图\grid_15.png", "32弹 全红了(红衣-重点)"),
        (r"E:\星星布丁\微信表情包\周三涵做表情41\原图\_panels\panel_15.png", "41弹 全红了(红衣-重点)"),
        (r"E:\星星布丁\微信表情包\周三涵做表情36\原图\_panels\panel_01.png", "36弹 panel01(正常对照)"),
        (r"E:\星星布丁\微信表情包\周三涵做表情37\原图\_panels\panel_01.png", "37弹 panel01(正常对照)"),
    ]
    if args.image:
        testset = [(args.image, "自定义图")]

    for p, lbl in testset:
        if not os.path.exists(p):
            print(f"⚠️ 不存在: {p}")
            continue
        if args.hue_guard:
            hue_guard_test(p, lbl)
        else:
            # 默认两种都跑
            off, on = hue_guard_test(p, lbl)
