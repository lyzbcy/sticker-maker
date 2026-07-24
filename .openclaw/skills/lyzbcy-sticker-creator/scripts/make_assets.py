#!/usr/bin/env python3
"""
一键生成发布素材 - 为表情包目录生成横幅、封面、图标

自动检测最终版目录中的图片，生成符合微信平台要求的横幅/封面/图标。

使用方式：
    # 为一弹表情包生成所有发布素材
    python make_assets.py --dir "E:\星星布丁\微信表情包\周三涵做表情4"

    # 指定特定图片作为素材源
    python make_assets.py --dir "E:\星星布丁\微信表情包\周三涵做表情4" --source 开心比耶.png

输出目录（在表情包目录下自动创建）：
    横幅/   → 横幅.png (750×400)
    封面/   → 封面.png (240×240)
    图标/   → 图标.png (50×50)
"""

import argparse
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 添加同目录路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from make_banner import make_banner
from make_cover import make_cover
from make_icon import make_icon
from asset_selection import pick_best_image, rank_images
from production_log import log_step


def detect_image_dir(base_dir):
    """自动检测图片目录：优先最终版 > 原图_透明ChromaKey > 原图"""
    candidates = ['最终版', '原图_透明ChromaKey', '原图']
    for candidate in candidates:
        d = os.path.join(base_dir, candidate)
        if os.path.isdir(d) and any(Path(d).glob('*.png')):
            return d, candidate
    return base_dir, '根目录'


def make_all_assets(sticker_dir, source_image=None):
    """
    为一弹表情包生成所有发布素材
    
    Args:
        sticker_dir: 表情包目录（如 周三涵做表情4）
        source_image: 指定主素材图片（可选，默认自动选择最佳）
    """
    # 检测图片目录
    image_dir, dir_name = detect_image_dir(sticker_dir)
    print(f'📁 图片源: {dir_name} ({image_dir})')
    
    images = sorted(Path(image_dir).glob('*.png'))
    if not images:
        print('❌ 未找到PNG图片！')
        return False
    
    print(f'📸 找到 {len(images)} 张表情图')
    
    # 创建输出目录
    banner_dir = os.path.join(sticker_dir, '横幅')
    cover_dir = os.path.join(sticker_dir, '封面')
    icon_dir = os.path.join(sticker_dir, '图标')
    
    for d in [banner_dir, cover_dir, icon_dir]:
        os.makedirs(d, exist_ok=True)
    
    # 选择素材图
    image_paths = [str(img) for img in images]
    if source_image:
        forced_img = source_image if os.path.isabs(source_image) else os.path.join(image_dir, source_image)
        banner_img = forced_img
        cover_img = forced_img
        icon_img = forced_img
        banner_candidates = [banner_img]
    else:
        banner_ranked = rank_images(image_paths, 'banner')
        banner_candidates = [item[1]["path"] for item in banner_ranked[:3]]
        banner_img = banner_candidates[0] if banner_candidates else None
        cover_img, _ = pick_best_image(image_paths, 'cover')
        icon_img, _ = pick_best_image(image_paths, 'icon')
        if not banner_img:
            banner_img = image_paths[0]
        if not cover_img:
            cover_img = banner_img
        if not icon_img:
            icon_img = cover_img
        if not banner_candidates:
            banner_candidates = [banner_img]

    print(f'  🖼️ 横幅候选: {os.path.basename(banner_img)}')
    if len(banner_candidates) > 1:
        print(f'  🖼️ 横幅小剧场辅助: {", ".join(os.path.basename(p) for p in banner_candidates[1:])}')
    print(f'  🖼️ 封面候选: {os.path.basename(cover_img)}')
    print(f'  🖼️ 图标候选: {os.path.basename(icon_img)}')

    banner_out = os.path.join(banner_dir, '横幅.png')
    
    cover_out = os.path.join(cover_dir, '封面.png')
    
    icon_out = os.path.join(icon_dir, '图标.png')
    
    print(f'\n🎨 生成发布素材...')
    print('=' * 50)
    
    # 1. 横幅
    print(f'\n📐 1/3 生成横幅 (750×400)...')
    make_banner(banner_candidates, banner_out, style='auto')
    
    # 2. 封面（直接用独立挑选的成品图，不依赖横幅图）
    print(f'\n📐 2/3 生成封面 (240×240)...')
    make_cover(cover_img, cover_out)
    
    # 3. 图标
    print(f'\n📐 3/3 生成图标 (50×50)...')
    make_icon(icon_img, icon_out)
    
    print(f'\n{"=" * 50}')
    print(f'✅ 发布素材生成完成！')
    print(f'  📁 横幅: {banner_out}')
    print(f'  📁 封面: {cover_out}')
    print(f'  📁 图标: {icon_out}')

    # 记录生产日志（结构化：含尺寸校验值，便于复盘素材是否达标）
    try:
        from production_log import log_step_rich
        from PIL import Image as _Img
        def _sz(p):
            try:
                return list(_Img.open(p).size)
            except Exception:
                return None
        log_step_rich(sticker_dir, "发布素材", "OK", step_data={
            "banner": os.path.basename(banner_out), "banner_size": _sz(banner_out),
            "cover": os.path.basename(cover_out), "cover_size": _sz(cover_out),
            "icon": os.path.basename(icon_out), "icon_size": _sz(icon_out),
            "source_dir": dir_name,
        }, details=f"横幅/封面/图标生成完成（源图目录: {dir_name}）")
    except Exception as e:
        print(f'  ⚠️ 生产日志写入失败: {e}')

    return True


def main():
    parser = argparse.ArgumentParser(description='一键生成微信表情包发布素材（横幅/封面/图标）')
    parser.add_argument('--dir', '-d', required=True, help='表情包目录路径（如 周三涵做表情4）')
    parser.add_argument('--source', '-s', help='指定主素材图片文件名（可选）')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.dir):
        print(f'❌ 目录不存在: {args.dir}')
        return 1
    
    success = make_all_assets(args.dir, args.source)
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
