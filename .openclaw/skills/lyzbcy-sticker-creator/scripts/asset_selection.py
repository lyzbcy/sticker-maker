#!/usr/bin/env python3
"""
发布素材选图策略

目标：
1. 横幅 / 封面 / 图标默认都选单张优质成品，不再机械拼贴
2. 图标强烈惩罚“脸贴边 / 半边脸 / 构图过挤”
3. 优先选择主体完整、居中、辨识度高的图片
4. 横幅强烈惩罚“整张方图背景 / 黑色底块 / 主体贴边”，避免发布素材像未抠干净的截图
"""

from __future__ import annotations

import math
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    raise

from face_detect import detect_face, get_alpha_bbox


def _clamp(value, low, high):
    return max(low, min(high, value))


def _norm_distance(center, target=0.5):
    return abs(center - target)


def _bbox_touches_edge(bbox, width, height, tolerance=0.04):
    left, top, right, bottom = bbox
    tol_x = width * tolerance
    tol_y = height * tolerance
    return (
        left <= tol_x or
        top <= tol_y or
        right >= width - tol_x or
        bottom >= height - tol_y
    )


def analyze_image(image_path):
    image_path = Path(image_path)
    with Image.open(image_path) as img:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        width, height = img.size
        alpha_bbox = get_alpha_bbox(img)
        if alpha_bbox:
            left, top, right, bottom = alpha_bbox
        else:
            left, top, right, bottom = (0, 0, width, height)

        char_w = max(1, right - left)
        char_h = max(1, bottom - top)
        char_area_ratio = (char_w * char_h) / float(width * height)
        char_center_x = (left + right) / 2.0 / width
        char_center_y = (top + bottom) / 2.0 / height

        face = detect_face(str(image_path), prefer_opencv=True)
        face_bbox = face.get("bbox")
        face_method = face.get("method", "none")
        face_conf = face.get("confidence", 0.0)

        face_area_ratio = 0.0
        face_center_x = 0.5
        face_center_y = 0.5
        face_edge_penalty = 0.0
        if face_bbox:
            fx, fy, fw, fh = face_bbox
            face_area_ratio = (fw * fh) / float(width * height)
            face_center_x = (fx + fw / 2.0) / width
            face_center_y = (fy + fh / 2.0) / height
            face_edge_penalty = 1.0 if _bbox_touches_edge((fx, fy, fx + fw, fy + fh), width, height, tolerance=0.05) else 0.0

        alpha_edge_penalty = 1.0 if _bbox_touches_edge((left, top, right, bottom), width, height, tolerance=0.03) else 0.0
        alpha_values = list(img.getchannel("A").getdata())
        opaque_canvas_ratio = sum(1 for a in alpha_values if a > 250) / float(max(1, len(alpha_values)))

        rgb_img = img.convert("RGB")
        border_samples = []
        step = max(1, min(width, height) // 40)
        for x in range(0, width, step):
            border_samples.append((x, 0))
            border_samples.append((x, height - 1))
        for y in range(0, height, step):
            border_samples.append((0, y))
            border_samples.append((width - 1, y))
        dark_border_hits = 0
        opaque_border_hits = 0
        for x, y in border_samples:
            if img.getpixel((x, y))[3] <= 128:
                continue
            opaque_border_hits += 1
            r, g, b = rgb_img.getpixel((x, y))
            if (r + g + b) / 3.0 < 70:
                dark_border_hits += 1
        dark_border_ratio = dark_border_hits / float(max(1, opaque_border_hits))

        return {
            "path": str(image_path),
            "name": image_path.name,
            "width": width,
            "height": height,
            "aspect_ratio": width / float(max(1, height)),
            "alpha_bbox": (left, top, right, bottom),
            "char_area_ratio": char_area_ratio,
            "char_center_x": char_center_x,
            "char_center_y": char_center_y,
            "face_bbox": face_bbox,
            "face_method": face_method,
            "face_confidence": face_conf,
            "face_area_ratio": face_area_ratio,
            "face_center_x": face_center_x,
            "face_center_y": face_center_y,
            "face_edge_penalty": face_edge_penalty,
            "alpha_edge_penalty": alpha_edge_penalty,
            "opaque_canvas_ratio": opaque_canvas_ratio,
            "dark_border_ratio": dark_border_ratio,
        }


def _score_banner(meta):
    char_size_score = 1.0 - min(abs(meta["char_area_ratio"] - 0.42) / 0.30, 1.0)
    horizontal_score = 1.0 - min(abs(meta["aspect_ratio"] - 1.0) / 0.8, 1.0)
    face_score = min(meta["face_area_ratio"] / 0.07, 1.0) if meta["face_bbox"] else 0.25
    center_score = 1.0 - min(_norm_distance(meta["char_center_x"], 0.5) / 0.28, 1.0)
    edge_penalty = meta["face_edge_penalty"] * 0.35 + meta["alpha_edge_penalty"] * 0.35
    full_canvas_penalty = 0.45 if meta["opaque_canvas_ratio"] > 0.86 else 0.0
    dark_block_penalty = meta["dark_border_ratio"] * 0.35
    return (
        char_size_score * 0.38 +
        horizontal_score * 0.20 +
        face_score * 0.22 +
        center_score * 0.20 -
        edge_penalty -
        full_canvas_penalty -
        dark_block_penalty
    )


def _score_cover(meta):
    char_size_score = 1.0 - min(abs(meta["char_area_ratio"] - 0.48) / 0.28, 1.0)
    face_score = min(meta["face_area_ratio"] / 0.08, 1.0) if meta["face_bbox"] else 0.30
    center_x_score = 1.0 - min(_norm_distance(meta["char_center_x"], 0.5) / 0.22, 1.0)
    center_y_score = 1.0 - min(_norm_distance(meta["char_center_y"], 0.55) / 0.25, 1.0)
    edge_penalty = meta["face_edge_penalty"] * 0.40 + meta["alpha_edge_penalty"] * 0.20
    return (
        char_size_score * 0.35 +
        face_score * 0.28 +
        center_x_score * 0.20 +
        center_y_score * 0.17 -
        edge_penalty
    )


def _score_icon(meta):
    face_present_score = 1.0 if meta["face_bbox"] else 0.15
    face_size_score = 1.0 - min(abs(meta["face_area_ratio"] - 0.12) / 0.10, 1.0) if meta["face_bbox"] else 0.0
    center_x_score = 1.0 - min(_norm_distance(meta["face_center_x"], 0.5) / 0.18, 1.0) if meta["face_bbox"] else 0.0
    center_y_score = 1.0 - min(_norm_distance(meta["face_center_y"], 0.42) / 0.22, 1.0) if meta["face_bbox"] else 0.0
    char_size_score = 1.0 - min(abs(meta["char_area_ratio"] - 0.52) / 0.25, 1.0)
    edge_penalty = meta["face_edge_penalty"] * 0.70 + meta["alpha_edge_penalty"] * 0.25
    return (
        face_present_score * 0.28 +
        face_size_score * 0.24 +
        center_x_score * 0.16 +
        center_y_score * 0.14 +
        char_size_score * 0.18 -
        edge_penalty
    )


def rank_images(image_paths, asset_type):
    metas = [analyze_image(p) for p in image_paths]
    scorer = {
        "banner": _score_banner,
        "cover": _score_cover,
        "icon": _score_icon,
    }[asset_type]

    ranked = []
    for meta in metas:
        score = scorer(meta)
        ranked.append((score, meta))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def pick_best_image(image_paths, asset_type):
    ranked = rank_images(image_paths, asset_type)
    if not ranked:
        return None, []
    return ranked[0][1]["path"], ranked
