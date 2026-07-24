#!/usr/bin/env python3
"""
一键发布微信表情包。

目标：
1. 只传表情包目录即可发起发布
2. 自动推导名称和类型
3. 复用 publish.js 的固定流程，减少 AI 参与
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PUBLISH_JS = SCRIPT_DIR / "publish.js"


def detect_type(sticker_dir: Path) -> str:
    final_dir = sticker_dir / "最终版"
    if final_dir.exists() and any(final_dir.glob("*.gif")):
        return "dynamic"
    if any(sticker_dir.glob("*.gif")):
        return "dynamic"
    return "static"


def main():
    parser = argparse.ArgumentParser(description="一键发布微信表情包")
    parser.add_argument("--dir", "-d", required=True, help="表情包目录，如 E:\\星星布丁\\微信表情包\\周三涵做表情7")
    parser.add_argument("--type", choices=["static", "dynamic"], help="表情类型，默认自动检测")
    parser.add_argument("--theme", default="日常交流", help="简介中的主题思想")
    args = parser.parse_args()

    sticker_dir = Path(args.dir).resolve()
    if not sticker_dir.exists():
        print(f"目录不存在: {sticker_dir}")
        return 1

    sticker_type = args.type or detect_type(sticker_dir)
    name = sticker_dir.name

    cmd = [
        "node",
        str(PUBLISH_JS),
        "--name",
        name,
        "--dir",
        str(sticker_dir),
        "--type",
        sticker_type,
        "--theme",
        args.theme,
    ]

    print("=" * 60)
    print("开始一键发布")
    print("=" * 60)
    print(f"目录: {sticker_dir}")
    print(f"名称: {name}")
    print(f"类型: {sticker_type}")
    print(f"主题: {args.theme}")

    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
