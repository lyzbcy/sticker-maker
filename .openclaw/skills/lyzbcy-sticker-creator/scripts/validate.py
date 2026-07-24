#!/usr/bin/env python3
"""
微信表情包 全流程校验器 / WeChat Sticker Validator
===================================================
模块化约束脚本，每步返回 PASS/FAIL/WARN + 修复建议。

设计原则：
- 每个 check_xxx() 独立可调用
- 返回结构化结果 (status, message, fix_hint)
- 笨蛋AI也能看懂报错
- 支持 --stage pre_generate / post_generate / pre_publish / full

用法：
    python validate.py --dir "E:\星星布丁\微信表情包\周三涵做表情1" --stage pre_publish
    python validate.py --dir "E:\星星布丁\微信表情包\周三涵做表情1" --stage full
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Windows GBK 编码修复
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 接入生产日志审计
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from production_log import check_required_steps, get_step_status
except Exception:
    check_required_steps = None
    get_step_status = None

# ============================================================
# 微信表情平台规范常量
# ============================================================
WECHAT_SPECS = {
    "sticker": {
        "width": 240,
        "height": 240,
        "min_side": 240,   # 尺寸下限（微信会压缩，不强制精确240）
        "max_side": 360,   # 尺寸上限
        "format": "PNG",
        "max_size_bytes": 500 * 1024,  # 500KB 警告线
        "min_count": 12,                # 最少12张（一弹）
        "max_count": 24,                # 最多24张
    },
    "banner": {
        "width": 750,
        "height": 400,
        "format": "PNG / JPG",
        "max_size_bytes": 500 * 1024,
    },
    "cover": {
        "width": 240,
        "height": 240,
        "format": "PNG",
        "max_size_bytes": 500 * 1024,
    },
    "icon": {
        "width": 50,
        "height": 50,
        "format": "PNG",
        "max_size_bytes": 100 * 1024,
    },
    "meaning": {
        "max_chars_per": 4,       # 每个含义词最多4字
        "min_chars_per": 1,       # 最少1字
        "no_duplicates": True,
    }
}

# ============================================================
# 工具函数
# ============================================================

class Result:
    """统一结果对象"""
    def __init__(self, check_name, status, message, fix_hint=""):
        self.check_name = check_name
        self.status = status    # PASS / FAIL / WARN
        self.message = message
        self.fix_hint = fix_hint
    
    def to_dict(self):
        return {
            "check": self.check_name,
            "status": self.status,
            "message": self.message,
            "fix": self.fix_hint
        }
    
    def print(self):
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(self.status, "❓")
        print(f"  {icon} [{self.status}] {self.check_name}: {self.message}")
        if self.fix_hint:
            print(f"      💡 修复: {self.fix_hint}")


def safe_png_info(p):
    """安全获取 PNG 信息，返回 (width, height, has_alpha) 或 None"""
    try:
        from PIL import Image
        img = Image.open(p)
        w, h = img.size
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        return w, h, has_alpha, os.path.getsize(p)
    except Exception as e:
        return None


# ============================================================
# 阶段 1: 生成前校验 (pre_generate)
# ============================================================

def check_base_images(config_path):
    """检查 base 图是否全部存在"""
    results = []
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        return [Result("base_images", "FAIL", f"无法加载 config.yaml: {e}")]
    
    base_images = config.get("base_images", {})
    if not base_images:
        return [Result("base_images", "FAIL", "config.yaml 中没有 base_images 配置")]
    
    missing = []
    found = []
    for char, variants in base_images.items():
        if isinstance(variants, dict):
            for variant, path in variants.items():
                if os.path.exists(path):
                    found.append(f"{char}/{variant}")
                else:
                    missing.append(f"{char}/{variant}")
        elif isinstance(variants, str):
            if os.path.exists(variants):
                found.append(char)
            else:
                missing.append(char)
    
    if missing:
        return [Result(
            "base_images",
            "FAIL",
            f"缺失 {len(missing)} 张 base 图: {', '.join(missing)}",
            f"检查路径是否正确，文件是否存在"
        )]
    
    return [Result("base_images", "PASS", f"全部 {len(found)} 张 base 图就绪")]


def check_reference_library(config_path, mode="single"):
    """检查参考图库存"""
    results = []
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        return [Result("reference_library", "FAIL", f"无法加载config: {e}")]
    
    ref_dir = config.get("reference_library", "")
    if not ref_dir or not os.path.exists(ref_dir):
        return [Result("reference_library", "FAIL", "参考图库路径不存在", "检查 config.yaml 中 reference_library")]
    
    all_refs = list(Path(ref_dir).glob("*.png")) + list(Path(ref_dir).glob("*.jpg"))
    
    if mode in ("single", "quad"):
        available = [r for r in all_refs if "双人" not in r.name]
    else:
        available = all_refs
    
    if len(available) >= 4:
        return [Result("reference_library", "PASS", f"可用参考图: {len(available)} 张 (≥4, 可走参考图模式)")]
    elif len(available) > 0:
        return [Result("reference_library", "WARN", f"参考图不足: {len(available)} 张 (<4, 回退 AI 模板)", "补充参考图或接受AI模板模式")]
    else:
        return [Result("reference_library", "WARN", "参考图库存为空，将使用AI模板模式", "添加参考图到参考图库目录")]


def check_codex_cli():
    """检查 Codex CLI 是否可用"""
    import subprocess
    codex_paths = [
        r"C:\Users\24676\AppData\Roaming\npm\codex.cmd",
        "codex"
    ]
    for cp in codex_paths:
        try:
            result = subprocess.run([cp, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return [Result("codex_cli", "PASS", f"Codex CLI 可用: {cp}")]
        except:
            continue
    
    return [Result("codex_cli", "FAIL", "Codex CLI 不可用", "安装 Codex CLI: npm install -g @anthropic-ai/codex")]


# ============================================================
# 阶段 2: 生成后校验 (post_generate)
# ============================================================

def check_folder_structure(base_dir):
    """检查文件夹结构是否完整"""
    results = []
    required = ["原图", "最终版"]
    recommended = ["横幅", "封面", "图标"]
    
    for folder in required:
        p = os.path.join(base_dir, folder)
        if os.path.isdir(p):
            results.append(Result(f"folder.{folder}", "PASS", f"{folder}/ 存在"))
        else:
            results.append(Result(f"folder.{folder}", "FAIL", f"缺少 {folder}/ 目录", f"运行 init 或手动创建 {folder}/"))
    
    for folder in recommended:
        p = os.path.join(base_dir, folder)
        if os.path.isdir(p):
            results.append(Result(f"folder.{folder}", "PASS", f"{folder}/ 存在"))
        else:
            results.append(Result(f"folder.{folder}", "WARN", f"缺少 {folder}/ 目录", f"运行 python make_assets.py --dir {base_dir}"))
    
    return results


def check_sticker_images(base_dir):
    """检查最终版/中的表情图是否符合微信规范"""
    results = []
    final_dir = os.path.join(base_dir, "最终版")
    
    if not os.path.isdir(final_dir):
        return [Result("sticker_images", "FAIL", f"最终版/ 目录不存在", f"先完成生图和重命名")]
    
    images = [f for f in os.listdir(final_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if not images:
        return [Result("sticker_images", "FAIL", "最终版/ 中没有图片", "先完成生图和裁剪")]
    
    spec = WECHAT_SPECS["sticker"]
    
    # 数量检查
    count = len(images)
    if count < spec["min_count"]:
        results.append(Result("sticker_count", "FAIL", f"图片数量不足: {count}/{spec['min_count']} (最少16张)", f"需要再生成至少 {spec['min_count'] - count} 张"))
    elif count > spec["max_count"]:
        results.append(Result("sticker_count", "WARN", f"图片数量超标: {count}/{spec['max_count']} (最多24张)", f"选择最好的 {spec['max_count']} 张提交"))
    else:
        results.append(Result("sticker_count", "PASS", f"数量合格: {count}张 (要求{spec['min_count']}-{spec['max_count']})"))
    
    # 逐张检查
    errors = []
    warnings = []
    for img_name in images:
        img_path = os.path.join(final_dir, img_name)
        info = safe_png_info(img_path)
        
        if info is None:
            errors.append(f"{img_name}: 无法读取")
            continue
        
        w, h, has_alpha, size = info
        
        # 尺寸（贴纸放宽到 240-360，微信上传时会压缩；不强制精确 240）
        min_s = spec.get("min_side", spec["width"])
        max_s = spec.get("max_side", spec["width"])
        if w < min_s or w > max_s or h < min_s or h > max_s:
            errors.append(f"{img_name}: 尺寸 {w}×{h} (需要 {min_s}-{max_s} 范围)")
        elif w != h:
            warnings.append(f"{img_name}: 非正方形 {w}×{h} (建议正方形)")
        
        # 格式 (只检查扩展名)
        if not img_name.lower().endswith('.png'):
            errors.append(f"{img_name}: 格式 {os.path.splitext(img_name)[1]} (需要 PNG)")
        
        # 透明通道（建议但非强制）
        if not has_alpha:
            warnings.append(f"{img_name}: 无透明通道 (建议RGBA，但非强制)")
        
        # 文件大小
        if size > spec["max_size_bytes"]:
            errors.append(f"{img_name}: 文件过大 {size//1024}KB (警告线 {spec['max_size_bytes']//1024}KB)")
    
    if errors:
        results.append(Result("sticker_individual", "FAIL", f"{len(errors)}张图有问题:", "\n".join(errors[:5])))
        if len(errors) > 5:
            results[-1].fix_hint += f"\n...还有 {len(errors)-5} 个问题"
    elif warnings:
        results.append(Result("sticker_individual", "WARN",
            f"{len(warnings)}张图无透明通道 (非强制)", 
            "微信建议透明背景PNG，但有背景的图通常也能过审"))
    else:
        results.append(Result("sticker_individual", "PASS", f"全部 {count} 张图片尺寸/格式/透明通道合格"))
    
    return results


def check_meanings(base_dir):
    """检查含义词"""
    results = []
    final_dir = os.path.join(base_dir, "最终版")
    
    if not os.path.isdir(final_dir):
        return [Result("meanings", "FAIL", "最终版/ 目录不存在")]
    
    images = [f for f in os.listdir(final_dir) if f.lower().endswith('.png')]
    spec = WECHAT_SPECS["meaning"]

    if not images:
        return [Result("meanings", "FAIL", "最终版/ 中没有图片，无法校验含义词", "先完成生图、裁剪和重命名")]
    
    meanings = []
    issues = []
    
    for img in images:
        # 提取含义词
        name = os.path.splitext(img)[0]
        if name.isdigit():
            issues.append(f"{img}: 数字命名，请用中文含义词重命名")
            continue
        
        meanings.append(name)
        
        if len(name) > spec["max_chars_per"]:
            issues.append(f"{img}: 含义词'{name}'超过{spec['max_chars_per']}字")
        if len(name) < spec["min_chars_per"]:
            issues.append(f"{img}: 含义词'{name}'少于{spec['min_chars_per']}字")
    
    # 检查重复
    seen = {}
    for m in meanings:
        if m in seen:
            issues.append(f"含义词重复: '{m}' (出现在{len([img for img in images if img.startswith(m)])}张图)")
        seen[m] = True
    
    if issues:
        results.append(Result("meanings", "FAIL", f"含义词问题: {len(issues)}个", "\n".join(issues[:5])))
    else:
        results.append(Result("meanings", "PASS", f"全部 {len(meanings)} 个含义词合格，无重复"))
    
    return results


# ============================================================
# 阶段 3: 发布前校验 (pre_publish)
# ============================================================

def check_banner(base_dir):
    """检查横幅"""
    banner_paths = [
        os.path.join(base_dir, "横幅", "横幅.png"),
        os.path.join(base_dir, "横幅", "banner.png"),
    ]
    spec = WECHAT_SPECS["banner"]
    
    for bp in banner_paths:
        if os.path.exists(bp):
            info = safe_png_info(bp)
            if info is None:
                return [Result("banner", "FAIL", f"横幅文件损坏: {bp}")]
            w, h, _, size = info
            if w != spec["width"] or h != spec["height"]:
                return [Result("banner", "FAIL", f"横幅尺寸错误: {w}×{h} (需要 {spec['width']}×{spec['height']})", f"运行 python make_banner.py 重新生成")]
            if size > spec["max_size_bytes"]:
                return [Result("banner", "WARN", f"横幅文件较大: {size//1024}KB (>500KB会压缩)", "考虑压缩或降低复杂度")]
            return [Result("banner", "PASS", f"横幅合格: {w}×{h}, {size//1024}KB")]
    
    return [Result("banner", "FAIL", "横幅/横幅.png 不存在", f"运行 python make_banner.py --input-dir 最终版/ --output-dir 横幅/")]


def check_cover(base_dir):
    """检查封面"""
    cover_paths = [
        os.path.join(base_dir, "封面", "封面.png"),
        os.path.join(base_dir, "封面", "cover.png"),
    ]
    spec = WECHAT_SPECS["cover"]
    
    req_w = spec["width"]
    req_h = spec["height"]
    
    for cp in cover_paths:
        if os.path.exists(cp):
            info = safe_png_info(cp)
            if info is None:
                return [Result("cover", "FAIL", f"封面文件损坏: {cp}")]
            w, h, has_alpha, size = info
            if w != req_w or h != req_h:
                return [Result("cover", "FAIL",
                    "封面尺寸错误: {}x{} (需要 {}x{})".format(w, h, req_w, req_h),
                    "运行 python make_cover.py 重新生成")]
            if not has_alpha:
                return [Result("cover", "WARN",
                    "封面无透明通道，微信建议透明背景PNG",
                    "使用透明背景的图片作为封面")]
            return [Result("cover", "PASS",
                "封面合格: {}x{}, RGBA, {}KB".format(w, h, size // 1024))]
    
    return [Result("cover", "FAIL",
        "封面/封面.png 不存在",
        "运行 python make_cover.py --input 最佳表情图.png --output 封面/封面.png")]


def check_icon(base_dir):
    """检查图标"""
    icon_paths = [
        os.path.join(base_dir, "图标", "图标.png"),
        os.path.join(base_dir, "图标", "icon.png"),
    ]
    spec = WECHAT_SPECS["icon"]
    req_w = spec["width"]
    req_h = spec["height"]
    max_size = spec["max_size_bytes"]
    
    for ip in icon_paths:
        if os.path.exists(ip):
            info = safe_png_info(ip)
            if info is None:
                return [Result("icon", "FAIL", f"图标文件损坏: {ip}")]
            w, h, has_alpha, size = info
            if w != req_w or h != req_h:
                return [Result("icon", "FAIL",
                    "图标尺寸错误: {}x{} (需要 {}x{})".format(w, h, req_w, req_h),
                    "运行 python make_icon.py 重新生成")]
            if not has_alpha:
                return [Result("icon", "WARN",
                    "图标无透明通道，微信要求透明背景",
                    "使用透明背景的头部截图")]
            if size > max_size:
                return [Result("icon", "WARN",
                    "图标文件较大: {}KB (>{}KB会压缩)".format(size // 1024, max_size // 1024),
                    "压缩图片")]
            return [Result("icon", "PASS",
                "图标合格: {}x{}, RGBA, {}KB".format(w, h, size // 1024))]
    
    return [Result("icon", "FAIL",
        "图标/图标.png 不存在",
        "运行 python make_icon.py --input 脸部特写.png --output 图标/图标.png")]


def check_description(base_dir):
    """检查表情介绍：发布页限制 80 字，优先使用 AI 写入的介绍.txt。"""
    candidates = ["介绍.txt", "表情介绍.txt", "description.txt"]
    for filename in candidates:
        path = os.path.join(base_dir, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                desc = " ".join(f.read().split()).strip()
        except Exception as e:
            return [Result("description", "FAIL", f"介绍文件读取失败: {filename} ({e})")]

        length = len(desc)
        if length == 0:
            return [Result("description", "FAIL", f"{filename} 为空", "请让 AI 写 1-80 字表情介绍")]
        if length > 80:
            return [Result("description", "FAIL", f"{filename} 超过 80 字: {length}/80", "压缩到 80 字以内")]
        return [Result("description", "PASS", f"介绍合格: {filename} ({length}/80)")]

    return [Result("description", "WARN", "缺少介绍.txt", "发布前让 AI 根据角色和含义词写 1-80 字介绍")]


def check_role_card(base_dir):
    """检查本次制作角色.md"""
    card_path = os.path.join(base_dir, "本次制作角色.md")
    if not os.path.exists(card_path):
        return [Result("role_card", "WARN", "本次制作角色.md 不存在，发布时将默认选「人物合辑」", "手动创建或在 main.py 自动生成")]
    
    with open(card_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    has_laoyu = "含捞鱼" in content
    if not has_laoyu:
        return [Result("role_card", "WARN", "角色卡中未找到「含捞鱼」标记", "补充含捞鱼：是/否")]
    
    return [Result("role_card", "PASS", "角色卡就绪")]


def check_appreciation_assets(base_dir=None):
    """检查赞赏页素材"""
    results = []
    
    only_laoyu = False
    if base_dir:
        card_path = os.path.join(base_dir, "本次制作角色.md")
        if os.path.exists(card_path):
            try:
                with open(card_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                only_laoyu = "只含捞鱼：是" in content or "角色分类：男人" in content
            except Exception:
                pass
                
    if only_laoyu:
        guide = r"E:\星星布丁\微信表情包\赞赏页\捞鱼-赞赏引导图.png"
        thanks = r"E:\星星布丁\微信表情包\赞赏页\捞鱼-赞赏致谢图.png"
        guide_name = "捞鱼-赞赏引导图.png"
        thanks_name = "捞鱼-赞赏致谢图.png"
    else:
        guide = r"E:\星星布丁\微信表情包\赞赏页\赞赏引导图.png"
        thanks = r"E:\星星布丁\微信表情包\赞赏页\赞赏致谢图.png"
        guide_name = "赞赏引导图.png"
        thanks_name = "赞赏致谢图.png"
    
    if os.path.exists(guide):
        results.append(Result("appreciation.guide", "PASS", f"赞赏引导图就绪 ({guide_name})"))
    else:
        results.append(Result("appreciation.guide", "FAIL", f"赞赏引导图缺失: {guide}", "准备赞赏引导图"))
    
    if os.path.exists(thanks):
        results.append(Result("appreciation.thanks", "PASS", f"赞赏致谢图就绪 ({thanks_name})"))
    else:
        results.append(Result("appreciation.thanks", "FAIL", f"赞赏致谢图缺失: {thanks}", "准备赞赏致谢图"))
    
    return results


# ============================================================
# 主入口
# ============================================================

def check_production_log(base_dir):
    """检查生产日志：必经步骤是否都执行了（防止漏步，如漏跑透明化）。"""
    results = []
    if check_required_steps is None:
        return results  # 生产日志模块不可用，跳过

    all_pass, problems = check_required_steps(base_dir)
    if all_pass:
        results.append(Result("production_log", "PASS",
                              "生产日志：所有必经步骤均已执行"))
    else:
        # 区分 FAIL（关键步骤漏了/失败）和 WARN（非关键步骤未记录）
        critical = ["生图", "透明化", "最终版"]
        has_critical = any(any(c in p for c in critical) for p in problems)
        severity = "FAIL" if has_critical else "WARN"
        results.append(Result("production_log", severity,
                              f"生产日志：{len(problems)} 个步骤未完成或失败",
                              "\n".join(problems)))
    return results


def run_checks(stage, base_dir, config_path=None, mode="single"):
    """运行指定阶段的全部检查"""
    all_results = []
    
    if stage in ("pre_generate", "full"):
        print("\n" + "="*60)
        print("📋 阶段 1: 生成前校验 (pre_generate)")
        print("="*60)
        
        if config_path:
            all_results.extend(check_base_images(config_path))
            all_results.extend(check_reference_library(config_path, mode))
        all_results.extend(check_codex_cli())
    
    if stage in ("post_generate", "full"):
        print("\n" + "="*60)
        print("📋 阶段 2: 生成后校验 (post_generate)")
        print("="*60)
        
        all_results.extend(check_folder_structure(base_dir))
        all_results.extend(check_sticker_images(base_dir))
        all_results.extend(check_meanings(base_dir))
    
    if stage in ("pre_publish", "full"):
        print("\n" + "="*60)
        print("📋 阶段 3: 发布前校验 (pre_publish)")
        print("="*60)
        
        all_results.extend(check_folder_structure(base_dir))
        all_results.extend(check_sticker_images(base_dir))
        all_results.extend(check_meanings(base_dir))
        all_results.extend(check_banner(base_dir))
        all_results.extend(check_cover(base_dir))
        all_results.extend(check_icon(base_dir))
        all_results.extend(check_description(base_dir))
        all_results.extend(check_role_card(base_dir))
        all_results.extend(check_appreciation_assets(base_dir))
        all_results.extend(check_production_log(base_dir))
    
    # 打印结果
    print()
    for r in all_results:
        r.print()
    
    # 统计
    pass_count = sum(1 for r in all_results if r.status == "PASS")
    fail_count = sum(1 for r in all_results if r.status == "FAIL")
    warn_count = sum(1 for r in all_results if r.status == "WARN")
    
    print()
    print("="*60)
    print(f"📊 校验结果: ✅ {pass_count}通过  ❌ {fail_count}失败  ⚠️ {warn_count}警告")
    print("="*60)
    
    if fail_count > 0:
        print()
        print("🔴 存在失败项，请修复后重试！")
        print(f"   失败的检查: {', '.join(r.check_name for r in all_results if r.status == 'FAIL')}")

    # 记录生产日志（结构化：校验明细入复盘记录）
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from production_log import log_step_rich
        failed_items = [r.check_name for r in all_results if r.status == "FAIL"]
        warned_items = [r.check_name for r in all_results if r.status == "WARN"]
        log_step_rich(base_dir, "校验",
                      "OK" if fail_count == 0 else "FAIL",
                      step_data={"stage": stage, "pass": pass_count,
                                 "fail": fail_count, "warn": warn_count,
                                 "failed_items": failed_items,
                                 "warned_items": warned_items},
                      details=f"{stage}: {pass_count}PASS/{fail_count}FAIL/{warn_count}WARN")
    except Exception:
        pass

    # 返回 JSON 结果（供脚本调用）
    return {
        "stage": stage,
        "pass": pass_count,
        "fail": fail_count,
        "warn": warn_count,
        "results": [r.to_dict() for r in all_results],
        "ok": fail_count == 0
    }


def main():
    parser = argparse.ArgumentParser(description="微信表情包全流程校验器")
    parser.add_argument("--dir", required=True, help="表情包目录路径")
    parser.add_argument("--stage", required=True, choices=["pre_generate", "post_generate", "pre_publish", "full"], help="校验阶段")
    parser.add_argument("--config", default=None, help="config.yaml 路径 (pre_generate 阶段需要)")
    parser.add_argument("--mode", default="single", help="生成模式: single/duo/quad")
    parser.add_argument("--json", action="store_true", help="以JSON格式输出")
    
    args = parser.parse_args()
    
    if args.stage in ("pre_generate", "full") and not args.config:
        # 自动查找 config.yaml
        skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_config = os.path.join(skill_dir, "config.yaml")
        if os.path.exists(default_config):
            args.config = default_config
    
    result = run_checks(args.stage, args.dir, args.config, args.mode)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
