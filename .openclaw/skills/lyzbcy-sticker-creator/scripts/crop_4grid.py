#!/usr/bin/env python3
"""
四宫格图片裁剪脚本

功能：将四宫格图片裁剪成4张独立的小图

输入：
    - 四宫格图片路径
    - 输出目录
    - 起始编号（可选，默认1）

输出：
    - 4张裁剪后的小图

使用方式：
    python crop_4grid.py --input image.png --output ./原图/ --start 1
"""

import argparse
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    exit(1)


def crop_4grid(image_path: str, output_dir: str, start_index: int = 1, padding: int = 5):
    """
    将四宫格图片裁剪成4张小图
    
    Args:
        image_path: 输入图片路径
        output_dir: 输出目录
        start_index: 起始编号
        padding: 裁剪时留的边距（避免白边）
    """
    # 打开图片
    img = Image.open(image_path)
    width, height = img.size
    
    # 计算每个格子的位置和大小
    # 四宫格: 2x2 布局
    cell_width = width // 2
    cell_height = height // 2
    
    # 裁剪位置（加入padding避免白边）
    positions = [
        (padding, padding, cell_width - padding, cell_height - padding),  # 左上
        (cell_width + padding, padding, width - padding, cell_height - padding),  # 右上
        (padding, cell_height + padding, cell_width - padding, height - padding),  # 左下
        (cell_width + padding, cell_height + padding, width - padding, height - padding),  # 右下
    ]
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 裁剪并保存
    saved_files = []
    for i, (left, top, right, bottom) in enumerate(positions):
        cropped = img.crop((left, top, right, bottom))
        output_path = os.path.join(output_dir, f"{start_index + i}.png")
        cropped.save(output_path, "PNG")
        saved_files.append(output_path)
        print(f"已保存: {output_path}")
    
    return saved_files


def main():
    parser = argparse.ArgumentParser(description="四宫格图片裁剪")
    parser.add_argument("--input", "-i", required=True, help="输入四宫格图片路径")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument("--start", "-s", type=int, default=1, help="起始编号（默认1）")
    parser.add_argument("--padding", "-p", type=int, default=5, help="裁剪边距（默认5像素）")
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"错误: 找不到文件 {args.input}")
        return 1
    
    # 执行裁剪
    saved_files = crop_4grid(args.input, args.output, args.start, args.padding)
    
    print(f"\n✅ 裁剪完成！共保存 {len(saved_files)} 张图片到 {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
