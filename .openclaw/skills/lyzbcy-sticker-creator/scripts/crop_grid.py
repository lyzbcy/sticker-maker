#!/usr/bin/env python3
"""
通用宫格图片裁剪脚本

功能：将 N×N 宫格图片裁剪成独立的子图

支持的宫格：
- 2×2（四宫格）：裁剪为4张图，命名 1.png ~ 4.png
- 3×3（九宫格）：裁剪为9张图，命名 frame_01.png ~ frame_09.png
- 4×4（十六宫格）：裁剪为16张图，命名 grid_01.png ~ grid_16.png

使用方式：
    # 四宫格（默认）
    python crop_grid.py --grid 2 --input image.png --output ./原图/ --start 1
    
    # 九宫格
    python crop_grid.py --grid 3 --input frame.png --output ./帧图/1/
    
    # 十六宫格
    python crop_grid.py --grid 4 --input image.png --output ./原图/ --start 1
    
    # 兼容旧命令（自动识别 grid 参数）
    python crop_grid.py --input image.png --output ./原图/ --start 1   # 默认2×2
"""

import argparse
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    exit(1)


def get_default_padding(grid_size):
    """根据宫格大小返回默认边距"""
    if grid_size == 2:
        return 5
    elif grid_size == 3:
        return 3
    elif grid_size == 4:
        return 2
    return 3


def get_file_naming(grid_size, index):
    """
    根据宫格大小和索引返回文件名
    
    2×2 (四宫格): 1.png, 2.png, 3.png, 4.png
    3×3 (九宫格): frame_01.png ~ frame_09.png
    4×4 (十六宫格): grid_01.png ~ grid_16.png
    """
    if grid_size == 2:
        return f"{index + 1}.png"
    elif grid_size == 3:
        return f"frame_{index + 1:02d}.png"
    elif grid_size == 4:
        return f"grid_{index + 1:02d}.png"
    else:
        return f"panel_{index + 1:02d}.png"


def crop_grid(image_path, output_dir, grid_size=2, start_index=1, padding=None, naming='auto'):
    """
    将 N×N 宫格图片裁剪成子图
    
    Args:
        image_path: 输入图片路径
        output_dir: 输出目录
        grid_size: 宫格大小（默认2，即2×2）
        start_index: 文件名起始编号（仅 grid=2 时有效）
        padding: 裁剪边距（None=自动）
        naming: 命名方式 'default'(按编号) | 'meaning'(含义词，仅2×2) | 'auto'(自动)
    
    Returns:
        list: 保存的文件路径列表
    """
    if padding is None:
        padding = get_default_padding(grid_size)
    
    # 打开图片
    img = Image.open(image_path)
    width, height = img.size
    
    print(f'📐 图片尺寸: {width}×{height}, 宫格: {grid_size}×{grid_size}, 边距: {padding}px')
    
    # 计算每个格子的位置和大小
    cell_width = width // grid_size
    cell_height = height // grid_size
    
    # 生成裁剪位置
    positions = []
    for row in range(grid_size):
        for col in range(grid_size):
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
        
        if grid_size == 2:
            # 四宫格使用起始编号
            filename = f"{start_index + i}.png"
        else:
            filename = get_file_naming(grid_size, i)
        
        output_path = os.path.join(output_dir, filename)
        cropped.save(output_path, "PNG")
        saved_files.append(output_path)
        print(f"  ✅ {filename} ({cropped.size[0]}×{cropped.size[1]})")
    
    return saved_files


def main():
    parser = argparse.ArgumentParser(description='通用宫格图片裁剪工具（支持2×2/3×3/4×4）')
    parser.add_argument("--input", "-i", required=True, help="输入宫格图片路径")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument("--grid", "-g", type=int, default=2, choices=[2, 3, 4, 5],
                        help="宫格大小：2=四宫格, 3=九宫格, 4=十六宫格, 5=二十五宫格（默认2）")
    parser.add_argument("--start", "-s", type=int, default=1, help="起始编号（仅 grid=2 时有效，默认1）")
    parser.add_argument("--padding", "-p", type=int, help="裁剪边距（默认：2×2=5px, 3×3=3px, 4×4=2px）")
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"❌ 错误: 找不到文件 {args.input}")
        return 1
    
    # 执行裁剪
    saved_files = crop_grid(
        args.input,
        args.output,
        grid_size=args.grid,
        start_index=args.start,
        padding=args.padding
    )
    
    grid_names = {2: '四宫格(2×2)', 3: '九宫格(3×3)', 4: '十六宫格(4×4)', 5: '二十五宫格(5×5)'}
    print(f"\n✅ {grid_names.get(args.grid, f'{args.grid}×{args.grid}')}裁剪完成！共保存 {len(saved_files)} 张图片到 {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
