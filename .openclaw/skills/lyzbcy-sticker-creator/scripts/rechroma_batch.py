#!/usr/bin/env python3
"""用 config.yaml 的新 chroma_key 参数批量重新抠图。

把 原图/_panels(或原图/grid_NN) 的源图重新抠到 原图_透明ChromaKey/。
参数：soft-matte + transparent_threshold=150 + opaque_threshold=155 + edge-contract 1
（对齐 config.yaml chroma_key 节，外部 remove_chroma_key.py 实现）。

用法：
  python rechroma_batch.py --episode "E:\\...\\周三涵做表情19"
  python rechroma_batch.py --episode "..." --src-subdir _panels --prefix panel_
"""
import argparse, subprocess, os, sys, glob
from pathlib import Path

SCRIPT = os.path.expanduser("~/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py")
KEY = "#ff00ff"
PARAMS = "--auto-key none --soft-matte --transparent-threshold 150 --opaque-threshold 155 --edge-contract 1"

def rechroma_one(inp, out):
    cmd = f'python "{SCRIPT}" --input "{inp}" --out "{out}" --key-color {KEY} --force {PARAMS}'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    ok = r.returncode == 0
    if not ok:
        print(f"  ❌ {os.path.basename(inp)}: {r.stderr.strip()[:200]}")
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", required=True, help="弹次目录绝对路径")
    args = ap.parse_args()
    ep = Path(args.episode)
    src_dir = ep / "原图" / "_panels"
    # 19弹: 原图/_panels/panel_NN.png ; 20弹: 原图/grid_NN.png
    if not src_dir.exists():
        src_dir = ep / "原图"
    out_dir = ep / "原图_透明ChromaKey"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 只取 panel_NN.png 或 grid_NN.png（排除 grid_4x4/contact_sheet/test等杂图）
    panels = sorted(
        [p for p in src_dir.glob("*.png")
         if p.stem.startswith(("panel_", "grid_")) and p.stem[6:8].isdigit()],
        key=lambda p: int(''.join(filter(str.isdigit, p.stem)))
    )
    if not panels:
        print(f"❌ 未在 {src_dir} 找到 panel_/grid_ 源图")
        sys.exit(1)

    print(f"{'='*60}\n重抠图: {ep.name}\n  源: {src_dir}\n  输出: {out_dir}\n  共 {len(panels)} 张\n  参数: {PARAMS}\n{'='*60}")
    ok = 0
    for i, p in enumerate(panels, 1):
        # 统一输出为 01.png ~ 16.png（与 _meaning_map.json 键一致）
        num = int(''.join(filter(str.isdigit, p.stem)))
        out = out_dir / f"{num:02d}.png"
        if rechroma_one(str(p), str(out)):
            print(f"  [{i}/{len(panels)}] ✅ {p.name} → {out.name}")
            ok += 1
    print(f"\n{'='*60}\n完成: {ok}/{len(panels)} 张成功\n{'='*60}")

if __name__ == "__main__":
    main()
