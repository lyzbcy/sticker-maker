#!/usr/bin/env python3
"""用重抠后的干净图（原图_透明ChromaKey/01.png~16.png）重生 最终版/。

按 _meaning_map.json 的键值映射重命名。会先清空最终版里的 .png（保留子目录和备份）。
"""
import argparse, json, os, shutil
from pathlib import Path
from PIL import Image

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", required=True)
    args = ap.parse_args()
    ep = Path(args.episode)
    chroma_dir = ep / "原图_透明ChromaKey"
    final_dir = ep / "最终版"
    mmap_path = ep / "原图" / "_meaning_map.json"

    if not (chroma_dir.exists() and mmap_path.exists()):
        print(f"❌ 缺少 原图_透明ChromaKey 或 _meaning_map.json: {ep}")
        return

    with open(mmap_path, encoding="utf-8") as f:
        meaning_map = json.load(f)

    final_dir.mkdir(parents=True, exist_ok=True)
    # 清空最终版里的 .png（保留 _isolated_old_dups 等子目录和 .txt）
    removed = 0
    for p in final_dir.glob("*.png"):
        p.unlink()
        removed += 1
    print(f"已清空 最终版/ 里 {removed} 个旧 png")

    print(f"\n{'='*60}\n重生最终版: {ep.name}\n{'='*60}")
    ok = 0
    for i in range(1, 17):
        src = chroma_dir / f"{i:02d}.png"
        if not src.exists():
            print(f"  ⚠️ 缺 {src.name}")
            continue
        meaning = meaning_map.get(str(i), f"表情{i}")
        dst = final_dir / f"{meaning}.png"
        # 转 RGBA 确保 alpha 干净，重存
        im = Image.open(src).convert("RGBA")
        im.save(dst, "PNG")
        print(f"  [{i:02d}] {src.name} → {meaning}.png")
        ok += 1
    print(f"\n✅ 完成 {ok}/16，输出: {final_dir}")

if __name__ == "__main__":
    main()
