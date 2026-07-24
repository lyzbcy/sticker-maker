#!/usr/bin/env python3
"""
横幅生成工具 - 从表情图中生成微信平台发布的横幅广告图

微信平台要求：
- 尺寸：750×400 像素
- 格式：JPG 或 PNG（>500KB 会被压缩）
- 横图，适合作为横幅展示，有张力
- 图片色调活泼明朗，与微信底色有较大区分
- 横幅内容须与表情有关，画面丰富，有故事性
- 避免白色背景，避免透明背景
- 图中元素不能因拉伸压扁导致变形
- 避免出现任何文字信息

设计风格（v3）：
- 简约纯色背景（从角色取色选柔和色）+ 极淡径向暗角
- 默认保留“第8弹式”单主角放大居中略偏下，配柔和脚下投影
- 当传入多张候选图时，自动升级为“表情小剧场”：主角居中，两侧小表情辅助叙事
- 主角周围散布可爱装饰：星星/爱心/闪光/空心圆
- 装饰只放在不遮挡角色的区域

使用方式：
    python make_banner.py --input 开心比耶.png --output ./横幅/横幅.png
    python make_banner.py --input-dir ./最终版/ --output-dir ./横幅/
"""

import argparse
import hashlib
import math
import os
import random
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageFilter, ImageDraw
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    exit(1)


# 柔和背景色候选池（高明度低饱和，活泼但不刺眼，区别于微信白底）
SOFT_BG_COLORS = [
    (255, 224, 233),  # 奶油粉
    (255, 198, 217),  # 樱花粉
    (212, 245, 233),  # 薄荷绿
    (255, 245, 214),  # 奶油黄
    (232, 220, 255),  # 薰衣草
    (214, 236, 255),  # 天蓝
    (255, 228, 196),  # 杏色
    (221, 246, 229),  # 嫩绿
]


def get_dominant_color(image, num_colors=3):
    """从图片提取主色调（返回最高频 RGB 元组）"""
    small = image.resize((50, 50))
    pixels = list(small.getdata())
    if image.mode == 'RGBA':
        pixels = [(r, g, b) for r, g, b, a in pixels if a > 128]
    if not pixels:
        return (255, 224, 233)
    quantized = [(p[0] // 32 * 32, p[1] // 32 * 32, p[2] // 32 * 32) for p in pixels]
    counter = Counter(quantized)
    return counter.most_common(1)[0][0]


def pick_soft_bg(dominant_rgb):
    """根据角色主色调，选一个互补/协调的柔和背景色。

    选与主色距离较远（对比明显）但同属柔和系的背景，避免角色融入背景。
    """
    best = None
    best_score = -1
    for bg in SOFT_BG_COLORS:
        # 距离越大对比越明显，但要排除太接近的
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(dominant_rgb, bg)))
        if dist > best_score:
            best_score = dist
            best = bg
    return best


def create_radial_vignette(width, height, bg_color):
    """纯色背景 + 极淡径向暗角（角落略深，中心略亮），增加层次感。"""
    base = Image.new('RGB', (width, height), bg_color)
    # 暗角层：四角加一层很淡的深色叠加
    vignette = Image.new('L', (width, height), 0)  # 全黑（不叠加）
    vd = ImageDraw.Draw(vignette)
    cx, cy = width // 2, height // 2
    max_r = math.sqrt(cx ** 2 + cy ** 2)
    # 用几个同心椭圆从中心向外画递增灰度，模拟径向衰减
    steps = 30
    for i in range(steps, 0, -1):
        ratio = i / steps  # 1.0(外) -> 接近0(内)
        # 外圈灰度更高（叠加更多暗色）
        gray = int(40 * (ratio ** 2))
        rx = int(cx * (0.3 + 0.9 * ratio))
        ry = int(cy * (0.3 + 0.9 * ratio))
        vd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=gray)
    vignette = vignette.filter(ImageFilter.GaussianBlur(40))
    # 把暗角作为暗色蒙版叠到背景上
    dark = Image.new('RGB', (width, height), (0, 0, 0))
    # 用 vignette 的灰度作为 dark 的不透明度
    result = Image.composite(
        Image.blend(base, dark, 0.0),  # 占位
        base,
        Image.new('L', (width, height), 0),
    )
    # 简化做法：直接按 vignette 把背景压暗
    arr_bg = base.convert('RGB')
    # 用 point 操作：bg = bg * (1 - vignette/255 * 0.18)
    import numpy as np
    bg_arr = np.array(arr_bg, dtype=float)
    v_arr = np.array(vignette, dtype=float) / 255.0
    bg_arr = bg_arr * (1.0 - v_arr[..., None] * 0.18)
    bg_arr = bg_arr.clip(0, 255).astype('uint8')
    return Image.fromarray(bg_arr, 'RGB')


def get_character_bbox(image):
    """获取角色在图片中的包围盒（基于 alpha 通道）"""
    if image.mode == 'RGBA':
        alpha = image.getchannel('A').point(lambda a: 255 if a > 16 else 0)
        bbox = alpha.getbbox()
        return bbox
    return (0, 0, image.width, image.height)


def maybe_remove_flat_opaque_background(image):
    """对整张不透明且四角近似同色的图，尝试擦掉纯色/浅渐变背景。

    这用于修复部分最终版素材仍带方形底图的问题，避免横幅像贴了一张卡片。
    只在 alpha 几乎铺满画布时启用，透明主体图不会被改动。
    """
    if image.mode != 'RGBA':
        image = image.convert('RGBA')

    alpha = image.getchannel('A')
    soft_bbox = alpha.point(lambda a: 255 if a > 16 else 0).getbbox()
    solid_bbox = alpha.point(lambda a: 255 if a > 180 else 0).getbbox()
    if not soft_bbox or not solid_bbox:
        return image
    full_area = image.width * image.height
    soft_area = (soft_bbox[2] - soft_bbox[0]) * (soft_bbox[3] - soft_bbox[1])
    solid_area = (solid_bbox[2] - solid_bbox[0]) * (solid_bbox[3] - solid_bbox[1])
    if soft_area / float(max(1, full_area)) < 0.94 and solid_area / float(max(1, full_area)) < 0.42:
        return image

    left, top, right, bottom = solid_bbox
    corner = max(4, min(right - left, bottom - top) // 12)
    samples = []
    for xs, ys in [
        (range(left, min(left + corner, right)), range(top, min(top + corner, bottom))),
        (range(max(left, right - corner), right), range(top, min(top + corner, bottom))),
        (range(left, min(left + corner, right)), range(max(top, bottom - corner), bottom)),
        (range(max(left, right - corner), right), range(max(top, bottom - corner), bottom)),
    ]:
        for x in xs:
            for y in ys:
                r, g, b, a = image.getpixel((x, y))
                if a > 180:
                    samples.append((r, g, b))
    if len(samples) < max(8, corner * corner // 2):
        return image

    def median_channel(idx):
        vals = sorted(p[idx] for p in samples)
        return vals[len(vals) // 2]

    bg = (median_channel(0), median_channel(1), median_channel(2))
    # 只处理浅色/中性色背景，避免误擦黑发、深衣服等主体。
    if sum(bg) / 3.0 < 90:
        return image

    out = image.copy()
    pixels = out.load()
    threshold = 46
    soft_threshold = 72
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = pixels[x, y]
            if a <= 0:
                continue
            dist = math.sqrt((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2)
            if dist <= threshold:
                pixels[x, y] = (r, g, b, 0)
            elif dist <= soft_threshold:
                fade = int(a * (dist - threshold) / (soft_threshold - threshold))
                pixels[x, y] = (r, g, b, fade)
    return out


def draw_star(draw, cx, cy, r, fill, points=5):
    """画一个五角星"""
    coords = []
    for i in range(points * 2):
        angle = math.pi / 2 + i * math.pi / points
        radius = r if i % 2 == 0 else r * 0.4
        coords.append((cx + radius * math.cos(angle),
                       cy - radius * math.sin(angle)))
    draw.polygon(coords, fill=fill)


def draw_heart(draw, cx, cy, size, fill):
    """画一个爱心（用两个圆+三角组合）"""
    s = size
    # 左右两个上半圆
    r = s // 2
    draw.ellipse([cx - s, cy - r, cx, cy + r - s // 3], fill=fill)
    draw.ellipse([cx, cy - r, cx + s, cy + r - s // 3], fill=fill)
    # 下方三角
    draw.polygon([(cx - s + 2, cy - s // 6),
                  (cx + s - 2, cy - s // 6),
                  (cx, cy + s)], fill=fill)


def draw_sparkle(draw, cx, cy, r, fill):
    """画一个四角闪光（十字星）"""
    draw.polygon([(cx, cy - r), (cx + r * 0.25, cy - r * 0.25),
                  (cx + r, cy), (cx + r * 0.25, cy + r * 0.25),
                  (cx, cy + r), (cx - r * 0.25, cy + r * 0.25),
                  (cx - r, cy), (cx - r * 0.25, cy - r * 0.25)], fill=fill)


def stable_seed(*parts):
    """为同一组输入生成稳定随机种子，避免 Python hash 随进程变化。"""
    raw = "|".join(str(p) for p in parts).encode("utf-8", errors="ignore")
    return int(hashlib.md5(raw).hexdigest()[:8], 16)


def load_subject(image_path):
    """打开图片并按 alpha 包围盒裁出主体。"""
    img = Image.open(image_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    img = maybe_remove_flat_opaque_background(img)
    bbox = get_character_bbox(img)
    if bbox:
        return img.crop(bbox)
    return img


def fit_subject(subject, target_h, max_w):
    """按目标高度缩放，必要时限制最大宽度。"""
    scale = target_h / max(1, subject.height)
    new_w = int(subject.width * scale)
    new_h = int(subject.height * scale)
    if new_w > max_w:
        scale = max_w / max(1, subject.width)
        new_w = int(subject.width * scale)
        new_h = int(subject.height * scale)
    return subject.resize((max(1, new_w), max(1, new_h)), Image.LANCZOS)


def paste_with_shadow(canvas, subject, x, y, shadow_alpha=55):
    """给主体加柔和脚下投影并粘贴，返回占位 bbox。"""
    new_w, new_h = subject.size
    shadow_w = int(new_w * 0.75)
    shadow_h = max(10, int(new_h * 0.06))
    shadow = Image.new('RGBA', (shadow_w + 40, shadow_h + 40), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse([20, 20, shadow_w + 20, shadow_h + 20], fill=(0, 0, 0, shadow_alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    sx = x + (new_w - shadow_w) // 2 - 20
    sy = y + new_h - shadow_h // 2 - 20
    canvas.paste(shadow, (sx, sy), shadow)
    canvas.paste(subject, (x, y), subject)
    return (x, y, x + new_w, y + new_h)


def make_banner(images, output_path, palette_index=None, style='auto'):
    """
    生成横幅图（v3：简约主视觉 + 可选表情小剧场）

    Args:
        images: 图片路径列表（第一张作为主角；第2/3张可作为两侧小表情）
        output_path: 输出路径
        palette_index: 背景色索引（None=按角色取色自动选）
        style: auto/simple/story。auto 在候选图>=3时使用 story，否则使用 simple
    """
    W, H = 750, 400

    # ===== 1. 取色 + 画背景 =====
    images = [str(p) for p in images if p]
    if not images:
        raise ValueError("make_banner requires at least one image")

    first_img = Image.open(images[0])
    if first_img.mode != 'RGBA':
        first_img = first_img.convert('RGBA')

    if palette_index is not None:
        bg_color = SOFT_BG_COLORS[palette_index % len(SOFT_BG_COLORS)]
    else:
        dominant = get_dominant_color(first_img)
        bg_color = pick_soft_bg(dominant)

    background = create_radial_vignette(W, H, bg_color)
    canvas = background.convert('RGBA')

    story_mode = (style == 'story') or (style == 'auto' and len(images) >= 3)

    # ===== 2. 抠主角 + 放大 + 投影 =====
    char_img = load_subject(images[0])
    char_w, char_h = char_img.size

    # simple 保留第8弹式主角大图；story 稍微缩小，给两侧小表情留空间。
    target_h = int(H * (0.56 if story_mode else 0.58))
    resized = fit_subject(char_img, target_h, int(W * (0.58 if story_mode else 0.70)))
    new_w, new_h = resized.size

    # 居中略偏下
    px = (W - new_w) // 2
    py = (H - new_h) // 2 + int(H * 0.06)

    subject_boxes = []

    # story 模式：先放左右两个小表情，像“情绪小剧场”，但不做硬拼贴。
    if story_mode:
        side_specs = [
            (images[1], int(W * 0.17), int(H * 0.48), int(H * 0.34), -7),
            (images[2], int(W * 0.70), int(H * 0.46), int(H * 0.32), 7),
        ]
        for img_path, sx, sy, side_h, angle in side_specs:
            side = fit_subject(load_subject(img_path), side_h, int(W * 0.25))
            side = side.rotate(angle, resample=Image.BICUBIC, expand=True)
            subject_boxes.append(paste_with_shadow(canvas, side, sx, sy, shadow_alpha=38))

    subject_boxes.append(paste_with_shadow(canvas, resized, px, py, shadow_alpha=70))

    # ===== 3. 装饰元素层 =====
    # 先建一个"角色占位蒙版"：角色区域=不透明，其它=透明。
    # 装饰只放在透明区域（不遮挡角色）。
    char_mask = Image.new('L', (W, H), 0)  # 0=可放装饰
    cm = ImageDraw.Draw(char_mask)
    # 角色区域留出一些边距
    pad = 15
    for left, top, right, bottom in subject_boxes:
        cm.rectangle([left - pad, top - pad, right + pad, bottom + pad], fill=255)

    deco = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    rng = random.Random(stable_seed(output_path, *images, style, palette_index))

    # 尝试在非角色区域随机撒装饰，撒够数量
    def try_place(draw_fn, count, size_range, colors, max_tries=200):
        placed = 0
        tries = 0
        while placed < count and tries < max_tries:
            tries += 1
            x = rng.randint(15, W - 15)
            y = rng.randint(15, H - 15)
            # 检查是否落在角色区域（含边距）
            if char_mask.getpixel((x, y)) > 0:
                continue
            r = rng.randint(*size_range)
            color = rng.choice(colors)
            draw_fn(dd, x, y, r, color)
            placed += 1

    star_colors = [(255, 255, 255, 180), (255, 245, 180, 200), (255, 220, 230, 170)]
    heart_colors = [(255, 150, 180, 170), (255, 180, 200, 160)]
    sparkle_colors = [(255, 255, 255, 200), (255, 250, 200, 220)]

    try_place(draw_star, 6 if story_mode else 5, (8, 16), star_colors)
    try_place(draw_heart, 4 if story_mode else 3, (7, 13), heart_colors)
    try_place(draw_sparkle, 7 if story_mode else 6, (4, 9), sparkle_colors)

    # 空心装饰圆圈（轮廓）
    placed_circles = 0
    tries = 0
    while placed_circles < 3 and tries < 100:
        tries += 1
        x = rng.randint(25, W - 25)
        y = rng.randint(25, H - 25)
        if char_mask.getpixel((x, y)) > 0:
            continue
        r = rng.randint(14, 24)
        col = rng.choice([(255, 255, 255, 90), (255, 200, 220, 100)])
        dd.ellipse([x - r, y - r, x + r, y + r], outline=col, width=2)
        placed_circles += 1

    # 合成装饰
    canvas = Image.alpha_composite(canvas, deco)

    # ===== 4. 输出 =====
    final = canvas.convert('RGB')
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    temp_path = output_path + '.temp.png'
    final.save(temp_path, 'PNG')
    size_kb = os.path.getsize(temp_path) / 1024

    if size_kb > 500:
        jpg_path = output_path.replace('.png', '.jpg')
        quality = 90
        while quality > 50:
            final.save(jpg_path, 'JPEG', quality=quality)
            if os.path.getsize(jpg_path) / 1024 <= 490:
                break
            quality -= 10
        if output_path.endswith('.png'):
            Image.open(jpg_path).save(output_path, 'PNG', optimize=True)
        else:
            os.replace(jpg_path, output_path)
        os.remove(temp_path)
        print(f'  📊 已压缩（{size_kb:.0f}KB → {os.path.getsize(output_path)/1024:.0f}KB）')
    else:
        final.save(output_path, 'PNG')
        os.remove(temp_path)

    print(f'  📁 横幅已保存: {output_path} ({os.path.getsize(output_path)/1024:.0f}KB, style={"story" if story_mode else "simple"})')
    return output_path


def main():
    parser = argparse.ArgumentParser(description='微信表情包横幅生成工具（750×400）')
    parser.add_argument('--input', '-i', nargs='+', help='输入图片路径（1~4张）')
    parser.add_argument('--input-dir', help='批量模式：从目录中选最佳图片组合生成横幅')
    parser.add_argument('--output', '-o', help='输出路径（单张模式）')
    parser.add_argument('--output-dir', help='批量模式输出目录')
    parser.add_argument('--palette', '-p', type=int, help='背景色索引（0-7）')
    parser.add_argument('--style', choices=['auto', 'simple', 'story'], default='auto',
                        help='横幅风格：auto=多候选时小剧场，否则简约；simple=第8弹式单主角；story=两侧小表情')

    args = parser.parse_args()

    if args.input and args.output:
        make_banner(args.input, args.output, args.palette, args.style)
        return 0

    if args.input_dir and args.output_dir:
        input_dir = Path(args.input_dir)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        images = sorted(list(input_dir.glob('*.png')))
        if not images:
            print('❌ 未找到PNG图片')
            return 1

        from asset_selection import pick_best_image, rank_images
        ranked = rank_images([str(img) for img in images], 'banner')
        selected = [item[1]["path"] for item in ranked[:3]]
        if not selected:
            selected_path, _ = pick_best_image([str(img) for img in images], 'banner')
            selected = [selected_path or str(images[0])]
        out_path = output_dir / '横幅.png'
        make_banner(selected, str(out_path), args.palette, args.style)
        return 0

    parser.print_help()
    return 1


if __name__ == '__main__':
    exit(main())
