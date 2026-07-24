# -*- coding: utf-8 -*-
"""生产日志审计模块 —— 每弹生成时记录每步执行结果，方便排查问题。

设计目标：
- 每个弹次目录生成一个 `生产日志.md`（人读，向后兼容）
- 同时维护 `production_record.json`（机读，结构化全量记录，复盘用）
- 透明化是否执行、透明像素占比、图片尺寸、含义词命名风格等关键数据都记入
- 防止再出现 12&13 那种"漏跑透明化，最终版带洋红底"的问题

用法（旧 API，保持兼容）：
    from production_log import log_step
    log_step(episode_dir, "生图", "OK",
             details="4×4生成完成",
             data={"mode": "reference", "size": [1024,1024]})

用法（新 API，结构化复盘记录）：
    from production_log import init_record, log_step_rich, write_feedback
    # 准备阶段：初始化 record + 写配置快照
    init_record(episode_dir, episode, config_snapshot={...})
    # 各阶段：写结构化详情（同时自动写一条人读摘要进 生产日志.md）
    log_step_rich(episode_dir, "含义预检", "OK",
                  step_data={"meanings": [...], "meaning_stats": {...}})
    # 发布后：回写精选反馈
    write_feedback(episode_dir, {"featured_count": 7, "featured_by_row": {...}})
"""

import json
import os
import re
from datetime import datetime

LOG_FILENAME = "生产日志.md"
RECORD_FILENAME = "production_record.json"
PIPELINE_VERSION = "2.0"
# 必经步骤（validate 检查时，这些必须都是 OK）
REQUIRED_STEPS = ["准备", "生图", "含义预检", "透明化", "最终版", "发布素材", "校验"]


def _log_path(episode_dir):
    return os.path.join(episode_dir, LOG_FILENAME)


def log_step(episode_dir, step, status, details="", data=None):
    """记录一步执行结果。

    Args:
        episode_dir: 弹次目录
        step: 步骤名（如 "生图"、"透明化"）
        status: 状态（"OK" / "FAIL" / "SKIP" / "WARN"）
        details: 人类可读的描述
        data: 可选的结构化数据（dict），以代码块形式附在后面
    """
    path = _log_path(episode_dir)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 首次创建时写表头
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 生产日志\n\n")
            f.write(f"> 自动生成，记录本弹每一步执行结果。遇到问题时优先看这里。\n\n")
    # 读取已有内容，更新该步骤的记录（同一步骤重复执行则覆盖）
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # 构造本步骤的段落
    icon = {"OK": "✅", "FAIL": "❌", "SKIP": "⏭️", "WARN": "⚠️"}.get(status, "•")
    block = f"\n## {icon} {step} — {status}（{ts}）\n\n"
    if details:
        block += f"{details}\n\n"
    if data:
        block += "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```\n"
    # 用分隔标记便于替换/追加
    marker = f"<!--STEP:{step}-->"
    if marker in content:
        # 替换已有记录（重新执行同一步骤时）
        import re
        pattern = re.compile(
            re.escape(marker) + r".*?(?=<!--STEP:|$)",
            re.DOTALL,
        )
        content = pattern.sub(marker + "\n" + block, content)
    else:
        if "<!--STEPS-->" not in content:
            content += "\n<!--STEPS-->\n"
        content = content.replace(
            "<!--STEPS-->",
            "<!--STEPS-->\n" + marker + "\n" + block,
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def get_step_status(episode_dir, step):
    """读取某步骤的最后状态。返回 (status, details) 或 None。"""
    path = _log_path(episode_dir)
    if not os.path.exists(path):
        return None
    import re
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    marker = f"<!--STEP:{step}-->"
    idx = content.find(marker)
    if idx < 0:
        return None
    # 取该步骤到下一个 STEP 标记之间的内容
    rest = content[idx:]
    next_marker = re.search(r"<!--STEP:(?!%s)" % re.escape(step) + r"[^>]+-->", rest[1:])
    end = next_marker.start() if next_marker else len(rest)
    block = rest[:end]
    # 提取状态（OK 后面可能是全角括号「（」或半角空格，所以用非单词边界）
    m = re.search(r"— (OK|FAIL|SKIP|WARN)(?:\W|$)", block)
    status = m.group(1) if m else "UNKNOWN"
    # 提取描述（第一个非空行）
    lines = [l for l in block.splitlines() if l.strip() and not l.strip().startswith(("<!", "```", "##"))]
    details = lines[0] if lines else ""
    return status, details


def check_required_steps(episode_dir):
    """检查所有必经步骤是否都已 OK。返回 (all_pass, missing_or_failed)。"""
    problems = []
    for step in REQUIRED_STEPS:
        result = get_step_status(episode_dir, step)
        if result is None:
            problems.append(f"{step}: 未执行")
        elif result[0] != "OK":
            problems.append(f"{step}: {result[0]} — {result[1]}")
    return (len(problems) == 0, problems)


# ============================================================
# 结构化复盘记录（production_record.json）—— v2.0 新增
# ============================================================

def _now():
    return datetime.now().isoformat(timespec="seconds")


def _record_path(episode_dir):
    return os.path.join(episode_dir, RECORD_FILENAME)


def _read_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _classify_keyword_style(keyword_combos):
    """判定 keyword 风格：short_combo（emotion_action 短词）/ long_sentence（长描述句）/ mixed。
    这是精选率的强相关因素（高质量弹 100% 用 short_combo）。"""
    if not keyword_combos:
        return "unknown"
    short = sum(1 for k in keyword_combos if "_" in k and len(k.split("_")[0]) <= 14)
    long_ = sum(1 for k in keyword_combos if "_" not in k and len(k.split()) >= 3)
    if short and not long_:
        return "short_combo"
    if long_ and not short:
        return "long_sentence"
    if short and long_:
        return "mixed"
    return "other"


def _classify_meaning_style(meanings):
    """判定含义命名风格：colloquial（口语化聊天词）/ descriptive（描述性场景词）/ mixed。
    高质量弹偏 colloquial（均字 2.1），低质量弹偏 descriptive（均字 2.7）。"""
    if not meanings:
        return {"style_flags": [], "avg_chars": 0}
    # 已知描述性场景词黑名单（来自 0% 精选弹的高频词）
    desc_words = {
        "并肩坐", "手拉手", "靠着你", "躺一起", "悄悄话", "惊讶对视",
        "甜蜜抱", "开心抱", "害羞低头", "冷战", "全神贯注", "亲亲",
        "欢呼", "比心", "捂嘴笑", "开心抱", "惊讶对视", "靠一起",
    }
    words = list(meanings)
    avg = round(sum(len(w) for w in words) / len(words), 2) if words else 0
    has_desc = any(w in desc_words or len(w) >= 4 for w in words)
    has_coll = any(len(w) <= 2 for w in words)
    flags = []
    if has_desc:
        flags.append("descriptive")
    if has_coll and not has_desc:
        flags.append("colloquial")
    if has_coll and has_desc:
        flags = ["mixed"]
    if not flags:
        flags = ["neutral"]
    return {"style_flags": flags, "avg_chars": avg}


def init_record(episode_dir, episode, config_snapshot):
    """准备阶段调用：初始化 production_record.json，写入配置快照。

    Args:
        episode_dir: 弹次目录
        episode: 弹次编号(int)
        config_snapshot: 配置快照 dict，建议包含:
            mode, row_modes(行级混合), reference_mode, keyword_combos,
            keyword_style(自动补), linkages_used, references, characters, costumes
    会自动补全 keyword_style（若未提供），并写一条"准备"摘要进 生产日志.md。
    """
    path = _record_path(episode_dir)
    # 自动判定 keyword 风格
    if "keyword_style" not in config_snapshot and "keyword_combos" in config_snapshot:
        config_snapshot["keyword_style"] = _classify_keyword_style(
            config_snapshot["keyword_combos"])
    record = {
        "episode": episode,
        "episode_name": os.path.basename(episode_dir.rstrip("\\/")),
        "created_at": _now(),
        "pipeline_version": PIPELINE_VERSION,
        "config_snapshot": config_snapshot,
        "steps": {},
        "quality_feedback": None,
    }
    _write_json(path, record)
    # 同步写一条人读摘要（兼容 validate.py）
    mode = config_snapshot.get("mode", "?")
    chars = config_snapshot.get("characters", [])
    ref_mode = config_snapshot.get("reference_mode", "?")
    log_step(episode_dir, "准备", "OK",
             details=f"弹次准备完成：模式={mode}, 角色={','.join(chars)}, "
                     f"参考图模式={ref_mode}, kw风格={config_snapshot.get('keyword_style','?')}",
             data={"mode": mode, "reference_mode": ref_mode,
                   "keyword_style": config_snapshot.get("keyword_style")})


def log_step_rich(episode_dir, step, status, step_data, details="", duration_sec=None):
    """各阶段调用：把结构化 step_data 并入 record.steps[step]。

    同时自动写一条人读摘要进 生产日志.md（向后兼容 validate.py 的检查）。
    step_data 里的字段会被完整保留；若 step_data 含 'meanings'，自动补 meaning_stats。

    Args:
        episode_dir: 弹次目录
        step: 步骤名（必须用 REQUIRED_STEPS 里的标准名）
        status: OK / FAIL / SKIP / WARN
        step_data: 该步骤的结构化记录 dict（见文档 6.3）
        details: 可选的人读描述（不填则从 step_data 自动生成摘要）
        duration_sec: 可选的耗时（秒）
    """
    path = _record_path(episode_dir)
    record = _read_json(path, default=None)
    if record is None:
        # record 未初始化（老流程或漏 init）：兜底创建一个最小 record
        record = {
            "episode": None,
            "episode_name": os.path.basename(episode_dir.rstrip("\\/")),
            "created_at": _now(),
            "pipeline_version": PIPELINE_VERSION,
            "config_snapshot": {},
            "steps": {},
            "quality_feedback": None,
        }
    entry = {"status": status, "ts": _now()}
    if duration_sec is not None:
        entry["duration_sec"] = duration_sec
    # 含义词自动补 meaning_stats
    if step == "含义预检" and "meanings" in step_data and "meaning_stats" not in step_data:
        ms = step_data.get("meanings", [])
        stats = _classify_meaning_style(ms)
        stats["count"] = len(ms)
        stats["unique"] = len(set(ms))
        stats["duplicates"] = len(ms) - len(set(ms))
        step_data["meaning_stats"] = stats
    entry.update(step_data)
    record["steps"][step] = entry
    _write_json(path, record)
    # 兼容：同步写一条人读摘要进 生产日志.md
    summary_data = {k: v for k, v in step_data.items()
                    if k in ("mode", "grid", "size", "count", "duplicates",
                             "avg_transparent_pct", "pass", "fail", "warn",
                             "meaning_stats", "attempts")}
    if not details:
        details = f"{step}: {status}"
    log_step(episode_dir, step, status, details, summary_data if summary_data else None)


def write_feedback(episode_dir, feedback):
    """发布后回写精选反馈，闭合复盘环。

    Args:
        feedback: dict，建议包含:
            featured_count, featured_rate, featured_by_row(行级精选分布),
            featured_meanings(入选含义词), review_notes(复盘备注)
    """
    path = _record_path(episode_dir)
    record = _read_json(path, default=None)
    if record is None:
        record = {
            "episode": None,
            "episode_name": os.path.basename(episode_dir.rstrip("\\/")),
            "created_at": _now(),
            "pipeline_version": PIPELINE_VERSION,
            "config_snapshot": {},
            "steps": {},
            "quality_feedback": None,
        }
    record["quality_feedback"] = feedback
    _write_json(path, record)


def get_record(episode_dir):
    """读取整弹的 production_record.json，供复盘脚本消费。"""
    return _read_json(_record_path(episode_dir), default=None)
