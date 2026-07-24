#!/usr/bin/env python3
"""
微信表情包批量处理工具

功能：
1. 批量裁剪四宫格图片
2. 批量裁剪九宫格帧图
3. 批量生成GIF

使用方式：
    python utils.py --command batch-crop --input-dir ./输入/ --output-dir ./输出/
"""

import argparse
import os
import glob
from pathlib import Path

# 导入其他脚本
try:
    from crop_4grid import crop_4grid
    from crop_9grid import crop_9grid
    from make_gif import create_loop_gif
except ImportError:
    print("请确保 crop_4grid.py, crop_9grid.py, make_gif.py 在同一目录")
    exit(1)


def batch_crop_4grid(input_dir: str, output_dir: str, start_index: int = 1):
    """
    批量裁剪四宫格图片
    
    Args:
        input_dir: 输入目录（包含多张四宫格图片）
        output_dir: 输出目录
        start_index: 起始编号
    """
    # 支持的图片格式
    patterns = ['*.png', '*.jpg', '*.jpeg', '*.gif']
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(input_dir, pattern)))
    
    files = sorted(files)
    print(f"找到 {len(files)} 张四宫格图片")
    
    current_index = start_index
    for file in files:
        print(f"\n处理: {os.path.basename(file)}")
        saved = crop_4grid(file, output_dir, current_index)
        current_index += len(saved)
    
    print(f"\n✅ 批量裁剪完成！共生成 {current_index - start_index} 张图片")


def batch_make_gif(frames_base_dir: str, output_dir: str):
    """
    批量生成GIF
    
    Args:
        frames_base_dir: 帧图基础目录（包含多个子目录，每个子目录是一组帧图）
        output_dir: 输出目录
    """
    # 获取所有帧图子目录
    subdirs = sorted([
        d for d in os.listdir(frames_base_dir)
        if os.path.isdir(os.path.join(frames_base_dir, d))
    ])
    
    print(f"找到 {len(subdirs)} 组帧图")
    
    os.makedirs(output_dir, exist_ok=True)
    
    for i, subdir in enumerate(subdirs, 1):
        frames_dir = os.path.join(frames_base_dir, subdir)
        output_path = os.path.join(output_dir, f"{i}.gif")
        
        print(f"\n处理第 {i} 组: {subdir}")
        create_loop_gif(frames_dir, output_path)
    
    print(f"\n✅ 批量GIF生成完成！共生成 {len(subdirs)} 个GIF")


def main():
    parser = argparse.ArgumentParser(description="微信表情包批量处理工具")
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # 批量裁剪四宫格
    crop_parser = subparsers.add_parser('batch-crop', help='批量裁剪四宫格')
    crop_parser.add_argument('--input-dir', '-i', required=True, help='输入目录')
    crop_parser.add_argument('--output-dir', '-o', required=True, help='输出目录')
    crop_parser.add_argument('--start', '-s', type=int, default=1, help='起始编号')
    
    # 批量生成GIF
    gif_parser = subparsers.add_parser('batch-gif', help='批量生成GIF')
    gif_parser.add_argument('--frames-dir', '-f', required=True, help='帧图基础目录')
    gif_parser.add_argument('--output-dir', '-o', required=True, help='输出目录')
    
    args = parser.parse_args()
    
    if args.command == 'batch-crop':
        batch_crop_4grid(args.input_dir, args.output_dir, args.start)
    elif args.command == 'batch-gif':
        batch_make_gif(args.frames_dir, args.output_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
