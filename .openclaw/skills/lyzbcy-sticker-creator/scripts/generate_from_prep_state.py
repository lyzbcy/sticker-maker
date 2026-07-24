#!/usr/bin/env python3
"""
根据 prep_state.json 调用 Codex CLI 生成四宫格图片。

目标：
1. 复用 prep_episode.py 的产物
2. 尽量减少临时 AI 决策
3. 为后续裁剪、抠图、发布素材生成稳定输入
"""

import argparse
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("请安装 PyYAML: pip install pyyaml")
    sys.exit(1)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
USED_COMBOS_PATH = os.path.join(SKILL_DIR, "used_combinations.txt")
KEYWORDS_PATH = os.path.join(SKILL_DIR, "keywords.json")
LINKAGE_SCRIPTS_PATH = os.path.join(SKILL_DIR, "linkage_scripts.json")
USED_LINKAGE_PATH = os.path.join(SKILL_DIR, "used_linkages.txt")
PANEL_COUNT = 16  # 4×4 十六宫格 = 16 个 panel
PANELS_PER_STORY = 4  # 每个小故事 4 格(起承转合)
STORIES_PER_PACK = 4  # 一弹串联 4 个独立小故事 × 4 格 = 16 格
SCRIPT_GROUPS = STORIES_PER_PACK  # 选 N 组剧本(=故事数)


def load_linkage_scripts():
    """加载联动剧本库。"""
    if not os.path.exists(LINKAGE_SCRIPTS_PATH):
        return []
    with open(LINKAGE_SCRIPTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("scripts", [])


def pick_linkage_scripts(scripts, count=SCRIPT_GROUPS, characters=None, preferred_id=None):
    """根据角色人设筛选剧本，然后随机选 count 组（多故事串联架构：选4组×4格=16格）。
    
    - 一弹选 count 组剧本，每组4个panel，组成4×4（每行一个独立小故事）
    - characters: 本弹次的角色列表，用于匹配剧本的 characters 标签
    - preferred_id: 指定优先选取的剧本 id（必须未用过且匹配角色），不随机；不足count时从未选中里补足
    - 用过的剧本永久淘汰（不再循环使用），池子不够时返回少于 count 个
    """
    # 加载已用记录
    used = set()
    if os.path.exists(USED_LINKAGE_PATH):
        with open(USED_LINKAGE_PATH, "r", encoding="utf-8") as f:
            used = set(line.strip() for line in f if line.strip())
    
    # 按角色筛选（严格匹配：剧本 characters 必须等于本弹角色集合）
    # 避免单人弹误选双人剧本（旧逻辑用 any() 会把含该角色的双人剧也匹配上）
    if characters:
        target = set(characters)
        def char_match(s):
            script_chars = set(s.get("characters", []))
            if not script_chars:
                return False  # 严格模式：不收通配剧本，避免单人弹混入双人剧情
            return script_chars == target
        candidate = [s for s in scripts if char_match(s)]
        if not candidate:
            print(f"  ⚠️ 没有严格匹配角色 {characters} 的剧本，使用全部剧本")
            candidate = scripts
    else:
        candidate = scripts
    
    # 排除已用
    available = [s for s in candidate if s.get("id", s.get("name", "")) not in used]
    
    if len(available) < count:
        print(f"  ⚠️ 可用剧本仅 {len(available)} 组（需要 {count}），不足时 AI 需补充新剧本")
    
    # 指定优先剧本：必须存在、未用过、匹配角色
    selected = []
    if preferred_id:
        pref = [s for s in available if s.get("id") == preferred_id]
        if pref:
            selected = pref[:count]
            print(f"  🎯 指定剧本: {preferred_id} ({pref[0].get('name')})")
        else:
            print(f"  ⚠️ 指定剧本 {preferred_id} 不可用(不存在/已用/角色不符)，随机选取")
    
    # 不足 count 个时，从未选中的可用剧本中随机补足（不覆盖已选的 preferred）
    if len(selected) < count:
        chosen_ids = {s.get("id") for s in selected}
        remaining = [s for s in available if s.get("id") not in chosen_ids]
        random.shuffle(remaining)
        selected = selected + remaining[: count - len(selected)]
    
    # 记录已用
    for s in selected:
        sid = s.get("id", s.get("name", ""))
        used.add(sid)
    with open(USED_LINKAGE_PATH, "w", encoding="utf-8") as f:
        for sid in sorted(used):
            f.write(sid + "\n")
    
    return selected


def expand_to_16_panels(script, characters, costumes):
    """[已废弃·保留兜底] 将4panel剧本扩展为16panel。
    
    历史用途：旧"单故事×16格"架构用此函数把4格剧本硬展开成16格，
    但会产生固定过渡词（闲着/咦？/决定了…）导致含义词严重重复（见 troubleshooting 坑5）。
    
    新架构（多故事串联）改为选4组剧本×4格，不再调用此函数。
    仅当未来需要"单故事深度模式"且能保证不注水时，才考虑启用。
    """
    original = script["panels"]
    script_name = script["name"]
    script_type = script["type"]
    
    # 角色人设关键词
    char_traits = {
        "星星布丁": "软萌、撒娇、爱哭、吃货、表情丰富、容易感动",
        "捞鱼": "高冷、宠溺、故作镇定、实际很暖、嘴硬心软",
        "周三涵": "安静、害羞、靠谱、呆萌、默默付出",
        "周五涵": "活泼、话痨、搞怪、点子多、气氛组"
    }
    
    char_desc = "、".join(char_traits.get(c, "") for c in characters)
    
    # 4幕结构模板
    acts = [
        {"name": "起", "anchor_idx": 0, "direction": "引入场景，角色初始状态，铺垫氛围"},
        {"name": "承", "anchor_idx": 1, "direction": "发展，情绪升级，冲突或互动加深"},
        {"name": "转", "anchor_idx": 2, "direction": "转折/高潮，意外或反转，情绪爆发点"},
        {"name": "合", "anchor_idx": 3, "direction": "结局，回归平静或新状态，留有余韵"}
    ]
    
    # 情绪/动作同义词库（用于扩展时多样化）
    import random as _r
    
    # 多样化情绪库，避免重复
    emotion_variants = {
        "happy": ["joyful", "cheerful", "delighted", "ecstatic", "giddy"],
        "sad": ["teary", "miserable", "heartbroken", "gloomy", "devastated"],
        "angry": ["annoyed", "frustrated", "furious", "irritated", "seething"],
        "excited": ["thrilled", "eager", "hyper", "electrified", "pumped"],
        "surprised": ["shocked", "startled", "amazed", "astonished", "bewildered"],
        "calm": ["peaceful", "serene", "relaxed", "content", "drowsy"],
        "shy": ["blushing", "flustered", "timid", "embarrassed", "bashful"],
        "love": ["loving", "affectionate", "adoring", "tender", "smitten"],
        "tired": ["exhausted", "sleepy", "drained", "drowsy", "wiped out"],
        "confused": ["puzzled", "bewildered", "lost", "unsure", "hesitant"],
        "proud": ["smug", "confident", "triumphant", "satisfied", "victorious"],
        "scared": ["nervous", "anxious", "terrified", "panicked", "worried"],
    }
    
    def vary_emotion(base_emotion, seed=0):
        """根据基础情绪返回一个变体，避免重复"""
        for key, variants in emotion_variants.items():
            if key in base_emotion:
                return variants[seed % len(variants)]
        return base_emotion
    
    # 多样化动作库
    action_variants = [
        "sitting down, hands on lap",
        "standing with arms crossed",
        "leaning forward with interest",
        "tilting head to the side",
        "clapping hands together",
        "waving one hand",
        "covering mouth",
        "pointing finger up",
        "stretching arms wide",
        "hugging knees",
        "lying on stomach",
        "jumping in place",
        "spinning around",
        "peeking through fingers",
        "fist pump",
        "slowly closing eyes",
    ]
    
    # 连接词库（用于含义词前缀，避免单调）
    prefix_pool = ["偷偷", "突然", "开心地", "认真地", "慢慢地", "飞快地", "悄悄地", "猛地"]
    suffix_pool = ["一下", "好久", "半天", "的样子", "停不下来", "太棒了", "完蛋了", "好开心"]
    
    # 根据剧本类型选择扩展策略
    expanded = []
    used_actions = set()
    
    for act_idx, act in enumerate(acts):
        anchor = original[act["anchor_idx"]]
        act_name = act["name"]
        
        # 每幕4个panel，锚点在第二个位置（idx 1）
        # panel顺序: 铺垫 → 锚点 → 延伸 → 收幕
        
        if act_idx == 0:
            # 第一幕「起」：引入
            # panel 1: 场景铺垫（与锚点完全不同的动作）
            pretext_actions = [a for a in action_variants if a not in used_actions]
            a1 = pretext_actions[0] if pretext_actions else anchor["action"]
            used_actions.add(a1)
            expanded.append({
                "emotion": vary_emotion(anchor["emotion"], 0),
                "action": a1,
                "cn": f"闲着没事",
                "en": f"idly {a1}, minding own business"
            })
            # panel 2: 锚点
            expanded.append(anchor)
            used_actions.add(anchor["action"])
            # panel 3: 反应
            a2 = pretext_actions[1] if len(pretext_actions) > 1 else "touching chin"
            used_actions.add(a2)
            expanded.append({
                "emotion": vary_emotion(anchor["emotion"], 1),
                "action": a2,
                "cn": f"咦？",
                "en": f"noticing something, touching chin, curious expression"
            })
            # panel 4: 决定行动
            a3 = pretext_actions[2] if len(pretext_actions) > 2 else "standing up"
            used_actions.add(a3)
            expanded.append({
                "emotion": vary_emotion(anchor["emotion"], 2),
                "action": a3,
                "cn": f"决定了！",
                "en": f"making a decision, {a3}, determined look"
            })
        elif act_idx == 1:
            # 第二幕「承」：发展
            # panel 5: 投入
            dev_actions = [a for a in action_variants if a not in used_actions]
            a1 = dev_actions[0] if dev_actions else "leaning forward with interest"
            used_actions.add(a1)
            expanded.append({
                "emotion": vary_emotion(anchor["emotion"], 0),
                "action": a1,
                "cn": f"全神贯注",
                "en": f"fully focused, {a1}, concentrating hard"
            })
            # panel 6: 锚点
            expanded.append(anchor)
            used_actions.add(anchor["action"])
            # panel 7: 被打断/分心
            a2 = dev_actions[1] if len(dev_actions) > 1 else "peeking through fingers"
            used_actions.add(a2)
            expanded.append({
                "emotion": vary_emotion("surprised", 0),
                "action": a2,
                "cn": f"哎？什么声音",
                "en": f"distracted by a sound, {a2}, looking around"
            })
            # panel 8: 继续坚持
            a3 = dev_actions[2] if len(dev_actions) > 2 else "clapping hands together"
            used_actions.add(a3)
            expanded.append({
                "emotion": vary_emotion(anchor["emotion"], 1),
                "action": a3,
                "cn": f"不管了继续",
                "en": f"ignoring distraction, {a3}, back to it"
            })
        elif act_idx == 2:
            # 第三幕「转」：转折
            # panel 9: 预感
            turn_actions = [a for a in action_variants if a not in used_actions]
            a1 = turn_actions[0] if turn_actions else "tilting head to the side"
            used_actions.add(a1)
            expanded.append({
                "emotion": vary_emotion("scared", 0),
                "action": a1,
                "cn": f"有种不祥的预感",
                "en": f"sensing something wrong, {a1}, worried expression"
            })
            # panel 10: 发现
            a2 = turn_actions[1] if len(turn_actions) > 1 else "covering mouth"
            used_actions.add(a2)
            expanded.append({
                "emotion": vary_emotion("surprised", 1),
                "action": a2,
                "cn": f"不会吧！",
                "en": f"shocked discovery, {a2}, eyes wide open"
            })
            # panel 11: 锚点（转折高潮）
            expanded.append(anchor)
            used_actions.add(anchor["action"])
            # panel 12: 应对
            a3 = turn_actions[2] if len(turn_actions) > 2 else "stretching arms wide"
            used_actions.add(a3)
            expanded.append({
                "emotion": vary_emotion(anchor["emotion"], 2),
                "action": a3,
                "cn": f"冷静冷静",
                "en": f"trying to stay calm, {a3}, taking deep breath"
            })
        else:
            # 第四幕「合」：结局
            # panel 13: 疲惫
            end_actions = [a for a in action_variants if a not in used_actions]
            a1 = end_actions[0] if end_actions else "lying on stomach"
            used_actions.add(a1)
            expanded.append({
                "emotion": vary_emotion("tired", 0),
                "action": a1,
                "cn": f"累趴了",
                "en": f"completely drained, {a1}, out of energy"
            })
            # panel 14: 锚点
            expanded.append(anchor)
            used_actions.add(anchor["action"])
            # panel 15: 释然
            a2 = end_actions[1] if len(end_actions) > 1 else "slowly closing eyes"
            used_actions.add(a2)
            expanded.append({
                "emotion": vary_emotion("calm", 0),
                "action": a2,
                "cn": f"都过去了",
                "en": f"feeling relieved, {a2}, peaceful smile"
            })
            # panel 16: 完美收尾
            a3 = end_actions[2] if len(end_actions) > 2 else "fist pump"
            used_actions.add(a3)
            expanded.append({
                "emotion": vary_emotion("happy", 4),
                "action": a3,
                "cn": f"今天也棒棒的",
                "en": f"a perfect ending, {a3}, big satisfied smile, eyes sparkling"
            })
    
    # 确保正好16个
    expanded = expanded[:16]
    while len(expanded) < 16:
        expanded.append(expanded[-1])
    
    # 含义词去重（加序号后缀如果重复）
    seen = {}
    for p in expanded:
        cn = p["cn"]
        if cn in seen:
            seen[cn] += 1
            p["cn"] = f"{cn}{seen[cn]}"
        else:
            seen[cn] = 1
    
    return expanded


def build_16grid_linkage(config, state, selected_scripts):
    """联动剧本模式：从选定的多组剧本构建4×4十六宫格prompt（多故事串联）。

    一弹选4组剧本，每组4个panel —— 16宫格每行一个独立小故事。
    含义词直接取剧本中的 cn 字段，不再需要识图AI推导。
    """
    # 收集 panel 描述和含义词（多故事串联：4个故事×4格=16格）
    panel_descs = []
    panel_meanings = []
    script_names = []
    # 每个故事占一行的 4 格，用于 prompt 分段标注
    stories_for_prompt = []

    for script in selected_scripts:
        script_names.append(script["name"])
        story_panels = script["panels"][:PANELS_PER_STORY]  # 每故事取4格
        stories_for_prompt.append({
            "name": script["name"],
            "type": script.get("type", ""),
            "note": script.get("link_note", ""),
            "panels": story_panels,
        })
        for panel in story_panels:
            panel_descs.append(panel["en"])
            panel_meanings.append(panel["cn"])

    # 兜底：若 panel 不足 16（剧本不足4个或部分不满4格），用占位补齐
    while len(panel_descs) < PANEL_COUNT:
        panel_descs.append(f"cute pose {len(panel_descs)+1}")
        panel_meanings.append(f"表情{len(panel_meanings)+1}")

    # 获取base角色描述
    mode = state["mode"]
    char_desc = ""
    if mode == "duo":
        char_desc = f"two characters: {', '.join(state['characters'])} as a cute couple"
    elif mode == "single":
        char_desc = f"one character: {state['characters'][0]}"
    elif mode == "quad":
        char_desc = f"four characters: {', '.join(state['characters'])}"

    # 构建 prompt：按行标注 4 个独立小故事
    story_rows = []
    for i, st in enumerate(stories_for_prompt):
        row = i + 1
        start = (row - 1) * PANELS_PER_STORY + 1
        end = row * PANELS_PER_STORY
        p_lines = "\n".join(
            f"      Panel {start+j} (Row {row}, Col {j+1}): {p['en']}"
            for j, p in enumerate(st["panels"])
        )
        story_rows.append(
            f"- ROW {row} (panels {start}-{end}): Story {chr(65+i)} \"{st['name']}\" — {st['note']}\n{p_lines}"
        )

    prompt = f"""Generate a single 4x4 grid image (4 rows × 4 columns = 16 panels) on a solid magenta (#FF00FF) background.

Each panel is a separate sticker showing {char_desc} in 3D clay style, chibi proportions, soft rounded forms.

IMPORTANT — this grid contains {STORIES_PER_PACK} SEPARATE mini-stories, one per ROW. Each row is an INDEPENDENT story; rows do NOT continue each other:

{chr(10).join(story_rows)}

Rules for the stories:
- Each row tells its own complete mini-story in {PANELS_PER_STORY} panels (setup → development → turn → resolution)
- Rows are independent — row 2 is NOT a sequel to row 1, etc.
- Within each row, the {PANELS_PER_STORY} panels should flow as a short coherent narrative
- Each panel must ALSO work individually as a standalone chat sticker

Visual rules:
- All panels must use solid magenta (#FF00ff) background for chroma-key extraction
- Character design must be consistent across all 16 panels
- Chibi style, big heads, soft clay texture, cute and expressive
- NO shadows on the magenta background: no drop/contact/ground/cast shadows. Use flat front
  lighting; character volume must come from the clay material's own shading, not projected
  shadows. (Shadows projected onto magenta blend into the background and ruin chroma-key cutout.)
- No text, no watermarks, no borders
- Each character MUST stay INSIDE its own panel: never touch or cross the
  panel edges/borders. Nothing (limbs, props, effects) may bleed into a
  neighboring panel — every panel is cropped independently on a hard cut line.
- Center each character with safe margins: fill about 60-70% of the panel
  area, leaving equal padding (at least ~12% of panel width) on all four sides.
"""
    
    inputs = _base_inputs(config, state)
    
    # 同时写入 meaning_map，跳过后续识图步骤
    meaning_map = {str(i+1): panel_meanings[i] for i in range(PANEL_COUNT)}
    
    return prompt, inputs, meaning_map, script_names


def load_state(state_path):
    with open(state_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_keywords():
    with open(KEYWORDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_meaning(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    if name.startswith("【双人】"):
        name = name.replace("【双人】", "", 1)
    if name.startswith("ref_"):
        name = name[4:]
    return name


def get_base_path(config, char_name, costume):
    base_images = config["base_images"].get(char_name, {})
    path = base_images.get(costume)
    if not path:
        raise FileNotFoundError(f"未找到 base 图: {char_name}/{costume}")
    if not os.path.exists(path):
        raise FileNotFoundError(f"base 图不存在: {path}")
    return path


# ============================================================
# 参考图轮换（移植自 main.py，作用在弹次 参考图/ 目录）
# ============================================================

def get_local_references(ref_dir, count, mode):
    """从弹次 参考图/ 目录挑最早的 count 张参考图。

    - duo 模式：【双人】优先，不足用普通图补齐
    - 单人/quad：只用普通图（排除【双人】）
    返回绝对路径列表，可能少于 count（由调用方决定是否回退）。
    """
    images = list(Path(ref_dir).glob("*.png"))
    images.extend(Path(ref_dir).glob("*.jpg"))
    if not images:
        return []

    # 按创建时间升序 → 最早的优先使用
    images.sort(key=lambda x: x.stat().st_ctime)

    duo_imgs = [img for img in images if "双人" in img.name]
    solo_imgs = [img for img in images if "双人" not in img.name]

    if mode == "duo":
        selected = duo_imgs[:count]
        remaining = count - len(selected)
        if remaining > 0:
            selected.extend(solo_imgs[:remaining])
    else:
        selected = solo_imgs[:count]

    return [str(img) for img in selected]


def move_used_references(refs, ref_dir):
    """把本组用过的参考图移到 参考图/已使用/，保证下一组拿到不同的图。"""
    used_dir = os.path.join(ref_dir, "已使用")
    os.makedirs(used_dir, exist_ok=True)
    moved = []
    for ref in refs:
        if os.path.exists(ref):
            filename = os.path.basename(ref)
            dest = os.path.join(used_dir, filename)
            if os.path.exists(dest):
                base, ext = os.path.splitext(filename)
                dest = os.path.join(used_dir, f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
            shutil.move(ref, dest)
            moved.append(filename)
    return moved


def get_unique_combinations(count):
    """从关键词库生成 count 个不重复的 emotion 组合（纯提示词模式回退用）。

    移植自 main.py get_unique_combinations，修掉编码问题。
    """
    keywords = load_keywords()
    used = set()
    if os.path.exists(USED_COMBOS_PATH):
        with open(USED_COMBOS_PATH, "r", encoding="utf-8") as f:
            used = set(line.strip() for line in f if line.strip())

    emotions = keywords.get("emotions", ["happy", "angry", "sad", "surprised"])
    actions = keywords.get("actions", ["waving", "pointing", "thumbs up", "hugging"])

    combos = []
    max_attempts = 200
    for _ in range(count):
        attempts = 0
        while attempts < max_attempts:
            combo = f"{random.choice(emotions)}_{random.choice(actions)}"
            if combo not in used:
                used.add(combo)
                combos.append(combo)
                break
            attempts += 1
        if attempts >= max_attempts:
            combos.append(f"{random.choice(emotions)}_{random.choice(actions)}")

    with open(USED_COMBOS_PATH, "w", encoding="utf-8") as f:
        for combo in sorted(used):
            f.write(combo + "\n")

    return combos


def _base_inputs(config, state):
    """根据模式构造 base 图输入列表（不含参考图）。"""
    mode = state["mode"]
    characters = state["characters"]
    costumes = state["costumes"]
    inputs = []
    if mode == "single":
        char_name = characters[0]
        inputs.append(get_base_path(config, char_name, costumes[char_name]))
    elif mode == "duo":
        for char_name in characters[:2]:
            inputs.append(get_base_path(config, char_name, costumes[char_name]))
    elif mode == "quad":
        for char_name in characters[:4]:
            inputs.append(get_base_path(config, char_name, costumes[char_name]))
    return inputs


def build_group_reference(config, state, refs):
    """参考图模式：用本组 4 张参考图构造 prompt + inputs。

    - refs 是本组实际拿到的参考图绝对路径（来自弹次 参考图/ 目录）
    - prompt 里的 {refN_name} 用参考图文件名（去前缀）填充
    """
    mode = state["mode"]
    names = [extract_meaning(r) for r in refs]
    while len(names) < REFS_PER_GROUP:
        names.append(f"动作{len(names) + 1}")

    if mode == "duo":
        template = config["prompts"]["reference_duo"]
        prompt = template.format(
            ref3_name=names[0], ref4_name=names[1],
            ref5_name=names[2], ref6_name=names[3],
        )
    elif mode == "quad":
        template = config["prompts"]["reference_quad"]
        prompt = template.format(
            ref5_name=names[0], ref6_name=names[1],
            ref7_name=names[2], ref8_name=names[3],
        )
    else:
        template = config["prompts"]["reference"]
        prompt = template.format(
            ref2_name=names[0], ref3_name=names[1],
            ref4_name=names[2], ref5_name=names[3],
        )

    inputs = _base_inputs(config, state) + list(refs)
    return prompt, inputs


def build_group_ai(config, state, emotions):
    """纯提示词模式（参考图不足时回退）：用去重 emotions 构造 prompt + inputs。"""
    mode = state["mode"]
    while len(emotions) < REFS_PER_GROUP:
        emotions.append(f"emotion_{len(emotions) + 1}")

    if mode == "duo":
        template = config["prompts"]["ai_duo"]
    elif mode == "quad":
        template = config["prompts"]["ai_quad"]
    else:
        template = config["prompts"]["ai_high_quality"]

    prompt = template.format(
        emotion_1=emotions[0], emotion_2=emotions[1],
        emotion_3=emotions[2], emotion_4=emotions[3],
    )
    inputs = _base_inputs(config, state)
    return prompt, inputs


def build_16grid_reference(config, state, refs):
    """4×4 十六宫格参考图模式：单次生成 16 个 panel。

    - refs 是 16 张参考图绝对路径（来自弹次 参考图/ 目录）
    - 用 reference_16grid 模板，image 1=base，image 2-17=16张参考图
    - 16 张参考图天然映射到 16 个 panel，无需轮换
    """
    names = [extract_meaning(r) for r in refs]
    while len(names) < 16:
        names.append(f"动作{len(names) + 1}")

    template = config["prompts"]["reference_16grid"]
    prompt = template.format(
        ref2_name=names[0], ref3_name=names[1], ref4_name=names[2], ref5_name=names[3],
        ref6_name=names[4], ref7_name=names[5], ref8_name=names[6], ref9_name=names[7],
        ref10_name=names[8], ref11_name=names[9], ref12_name=names[10], ref13_name=names[11],
        ref14_name=names[12], ref15_name=names[13], ref16_name=names[14], ref17_name=names[15],
    )
    inputs = _base_inputs(config, state) + list(refs)
    return prompt, inputs


def build_16grid_ai(config, state, emotions):
    """4×4 十六宫格纯提示词模式（参考图不足16张时回退）。

    用 ai_16grid 模板，填 16 个去重 emotions。
    """
    while len(emotions) < 16:
        emotions.append(f"emotion_{len(emotions) + 1}")

    template = config["prompts"]["ai_16grid"]
    prompt = template.format(
        emotion_1=emotions[0], emotion_2=emotions[1], emotion_3=emotions[2], emotion_4=emotions[3],
        emotion_5=emotions[4], emotion_6=emotions[5], emotion_7=emotions[6], emotion_8=emotions[7],
        emotion_9=emotions[8], emotion_10=emotions[9], emotion_11=emotions[10], emotion_12=emotions[11],
        emotion_13=emotions[12], emotion_14=emotions[13], emotion_15=emotions[14], emotion_16=emotions[15],
    )
    inputs = _base_inputs(config, state)
    return prompt, inputs


def get_state_ai_combinations(state, count):
    """优先使用 prep_state 中由 AI 审核过的可爱提示词组合。"""
    combos = state.get("keyword_combos") or []
    combos = [str(c).strip() for c in combos if str(c).strip()]
    if len(combos) >= count:
        return combos[:count]
    return []


def find_new_image(old_times, codex_dir):
    new_files = glob.glob(os.path.join(codex_dir, "**", "*.png"), recursive=True)
    changed = []
    for f in new_files:
        mtime = os.path.getmtime(f)
        if f not in old_times or mtime > old_times[f]:
            changed.append((mtime, f))
    if changed:
        changed.sort(reverse=True)
        return changed[0][1]
    if new_files:
        new_files.sort(key=os.path.getmtime, reverse=True)
        return new_files[0]
    return None


def parse_session_id(text):
    match = re.search(r"session id:\s*([0-9a-fA-F-]+)", text)
    return match.group(1) if match else None


def isolate_generated_images_root(codex_dir):
    os.makedirs(codex_dir, exist_ok=True)
    session_dirs = [p for p in Path(codex_dir).iterdir() if p.is_dir()]
    if not session_dirs:
        return None

    archive_root = Path(codex_dir).parent / "generated_images_archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_dir = archive_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir.mkdir(parents=True, exist_ok=True)

    for session_dir in session_dirs:
        shutil.move(str(session_dir), str(archive_dir / session_dir.name))

    return str(archive_dir)


def find_image_in_session(codex_dir, session_id, wait_seconds=6):
    if not session_id:
        return None

    session_dir = os.path.join(codex_dir, session_id)
    deadline = time.time() + wait_seconds

    while time.time() < deadline:
        if os.path.isdir(session_dir):
            files = glob.glob(os.path.join(session_dir, "*.png"))
            if files:
                files.sort(key=os.path.getmtime, reverse=True)
                return files[0]
        time.sleep(1)

    return None


def run_codex(prompt, inputs, timeout_sec):
    codex_dir = os.path.expanduser("~/.codex/generated_images")
    archive_dir = isolate_generated_images_root(codex_dir)
    if archive_dir:
        print(f"  已归档旧生成结果: {archive_dir}")
    old_files = glob.glob(os.path.join(codex_dir, "**", "*.png"), recursive=True)
    old_times = {f: os.path.getmtime(f) for f in old_files}

    prompt_file = os.path.join(SKILL_DIR, "temp_prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    cmd = 'codex exec --enable image_generation --skip-git-repo-check --sandbox read-only --ephemeral'
    for image_path in inputs:
        cmd += f' -i "{image_path}"'

    full_cmd = f'Get-Content -Path "{prompt_file}" -Encoding UTF8 | {cmd}'
    result = subprocess.run(
        ["powershell", "-Command", full_cmd],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        encoding="utf-8",
        errors="ignore",
    )

    combined_output = "\n".join([result.stdout or "", result.stderr or ""])
    session_id = parse_session_id(combined_output)
    time.sleep(2)
    latest = find_image_in_session(codex_dir, session_id)
    if not latest:
        latest = find_new_image(old_times, codex_dir)
    if result.returncode != 0:
        if latest:
            print(f"  Codex 返回非 0，但在当前会话 {session_id or 'unknown'} 中检测到新图片，按成功处理")
            return latest
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Codex CLI 执行失败")
    if not latest:
        raise FileNotFoundError("未找到 Codex 新生成的图片")
    return latest


def main():
    parser = argparse.ArgumentParser(description="根据 prep_state.json 生成 4×4 十六宫格图（单次生16个panel）")
    parser.add_argument("--state", required=True, help="prep_state.json 路径")
    parser.add_argument("--config", default=os.path.join(SKILL_DIR, "config.yaml"), help="config.yaml 路径")
    parser.add_argument("--timeout", type=int, default=400, help="单次 Codex 超时秒数（4×4 内容多，建议≥400）")
    parser.add_argument("--force-ai", action="store_true", help="强制使用 prep_state.keyword_combos / AI 模板，不使用参考图")
    parser.add_argument("--no-linkage", action="store_true", help="禁用联动剧本模式，回退旧逻辑")
    parser.add_argument("--script", default=None, help="指定联动剧本 id（优先选取，需未用过且角色匹配），不指定则随机")
    args = parser.parse_args()

    state = load_state(args.state)
    config = load_config(args.config)
    output_dir = state["output_dir"].replace("/", os.sep)
    raw_dir = os.path.join(output_dir, "原图")
    ref_dir = os.path.join(output_dir, "参考图")
    os.makedirs(raw_dir, exist_ok=True)

    print("=" * 60)
    print("生成 4×4 十六宫格图（单次生 16 个 panel）")
    print("=" * 60)
    print(f"弹次: {state['episode_name']}")
    print(f"模式: {state['mode']}")
    print(f"输出目录: {raw_dir}")

    # ===== 模式选择：参考图够→参考图模式，不够→联动剧本模式 =====
    linkage_meaning_map = None
    selected_script_names = None

    refs = get_local_references(ref_dir, PANEL_COUNT, state["mode"])

    if len(refs) >= PANEL_COUNT and not args.force_ai:
        # ===== 参考图模式（优先） =====
        print(f"📸 参考图模式: 参考图目录可用 {len(refs)} 张 ≥ {PANEL_COUNT}，走参考图模式")
        prompt, inputs = build_16grid_reference(config, state, refs)
        mode_used = "reference_16grid"
        print(f"  📷 16 张参考图: {[os.path.basename(r) for r in refs]}")

    elif not args.no_linkage:
        # ===== 联动剧本模式（参考图不足时） =====
        # 多故事串联：选 STORIES_PER_PACK 个独立小故事，每个 PANELS_PER_STORY 格，
        # 共 STORIES_PER_PACK × PANELS_PER_STORY = 16 格，每格都有独立笑点，不注水。
        scripts = load_linkage_scripts()
        if scripts:
            characters = state.get("characters", [])
            selected_scripts = pick_linkage_scripts(scripts, SCRIPT_GROUPS, characters=characters, preferred_id=args.script)
            selected_script_names = [s["name"] for s in selected_scripts]
            total_panels = sum(len(s["panels"]) for s in selected_scripts)
            print(f"🎬 联动剧本模式（多故事串联）: 参考图仅 {len(refs)} 张 < {PANEL_COUNT}，选 {len(selected_scripts)} 个小故事 × {PANELS_PER_STORY} 格")
            print(f"   本弹 {len(selected_scripts)} 个故事：")
            for i, s in enumerate(selected_scripts):
                row = i + 1
                start = (row - 1) * PANELS_PER_STORY + 1
                end = row * PANELS_PER_STORY
                cns = " / ".join(p["cn"] for p in s["panels"][:PANELS_PER_STORY])
                print(f"     第{row}行 (panel {start}-{end}) [{s['name']}] ({s.get('type','')}) - {s.get('link_note','')}")
                print(f"       含义词: {cns}")
            
            prompt, inputs, linkage_meaning_map, selected_script_names = build_16grid_linkage(
                config, state, selected_scripts
            )
            mode_used = "linkage_16grid_multi"
        else:
            print("⚠️ linkage_scripts.json 不存在或为空，回退 AI 模板")
            emotions = get_state_ai_combinations(state, PANEL_COUNT) or get_unique_combinations(PANEL_COUNT)
            prompt, inputs = build_16grid_ai(config, state, emotions)
            mode_used = "ai_16grid"
            print(f"  🎨 16 个情绪: {emotions}")

    else:
        # ===== AI模板模式（--no-linkage 强制） =====
        print("🎲 AI 模板模式 (--no-linkage)")
        emotions = get_state_ai_combinations(state, PANEL_COUNT) or get_unique_combinations(PANEL_COUNT)
        prompt, inputs = build_16grid_ai(config, state, emotions)
        mode_used = "ai_16grid"
        print(f"  🎨 16 个情绪: {emotions}")

    print(f"\n第 1/1 组生成中（4×4 十六宫格）...")
    import time as _time
    _gen_start = _time.time()
    latest = run_codex(prompt, inputs, args.timeout)
    _gen_duration = int(_time.time() - _gen_start)
    target = os.path.join(raw_dir, "grid_4x4.png")
    shutil.copy2(latest, target)
    print(f"  已保存: {target}")

    # 将用过的参考图从参考图库移入「已使用」，防止下一弹重复选取
    ref_library = config.get('reference_library', '')
    if ref_library and os.path.isdir(ref_library) and refs:
        # refs 是弹次本地参考图/ 中的拷贝路径，需映射到参考图库中的原图路径
        lib_refs = [os.path.join(ref_library, os.path.basename(r)) for r in refs]
        moved = move_used_references(lib_refs, ref_library)
        if moved:
            print(f"\n📦 已将 {len(moved)} 张参考图从参考图库移入已使用/: {moved}")
    else:
        # fallback: 至少把弹次本地参考图移走
        if refs:
            move_used_references(refs, ref_dir)

    print("\n" + "=" * 60)
    print(f"✅ 4×4 十六宫格生成完成 (模式: {mode_used})")
    print(f"   下一步: python check_and_rename.py --dir \"{output_dir}\"")
    print("=" * 60)

    # 联动剧本模式：直接写入 meaning_map（含义词来自剧本，无需识图AI）
    if linkage_meaning_map:
        import json as _json
        meaning_path = os.path.join(raw_dir, "_meaning_map.json")
        with open(meaning_path, "w", encoding="utf-8") as f:
            _json.dump(linkage_meaning_map, f, ensure_ascii=False, indent=2)
        print(f"📝 含义词已从剧本写入: _meaning_map.json")
        print(f"   剧本: {', '.join(selected_script_names)}")
        print(f"   含义词: {list(linkage_meaning_map.values())}")

        # 提示 AI 补充新剧本
        print("\n" + "-" * 60)
        print("🔄 联动剧本自动补充（AI 必做）")
        print("-" * 60)
        print(f"   本次用掉 {len(selected_script_names)} 组剧本: {', '.join(selected_script_names)}")
        used_ids = set()
        if os.path.exists(USED_LINKAGE_PATH):
            with open(USED_LINKAGE_PATH, "r", encoding="utf-8") as f:
                used_ids = set(line.strip() for line in f if line.strip())
        remaining_scripts = load_linkage_scripts()
        remaining_unused = len([s for s in remaining_scripts if s.get("id", s.get("name", "")) not in used_ids])
        print(f"   当前池子剩余可用: {remaining_unused} 组")
        print(f"   → 请立即设计 ≥1 组新剧本，追加到 linkage_scripts.json")
        print(f"   → 新剧本每组标准 4 个 panel（起承转合），一弹选4组×4格=16格（多故事串联）")
        print(f"   → 参考格式: id/name/type/link_note/panels[4](cn+en+emotion+action)")
        print(f"   → 取材方向: 日常生活、情侣互动、网络热梗、季节场景、职场校园")
        print("-" * 60)

    # 记录生产日志（结构化：模式/尺寸/耗时/参考图/剧本 入复盘记录）
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from production_log import log_step_rich
        from PIL import Image as _Img
        w, h = _Img.open(target).size
        gen_data = {
            "mode": mode_used, "grid": "4x4", "image_size": [w, h],
            "ref_count": len(refs),
            "references": [os.path.basename(r) for r in refs],
            "duration_sec": _gen_duration,
        }
        # 联动剧本模式额外记录用了哪些剧本
        if selected_script_names:
            gen_data["linkages_used"] = selected_script_names
        # 含义词若已从剧本生成，一并记录（供复盘对照命名风格）
        if linkage_meaning_map:
            gen_data["meanings_from_linkage"] = list(linkage_meaning_map.values())
        log_step_rich(output_dir, "生图", "OK", step_data=gen_data,
                      details=f"4×4十六宫格生成完成，模式={mode_used}，"
                              f"尺寸{w}x{h}，耗时{_gen_duration}s")
    except Exception as e:
        print(f"  ⚠️ 生产日志写入失败: {e}")


if __name__ == "__main__":
    main()
