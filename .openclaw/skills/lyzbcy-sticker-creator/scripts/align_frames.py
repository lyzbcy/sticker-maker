#!/usr/bin/env python3
"""
帧对齐脚本 - 减少九宫格 GIF 晃动（v3 稳定版）

功能：
1. 自动检测背景色
2. 检测每帧角色位置（支持三种方法）
3. 计算所有帧的公共区域
4. 对齐并统一裁剪（不会有边缘超出问题）

使用方法：
    # 单个九宫格
    python align_frames.py input.png output.gif

    # 批量处理
    python align_frames.py --batch "帧图目录" "输出目录"

检测方法（经测试验证）：
    --method centroid  # 整体质心，最稳定（默认）
    --method head      # 头部区域质心
    --method top       # 头顶中心（不推荐）

原理（来自周五涵的建议）：
- 不扩大画布，而是缩小对齐
- 找到所有帧的公共区域，统一裁剪
- 代价是画面稍微缩小，但不会有边缘问题

作者：周三涵 + 周五涵
日期：2026-05-29
"""

from PIL import Image
import numpy as np
from pathlib import Path
import argparse

def detect_background_color(img):
    """自动检测背景色（取四角颜色的平均值）"""
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    arr = np.array(img)
    h, w = arr.shape[:2]
    
    corners = [
        arr[0:10, 0:10],
        arr[0:10, w-10:w],
        arr[h-10:h, 0:10],
        arr[h-10:h, w-10:w],
    ]
    
    all_corners = np.concatenate([c.reshape(-1, 3) for c in corners])
    return tuple(np.mean(all_corners, axis=0).astype(int))

def crop_9grid(img_path):
    """裁剪九宫格为9帧"""
    img = Image.open(img_path)
    width, height = img.size
    cell_w, cell_h = width // 3, height // 3
    
    frames = []
    for row in range(3):
        for col in range(3):
            left = col * cell_w
            top = row * cell_h
            cell = img.crop((left, top, left + cell_w, top + cell_h))
            frames.append(cell)
    
    return frames

def find_character_center(img, bg_color, method='centroid', tolerance=15):
    """
    检测角色中心位置
    
    method:
    - centroid: 整体质心（推荐，最稳定）
    - head: 头部区域质心（上1/3区域）
    - top: 头顶中心（最上方像素行中心）
    """
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    arr = np.array(img)
    h, w = arr.shape[:2]
    
    # 背景检测
    bg_match = np.all(np.abs(arr - bg_color) <= tolerance, axis=2)
    character_mask = ~bg_match
    
    if method == 'centroid':
        # 整体质心
        y_indices, x_indices = np.where(character_mask)
        if len(x_indices) == 0:
            return None
        return np.mean(x_indices), np.mean(y_indices)
    
    elif method == 'head':
        # 头部区域（上1/3）
        head_region = character_mask[:h//3, :]
        if not np.any(head_region):
            head_region = character_mask[:h//2, :]
        if not np.any(head_region):
            return None
        y_indices, x_indices = np.where(head_region)
        return np.mean(x_indices), np.mean(y_indices)
    
    elif method == 'top':
        # 头顶中心
        rows_with_character = np.any(character_mask, axis=1)
        if not np.any(rows_with_character):
            return None
        top_row = np.where(rows_with_character)[0][0]
        cols_in_top_row = np.where(character_mask[top_row, :])[0]
        if len(cols_in_top_row) == 0:
            return None
        return np.mean(cols_in_top_row), float(top_row)
    
    return None

def align_and_crop(frames, bg_color, method='centroid'):
    """
    对齐并统一裁剪（v3 改进版）
    
    1. 找到所有帧角色位置的平均中心
    2. 计算每帧需要的平移量
    3. 计算所有帧的公共区域
    4. 裁剪并返回统一尺寸的帧
    """
    original_w, original_h = frames[0].size
    
    # 检测每帧中心
    centers = []
    for frame in frames:
        center = find_character_center(frame, bg_color, method)
        centers.append(center if center else (original_w/2, original_h/2))
    
    # 计算平均中心
    avg_cx = np.mean([c[0] for c in centers])
    avg_cy = np.mean([c[1] for c in centers])
    
    # 计算每帧的平移量
    offsets = [(avg_cx - c[0], avg_cy - c[1]) for c in centers]
    
    # 计算所有帧平移后的有效边界
    left_bounds = [max(0, o[0]) for o in offsets]
    right_bounds = [min(original_w, original_w + o[0]) for o in offsets]
    top_bounds = [max(0, o[1]) for o in offsets]
    bottom_bounds = [min(original_h, original_h + o[1]) for o in offsets]
    
    # 找到所有帧的公共区域
    crop_left = int(np.ceil(max(left_bounds)))
    crop_right = int(np.floor(min(right_bounds)))
    crop_top = int(np.ceil(max(top_bounds)))
    crop_bottom = int(np.floor(min(bottom_bounds)))
    
    crop_w = crop_right - crop_left
    crop_h = crop_bottom - crop_top
    
    if crop_w <= 0 or crop_h <= 0:
        print("  WARNING: No common area! Using original size.")
        crop_left, crop_top = 0, 0
        crop_right, crop_bottom = original_w, original_h
        crop_w, crop_h = original_w, original_h
    
    # 对齐并裁剪每帧
    aligned_frames = []
    for frame, (ox, oy) in zip(frames, offsets):
        aligned = Image.new('RGB', (original_w, original_h), bg_color)
        paste_x = int(round(ox))
        paste_y = int(round(oy))
        aligned.paste(frame, (paste_x, paste_y))
        cropped = aligned.crop((crop_left, crop_top, crop_right, crop_bottom))
        aligned_frames.append(cropped)
    
    max_offset = (max(abs(o[0]) for o in offsets), max(abs(o[1]) for o in offsets))
    
    return aligned_frames, (crop_w, crop_h), (avg_cx, avg_cy), max_offset

def make_gif(frames, output_path, duration=100):
    """生成循环播放的 GIF"""
    play_frames = frames + frames[-2:0:-1]
    frames[0].save(
        output_path,
        save_all=True,
        append_images=play_frames[1:],
        duration=duration,
        loop=0,
        disposal=2
    )

def process_single(input_path, output_path, duration=100, method='centroid'):
    """处理单个九宫格"""
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    print(f"Processing {input_path.name}...")
    
    frames = crop_9grid(input_path)
    original_size = frames[0].size
    bg_color = detect_background_color(frames[0])
    
    aligned_frames, new_size, avg_center, max_offset = align_and_crop(frames, bg_color, method)
    
    print(f"  Original: {original_size[0]}x{original_size[1]}")
    print(f"  After crop: {new_size[0]}x{new_size[1]}")
    print(f"  Max offset: ({max_offset[0]:.1f}, {max_offset[1]:.1f})px")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    make_gif(aligned_frames, output_path, duration)
    print(f"  Output: {output_path}")
    
    return new_size, max_offset

def process_batch(input_dir, output_dir, duration=100, method='centroid'):
    """批量处理九宫格"""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    
    grids = sorted(input_dir.glob("*.png"))
    print(f"Found {len(grids)} grids\n")
    
    results = []
    for i, grid_path in enumerate(grids, 1):
        output_path = output_dir / f"{i}.gif"
        new_size, max_offset = process_single(grid_path, output_path, duration, method)
        results.append({
            'grid': grid_path.name,
            'index': i,
            'new_size': new_size,
            'max_offset': max_offset
        })
    
    # 汇总
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"{'#':<4} {'Grid':<15} {'Size':<12} {'Max Offset':<12}")
    print("-" * 60)
    for r in results:
        print(f"{r['index']:<4} {r['grid']:<15} {r['new_size'][0]}x{r['new_size'][1]:<6} ({r['max_offset'][0]:.0f}, {r['max_offset'][1]:.0f})")
    
    print(f"\nTotal: {len(results)} GIFs")
    print(f"Output: {output_dir}")

def main():
    parser = argparse.ArgumentParser(description='Frame Alignment v3 - Stable Edition')
    parser.add_argument('input', help='Input PNG file or directory')
    parser.add_argument('output', help='Output GIF file or directory')
    parser.add_argument('--batch', action='store_true', help='Batch mode')
    parser.add_argument('--duration', type=int, default=100, help='Frame duration in ms')
    parser.add_argument('--method', choices=['centroid', 'head', 'top'], default='centroid',
                        help='Detection method (default: centroid, recommended)')
    
    args = parser.parse_args()
    
    if args.batch:
        process_batch(args.input, args.output, args.duration, args.method)
    else:
        process_single(args.input, args.output, args.duration, args.method)

if __name__ == "__main__":
    main()
