#!/usr/bin/env python3
"""
封面生成工具 - 从表情图中生成微信平台发布的封面

微信平台要求：
- 尺寸：240×240 像素
- 格式：PNG（>500KB 会被压缩）
- 选取最具辨识度的形象，正面半身像或全身像
- 透明背景
- 形象不应有白色描边，避免锯齿
- 合理安排图片布局，避免过多留白
- 画面尽量简洁，避免装饰元素
- 除纯文字类型外，避免出现文字
- 尽量和横幅采用同一张图

生成策略：
1. 找到角色的包围盒（基于alpha通道）
2. 从包围盒裁剪，保持角色完整
3. 缩放到240×240，角色居中
4. 保持透明背景

使用方式：
    python make_cover.py --input 开心比耶.png --output ./封面/封面.png
    python make_cover.py --input-dir ./最终版/ --output-dir ./封面/ --banner-ref ./横幅/横幅.png
"""

import argparse
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    exit(1)


def get_character_bbox(image, min_alpha=30):
    """获取角色在图片中的包围盒（基于alpha通道，容忍半透明边缘）"""
    if image.mode == 'RGBA':
        alpha = image.getchannel('A')
        # 用阈值过滤半透明边缘
        data = list(alpha.getdata())
        w, h = alpha.size
        
        left, top, right, bottom = w, h, 0, 0
        for y in range(h):
            for x in range(w):
                if data[y * w + x] > min_alpha:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)
        
        if left < right and top < bottom:
            return (left, top, right, bottom)
    
    # RGB模式：返回整图（假设角色占满画面）
    return (0, 0, image.width, image.height)


def make_cover(image_path, output_path, banner_ref=None):
    """
    生成封面图（240×240）
    
    Args:
        image_path: 输入表情图片路径
        output_path: 输出路径
        banner_ref: 横幅参考图路径（尽量用同一张图）
    """
    SIZE = 240
    
    # 如果指定了横幅主图参考，优先与横幅使用同一张源图
    src_path = banner_ref if banner_ref and os.path.exists(banner_ref) else image_path
    
    img = Image.open(src_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    bbox = get_character_bbox(img)
    
    if bbox:
        left, top, right, bottom = bbox
        char_w = right - left
        char_h = bottom - top
        
        # 裁剪角色区域（加10%边距）
        margin_x = int(char_w * 0.08)
        margin_y = int(char_h * 0.08)
        crop_box = (
            max(0, left - margin_x),
            max(0, top - margin_y),
            min(img.width, right + margin_x),
            min(img.height, bottom + margin_y)
        )
        cropped = img.crop(crop_box)
    else:
        cropped = img
    
    # 缩放到240×240（保持比例，填充透明）
    crop_w, crop_h = cropped.size
    scale = min(SIZE / crop_w, SIZE / crop_h)
    new_w = int(crop_w * scale)
    new_h = int(crop_h * scale)
    
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)
    
    # 创建240×240透明画布
    canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    
    # 居中放置
    px = (SIZE - new_w) // 2
    py = (SIZE - new_h) // 2
    canvas.paste(resized, (px, py), resized)
    
    # 保存
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    canvas.save(output_path, 'PNG', optimize=True)
    
    size_kb = os.path.getsize(output_path) / 1024
    print(f'  📁 封面已保存: {output_path} ({size_kb:.0f}KB)')
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description='微信表情包封面生成工具（240×240 PNG透明背景）')
    parser.add_argument('--input', '-i', help='单张输入图片路径')
    parser.add_argument('--input-dir', help='批量输入目录（取第一张最合适的）')
    parser.add_argument('--output', '-o', help='输出路径（单张模式）')
    parser.add_argument('--output-dir', help='批量输出目录')
    parser.add_argument('--banner-ref', help='横幅参考图路径（尽量复用横幅的图）')
    
    args = parser.parse_args()
    
    if args.input and args.output:
        make_cover(args.input, args.output, args.banner_ref)
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
        best_image, _ = pick_best_image([str(img) for img in images], 'cover')
        if not best_image:
            best_image = str(images[0])
        out_path = output_dir / '封面.png'
        make_cover(best_image, str(out_path), args.banner_ref)
        return 0
    
    parser.print_help()
    return 1


if __name__ == '__main__':
    exit(main())
