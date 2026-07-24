#!/usr/bin/env python3
"""生成后含义预检：把 4 组四宫格裁成 16 个 panel，拼成大图供识图AI核对+命名。

定位：生图模块1完成之后、裁剪到 原图/ 单图之前。
产物：
  - 原图/_panels/panel_NN.png  （16 张单 panel，按 #1-#16 编号）
  - 原图/_contact_sheet.png    （4×4 大图，带编号标注）
  - 原图/_meaning_map.json     （{编号: 2-4字含义}，供后续 finalize 消费）

工作流：
  1. 本脚本生成 _contact_sheet.png 并打印识图 prompt
  2. 调用方（AI/人）用识图AI 核对大图，拿到 16 个含义
  3. 把含义写入 _meaning_map.json（可用 --set 一次性写入，或手动编辑）
  4. 后续裁剪/抠图/重命名步骤读 _meaning_map.json

注意：本脚本不动 quad 原图，也不重命名。只产出供后续消费的中间产物。
"""

import argparse
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)


def crop_quads_to_panels(raw_dir, panels_dir, grid=4):
    """把单张 4×4 十六宫格图裁成 16 个 panel，编号 #1-#16（从左到右、从上到下）。"""
    os.makedirs(panels_dir, exist_ok=True)
    panels = []  # [(编号, 路径)]
    grid_path = os.path.join(raw_dir, "grid_4x4.png")
    if not os.path.exists(grid_path):
        print(f"  ❌ 缺少 {grid_path}")
        return panels

    img = Image.open(grid_path)
    w, h = img.size
    cw, ch = w // grid, h // grid
    pad = 3
    idx = 1
    for row in range(grid):
        for col in range(grid):
            box = (col * cw + pad, row * ch + pad,
                   (col + 1) * cw - pad, (row + 1) * ch - pad)
            panel = img.crop(box)
            outp = os.path.join(panels_dir, f"panel_{idx:02d}.png")
            panel.save(outp, "PNG")
            panels.append((idx, outp))
            idx += 1
    return panels


def build_contact_sheet(panels, out_path, cell=280):
    """把 16 个 panel 拼成 4×4 大图，带 #编号标注。"""
    cols, rows = 4, 4
    labelh = 26
    W = cols * cell
    H = rows * (cell + labelh) + 6
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for idx, p in panels:
        r = (idx - 1) // cols
        c = (idx - 1) % cols
        im = Image.open(p).convert("RGB").resize((cell, cell))
        x = c * cell
        y = r * (cell + labelh) + labelh
        sheet.paste(im, (x, y))
        draw.text((x + 4, r * (cell + labelh) + 2),
                  f"#{idx}", fill=(200, 0, 0))
    sheet.save(out_path)
    return out_path


# 识图AI 要用的 prompt 模板（打印给调用方，由 AI/人复制使用）
VISION_PROMPT_TEMPLATE = """这是一张 4x4 贴纸表，共16个panel，编号 #1 到 #16（从左到右、从上到下）。
每个 panel 对应一张参考图的表情。

请完成两件事：
1. 对每个 panel 输出一个 2-4 字的中文含义（描述角色在做什么/什么情绪），要适合做微信表情包名。
2. 检查重复：如果某些 panel 表情明显雷同，在"重复告警"里列出。

请严格用下面的 JSON 格式输出（不要其它内容）：
{
  "meanings": {"1": "含义", "2": "含义", ..., "16": "含义"},
  "重复告警": ["#X 与 #Y 疑似重复(都是...)", "..."]
}
"""


def write_meaning_map(meaning_map, out_path):
    """把 {编号: 含义} 写入 _meaning_map.json。"""
    normalized = {str(k): v for k, v in meaning_map.items()}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="生成后含义预检：拼大图 + 产 meaning_map")
    parser.add_argument("--dir", required=True, help="弹次目录")
    parser.add_argument("--set", dest="meanings_json", default=None,
                        help="直接写入 _meaning_map.json，传入 JSON 字符串 {编号: 含义}")
    parser.add_argument("--check-only", action="store_true",
                        help="只生成大图+打印 prompt，不要求 meanings")
    args = parser.parse_args()

    raw_dir = os.path.join(args.dir, "原图")
    panels_dir = os.path.join(raw_dir, "_panels")
    sheet_path = os.path.join(raw_dir, "_contact_sheet.png")
    map_path = os.path.join(raw_dir, "_meaning_map.json")

    # --set 模式：直接写含义图，跳过拼图
    if args.meanings_json:
        meaning_map = json.loads(args.meanings_json)
        write_meaning_map(meaning_map, map_path)
        print(f"✅ 已写入 {map_path} ({len(meaning_map)} 个含义)")
        # 记录生产日志（结构化：含义词 + 命名风格入复盘记录）
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from production_log import log_step_rich
            meanings_list = [meaning_map[str(i)] for i in range(1, len(meaning_map) + 1)
                             if str(i) in meaning_map]
            dup_count = len(meanings_list) - len(set(meanings_list))
            log_step_rich(args.dir, "含义预检",
                          "OK" if dup_count == 0 else "WARN",
                          step_data={"meanings": meanings_list,
                                     "vision_check": {"method": "识图AI/人工"}},
                          details=f"含义命名完成，{len(meaning_map)} 个" +
                                  (f"，⚠️ 有{dup_count}个重名" if dup_count else ""))
        except Exception as e:
            print(f"  ⚠️ 生产日志写入失败: {e}")
        return

    # 默认：裁 panel + 拼大图 + 打印 prompt
    print("=" * 60)
    print("🔍 含义预检：裁 panel + 拼大图")
    print("=" * 60)

    panels = crop_quads_to_panels(raw_dir, panels_dir)
    if not panels:
        print(f"❌ 未找到十六宫格原图: {raw_dir}/grid_4x4.png")
        return

    build_contact_sheet(panels, sheet_path)
    print(f"✅ 裁出 {len(panels)} 个 panel 到 _panels/")
    print(f"✅ 拼图已保存: {sheet_path}")
    print()
    print("📋 请把以下大图交给识图AI核对：")
    print(f"   文件: {sheet_path}")
    print()
    print("📋 识图 prompt（复制给识图AI）：")
    print("-" * 60)
    print(VISION_PROMPT_TEMPLATE)
    print("-" * 60)
    print()
    print("拿到 AI 返回的 JSON 后，用以下命令写入 meaning_map：")
    print(f'   python check_and_rename.py --dir "{args.dir}" '
          f'--set \'{{"1":"含义","2":"含义",...}}\'')
    print()
    print("或人工编辑：")
    print(f"   {map_path}")


if __name__ == "__main__":
    main()
