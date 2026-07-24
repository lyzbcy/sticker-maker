#!/usr/bin/env python3
"""统计重抠后成品的边缘质量：残留近洋红像素(粉边)、透明率、半透明率。

对比新抠图 vs 备份的旧抠图，逐张输出，确认改善是全量的而非偶然。
"""
import sys, os
from collections import Counter
from pathlib import Path
from PIL import Image

def stats(path):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    total = w * h
    a_hist = Counter(im.getchannel("A").getdata())
    trans = a_hist.get(0, 0)
    partial = sum(v for k, v in a_hist.items() if 0 < k < 255)
    # 残留近洋红(粉边): 不透明且洋红占优的像素
    near_mag = 0
    px = im.load()
    for y in range(h):
        for x in range(w):
            r, g, b, al = px[x, y]
            if al == 0:
                continue
            if min(r, b) - g >= 16 and min(r, b) >= 100:
                near_mag += 1
    return {
        "trans_pct": round(trans * 100 / total, 1),
        "partial_pct": round(partial * 100 / total, 1),
        "near_mag": near_mag,
    }

def report(label, d):
    # 匹配 01.png~16.png（纯数字文件名），排除 grid_*/contact_sheet/test 等
    files = sorted(
        [p for p in d.glob("*.png") if p.stem.isdigit() and 1 <= int(p.stem) <= 16],
        key=lambda p: int(p.stem)
    )
    print(f"\n{'='*70}\n{label}\n  目录: {d}\n  张数: {len(files)}\n{'='*70}")
    print(f"  {'文件':<10} {'透明%':>7} {'半透%':>7} {'残留洋红px':>11}")
    total_mag = 0
    bad = []
    for f in files:
        s = stats(f)
        total_mag += s["near_mag"]
        flag = "  ⚠️" if s["near_mag"] > 100 else ""
        if s["near_mag"] > 100:
            bad.append(f.name)
        print(f"  {f.name:<10} {s['trans_pct']:>7} {s['partial_pct']:>7} {s['near_mag']:>11}{flag}")
    print(f"  {'合计残留洋红':<26} {total_mag:>11}")
    if bad:
        print(f"  ⚠️ 残留较多的: {bad}")
    else:
        print(f"  ✅ 全部清零/极低")
    return total_mag

if __name__ == "__main__":
    base = Path(r"E:\星星布丁\微信表情包")
    # 新抠图
    m19_new = report("19弹 重抠后 (新参数)", base / "周三涵做表情19" / "原图_透明ChromaKey")
    m20_new = report("20弹 重抠后 (新参数)", base / "周三涵做表情20" / "原图_透明ChromaKey")
    # 旧备份对比（取最新的backup）
    def latest_backup(ep):
        bks = sorted((base/ep).glob("原图_透明ChromaKey_backup_*"))
        return bks[-1] if bks else None
    b19 = latest_backup("周三涵做表情19")
    b20 = latest_backup("周三涵做表情20")
    if b19:
        m19_old = report("19弹 旧版 (备份对比)", b19)
        print(f"\n>>> 19弹 残留洋红: 旧 {m19_old}px → 新 {m19_new}px")
    if b20:
        m20_old = report("20弹 旧版 (备份对比)", b20)
        print(f"\n>>> 20弹 残留洋红: 旧 {m20_old}px → 新 {m20_new}px")
