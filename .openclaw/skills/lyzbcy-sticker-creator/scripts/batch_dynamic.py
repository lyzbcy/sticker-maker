#!/usr/bin/env python3
"""批量生成动态表情"""

import os
import sys
import subprocess
import glob
import shutil
import time

EPISODE = 7
BASE_DIR = f"E:/星星布丁/微信表情包/星星布丁第{EPISODE}弹"
ORIGINAL_DIR = f"{BASE_DIR}/原图"
FRAME_DIR = f"{BASE_DIR}/帧图"
OUTPUT_DIR = f"{BASE_DIR}/成品"

# 动作关键词库
ACTIONS = [
    "waving hand with happy expression",
    "jumping excitedly",
    "spinning around",
    "nodding head",
    "clapping hands",
    "heart gesture with fingers",
    "blowing a kiss",
    "thumbs up with big smile",
    "shrugging shoulders",
    "dancing happily",
    "jumping with joy",
    "bowing politely",
    "patting head gently",
    "stretching arms",
    "cheering with both arms up",
    "peeking from behind hands",
    "winking playfully",
    "giggling and bouncing",
    "covering mouth while laughing",
    "happy spinning with arms out"
]

def generate_9grid_codex(input_image, action):
    """使用 Codex 生成九宫格帧图"""
    
    prompt = f"""Pixel art style, 3x3 grid layout, no gaps, no grid lines, no numbers. 
Each cell is exactly the same size. 
All cells show the same character from image 1. 
From left to right, top to bottom: animation frames 1 to 9, {action}, smooth transitions between frames.
Center composition, proper margins around the character.
Transparent background."""
    
    cmd = f'echo "{prompt}" | codex exec --enable image_generation --sandbox read-only -i "{input_image}"'
    
    # 记录当前图片
    codex_dir = os.path.expanduser('~/.codex/generated_images')
    old_files = glob.glob(os.path.join(codex_dir, '**', '*.png'), recursive=True)
    old_times = {f: os.path.getmtime(f) for f in old_files}
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',
            errors='ignore'
        )
        
        time.sleep(2)
        
        # 查找新图片
        new_files = glob.glob(os.path.join(codex_dir, '**', '*.png'), recursive=True)
        for f in new_files:
            if f not in old_times or os.path.getmtime(f) > old_times.get(f, 0):
                return f
        
        return None
        
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return None

def crop_9grid(input_path, output_dir):
    """裁剪九宫格"""
    from PIL import Image
    
    img = Image.open(input_path)
    width, height = img.size
    cell_w, cell_h = width // 3, height // 3
    
    os.makedirs(output_dir, exist_ok=True)
    
    for i in range(9):
        row, col = i // 3, i % 3
        left, top = col * cell_w, row * cell_h
        cell = img.crop((left, top, left + cell_w, top + cell_h))
        cell.save(os.path.join(output_dir, f'frame_{i+1:02d}.png'))

def make_gif(input_dir, output_path, duration=100):
    """制作 GIF"""
    from PIL import Image
    
    frames = []
    for i in range(1, 10):
        path = os.path.join(input_dir, f'frame_{i:02d}.png')
        if os.path.exists(path):
            frames.append(Image.open(path))
    
    if not frames:
        return False
    
    # 正向 + 反向循环
    all_frames = frames + frames[-2:0:-1]
    
    all_frames[0].save(
        output_path,
        save_all=True,
        append_images=all_frames[1:],
        duration=duration,
        loop=0,
        disposal=2
    )
    
    return True

def main():
    # 获取所有原图
    originals = sorted(
        [f for f in os.listdir(ORIGINAL_DIR) if f.endswith('.png') and f[0].isdigit()],
        key=lambda x: int(x.split('.')[0])
    )
    
    print(f"📦 找到 {len(originals)} 张原图")
    
    # 检查已生成的 GIF
    existing_gifs = set(
        f.replace('.gif', '.png') for f in os.listdir(OUTPUT_DIR) if f.endswith('.gif')
    )
    
    to_process = [f for f in originals if f not in existing_gifs]
    print(f"🎬 需要处理 {len(to_process)} 张")
    
    for idx, orig in enumerate(to_process):
        num = int(orig.split('.')[0])
        print(f"\n=== [{idx+1}/{len(to_process)}] 处理 {orig} ===")
        
        input_path = os.path.join(ORIGINAL_DIR, orig)
        frame_dir = os.path.join(FRAME_DIR, str(num))
        output_path = os.path.join(OUTPUT_DIR, f"{num}.gif")
        
        # 选择动作
        action = ACTIONS[idx % len(ACTIONS)]
        print(f"  动作: {action[:40]}...")
        
        # 生成九宫格
        print(f"  🎨 生成九宫格...")
        grid_path = generate_9grid_codex(input_path, action)
        
        if grid_path:
            print(f"  ✅ 九宫格生成完成")
            
            # 裁剪
            os.makedirs(frame_dir, exist_ok=True)
            crop_9grid(grid_path, frame_dir)
            print(f"  ✅ 裁剪完成")
            
            # 制作 GIF
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            if make_gif(frame_dir, output_path):
                print(f"  ✅ GIF 保存: {output_path}")
            else:
                print(f"  ❌ GIF 制作失败")
        else:
            print(f"  ❌ 九宫格生成失败")

if __name__ == '__main__':
    main()
