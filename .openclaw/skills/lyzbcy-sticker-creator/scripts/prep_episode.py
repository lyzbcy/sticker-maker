#!/usr/bin/env python3
"""
微信表情包 准备脚本 / Episode Preparer
======================================
替代 main.py 中破碎的 init 部分。
模块化、独立可调用、每步返回明确结果。

功能：
1. 扫描当前已有弹次，自动编号
2. 创建统一文件夹结构
3. 选定角色/模式/参考图
4. 生成 本次制作角色.md
5. 输出 JSON 供后续步骤消费

用法：
    python prep_episode.py --mode auto --type static
    python prep_episode.py --mode duo --type static
    python prep_episode.py --mode single --character 周三涵
"""

import os
import sys
import re
import json
import random
import argparse
from datetime import datetime
from pathlib import Path
import yaml

# Windows GBK 编码修复
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ============================================================
# 配置加载
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SKILL_DIR, 'config.yaml')
KEYWORDS_PATH = os.path.join(SKILL_DIR, 'keywords.json')
USED_COMBOS_PATH = os.path.join(SKILL_DIR, 'used_combinations.txt')
STATE_PATH = os.path.join(SKILL_DIR, '..', 'state.json')  # .openclaw/state.json


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_keywords():
    with open(KEYWORDS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"episodes": {}, "last_episode": 0}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================
# 弹次检测
# ============================================================

def find_next_episode(output_dir):
    """扫描输出目录，找到下一个弹次编号"""
    pattern = re.compile(r'周三涵做表情(\d+)$')
    max_n = 0
    
    try:
        for entry in os.listdir(output_dir):
            match = pattern.match(entry)
            if match:
                n = int(match.group(1))
                max_n = max(max_n, n)
    except FileNotFoundError:
        pass
    
    return max_n + 1


# ============================================================
# 模式 & 角色选择
# ============================================================

def choose_mode(config):
    """根据配置的概率随机选择模式"""
    probs = config.get('mode_probabilities', {'single': 0.7, 'duo': 0.25, 'quad': 0.05})
    rand = random.random()
    
    cumulative = 0
    for mode_name in ['single', 'duo', 'quad']:
        cumulative += probs.get(mode_name, 0)
        if rand < cumulative:
            return mode_name
    
    return 'single'  # fallback


def choose_single_character(config):
    """随机选择单人模式的角色"""
    probs = config.get('single_character_probabilities', {
        '星星布丁': 0.75, '捞鱼': 0.2, '周三涵': 0.03, '周五涵': 0.02
    })
    rand = random.random()
    
    cumulative = 0
    for char, prob in probs.items():
        cumulative += prob
        if rand < cumulative:
            return char
    
    return '星星布丁'


def choose_costume(config, character):
    """随机选择角色的衣服版本"""
    if character not in config.get('base_images', {}):
        return 'base1'
    
    costumes = config.get('character_costume_probabilities', {}).get(character, {})
    if not costumes:
        return 'base1'
    
    rand = random.random()
    cumulative = 0
    for costume, prob in costumes.items():
        cumulative += prob
        if rand < cumulative:
            return costume
    
    return list(costumes.keys())[0]


# ============================================================
# 参考图选择
# ============================================================

def pick_references(config, mode, count=4):
    """按模式选择参考图（自动排除已使用文件夹中的图）"""
    ref_dir = config.get('reference_library', '')
    if not ref_dir or not os.path.exists(ref_dir):
        return []
    
    ref_prob = config.get('reference_probabilities', {})
    
    # 收集「已使用」中的文件名，避免重复选取
    used_dir = os.path.join(ref_dir, '已使用')
    used_names = set()
    if os.path.isdir(used_dir):
        for f in os.listdir(used_dir):
            used_names.add(f)
    
    # 扫描所有图片（排除已使用中的）
    all_refs = list(Path(ref_dir).glob('*.png'))
    all_refs.extend(Path(ref_dir).glob('*.jpg'))
    all_refs = [str(r) for r in all_refs if os.path.basename(r) not in used_names]
    
    # 按创建时间排序
    all_refs.sort(key=lambda x: os.path.getctime(x))
    
    # 分类
    duo_refs = [r for r in all_refs if '双人' in os.path.basename(r)]
    solo_refs = [r for r in all_refs if '双人' not in os.path.basename(r)]
    
    # 过滤掉概率为0的
    enabled_duo = [r for r in duo_refs if ref_prob.get(os.path.basename(r), 1) > 0]
    enabled_solo = [r for r in solo_refs if ref_prob.get(os.path.basename(r), 1) > 0]
    
    if mode == 'duo':
        selected = enabled_duo[:count]
        remaining = count - len(selected)
        if remaining > 0:
            selected.extend(enabled_solo[:remaining])
    else:
        selected = enabled_solo[:count]
    
    return selected


# ============================================================
# AI 模板关键词
# ============================================================

def pick_keyword_combos(keywords, mode, count=4):
    """从关键词库中挑选动作+情绪组合"""
    actions = keywords.get('actions', ['waving', 'pointing', 'crossing arms', 'holding heart'])
    emotions = keywords.get('emotions', ['happy', 'sad', 'surprised', 'angry'])
    
    # 读取已用记录
    used = set()
    if os.path.exists(USED_COMBOS_PATH):
        with open(USED_COMBOS_PATH, 'r', encoding='utf-8') as f:
            used = set(line.strip() for line in f if line.strip())
    
    combos = []
    for _ in range(count):
        # 尝试找未用过的组合
        found = False
        for attempt in range(100):
            combo = f"{random.choice(emotions)}_{random.choice(actions)}"
            if combo not in used:
                used.add(combo)
                combos.append(combo)
                found = True
                break
        if not found:
            combos.append(f"{random.choice(emotions)}_{random.choice(actions)}")
    
    # 保存已用组合
    with open(USED_COMBOS_PATH, 'w', encoding='utf-8') as f:
        for c in sorted(used):
            f.write(c + '\n')
    
    return combos


# ============================================================
# 文件夹创建
# ============================================================

def create_folders(output_dir, sticker_type='static'):
    """创建统一文件夹结构"""
    folders = ['参考图', '原图', '原图_透明ChromaKey', '最终版',
               '横幅', '封面', '图标']
    if sticker_type == 'dynamic':
        folders.append('帧图')
    
    created = []
    for folder in folders:
        p = os.path.join(output_dir, folder)
        os.makedirs(p, exist_ok=True)
        created.append(folder)
        print(f'  ✅ {folder}/')
    
    return created


# ============================================================
# 角色卡生成
# ============================================================

def generate_role_card(episode, mode, characters, sticker_type, refs=None, combos=None):
    """自动生成 本次制作角色.md"""
    content = f"""# 本次制作角色

## 基本信息
- 弹次：周三涵做表情{episode}
- 类型：{'动态表情' if sticker_type == 'dynamic' else '静态表情'}
- 模式：{mode}
- 生成日期：{datetime.now().strftime('%Y-%m-%d')}

## 角色列表
"""
    for c in characters:
        content += f"- {c}\n"
    
    content += "\n## 参考图列表\n"
    if refs:
        for r in refs:
            content += f"- {os.path.basename(r)}\n"
    else:
        content += "- 无\n"
        
    content += "\n## AI 模板提示词组合\n"
    if combos:
        for c in combos:
            content += f"- {c}\n"
    else:
        content += "- 无\n"
    
    only_laoyu = len(characters) == 1 and characters[0] == '捞鱼'
    has_laoyu = '捞鱼' in characters
    
    role_category = '男人' if only_laoyu else ('人物合辑' if has_laoyu else '女人')
    
    content += f"""
## 角色判定
- 只含捞鱼：{'是' if only_laoyu else '否'}
- 含捞鱼：{'是' if has_laoyu else '否'}

## 发布指引（供 lyzbcy-sticker-publisher 读取）
- 角色分类：{role_category}
"""
    return content


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="微信表情包准备脚本")
    parser.add_argument("--mode", default="auto", help="生成模式: auto/single/duo/quad")
    parser.add_argument("--type", default="static", help="表情类型: static/dynamic")
    parser.add_argument("--character", default=None, help="指定角色 (single模式)")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际创建")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎨 微信表情包 准备脚本")
    print("=" * 60)
    
    # 加载配置
    config = load_config()
    keywords = load_keywords()
    output_root = config['project']['output_dir']
    
    # 决定模式
    mode = args.mode
    if mode == 'auto':
        mode = choose_mode(config)
    
    print(f"\n📋 模式: {mode}")
    
    # 决定角色
    characters = []
    if mode == 'single':
        char = args.character or choose_single_character(config)
        characters = [char]
    elif mode == 'duo':
        characters = config.get('duo_bases', ['星星布丁', '捞鱼'])
    elif mode == 'quad':
        characters = config.get('quad_bases', ['星星布丁', '捞鱼', '周三涵', '周五涵'])
    
    print(f"👤 角色: {', '.join(characters)}")
    
    # 选择衣服
    costumes = {}
    for char in characters:
        c = choose_costume(config, char)
        costumes[char] = c
        print(f"  👗 {char}: {c}")
    
    # 弹次编号
    episode = find_next_episode(output_root)
    episode_name = f"周三涵做表情{episode}"
    output_dir = os.path.join(output_root, episode_name)
    
    print(f"\n📁 弹次: {episode_name}")
    print(f"📁 路径: {output_dir}")
    
    if args.dry_run:
        print("\n🔍 [预览模式] 不会实际创建文件")
        return
    
    # 创建文件夹
    print("\n📁 创建文件夹...")
    create_folders(output_dir, args.type)
    
    # 选择参考图
    # 需要 4 组四宫格 × 每组 4 张 = 16 张不重复参考图，才能保证 4 组不雷同
    REFS_PER_GROUP = 4
    NUM_GROUPS = 4
    total_refs_needed = REFS_PER_GROUP * NUM_GROUPS
    refs = pick_references(config, mode, count=total_refs_needed)
    has_enough_refs = len(refs) >= total_refs_needed

    if has_enough_refs:
        print(f"\n📸 参考图模式: {len(refs)} 张已就绪 (够 {NUM_GROUPS} 组 × {REFS_PER_GROUP} 张)")
        for r in refs:
            print(f"  📷 {os.path.basename(r)}")
        # 复制参考图到目录
        ref_copy_dir = os.path.join(output_dir, '参考图')
        for r in refs:
            import shutil
            shutil.copy2(r, os.path.join(ref_copy_dir, os.path.basename(r)))
    else:
        print(f"\n🎲 AI模板模式 (参考图不足 {total_refs_needed} 张，仅 {len(refs)} 张 → 回退纯提示词)")
    
    # 生成关键词组合
    combos = pick_keyword_combos(keywords, mode)
    print(f"🎯 动作组合: {', '.join(combos)}")
    
    # 生成角色卡
    card_content = generate_role_card(
        episode, mode, characters, args.type,
        refs=refs if has_enough_refs else None,
        combos=combos
    )
    card_path = os.path.join(output_dir, '本次制作角色.md')
    with open(card_path, 'w', encoding='utf-8') as f:
        f.write(card_content)
    print(f"\n📝 角色卡已生成: 本次制作角色.md")

    # 记录生产日志（准备步骤）+ 初始化结构化复盘记录
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from production_log import log_step, init_record
        reference_mode = "reference" if has_enough_refs else "ai_template"
        log_step(output_dir, "准备", "OK",
                 details=f"弹次准备完成：模式={mode}, 角色={','.join(characters)}, "
                         f"参考图={len(refs)}张",
                 data={"mode": mode, "characters": characters,
                       "reference_mode": reference_mode,
                       "ref_count": len(refs)})
        # 初始化 production_record.json（写配置快照，供复盘用）
        init_record(output_dir, episode, {
            "mode": mode,
            "characters": characters,
            "costumes": costumes,
            "reference_mode": reference_mode,
            "keyword_combos": combos,
            "references": [os.path.basename(r) for r in refs],
            "ref_count": len(refs),
            "sticker_type": args.type,
            "has_laoyu": '捞鱼' in characters,
        })
    except Exception as e:
        print(f"  ⚠️ 生产日志写入失败: {e}")

    # 生成 prep_state.json（供后续步骤消费）
    state = {
        "episode": episode,
        "episode_name": episode_name,
        "output_dir": output_dir,
        "mode": mode,
        "characters": characters,
        "costumes": costumes,
        "sticker_type": args.type,
        "reference_mode": "reference" if has_enough_refs else "ai_template",
        "references": [os.path.basename(r) for r in refs],
        "keyword_combos": combos,
        "has_laoyu": '捞鱼' in characters,
        "created_at": datetime.now().isoformat()
    }
    state_path = os.path.join(output_dir, 'prep_state.json')
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    
    # 更新全局状态
    global_state = load_state()
    global_state['last_episode'] = episode
    global_state['episodes'][str(episode)] = {
        "name": episode_name,
        "mode": mode,
        "characters": characters,
        "status": "prepared",
        "created_at": datetime.now().isoformat()
    }
    save_state(global_state)
    
    print("\n" + "=" * 60)
    print("✅ 准备完成！下一步:")
    print(f"   cd {output_dir}")
    print(f"   然后开始 Codex 生图 (4组四宫格)")
    print(f"   prep_state.json 已保存 → 后续步骤可直接消费")
    print("=" * 60)
    
    # 打印 JSON 结果
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
