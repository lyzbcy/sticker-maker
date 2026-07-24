#!/usr/bin/env python3
"""
微信表情包自动化主程序

功能：
1. 初始化文件夹结构
2. 调用 Codex CLI 生成图片（使用参考图或 AI 模板）
3. 裁剪图片
4. 生成 GIF（可选）
5. 发布到微信表情平台（可选）

使用方式：
    python main.py --episode 6 --type static
    python main.py --episode 6 --type dynamic --publish
    python main.py --episode 6 --mode duo  # 双人模式
"""

import argparse
import os
import json
import re
import subprocess
import random
import shutil
import glob
from datetime import datetime
from pathlib import Path
import yaml

# 脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)

def load_config():
    """加载配置文件"""
    config_path = os.path.join(SKILL_DIR, 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_keywords():
    """加载关键词库"""
    keywords_path = os.path.join(SKILL_DIR, 'keywords.json')
    with open(keywords_path, 'r', encoding='utf-8') as f:
        return json.load(f)


class StickerAutomation:
    """微信表情包自动化"""
    
    def __init__(self, episode: int, sticker_type: str = 'static', mode: str = 'auto', grid_size: int = 2):
        self.episode = episode
        self.sticker_type = sticker_type
        self.mode = mode  # single, duo, quad, auto（自动随机）
        self.grid_size = grid_size  # ⭐ 宫格大小：2=四宫格, 3=九宫格, 4=十六宫格
        self.config = load_config()
        self.keywords = load_keywords()
        self.output_dir = os.path.join(self.config['project']['output_dir'], f'周三涵做表情{episode}')
        self.state_file = os.path.join(self.config['project']['output_dir'], '.openclaw', 'state.json')
    
    def choose_random_mode(self):
        """随机选择模式（根据配置的概率）"""
        probs = self.config['mode_probabilities']
        rand = random.random()
        
        if rand < probs['single']:
            return 'single'
        elif rand < probs['single'] + probs['duo']:
            return 'duo'
        else:
            return 'quad'
    
    def choose_single_character(self):
        """随机选择单人模式的角色（根据配置的概率）"""
        probs = self.config['single_character_probabilities']
        rand = random.random()
        
        cumulative = 0
        for char, prob in probs.items():
            cumulative += prob
            if rand < cumulative:
                return char
        
        return list(probs.keys())[0]  # 默认返回第一个
    
    def choose_xingxing_costume(self):
        """随机选择星星布丁的衣服版本（根据配置的概率）"""
        probs = self.config['xingxing_pudding_costume_probabilities']
        rand = random.random()
        
        cumulative = 0
        for costume, prob in probs.items():
            cumulative += prob
            if rand < cumulative:
                return costume
        
        return 'base3'  # 默认返回base3
    
    def get_base_image(self, character):
        """获取角色的base图路径（支持星星布丁多衣服版本）"""
        base_config = self.config['base_images'][character]
        
        if character == '星星布丁' and isinstance(base_config, dict):
            # 星星布丁有多套衣服，随机选择
            costume = self.choose_xingxing_costume()
            print(f'    👗 星星布丁衣服: {costume}')
            return base_config[costume]
        elif isinstance(base_config, dict):
            # 其他角色的dict配置，取第一个
            return list(base_config.values())[0]
        else:
            # 直接是路径字符串
            return base_config
        
    def init_folders(self):
        """初始化文件夹结构（遵循统一规范）"""
        print(f'📁 创建文件夹结构: {self.output_dir}')
        
        # 统一规范的文件夹结构
        folders = ['参考图', '原图', '原图_透明ChromaKey', '最终版',
                   '横幅', '封面', '图标']  # ⭐ 新增发布素材目录
        if self.sticker_type == 'dynamic':
            folders.append('帧图')
        
        for folder in folders:
            path = os.path.join(self.output_dir, folder)
            os.makedirs(path, exist_ok=True)
            print(f'  ✓ {folder}/')
        
        print('✅ 文件夹结构创建完成')
    
    def get_reference_count(self, mode=None):
        """获取可用参考图数量（根据模式过滤）
        - 单人/四人模式：排除【双人】标签的图
        - 双人模式：全部可用
        """
        ref_dir = self.config['reference_library']
        if not os.path.exists(ref_dir):
            return 0
        
        images = list(Path(ref_dir).glob('*.png'))
        images.extend(Path(ref_dir).glob('*.jpg'))
        
        if mode in ('single', 'quad'):
            return sum(1 for img in images if '双人' not in img.name)
        elif mode == 'duo':
            return len(images)
        elif mode == 'auto':
            # 自动模式未知下组模式 → 取保守值（单人数量）
            return sum(1 for img in images if '双人' not in img.name)
        return len(images)
    
    def extract_meaning_from_ref(self, ref_path):
        """从参考图文件名提取含义词和双人标签
        ref_开心比耶.png → 开心比耶
        reg_开心比耶.png → 开心比耶
        【双人】拥抱.png → 拥抱
        ref_001.png → 空字符串
        """
        basename = os.path.basename(ref_path)
        name = os.path.splitext(basename)[0]
        
        # 去掉 ref_ 前缀（兼容旧格式）
        if name.startswith('ref_'):
            name = name[4:]
        
        # 去掉【双人】标签
        name = re.sub(r'【双人】', '', name).strip()
        
        # 纯数字编号 → 无法提取
        if re.match(r'^[\d_]+$', name):
            return ''
        return name
    
    def get_local_references(self, count: int = 4, mode: str = 'single'):
        """获取参考图（按模式过滤，按创建时间取最早）
        - 双人模式：【双人】优先，不足用普通图补齐
        - 单人/四人模式：只用普通图（排除【双人】）
        """
        ref_dir = self.config['reference_library']
        
        images = list(Path(ref_dir).glob('*.png'))
        images.extend(Path(ref_dir).glob('*.jpg'))
        
        if not images:
            return []
        
        # 按创建时间排序（升序 → 最早的优先使用）
        images.sort(key=lambda x: x.stat().st_ctime)
        
        # 分类
        duo_imgs = [img for img in images if '双人' in img.name]
        solo_imgs = [img for img in images if '双人' not in img.name]
        
        if mode == 'duo':
            # 双人模式：【双人】优先，不足用普通图补齐
            selected = duo_imgs[:count]
            remaining = count - len(selected)
            if remaining > 0:
                selected.extend(solo_imgs[:remaining])
        else:
            # 单人/四人/auto：只用普通图
            selected = solo_imgs[:count]
        
        return [str(img) for img in selected]
    
    def move_used_references(self, refs):
        """移动已使用的参考图到'已使用'文件夹"""
        used_dir = os.path.join(self.config['reference_library'], '已使用')
        os.makedirs(used_dir, exist_ok=True)
        
        for ref in refs:
            if os.path.exists(ref):
                filename = os.path.basename(ref)
                dest = os.path.join(used_dir, filename)
                # 如果目标文件已存在，添加时间戳
                if os.path.exists(dest):
                    base, ext = os.path.splitext(filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    dest = os.path.join(used_dir, f'{base}_{timestamp}{ext}')
                shutil.move(ref, dest)
                print(f'  📦 已移动: {filename} → 已使用/')
    
    def get_unique_combinations(self, count: int = 4):
        """获取不重复的动作组合（支持2×2/3×3/4×4不同数量）"""
        used_file = os.path.join(SKILL_DIR, 'used_combinations.txt')
        
        # 读取已使用的组合
        used = set()
        if os.path.exists(used_file):
            with open(used_file, 'r', encoding='utf-8') as f:
                used = set(line.strip() for line in f if line.strip())
        
        emotions = self.keywords['emotions']
        actions = self.keywords['actions']
        
        # 生成不重复的组合
        combinations = []
        max_attempts = 200
        
        for _ in range(count):
            attempts = 0
            while attempts < max_attempts:
                emotion = random.choice(emotions)
                action = random.choice(actions)
                combo = f'{emotion}_{action}'
                
                if combo not in used:
                    used.add(combo)
                    combinations.append(combo)
                    break
                
                attempts += 1
            
            if attempts >= max_attempts:
                # 如果尝试太多次，随机生成一个
                combinations.append(f'{random.choice(emotions)}_{random.choice(actions)}')
        
        # 保存已使用的组合
        with open(used_file, 'w', encoding='utf-8') as f:
            for combo in used:
                f.write(combo + '\n')
        
        return combinations
    
    def generate_quad_with_codex(self, refs=None, emotions=None, background_mode='transparent', character=None):
        """使用 Codex CLI 生成宫格图（支持2×2/3×3/4×4）"""
        
        g = self.grid_size  # 宫格大小
        total_cells = g * g  # 总格数
        
        # 记录当前最新的图片时间戳
        codex_dir = os.path.expanduser('~/.codex/generated_images')
        old_files = glob.glob(os.path.join(codex_dir, '**', '*.png'), recursive=True)
        old_times = {f: os.path.getmtime(f) for f in old_files}
        
        if self.mode == 'quad':
            # 四人模式（家庭彩蛋）—— 仅 2×2 支持
            print(f'  👨‍👩‍👧‍👦 使用四人模式（家庭彩蛋）')
            quad_bases = self.config['quad_bases']
            base_images = [self.get_base_image(name) for name in quad_bases]
            
            if refs:
                print(f'  📦 使用参考图模式（四人）')
                prompt = self.config['prompts']['reference_quad']
                cmd = f'codex exec --enable image_generation --sandbox read-only'
                for base in base_images:
                    cmd += f' -i "{base}"'
                for ref in refs:
                    cmd += f' -i "{ref}"'
            else:
                print(f'  🎨 使用 AI 模板模式（四人）')
                prompt_template = self.config['prompts']['ai_quad']
                prompt = prompt_template.format(
                    emotion_1=emotions[0], emotion_2=emotions[1],
                    emotion_3=emotions[2], emotion_4=emotions[3]
                )
                cmd = f'codex exec --enable image_generation --sandbox read-only'
                for base in base_images:
                    cmd += f' -i "{base}"'
                    
        elif self.mode == 'duo':
            # 双人模式 —— 仅 2×2 支持
            print(f'  💑 使用双人模式')
            duo_bases = self.config['duo_bases']
            base_image_1 = self.get_base_image(duo_bases[0])
            base_image_2 = self.get_base_image(duo_bases[1])
            
            if refs:
                print(f'  📦 使用参考图模式（双人）')
                prompt = self.config['prompts']['reference_duo']
                cmd = f'codex exec --enable image_generation --sandbox read-only'
                cmd += f' -i "{base_image_1}"'
                cmd += f' -i "{base_image_2}"'
                for ref in refs:
                    cmd += f' -i "{ref}"'
            else:
                print(f'  🎨 使用 AI 模板模式（双人）')
                prompt_template = self.config['prompts']['ai_duo']
                prompt = prompt_template.format(
                    emotion_1=emotions[0], emotion_2=emotions[1],
                    emotion_3=emotions[2], emotion_4=emotions[3]
                )
                cmd = f'codex exec --enable image_generation --sandbox read-only'
                cmd += f' -i "{base_image_1}"'
                cmd += f' -i "{base_image_2}"'
        else:
            # 单人模式（支持多角色概率 + 多宫格 ⭐）
            if character:
                chosen_char = character
            else:
                chosen_char = self.choose_single_character()
            
            print(f'  👤 使用单人模式 - 角色: {chosen_char}')
            base_image = self.get_base_image(chosen_char)
            
            if refs:
                # 参考图模式
                print(f'  📦 使用参考图模式（单人 {g}×{g}）')
                # 根据宫格选择 prompt
                if g == 2:
                    prompt = self.config['prompts']['reference']
                elif g == 3:
                    prompt = self.config['prompts']['reference_9grid']
                elif g == 4:
                    prompt = self.config['prompts']['reference_16grid']
                else:
                    prompt = self.config['prompts']['reference']
                
                cmd = f'codex exec --enable image_generation --sandbox read-only'
                cmd += f' -i "{base_image}"'
                for ref in refs:
                    cmd += f' -i "{ref}"'
            else:
                # AI 模板模式
                print(f'  🎨 使用 AI 模板模式（单人 {g}×{g}）')
                
                # 根据宫格选择 prompt
                if g == 2:
                    if background_mode == 'transparent':
                        prompt_template = self.config['prompts']['ai_transparent']
                    else:
                        background = random.choice([b for b in self.keywords['backgrounds'] if b != 'transparent background'])
                        prompt_template = self.config['prompts']['ai_with_background']
                        prompt = prompt_template.format(
                            emotion_1=emotions[0], emotion_2=emotions[1],
                            emotion_3=emotions[2], emotion_4=emotions[3],
                            background=background
                        )
                        cmd = f'codex exec --enable image_generation --sandbox read-only'
                        cmd += f' -i "{base_image}"'
                        # 已经是完整 prompt，直接往下走
                        print(f'  📤 发送请求...')
                        print(f'  Prompt: {prompt[:80]}...')
                        prompt_file = os.path.join(SKILL_DIR, 'temp_prompt.txt')
                        with open(prompt_file, 'w', encoding='utf-8') as f:
                            f.write(prompt)
                        full_cmd = f'Get-Content -Path "{prompt_file}" -Encoding UTF8 | {cmd}'
                        # 跳到执行
                        result = subprocess.run(
                            ['powershell', '-Command', full_cmd],
                            capture_output=True, text=True, timeout=300,
                            encoding='utf-8', errors='ignore'
                        )
                        print(f'  ✅ Codex 执行完成')
                        import time
                        time.sleep(2)
                        new_files = glob.glob(os.path.join(codex_dir, '**', '*.png'), recursive=True)
                        for f in new_files:
                            if f not in old_times or os.path.getmtime(f) > old_times.get(f, 0):
                                print(f'  📁 找到新图片: {os.path.basename(f)}')
                                return f
                        if new_files:
                            new_files.sort(key=os.path.getmtime, reverse=True)
                            return new_files[0]
                        return None
                
                elif g == 3:
                    prompt_template = self.config['prompts']['ai_9grid']
                elif g == 4:
                    prompt_template = self.config['prompts']['ai_16grid']
                else:
                    prompt_template = self.config['prompts']['ai_transparent']
                
                # 格式化 emotions（动态适配数量）
                if g == 2:
                    prompt = prompt_template.format(
                        emotion_1=emotions[0], emotion_2=emotions[1],
                        emotion_3=emotions[2], emotion_4=emotions[3]
                    )
                elif g == 3:
                    prompt = prompt_template.format(
                        emotion_1=emotions[0], emotion_2=emotions[1], emotion_3=emotions[2],
                        emotion_4=emotions[3], emotion_5=emotions[4], emotion_6=emotions[5],
                        emotion_7=emotions[6], emotion_8=emotions[7], emotion_9=emotions[8]
                    )
                elif g == 4:
                    prompt = prompt_template.format(
                        emotion_1=emotions[0], emotion_2=emotions[1], emotion_3=emotions[2], emotion_4=emotions[3],
                        emotion_5=emotions[4], emotion_6=emotions[5], emotion_7=emotions[6], emotion_8=emotions[7],
                        emotion_9=emotions[8], emotion_10=emotions[9], emotion_11=emotions[10], emotion_12=emotions[11],
                        emotion_13=emotions[12], emotion_14=emotions[13], emotion_15=emotions[14], emotion_16=emotions[15]
                    )
                
                cmd = f'codex exec --enable image_generation --sandbox read-only'
                cmd += f' -i "{base_image}"'
        
        print(f'  📤 发送请求...')
        print(f'  Prompt: {prompt[:80]}...')
        
        # 写入临时文件
        prompt_file = os.path.join(SKILL_DIR, 'temp_prompt.txt')
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        # 构建完整命令
        full_cmd = f'Get-Content -Path "{prompt_file}" -Encoding UTF8 | {cmd}'
        
        try:
            result = subprocess.run(
                ['powershell', '-Command', full_cmd],
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                errors='ignore'
            )
            
            print(f'  ✅ Codex 执行完成')
            
            # 等待一下让文件系统同步
            import time
            time.sleep(2)
            
            # 查找新生成的图片（比旧图片更新的）
            new_files = glob.glob(os.path.join(codex_dir, '**', '*.png'), recursive=True)
            for f in new_files:
                if f not in old_times or os.path.getmtime(f) > old_times.get(f, 0):
                    print(f'  📁 找到新图片: {os.path.basename(f)}')
                    return f
            
            # 如果没找到新的，返回最新的
            if new_files:
                new_files.sort(key=os.path.getmtime, reverse=True)
                return new_files[0]
            
            return None
            
        except subprocess.TimeoutExpired:
            print(f'  ❌ 生成超时')
            return None
        except Exception as e:
            print(f'  ❌ 错误: {e}')
            return None
    
    def _find_latest_codex_image(self):
        """查找 Codex CLI 最新生成的图片"""
        codex_dir = os.path.expanduser('~/.codex/generated_images')
        if not os.path.exists(codex_dir):
            return None
        
        pattern = os.path.join(codex_dir, '**', '*.png')
        files = glob.glob(pattern, recursive=True)
        
        if not files:
            return None
        
        files.sort(key=os.path.getmtime, reverse=True)
        return files[0]
    
    def generate_quad_images(self, count: int = 3):
        """生成宫格图片（参考图优先，库存不足时回退 AI 模板，支持2×2/3×3/4×4）"""
        
        g = self.grid_size
        total_cells = g * g  # 每组的格子数
        characters_used = set()
        all_meanings = {}  # {图片序号: 含义词}
        
        grid_names = {2: '四宫格(2×2)', 3: '九宫格(3×3)', 4: '十六宫格(4×4)'}
        print(f'🔲 宫格模式: {grid_names.get(g, f"{g}×{g}")}，每组 {total_cells} 格')
        
        # 如果是auto模式，每组随机选择模式
        for i in range(count):
            if self.mode == 'auto':
                current_mode = self.choose_random_mode()
                self.mode = current_mode
            else:
                current_mode = self.mode
            
            # 追踪角色
            if current_mode == 'single':
                chosen_char = self.choose_single_character()
                characters_used.add(chosen_char)
            elif current_mode == 'duo':
                characters_used.update(self.config['duo_bases'])
            elif current_mode == 'quad':
                characters_used.update(self.config['quad_bases'])
            
            mode_text = {'single': '单人', 'duo': '双人', 'quad': '四人(家庭彩蛋)'}
            print(f'\n🎨 第 {i+1}/{count} 组 - {mode_text.get(current_mode, current_mode)}模式')
            
            # 检查参考图库存（按模式过滤）
            ref_count = self.get_reference_count(mode=current_mode)
            # 参考图需要 >= total_cells（3×3需要9张，4×4需要16张）
            # 但 3×3/4×4 时参考图可能不够，降低阈值或回退 AI
            min_refs = total_cells if g == 2 else min(total_cells, 9)
            print(f'  📊 参考图库存: {ref_count} 张（{current_mode}模式可用，需要 ≥ {min_refs}）')
            
            if ref_count >= min_refs:
                # ===== 参考图模式 =====
                refs = self.get_local_references(count=total_cells, mode=current_mode)
                
                # 从文件名提取含义词
                meanings = []
                for ref in refs:
                    meaning = self.extract_meaning_from_ref(ref)
                    if meaning:
                        meanings.append(meaning)
                    else:
                        meanings.append('')
                
                if any(not m for m in meanings):
                    print(f'  ⚠️  部分参考图无法提取含义词')
                else:
                    print(f'  📋 含义词: {meanings[:6]}{"..." if len(meanings) > 6 else ""}')
                
                result = self.generate_quad_with_codex(refs=refs)
                
                if result:
                    self.move_used_references(refs)
            else:
                # ===== AI 模板模式（回退）=====
                print(f'  ⚠️  参考图库存不足（{ref_count} < {min_refs}），回退到 AI 模板模式')
                emotions = self.get_unique_combinations(total_cells)
                print(f'  🎭 动作组合: {emotions[:4]}{"..." if len(emotions) > 4 else ""}')
                
                # 含义词从情绪组合推导
                meanings = [e.replace('_', '') for e in emotions]
                
                result = self.generate_quad_with_codex(emotions=emotions)
            
            if result:
                # 复制到输出目录
                output_path = os.path.join(self.output_dir, '原图', f'quad_{i+1}.png')
                shutil.copy(result, output_path)
                print(f'  📁 已保存: {output_path}')
                
                # 裁剪（根据宫格大小）
                self.crop_quad_image(output_path, i * total_cells + 1)
                
                # 追踪含义词
                for j, meaning in enumerate(meanings):
                    all_meanings[i * total_cells + j + 1] = meaning
        
        print(f'\n✅ 宫格图片生成完成（{g}×{g}，共 {count * total_cells} 格）')
        
        # 写角色卡
        if characters_used:
            self.write_character_card(characters_used)
        
        # 自动重命名为含义词
        self.auto_rename_to_final(all_meanings)
        
        return characters_used
    
    def crop_quad_image(self, input_path: str, start_index: int):
        """裁剪宫格图片（使用统一 crop_grid.py，支持2×2/3×3/4×4）"""
        g = self.grid_size
        grid_names = {2: '四宫格', 3: '九宫格', 4: '十六宫格'}
        print(f'  ✂️ 裁剪{grid_names.get(g, f"{g}×{g}")}...')
        
        output_dir = os.path.join(self.output_dir, '原图')
        script_path = os.path.join(SKILL_DIR, 'scripts', 'crop_grid.py')
        
        if not os.path.exists(script_path):
            print(f'  ⚠️  裁剪脚本不存在，尝试旧脚本...')
            # 回退到旧脚本
            if g == 2:
                script_path = os.path.join(SKILL_DIR, 'scripts', 'crop_4grid.py')
            elif g == 3:
                script_path = os.path.join(SKILL_DIR, 'scripts', 'crop_9grid.py')
        
        grid_pad = self.config.get('crop', {}).get(f'grid_{g}_padding')
        pad_arg = f' --padding {grid_pad}' if grid_pad is not None else ''
        cmd = f'python "{script_path}" --input "{input_path}" --output "{output_dir}" --grid {g} --start {start_index}{pad_arg}'
        
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(f'  ✅ 裁剪完成')
            else:
                print(f'  ⚠️ 裁剪输出: {result.stderr[:200]}')
        except Exception as e:
            print(f'  ❌ 裁剪失败: {e}')
    
    def process_chroma_key(self):
        """Chroma-key处理：移除洋红色背景

        色值必须与生图 prompt 里的洋红严格一致（见 config.yaml chroma_key）。
        历史问题：旧实现用 --auto-key border 动态采样，色值漂移导致抠图质量差；
        现改为从 config 读取 --key-color 显式传入。
        """
        print(f'\n🎨 Chroma-key 处理...')

        # 从 config 读取统一色值（生图端与抠图端对齐的唯一来源）
        chroma_cfg = self.config.get('chroma_key', {})
        key_color = chroma_cfg.get('background_color', '#ff00ff')

        input_dir = os.path.join(self.output_dir, '原图')
        output_dir = os.path.join(self.output_dir, '原图_透明ChromaKey')

        chroma_script = os.path.expanduser('~/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py')

        if not os.path.exists(chroma_script):
            print(f'  ⚠️  Chroma-key 脚本不存在，跳过')
            return

        # 处理每张图片
        images = list(Path(input_dir).glob('*.png'))

        for img in images:
            input_path = str(img)
            output_path = os.path.join(output_dir, img.name)

            # 色度键参数全部从 config.yaml chroma_key 节读取（单一来源）。
            # ⚠️ 关键教训：绝不开启 soft-matte。3D黏土角色的粉肤色 RGB 与洋红 key
            #   (255,0,255) 在 dominance 判定下相似，soft-matte 会把皮肤大面积抠成
            #   半透明（实测半透明占比 1.8%→43%，皮肤镂空残破）。必须用纯硬阈值。
            # 参数来源：对 14/17/18 弹现存好成品做网格搜索（5轮/上百组）复现，
            #   auto-key border + tolerance 85 + edge_contract 1 + edge_feather 0
            #   的 alpha 一致率 97.4%，是 remove_chroma_key.py 的最佳复现。
            # edge_contract 1：收缩 alpha 蒙版 1px，吃掉洋红背景×角色色的混色边，
            #   把边缘洋红像素从 ~460 降到 0。详见 config.yaml 同节 note。
            auto_key = chroma_cfg.get('auto_key', 'border')
            tolerance = chroma_cfg.get('tolerance', 150)
            edge_feather = chroma_cfg.get('edge_feather', 0)
            edge_contract = chroma_cfg.get('edge_contract', 1)
            soft_matte = chroma_cfg.get('soft_matte', True)
            transparent_threshold = chroma_cfg.get('transparent_threshold', 150)
            opaque_threshold = chroma_cfg.get('opaque_threshold', 155)
            soft_flag = '--soft-matte' if soft_matte else ''
            # soft-matte 模式下传透明/不透明阈值，让阴影区(≤150)全透明、
            # 过渡区(150-155)半透明渐变消除锯齿、≥155全保留（不碰肤色156）
            soft_thresh_flag = (f'--transparent-threshold {transparent_threshold} '
                                f'--opaque-threshold {opaque_threshold}') if soft_matte else ''
            cmd = (f'python "{chroma_script}" --input "{input_path}" --out "{output_path}" '
                   f'--key-color {key_color} --auto-key {auto_key} '
                   f'--tolerance {tolerance} {soft_flag} {soft_thresh_flag} '
                   f'--edge-contract {edge_contract} --edge-feather {edge_feather} --force')

            try:
                subprocess.run(cmd, shell=True, capture_output=True, text=True)
                print(f'  ✅ {img.name}')
            except Exception as e:
                print(f'  ❌ {img.name}: {e}')

        print(f'  ✅ Chroma-key 处理完成 (key-color={key_color})')

        # 记录生产日志（防漏步：透明化是必经步骤）
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from production_log import log_step_rich
            from collections import Counter
            from PIL import Image as _Img
            trans_pcts = []
            magenta_edges_total = 0
            for img in images:
                out_p = os.path.join(output_dir, img.name)
                if os.path.exists(out_p):
                    im = _Img.open(out_p)
                    if im.mode == 'RGBA':
                        total = im.size[0] * im.size[1]
                        a_hist = Counter(im.getchannel('A').getdata())
                        trans = a_hist.get(0, 0)
                        trans_pcts.append(trans * 100 // total)
            avg = sum(trans_pcts) // len(trans_pcts) if trans_pcts else 0
            trans_min = min(trans_pcts) if trans_pcts else 0
            trans_max = max(trans_pcts) if trans_pcts else 0
            log_step_rich(self.output_dir, "透明化",
                          "OK" if trans_pcts else "FAIL",
                          step_data={
                              "key_color": key_color,
                              "count": len(trans_pcts),
                              "transparent_pct_avg": avg,
                              "transparent_pct_min": trans_min,
                              "transparent_pct_max": trans_max,
                          },
                          details=f"chroma-key 完成，处理 {len(images)} 张，"
                                  f"透明度 {trans_min}-{trans_max}%（均{avg}%）")
        except Exception as e:
            print(f'  ⚠️ 生产日志写入失败: {e}')
    
    def write_character_card(self, characters_used):
        """生成本次制作角色.md（供发布 skill 读取）"""
        card_path = os.path.join(self.output_dir, '本次制作角色.md')
        
        has_laoyu = '捞鱼' in characters_used
        has_xingxing = '星星布丁' in characters_used
        has_zhou3 = '周三涵' in characters_used
        has_zhou5 = '周五涵' in characters_used
        
        character_list = []
        for char in ['星星布丁', '捞鱼', '周三涵', '周五涵']:
            if char in characters_used:
                character_list.append(f'- {char}')
        
        content = f'''# 本次制作角色

## 基本信息
- 弹次：{os.path.basename(self.output_dir)}
- 类型：{'静态表情' if self.sticker_type == 'static' else '动态表情'}
- 模式：{self.mode}
- 生成日期：{datetime.now().strftime('%Y-%m-%d')}

## 角色列表
{chr(10).join(character_list)}

## 含捞鱼：{'是' if has_laoyu else '否'}

## 发布指引（供 lyzbcy-sticker-publisher 读取）
- 含捞鱼：{'是 → 选择「人物合辑(包含以上多个)」' if has_laoyu else '否 → 选择「女人」'}
'''
        
        with open(card_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f'\n📋 已生成本次制作角色.md → {card_path}')
    
    def auto_rename_to_final(self, meanings: dict):
        """使用生成时追踪的含义词自动重命名到最终版目录
        meanings: {序号: 含义词}  如 {1: '开心比耶', 2: '生气跺脚', ...}
        自动适配不同宫格大小的文件命名格式
        """
        print(f'\n📝 自动重命名为含义词...')
        
        # 优先使用透明 ChromaKey 目录
        input_dir = os.path.join(self.output_dir, '原图_透明ChromaKey')
        if not os.path.exists(input_dir) or not list(Path(input_dir).glob('*.png')):
            input_dir = os.path.join(self.output_dir, '原图')
        
        output_dir = os.path.join(self.output_dir, '最终版')
        os.makedirs(output_dir, exist_ok=True)
        
        g = self.grid_size
        
        # 根据宫格大小确定源文件命名格式
        if g == 2:
            # 2×2： 1.png, 2.png, 3.png, 4.png
            get_src_name = lambda idx: f'{idx}.png'
        elif g == 3:
            # 3×3： frame_01.png, frame_02.png, ...
            get_src_name = lambda idx: f'frame_{idx:02d}.png'
        elif g == 4:
            # 4×4： grid_01.png, grid_02.png, ...
            get_src_name = lambda idx: f'grid_{idx:02d}.png'
        else:
            get_src_name = lambda idx: f'{idx}.png'
        
        renamed = 0
        for index, meaning in sorted(meanings.items()):
            if not meaning:
                meaning = f'图{index}'
                print(f'  ⚠️  序号 {index} 含义词为空，使用默认名: {meaning}')
            
            src_name = get_src_name(index)
            src = os.path.join(input_dir, src_name)
            if os.path.exists(src):
                dst = os.path.join(output_dir, f'{meaning}.png')
                shutil.copy2(src, dst)
                print(f'  ✅ {src_name} → {meaning}.png')
                renamed += 1
            else:
                print(f'  ❌ 找不到源文件: {src}')
        
        print(f'  📁 共重命名 {renamed} 张图片到 {output_dir}')
    
    def generate_assets(self):
        """生成发布素材：横幅(750×400)、封面(240×240)、图标(50×50)"""
        print(f'\n🎨 生成发布素材（横幅/封面/图标）...')
        print('=' * 40)
        
        assets_script = os.path.join(SCRIPT_DIR, 'make_assets.py')
        
        if not os.path.exists(assets_script):
            print(f'  ⚠️  make_assets.py 不存在，跳过')
            return
        
        cmd = f'python "{assets_script}" --dir "{self.output_dir}"'
        
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            print(result.stdout)
            if result.returncode != 0:
                print(result.stderr)
        except Exception as e:
            print(f'  ❌ 素材生成失败: {e}')
    
    def rename_to_final(self):
        """重命名为含义词并复制到最终版目录（由 auto_rename_to_final 替代）"""
        print(f'\n📝 重命名步骤已由 auto_rename_to_final 自动完成')
        # 含义词已在 generate_quad_images 中追踪并自动重命名
        # 此方法保留以兼容旧调用方式
    
    def save_state(self, status: str):
        """保存运行状态"""
        state = {
            'episode': self.episode,
            'type': self.sticker_type,
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'output_dir': self.output_dir
        }
        
        state_dir = os.path.dirname(self.state_file)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)
        
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description='微信表情包自动化')
    parser.add_argument('--episode', '-e', type=int, required=True, help='弹数（如 6）')
    parser.add_argument('--type', '-t', choices=['static', 'dynamic'], default='static', help='类型：static 或 dynamic')
    parser.add_argument('--mode', '-m', choices=['single', 'duo', 'quad', 'auto'], default='auto', help='模式：single（单人）、duo（双人）、quad（四人家庭彩蛋）、auto（自动随机，默认）')
    parser.add_argument('--publish', '-p', action='store_true', help='生成后自动发布')
    parser.add_argument('--quad-count', '-q', type=int, default=3, help='四宫格组数（默认3组）')
    parser.add_argument('--grid', '-g', type=int, default=2, choices=[2, 3, 4],
                        help='宫格模式：2=四宫格(默认), 3=九宫格, 4=十六宫格')
    
    args = parser.parse_args()
    
    if args.mode == 'auto':
        mode_text = '自动随机'
        print('🎲 模式: 自动随机（单人70%、双人25%、四人5%）')
    else:
        mode_names = {'single': '单人', 'duo': '双人', 'quad': '四人(家庭彩蛋)'}
        mode_text = mode_names.get(args.mode, args.mode)
        print(f'📌 模式: {mode_text}')
    
    print('🦞 微信表情包自动化系统')
    print('=' * 40)
    print(f'弹数: 周三涵做表情{args.episode}')
    print(f'类型: {"静态表情" if args.type == "static" else "动态表情"}')
    print(f'模式: {mode_text}模式')
    print(f'宫格: {args.grid}×{args.grid}')
    print(f'自动发布: {"是" if args.publish else "否"}')
    print('=' * 40)
    
    automation = StickerAutomation(args.episode, args.type, args.mode, args.grid)
    
    try:
        # 1. 初始化文件夹
        automation.init_folders()
        
        # 2. 生成四宫格图片
        automation.generate_quad_images(args.quad_count)
        
        # 3. Chroma-key处理（移除背景）
        automation.process_chroma_key()
        
        # 4. 提示重命名为含义词
        automation.rename_to_final()
        
        # 5. 生成发布素材（横幅、封面、图标）⭐
        automation.generate_assets()
        
        # 6. 保存状态
        automation.save_state('completed')
        
        print('\n' + '=' * 40)
        print('✅ 全部完成！')
        print(f'📁 输出目录: {automation.output_dir}')
        print(f'⭐ 最终版目录: {os.path.join(automation.output_dir, "最终版")}')
        print('📝 已按生成阶段追踪的含义词写入最终版目录；发布前仍建议做一次视觉复核')
        
    except KeyboardInterrupt:
        print('\n\n⚠️  用户中断')
        automation.save_state('interrupted')
    except Exception as e:
        print(f'\n❌ 发生错误: {e}')
        automation.save_state('error')


if __name__ == '__main__':
    main()
