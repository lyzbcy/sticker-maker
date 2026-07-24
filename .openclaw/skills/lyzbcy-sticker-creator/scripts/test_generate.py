#!/usr/bin/env python3
"""测试脚本 - 生成更多 AI 模板原图"""

import os
import sys
import subprocess
import shutil

sys.path.insert(0, os.path.dirname(__file__))
from main import StickerAutomation

auto = StickerAutomation(7, 'static')

# 生成 2 组 AI 模板四宫格
for i in range(2):
    print(f'\n=== 第 {i+1} 组 AI 模板 ===')
    
    # 获取动作组合
    emotions = auto.get_unique_combinations(4)
    print(f'动作组合: {emotions}')
    
    # 生成
    result = auto.generate_quad_with_codex(emotions=emotions)
    
    if result:
        # 复制
        output = f'E:/星星布丁/微信表情包/星星布丁第7弹/原图/quad_ai_{i+1}.png'
        shutil.copy(result, output)
        print(f'已保存: {output}')
        
        # 裁剪
        start = 9 + i * 4
        script_dir = os.path.dirname(__file__)
        cmd = f'python "{script_dir}/crop_4grid.py" --input "{output}" --output "E:/星星布丁/微信表情包/星星布丁第7弹/原图" --start {start}'
        subprocess.run(cmd, shell=True, capture_output=True)
        print(f'已裁剪: {start}.png ~ {start+3}.png')

print('\n完成！')
