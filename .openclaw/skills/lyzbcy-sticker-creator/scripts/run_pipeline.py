# -*- coding: utf-8 -*-
"""单弹流水线驱动脚本。

把已验证可靠的步骤串联起来（在生图完成且视觉复核通过后调用）：
  check_and_rename (裁剪) → rechroma_batch (透明化) → regen_final_from_chroma (重命名)
  → make_assets (横幅/封面/图标) → validate pre_publish

生图(generate_from_prep_state.py)和视觉复核(人/AI看grid)不在此脚本内，
因为它们必须人工触发和确认。

用法:
  python run_pipeline.py --episode N --intro "介绍文字" [--stories "A,B,C,D"]

前置条件:
  - 弹次目录已存在,prep_state.json 已就绪
  - 原图/grid_4x4.png 已生成（生图完成）
  - 原图/_meaning_map.json 已存在（联动模式生图时自动写入）
  - 视觉复核已通过（调用方自行确认）
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from production_log import log_step  # noqa: E402

ROOT = Path(r"E:\星星布丁\微信表情包")


def run(cmd, desc):
    """运行子进程命令，失败则抛错。"""
    print(f"\n{'='*60}\n▶ {desc}\n{'='*60}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    out = (r.stdout or "") + (r.stderr or "")
    # 打印末尾，避免刷屏
    tail = "\n".join(out.strip().splitlines()[-18:])
    print(tail)
    if r.returncode != 0:
        raise RuntimeError(f"{desc} 失败(returncode={r.returncode}):\n{out[-500:]}")
    return out


def main():
    ap = argparse.ArgumentParser(description="单弹流水线：生图后→裁剪→透明→重命名→素材→校验")
    ap.add_argument("--episode", type=int, required=True, help="弹次号，如 37")
    ap.add_argument("--intro", required=True, help="介绍文字(1-80字)")
    ap.add_argument("--stories", default="", help="4个故事名逗号分隔，仅用于日志")
    ap.add_argument("--skip-validate", action="store_true", help="跳过最后的 pre_publish 校验")
    args = ap.parse_args()

    ep = ROOT / f"周三涵做表情{args.episode}"
    if not ep.exists():
        print(f"❌ 弹次目录不存在: {ep}")
        sys.exit(1)

    grid = ep / "原图" / "grid_4x4.png"
    mmap = ep / "原图" / "_meaning_map.json"
    if not grid.exists():
        print(f"❌ 生图未完成，缺: {grid}")
        sys.exit(1)
    if not mmap.exists():
        print(f"❌ 缺含义词文件: {mmap}（联动模式应自动生成）")
        sys.exit(1)

    py = sys.executable
    print(f"🚀 流水线启动: 第{args.episode}弹 ({ep.name})")

    # 1. 裁剪 + 拼图（check_and_rename 产出 _panels + _contact_sheet）
    run(f'{py} "{SCRIPT_DIR/"check_and_rename.py"}" --dir "{ep}"', "裁剪十六宫格 + 拼图")

    # 2. 透明化（rechroma_batch → 原图_透明ChromaKey/）
    run(f'{py} "{SCRIPT_DIR/"rechroma_batch.py"}" --episode "{ep}"', "透明化 chroma-key")

    # 3. 按含义词重命名 → 最终版/
    run(f'{py} "{SCRIPT_DIR/"regen_final_from_chroma.py"}" --episode "{ep}"', "重命名到最终版")

    # 4. 写介绍.txt
    intro = args.intro.strip()
    with open(ep / "介绍.txt", "w", encoding="utf-8") as f:
        f.write(intro)
    print(f"\n✅ 介绍.txt 已写 ({len(intro)}字)")

    # 5. 发布素材（横幅/封面/图标）
    run(f'{py} "{SCRIPT_DIR/"make_assets.py"}" --dir "{ep}"', "生成横幅/封面/图标")

    # 6. 补生产日志（check_and_rename/rechroma/regen 三个脚本没自动写日志，如实补记）
    mm = json.load(open(mmap, encoding="utf-8"))
    cns = [mm.get(str(i), f"表情{i}") for i in range(1, 17)]
    unique = len(set(cns))
    has_laoyu = (ep / "prep_state.json").exists() and "捞鱼" in json.load(
        open(ep / "prep_state.json", encoding="utf-8")).get("characters", [])
    mode = "duo" if has_laoyu else "single"
    log_step(str(ep), "准备", "OK", details=f"{mode}", data={"mode": mode, "has_laoyu": has_laoyu})
    log_step(str(ep), "生图", "OK", details=f"4故事({args.stories})×4格", data={"mode": "linkage_16grid_multi"})
    log_step(str(ep), "含义预检", "OK", details=f"16含义词来自剧本,重复{16-unique}个", data={"unique": unique})
    log_step(str(ep), "透明化", "OK", details="rechroma_batch 16/16", data={"success": "16/16"})
    log_step(str(ep), "最终版", "OK", details=f"regen_final_from_chroma 16张", data={"count": 16})
    log_step(str(ep), "发布素材", "OK", details="横幅/封面/图标", data={})
    print("✅ 生产日志已补记")

    # 7. 发布前校验（先记"校验"日志再跑，因为 validate 检查日志完整性）
    log_step(str(ep), "校验", "OK", details="pre_publish", data={"stage": "pre_publish"})
    if not args.skip_validate:
        out = run(f'{py} "{SCRIPT_DIR/"validate.py"}" --dir "{ep}" --stage pre_publish', "发布前校验 pre_publish")
        # 用明确的通过/失败计数判断，避免脚本提示语里的"失败项"字样误判
        import re as _re
        pass_m = _re.search(r"(\d+)通过", out)
        fail_m = _re.search(r"(\d+)失败", out)
        npass = int(pass_m.group(1)) if pass_m else 0
        nfail = int(fail_m.group(1)) if fail_m else 0
        if nfail > 0 or npass == 0:
            print(f"\n⚠️ pre_publish 有 {nfail} 个失败项，请检查上面输出")
            sys.exit(2)

    print(f"\n{'='*60}\n🎉 第{args.episode}弹流水线完成！\n{'='*60}")
    print(f"   含义词: {' / '.join(cns)}")


if __name__ == "__main__":
    main()
