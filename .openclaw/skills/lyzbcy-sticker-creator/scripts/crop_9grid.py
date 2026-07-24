#!/usr/bin/env python3
"""
九宫格图片裁剪脚本

功能：将九宫格图片裁剪成9张独立的帧图

输入：
    - 九宫格图片路径
    - 输出目录
    - 帧图编号（可选，用于文件夹命名）

输出：
    - 9张裁剪后的帧图

使用方式：
    python crop_9grid.py --input frame.png --output ./帧图/1/
"""

import argparse
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    exit(1)


def crop_9grid(image_path: str, output_dir: str, padding: int = 3):
    """
    将九宫格图片裁剪成9张帧图
    
    Args:
        image_path: 输入图片路径
        output_dir: 输出目录
        padding: 裁剪时留的边距（避免白边）
    """
    # 打开图片
    img = Image.open(image_path)
    width, height = img.size
    
    # 计算每个格子的位置和大小
    # 九宫格: 3x3 布局
    cell_width = width // 3
    cell_height = height // 3
    
    # 裁剪位置（从左到右，从上到下）
    positions = []
    for row in range(3):
        for col in range(3):
            left = col * cell_width + padding
            top = row * cell_height + padding
            right = (col + 1) * cell_width - padding
            bottom = (row + 1) * cell_height - padding
            positions.append((left, top, right, bottom))
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 裁剪并保存
    saved_files = []
    for i, (left, top, right, bottom) in enumerate(positions):
        cropped = img.crop((left, top, right, bottom))
        output_path = os.path.join(output_dir, f"frame_{i+1:02d}.png")
        cropped.save(output_path, "PNG")
        saved_files.append(output_path)
        print(f"已保存: {output_path}")
    
    return saved_files


def main():
    parser = argparse.ArgumentParser(description="九宫格图片裁剪")
    parser.add_argument("--input", "-i", required=True, help="输入九宫格图片路径")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument("--padding", "-p", type=int, default=3, help="裁剪边距（默认3像素）")
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"错误: 找不到文件 {args.input}")
        return 1
    
    # 执行裁剪
    saved_files = crop_9grid(args.input, args.output, args.padding)
    
    print(f"\n✅ 裁剪完成！共保存 {len(saved_files)} 张帧图到 {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
