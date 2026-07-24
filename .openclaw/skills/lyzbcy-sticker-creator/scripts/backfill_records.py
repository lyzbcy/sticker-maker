# -*- coding: utf-8 -*-
"""批量补写历史弹次的 production_record.json（复盘用）。

从现有的 prep_state.json（制作配置）+ _meaning_map.json（原始命名）反推，
给第1-54弹生成结构化复盘记录。让精选质量分析报告里的手动统计以后能脚本化复现。

用法：
    python backfill_records.py                    # 补写所有缺失的弹次
    python backfill_records.py --episode 9        # 只补某一弹
    python backfill_records.py --force            # 覆盖已存在的 record
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from production_log import init_record, log_step_rich, write_feedback, get_record

ROOT = "E:/星星布丁/微信表情包"
FEATURED_DIR = os.path.join(ROOT, "所有表情/精选")


def _collect_featured(episode):
    """扫描精选目录，返回 (精选数, 精选含义词列表)。"""
    prefix = f"第{episode}弹-"
    meanings = []
    for f in os.listdir(FEATURED_DIR):
        if f.startswith(prefix) and f.endswith(".png"):
            meanings.append(f[len(prefix):-4])
    return len(meanings), sorted(meanings)


def backfill_episode(episode, force=False):
    ep_dir = os.path.join(ROOT, f"周三涵做表情{episode}")
    state_path = os.path.join(ep_dir, "prep_state.json")
    record_path = os.path.join(ep_dir, "production_record.json")

    if not os.path.isdir(ep_dir):
        return False, "目录不存在"
    if os.path.exists(record_path) and not force:
        return False, "已存在（跳过，用 --force 覆盖）"
    if not os.path.exists(state_path):
        return False, "无 prep_state.json（星系列早期弹次）"

    state = json.load(open(state_path, encoding="utf-8"))

    # 1. 初始化 record + 配置快照（从 prep_state 反推）
    config_snapshot = {
        "mode": state.get("mode"),
        "characters": state.get("characters", []),
        "costumes": state.get("costumes", {}),
        "reference_mode": state.get("reference_mode"),
        "keyword_combos": state.get("keyword_combos", []),
        "references": state.get("references", []),
        "ref_count": len(state.get("references", [])),
        "sticker_type": state.get("sticker_type"),
        "has_laoyu": state.get("has_laoyu"),
        "backfilled": True,  # 标记为反推数据（非实时记录）
    }
    init_record(ep_dir, episode, config_snapshot)

    # 2. 含义预检步骤（从 _meaning_map.json 反推）
    map_path = os.path.join(ep_dir, "原图", "_meaning_map.json")
    if os.path.exists(map_path):
        mmap = json.load(open(map_path, encoding="utf-8"))
        meanings = [mmap[str(i)] for i in range(1, 17) if str(i) in mmap]
        if meanings:
            log_step_rich(ep_dir, "含义预检", "OK", step_data={
                "meanings": meanings,
                "vision_check": {"method": "backfill_from_meaning_map"},
            }, details=f"（反推）含义命名 {len(meanings)} 个")

    # 3. 精选反馈（从精选目录扫描）
    feat_count, feat_meanings = _collect_featured(episode)
    final_dir = os.path.join(ep_dir, "最终版")
    total = sum(1 for f in os.listdir(final_dir)
                if f.endswith(".png") and not f.startswith("_")) if os.path.isdir(final_dir) else 0
    rate = round(feat_count / total, 4) if total else 0.0
    write_feedback(ep_dir, {
        "featured_count": feat_count,
        "featured_total": total,
        "featured_rate": rate,
        "featured_meanings": feat_meanings,
        "review_notes": "（反推自精选目录）",
    })
    return True, f"精选 {feat_count}/{total} ({rate:.1%})"


def main():
    parser = argparse.ArgumentParser(description="批量补写历史 production_record.json")
    parser.add_argument("--episode", type=int, default=None, help="只补某一弹")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 record")
    args = parser.parse_args()

    episodes = [args.episode] if args.episode else range(1, 55)
    ok, skip, fail = 0, 0, 0
    for ep in episodes:
        done, msg = backfill_episode(ep, force=args.force)
        if done:
            print(f"✅ 第{ep:>2}弹: {msg}")
            ok += 1
        elif "跳过" in msg:
            skip += 1
        else:
            print(f"⏭️  第{ep:>2}弹: {msg}")
            fail += 1
    print(f"\n📊 完成: {ok} 补写, {skip} 跳过, {fail} 不可补（早期星系列无 prep_state）")


if __name__ == "__main__":
    main()
