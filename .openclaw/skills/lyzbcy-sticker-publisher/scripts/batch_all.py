#!/usr/bin/env python3
"""批量发布总控：分批调用 batch_publish.js，支持断点续传 + 失败自动重试。

为什么需要这个脚本：
  单弹发布约 90-115 秒，且每弹会启停一次 Edge 浏览器。
  外层 AI 的单次 Bash 调用通常有 ~10 分钟超时，装不下几十弹连续发布。
  本脚本把待发布弹次切成小批（默认 5 弹/批，≈10 分钟），逐批跑，
  每批结束立即合并结果到 _batch_total.json，即使中途被超时杀掉，
  已完成的批次也安全保存，下次运行自动从断点续传（跳过已成功弹次）。

用法：
  # 发布弹 19-54（默认范围）
  python batch_all.py
  # 指定范围
  python batch_all.py --start 19 --end 54
  # 指定具体弹次（逗号分隔，优先于 start/end）
  python batch_all.py --only 23,51,53
  # 续传模式：跳过 _batch_total.json 里已 OK 的弹次，只补发剩余 + 重试失败的
  python batch_all.py --resume
  # 修改每批大小和弹间间隔（秒）
  python batch_all.py --batch 5 --gap 8
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BATCH_JS = SCRIPT_DIR / "batch_publish.js"
RESULT_TOTAL = SCRIPT_DIR / "_batch_total.json"      # 跨批次累积结果（断点续传依据）
RESULT_BATCH = SCRIPT_DIR / "_batch_result.json"     # batch_publish.js 当批输出（会被覆盖）

ROOT = Path(r"E:\星星布丁\微信表情包")


def load_total():
    """读取累积结果 {ep: record}。"""
    if RESULT_TOTAL.exists():
        try:
            return {r["ep"]: r for r in json.loads(RESULT_TOTAL.read_text(encoding="utf-8"))}
        except Exception:
            return {}
    return {}


def save_total(total):
    """写入累积结果（按 ep 排序）。"""
    RESULT_TOTAL.write_text(
        json.dumps([total[k] for k in sorted(total)], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def merge_batch_into_total(total):
    """把 batch_publish.js 当批的 _batch_result.json 合并进 total。"""
    if not RESULT_BATCH.exists():
        return
    try:
        for r in json.loads(RESULT_BATCH.read_text(encoding="utf-8")):
            total[r["ep"]] = r
    except Exception:
        pass


def ok_eps(total):
    return {e for e, r in total.items() if r.get("status") == "OK"}


def run_batch(eps, gap):
    """跑一批弹次（调用 batch_publish.js）。"""
    only_str = ",".join(str(e) for e in eps)
    print(f"\n▶ 批次 弹{eps[0]}-{eps[-1]} ({only_str})")
    r = subprocess.run(
        ["node", str(BATCH_JS), "--only", only_str, "--gap", str(gap)],
        cwd=str(SCRIPT_DIR), capture_output=True, text=True,
        encoding="utf-8", errors="ignore",
    )
    # 打印尾部进度
    tail = "\n".join((r.stdout or "").splitlines()[-12:])
    if tail.strip():
        print(tail)
    if r.returncode != 0 and r.stderr:
        print("  (stderr):", r.stderr.strip()[-200:])


def main():
    ap = argparse.ArgumentParser(description="批量发布总控：分批 + 断点续传 + 失败重试")
    ap.add_argument("--start", type=int, default=19, help="起始弹次（默认19）")
    ap.add_argument("--end", type=int, default=54, help="结束弹次（默认54）")
    ap.add_argument("--only", default=None, help="指定弹次，逗号分隔（优先于 start/end）")
    ap.add_argument("--resume", action="store_true", help="续传：跳过已 OK 的弹次，只补发剩余")
    ap.add_argument("--retry", type=int, default=2, help="全部跑完后，对失败弹次自动重试次数（默认2）")
    ap.add_argument("--batch", type=int, default=5, help="每批弹数（默认5，适配10分钟超时）")
    ap.add_argument("--gap", type=int, default=8, help="弹间间隔秒数（默认8）")
    args = ap.parse_args()

    # 确定待发布弹次
    if args.only:
        target = sorted({int(x) for x in args.only.split(",")})
    else:
        target = list(range(args.start, args.end + 1))

    total = load_total()

    # 续传：剔除已成功弹次
    if args.resume:
        already = sorted(ok_eps(total) & set(target))
        target = [e for e in target if e not in ok_eps(total)]
        print(f"📦 续传模式：目标 {len(already) + len(target)} 弹，已成功 {len(already)} 弹，"
              f"本次待发 {len(target)} 弹: {target}")
    else:
        print(f"📦 批量发布：共 {len(target)} 弹: {target}")

    if not target:
        print("✅ 无待发布弹次（全部已完成）")
    else:
        print(f"   每批 {args.batch} 弹，弹间间隔 {args.gap} 秒\n" + "=" * 60)
        # 分批发布
        for i in range(0, len(target), args.batch):
            chunk = target[i:i + args.batch]
            run_batch(chunk, args.gap)
            merge_batch_into_total(total)
            save_total(total)
            done = len(ok_eps(total) & set(target))
            print(f"  本批结束，目标内已成功 {done}/{len(target)}")

    # 失败重试
    all_target = sorted({int(x) for x in (args.only.split(",") if args.only else range(args.start, args.end + 1))})
    failed = sorted(set(all_target) - ok_eps(total))
    for attempt in range(1, args.retry + 1):
        failed = sorted(set(all_target) - ok_eps(total))
        if not failed:
            break
        print(f"\n🔄 失败重试 {attempt}/{args.retry}：{failed}")
        for e in failed:
            run_batch([e], 0)
            merge_batch_into_total(total)
            save_total(total)

    # 汇总
    ok = sorted(ok_eps(total) & set(all_target))
    fail = sorted(set(all_target) - ok_eps(total))
    print("\n" + "=" * 60 + "\n🏁 批量发布完成\n" + "=" * 60)
    print(f"✅ 成功({len(ok)}): {ok}")
    print(f"❌ 失败({len(fail)}): {fail}")
    print(f"📄 结果: {RESULT_TOTAL}")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
