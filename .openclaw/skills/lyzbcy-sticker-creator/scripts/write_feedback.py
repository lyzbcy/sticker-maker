# -*- coding: utf-8 -*-
"""精选反馈回写工具 —— 发布后标注精选，闭合复盘环。

每弹发布一段时间后，人工挑选优质表情进「精选」目录。
本工具把精选结果回写到 production_record.json 的 quality_feedback 字段，
并支持按行统计（行级混合模式下，看 single 行 vs duo 行的精选贡献）。

用法：
    # 基本用法：自动扫描精选目录统计该弹
    python write_feedback.py --episode 9 --featured-dir "E:/星星布丁/微信表情包/所有表情/精选"

    # 手动指定精选含义词 + 行级分布
    python write_feedback.py --episode 12 --featured-dir "..." \
        --by-row '{"row1":3,"row2":2,"row3_duo":0,"row4":1}' \
        --notes "duo行翻车，single行稳定"

    # 查看某弹当前反馈
    python write_feedback.py --episode 9 --show
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from production_log import write_feedback, get_record


def _episode_dir(episode):
    return os.path.join("E:/星星布丁/微信表情包", f"周三涵做表情{episode}")


def _collect_featured(episode, featured_dir):
    """从精选目录扫描该弹的精选作品，返回 (精选数, 总数, 精选含义词列表)。"""
    prefix = f"第{episode}弹-"
    featured_meanings = []
    for f in os.listdir(featured_dir):
        if f.startswith(prefix) and f.endswith(".png"):
            meaning = f[len(prefix):-4]  # 去掉 "第N弹-" 和 ".png"
            featured_meanings.append(meaning)
    # 总数从最终版目录统计
    final_dir = os.path.join(_episode_dir(episode), "最终版")
    total = 0
    if os.path.isdir(final_dir):
        total = sum(1 for f in os.listdir(final_dir)
                    if f.endswith(".png") and not f.startswith("_"))
    return len(featured_meanings), total, sorted(featured_meanings)


def main():
    parser = argparse.ArgumentParser(description="精选反馈回写工具")
    parser.add_argument("--episode", type=int, required=True, help="弹次编号")
    parser.add_argument("--featured-dir", default="E:/星星布丁/微信表情包/所有表情/精选",
                        help="精选目录路径")
    parser.add_argument("--by-row", default=None,
                        help="行级精选分布 JSON，如 {\"row1\":3,\"row3_duo\":0}")
    parser.add_argument("--notes", default="", help="复盘备注")
    parser.add_argument("--show", action="store_true", help="只查看当前反馈，不写入")
    args = parser.parse_args()

    ep_dir = _episode_dir(args.episode)

    if args.show:
        r = get_record(ep_dir)
        if r is None:
            print(f"❌ 第{args.episode}弹 无 production_record.json")
            return
        fb = r.get("quality_feedback")
        print(json.dumps(fb, ensure_ascii=False, indent=2) if fb else "（尚未回写反馈）")
        return

    if not os.path.isdir(ep_dir):
        print(f"❌ 弹次目录不存在: {ep_dir}")
        return

    feat_count, total, feat_meanings = _collect_featured(args.episode, args.featured_dir)
    rate = round(feat_count / total, 4) if total else 0.0

    feedback = {
        "featured_count": feat_count,
        "featured_total": total,
        "featured_rate": rate,
        "featured_meanings": feat_meanings,
        "review_notes": args.notes,
    }
    if args.by_row:
        feedback["featured_by_row"] = json.loads(args.by_row)

    write_feedback(ep_dir, feedback)
    print(f"✅ 第{args.episode}弹 反馈已回写: {feat_count}/{total} 精选 (率 {rate:.1%})")
    if feat_meanings:
        print(f"   入选含义词: {feat_meanings}")


if __name__ == "__main__":
    main()
