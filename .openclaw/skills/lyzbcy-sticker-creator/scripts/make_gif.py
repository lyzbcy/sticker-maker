#!/usr/bin/env python3
"""
GIF 帧拼接脚本

功能：将多张帧图拼接成循环播放的GIF

输入：
    - 帧图目录（包含 frame_01.png ~ frame_09.png）
    - 输出GIF路径

输出：
    - 循环播放的GIF

帧序策略：
    原始帧: 1-2-3-4-5-6-7-8-9
    循环帧: 1-2-3-4-5-6-7-8-9-8-7-6-5-4-3-2（首尾相连，无限循环）

使用方式：
    python make_gif.py --input ./帧图/1/ --output ./output.gif
"""

import argparse
import os
import glob
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("请安装 Pillow: pip install Pillow")
    exit(1)


def encode_rgba_frames(frames, output_path, durations):
    """Encode the supplied timeline with one palette; never invent extra frames."""
    if len(frames) < 2 or len(frames) != len(durations):
        raise ValueError('At least two frames and matching durations required')
    if any(d <= 0 or d % 10 for d in durations):
        raise ValueError('GIF durations must be positive multiples of 10 ms')
    frames = [f.convert('RGBA') for f in frames]
    w, h = frames[0].size
    if any(f.size != (w, h) for f in frames):
        raise ValueError('Use one common canvas before encoding')
    atlas = Image.new('RGB', (w * len(frames), h), 'white')
    for i, f in enumerate(frames):
        atlas.paste(f, (i * w, 0), f)
    palette = atlas.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    encoded = []
    for f in frames:
        rgb = Image.new('RGB', f.size, 'white')
        rgb.paste(f, mask=f.getchannel('A'))
        q = rgb.quantize(palette=palette, dither=Image.Dither.NONE)
        q.paste(255, mask=f.getchannel('A').point(lambda a: 255 if a < 128 else 0))
        q.info['transparency'] = 255
        encoded.append(q)
    dest = Path(output_path)
    if dest.exists():
        raise FileExistsError(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    encoded[0].save(dest, save_all=True, append_images=encoded[1:],
                    duration=durations, loop=0, disposal=2, transparency=255,
                    optimize=False)
    actual = []
    with Image.open(dest) as gif:
        for i in range(gif.n_frames):
            gif.seek(i)
            actual.append(gif.info['duration'])
            if gif.convert('RGBA').getpixel((0, 0))[3] != 0:
                raise ValueError('Transparent corner lost after encoding')
        if sum(actual) != sum(durations) or gif.info.get('loop') != 0:
            raise ValueError('Encoded timeline mismatch')
    return {'frames': len(actual), 'durations_ms': actual, 'total_ms': sum(actual),
            'size': [w, h], 'bytes': dest.stat().st_size, 'loop': 0}


def create_loop_gif(frame_dir: str, output_path: str, duration: int = 100):
    """
    将帧图拼接成循环GIF
    
    Args:
        frame_dir: 帧图目录
        output_path: 输出GIF路径
        duration: 每帧持续时间（毫秒）
    """
    # 获取所有帧图
    frame_files = sorted(glob.glob(os.path.join(frame_dir, "frame_*.png")))
    
    if len(frame_files) < 2:
        print(f"错误: 帧图数量不足，需要至少2张，当前 {len(frame_files)} 张")
        return None
    
    # 加载帧图
    frames = [Image.open(f) for f in frame_files]
    
    # 创建循环帧序列: 1-2-3-...-9-8-7-...-2
    # 这样GIF播放时会首尾相连，无限循环
    loop_indices = list(range(len(frames))) + list(range(len(frames) - 2, 0, -1))
    # 例如: [0,1,2,3,4,5,6,7,8,7,6,5,4,3,2,1] (如果有9帧)
    
    loop_frames = [frames[i] for i in loop_indices]
    
    # 保存为GIF
    first_frame = loop_frames[0]
    first_frame.save(
        output_path,
        format="GIF",
        append_images=loop_frames[1:],
        save_all=True,
        duration=duration,
        loop=0,  # 无限循环
        disposal=2,  # 清除前一帧
    )
    
    print(f"已保存: {output_path}")
    print(f"  帧数: {len(loop_frames)} (原始 {len(frames)} 帧)")
    print(f"  每帧时长: {duration}ms")
    print(f"  总时长: {len(loop_frames) * duration / 1000:.1f}s")
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description="GIF帧拼接")
    parser.add_argument("--input", "-i", required=True, help="帧图目录")
    parser.add_argument("--output", "-o", required=True, help="输出GIF路径")
    parser.add_argument("--duration", "-d", type=int, default=100, help="每帧时长（毫秒，默认100）")
    
    args = parser.parse_args()
    
    # 检查输入目录
    if not os.path.isdir(args.input):
        print(f"错误: 找不到目录 {args.input}")
        return 1
    
    # 创建输出目录（如果需要）
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # 执行拼接
    result = create_loop_gif(args.input, args.output, args.duration)
    
    if result:
        print(f"\n✅ GIF创建成功！")
        return 0
    else:
        print("\n❌ GIF创建失败")
        return 1


if __name__ == "__main__":
    exit(main())
