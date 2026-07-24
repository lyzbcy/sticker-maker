#!/usr/bin/env python3
"""
图标生成工具 - 从表情图中生成微信平台发布的图标

微信平台要求：
- 尺寸：50×50 像素
- 格式：PNG（>100KB 会被压缩）
- 选取最具辨识度和清晰的图片，画面尽量简洁
- 建议使用仅含表情角色的头部正面图像做图标
- 形象不应有白色描边，避免锯齿
- 透明背景
- 不要出现正方形边框，避免表情主体出现生硬的直角边缘
- 合理安排图片布局，避免过多留白
- 不同的表情专辑应使用不一样的图片做图标

生成策略：
1. 使用 face_detect.py 检测角色头部位置
2. 裁剪头部区域
3. 缩放至50×50，角色居中
4. 确保无直角边缘（圆形/圆角裁剪可选）
5. 保持透明背景

使用方式：
    python make_icon.py --input 开心比耶.png --output ./图标/图标.png
    python make_icon.py --input-dir ./最终版/ --output-dir ./图标/
"""

import argparse
import os
import sys
from pathlib import Path

# 添加同目录路径以导入 face_detect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    exit(1)

from face_detect import detect_face, get_alpha_bbox


def make_icon(image_path, output_path, prefer_opencv=True):
    """
    生成图标（50×50 PNG透明背景）
    
    Args:
        image_path: 输入图片路径
        output_path: 输出路径
        prefer_opencv: 是否优先使用OpenCV人脸检测
    """
    SIZE = 50
    
    img = Image.open(image_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # 尝试检测人脸/头部
    face_result = detect_face(image_path, prefer_opencv=prefer_opencv)
    
    if face_result['bbox'] and face_result['method'] != 'none':
        x, y, w, h = face_result['bbox']

        # 图标用更稳的方形构图：保住完整脸、头发和一点肩部空间
        face_cx = x + w / 2
        face_cy = y + h / 2
        crop_size = int(max(w, h) * 2.4)
        crop_size = max(crop_size, int(min(img.width, img.height) * 0.42))
        crop_size = min(crop_size, max(img.width, img.height))
        crop_left = int(face_cx - crop_size / 2)
        crop_top = int(face_cy - crop_size * 0.42)
        crop_left = max(0, min(crop_left, img.width - crop_size))
        crop_top = max(0, min(crop_top, img.height - crop_size))
        crop_box = (
            crop_left,
            crop_top,
            min(img.width, crop_left + crop_size),
            min(img.height, crop_top + crop_size)
        )
        cropped = img.crop(crop_box)
        print(f"  ✅ 图标 [{face_result['method']}]: head at ({x},{y}) {w}×{h}")
    else:
        # 回退：基于alpha通道的包围盒取上半部分
        bbox = get_alpha_bbox(img)
        if bbox:
            left, top, right, bottom = bbox
            char_w = right - left
            char_h = bottom - top
            # 回退时也保持尽量完整的人头和上半身，不只截半张脸
            head_h = int(char_h * 0.68)
            crop_size = max(char_w, head_h)
            crop_left = max(0, min(int((left + right) / 2 - crop_size / 2), img.width - crop_size))
            crop_top = max(0, min(int(top - char_h * 0.06), img.height - crop_size))
            head_box = (
                crop_left,
                crop_top,
                min(img.width, crop_left + crop_size),
                min(img.height, crop_top + crop_size)
            )
            cropped = img.crop(head_box)
            print(f'  ⚠️  回退模式：取角色上半身方形构图')
        else:
            # 完全回退：裁剪图片上方中心
            w, h = img.size
            crop_size = min(w, int(h * 0.72))
            crop_box = (
                max(0, w // 2 - crop_size // 2),
                0,
                min(w, w // 2 + crop_size // 2),
                min(h, crop_size)
            )
            cropped = img.crop(crop_box)
            print(f'  ⚠️  回退模式：取图片上方中心')
    
    # 缩放到50×50（保持比例）
    crop_w, crop_h = cropped.size
    scale = min(SIZE / crop_w, SIZE / crop_h)
    new_w = int(crop_w * scale)
    new_h = int(crop_h * scale)
    
    # 确保至少30px（太小说明检测有问题）
    if new_w < 30 or new_h < 30:
        scale = max(30 / crop_w, 30 / crop_h)
        new_w = max(30, int(crop_w * scale))
        new_h = max(30, int(crop_h * scale))
    
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)
    
    # 创建50×50透明画布
    canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    
    # 居中放置
    px = (SIZE - new_w) // 2
    py = (SIZE - new_h) // 2
    canvas.paste(resized, (px, py), resized)
    
    # 确保无直角边缘（锐化透明边缘的直角像素）
    # 对边缘做轻微的alpha羽化
    alpha = canvas.getchannel('A')
    from PIL import ImageFilter
    alpha_blurred = alpha.filter(ImageFilter.GaussianBlur(radius=0.5))
    canvas.putalpha(alpha_blurred)
    
    # 保存
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    canvas.save(output_path, 'PNG', optimize=True)
    
    size_kb = os.path.getsize(output_path) / 1024
    print(f'  📁 图标已保存: {output_path} ({size_kb:.0f}KB)')
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description='微信表情包图标生成工具（50×50 PNG透明背景）')
    parser.add_argument('--input', '-i', help='单张输入图片路径')
    parser.add_argument('--input-dir', help='批量输入目录（挑选最佳图片制作图标）')
    parser.add_argument('--output', '-o', help='输出路径（单张模式）')
    parser.add_argument('--output-dir', help='批量输出目录')
    parser.add_argument('--no-opencv', action='store_true', help='不使用OpenCV人脸检测')
    
    args = parser.parse_args()
    
    if args.input and args.output:
        make_icon(args.input, args.output, prefer_opencv=not args.no_opencv)
        return 0
    
    if args.input_dir and args.output_dir:
        input_dir = Path(args.input_dir)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        images = sorted(list(input_dir.glob('*.png')))
        if not images:
            print('❌ 未找到PNG图片')
            return 1
        
        from asset_selection import pick_best_image
        best_image, _ = pick_best_image([str(img) for img in images], 'icon')
        if not best_image:
            best_image = str(images[0])
        out_path = output_dir / '图标.png'
        make_icon(best_image, str(out_path), prefer_opencv=not args.no_opencv)
        return 0
    
    parser.print_help()
    return 1


if __name__ == '__main__':
    exit(main())
