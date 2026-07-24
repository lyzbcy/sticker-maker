#!/usr/bin/env python3
"""
面部/头部检测工具 - 面部检测 + 头部区域裁剪

功能：从表情图中智能检测角色头部位置，用于制作图标/封面

检测方法（按优先级）：
1. OpenCV Haar Cascade 人脸检测（精确，需安装 opencv-python）
2. Pillow 启发式检测（像素密度 + 上半身推断，纯Pillow实现）

使用方式：
    # 检测单张图
    python face_detect.py --input image.png
    
    # 裁剪头部区域并保存
    python face_detect.py --input image.png --output head.png
    
    # 批量处理
    python face_detect.py --input-dir ./最终版/ --output-dir ./头部/

依赖：
    pip install Pillow
    pip install opencv-python  # 可选，用于精确人脸检测
"""

import argparse
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    exit(1)


# ============ 方法1：OpenCV 人脸检测 ============

def detect_face_opencv(image_path):
    """使用 OpenCV Haar Cascade 检测人脸，返回 (x, y, w, h) 或 None"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    
    # Windows 下中文路径对 cv2.imread 不稳定，改用 fromfile + imdecode
    image_bytes = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return None
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 尝试多个级联分类器
    cascade_files = [
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml',
        cv2.data.haarcascades + 'haarcascade_frontalface_alt.xml',
        cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml',
    ]
    
    for cascade_file in cascade_files:
        if not os.path.exists(cascade_file):
            continue
        face_cascade = cv2.CascadeClassifier(cascade_file)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) > 0:
            # 返回最大的脸
            faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
            x, y, w, h = faces[0]
            return (x, y, w, h)
    
    # 尝试侧脸检测
    profile_cascade = cv2.data.haarcascades + 'haarcascade_profileface.xml'
    if os.path.exists(profile_cascade):
        face_cascade = cv2.CascadeClassifier(profile_cascade)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) > 0:
            faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
            x, y, w, h = faces[0]
            return (x, y, w, h)
    
    return None


# ============ 方法2：Pillow 启发式头部检测 ============

def get_alpha_bbox(image):
    """获取RGBA图片中非透明像素的包围盒"""
    if image.mode != 'RGBA':
        return (0, 0, image.width, image.height)
    
    alpha = image.getchannel('A')
    bbox = alpha.getbbox()  # (left, top, right, bottom)
    return bbox if bbox else (0, 0, image.width, image.height)


def detect_head_pillow(image_path, head_ratio=0.45):
    """
    使用 Pillow 启发式检测头部区域
    
    算法：
    1. 找到非透明像素的包围盒（角色区域）
    2. 取角色上半部分（头部通常在上方 40-50%）
    3. 在上半部分中找到像素密度最高的方形区域
    
    Args:
        image_path: 图片路径
        head_ratio: 头部占角色的比例（默认0.45，即角色上方45%是头部）
    
    Returns:
        (x, y, w, h) 头部边界框（相对原图坐标）
    """
    img = Image.open(image_path)
    
    if img.mode == 'RGBA':
        # RGBA：基于alpha通道检测
        bbox = get_alpha_bbox(img)
        left, top, right, bottom = bbox
        char_width = right - left
        char_height = bottom - top
        char_center_x = (left + right) // 2
        char_center_y = top + int(char_height * head_ratio * 0.5)
        
        # 头部区域：角色上方40%，宽度取角色宽度的60%（头部通常比身体窄）
        head_size = int(char_width * 0.65)
        head_x = max(0, char_center_x - head_size // 2)
        head_y = max(0, top - int(char_height * 0.05))
        head_w = min(head_size, img.width - head_x)
        head_h = min(int(char_height * head_ratio + char_height * 0.15), img.height - head_y)
        
        # 在头部区域内找到像素最密集的子区域（缩窄到实际头部）
        alpha = img.getchannel('A')
        
        # 将头部区域细分为多个候选窗口，选不透明像素最多的
        best_density = 0
        best_region = (head_x, head_y, head_w, head_h)
        
        for offset_y in range(0, int(head_h * 0.3), max(1, int(head_h * 0.05))):
            for offset_x in range(-int(head_w * 0.1), int(head_w * 0.1), max(1, int(head_w * 0.05))):
                rx = max(0, head_x + offset_x)
                ry = max(0, head_y + offset_y)
                rw = min(head_w, img.width - rx)
                rh = min(int(head_h * 0.85), img.height - ry)
                if rw <= 10 or rh <= 10:
                    continue
                region = alpha.crop((rx, ry, rx + rw, ry + rh))
                data = list(region.getdata())
                total = len(data)
                if total == 0:
                    continue
                opaque = sum(1 for p in data if p > 127)
                density = opaque / total
                if density > best_density:
                    best_density = density
                    best_region = (rx, ry, rw, rh)
        
        return best_region
    
    else:
        # RGB：无法精确检测，返回图片上方1/3中心区域
        w, h = img.size
        cx = w // 2
        head_size = int(w * 0.5)
        return (cx - head_size // 2, 0, head_size, int(h * 0.5))


# ============ 统一接口 ============

def detect_face(image_path, prefer_opencv=True):
    """
    统一的人脸/头部检测接口
    
    Args:
        image_path: 图片路径
        prefer_opencv: 是否优先使用 OpenCV
        
    Returns:
        dict: {
            'bbox': (x, y, w, h),  # 检测到的区域边界框
            'method': 'opencv' | 'pillow',  # 使用的检测方法
            'confidence': float,  # 置信度（仅 OpenCV）
        }
    """
    result = {'bbox': None, 'method': 'none', 'confidence': 0}
    
    # 尝试 OpenCV
    if prefer_opencv:
        face = detect_face_opencv(image_path)
        if face:
            result['bbox'] = face
            result['method'] = 'opencv'
            result['confidence'] = 0.8
            return result
    
    # 回退到 Pillow 启发式
    head = detect_head_pillow(image_path)
    if head:
        result['bbox'] = head
        result['method'] = 'pillow'
        result['confidence'] = 0.6
        return result
    
    return result


# ============ 头部裁剪 ============

def crop_head(image_path, output_path=None, margin_ratio=0.15, prefer_opencv=True):
    """
    裁剪角色头部区域
    
    Args:
        image_path: 输入图片路径
        output_path: 输出路径（None 则返回 PIL Image）
        margin_ratio: 头部周围的留白比例
        prefer_opencv: 是否优先使用 OpenCV
        
    Returns:
        PIL.Image 或 None
    """
    result = detect_face(image_path, prefer_opencv=prefer_opencv)
    
    if result['bbox'] is None:
        print(f"  ⚠️  未检测到头部: {image_path}")
        # 回退：裁剪图片上方中央部分
        img = Image.open(image_path)
        w, h = img.size
        crop_size = min(w, h // 2)
        head_img = img.crop((
            max(0, w // 2 - crop_size // 2),
            0,
            min(w, w // 2 + crop_size // 2),
            min(h, crop_size)
        ))
    else:
        x, y, w, h = result['bbox']
        img = Image.open(image_path)
        
        # 添加边距
        margin_x = int(w * margin_ratio)
        margin_y = int(h * margin_ratio)
        crop_box = (
            max(0, x - margin_x),
            max(0, y - margin_y),
            min(img.width, x + w + margin_x),
            min(img.height, y + h + margin_y)
        )
        head_img = img.crop(crop_box)
        print(f"  ✅ 检测到头部 [{result['method']}]: bbox=({x},{y},{w},{h})")
    
    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        head_img.save(output_path, 'PNG')
        print(f"  📁 已保存: {output_path}")
    
    return head_img


def main():
    parser = argparse.ArgumentParser(description='面部/头部检测工具')
    parser.add_argument('--input', '-i', help='单张输入图片路径')
    parser.add_argument('--input-dir', help='批量输入目录')
    parser.add_argument('--output', '-o', help='输出图片路径（单张模式）')
    parser.add_argument('--output-dir', help='批量输出目录')
    parser.add_argument('--margin', '-m', type=float, default=0.15, help='头部边距比例（默认0.15）')
    parser.add_argument('--no-opencv', action='store_true', help='不使用OpenCV（仅Pillow启发式）')
    parser.add_argument('--detect-only', action='store_true', help='仅检测不裁剪')
    
    args = parser.parse_args()
    
    # 仅检测模式
    if args.detect_only and args.input:
        result = detect_face(args.input, prefer_opencv=not args.no_opencv)
        if result['bbox']:
            x, y, w, h = result['bbox']
            print(f"检测结果 [{result['method']}]: x={x} y={y} w={w} h={h}")
        else:
            print("未检测到面部/头部")
        return 0
    
    # 单张模式
    if args.input:
        crop_head(
            args.input,
            args.output,
            margin_ratio=args.margin,
            prefer_opencv=not args.no_opencv
        )
    
    # 批量模式
    if args.input_dir and args.output_dir:
        input_dir = Path(args.input_dir)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        images = list(input_dir.glob('*.png'))
        if not images:
            images = list(input_dir.glob('*.jpg'))
        
        print(f'📁 批量处理 {len(images)} 张图片...')
        for img in images:
            out_path = output_dir / f'head_{img.stem}.png'
            crop_head(
                str(img),
                str(out_path),
                margin_ratio=args.margin,
                prefer_opencv=not args.no_opencv
            )
        print(f'✅ 批量处理完成！共 {len(images)} 张')
    
    return 0


if __name__ == '__main__':
    exit(main())
