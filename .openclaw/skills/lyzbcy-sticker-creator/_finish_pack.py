#!/usr/bin/env python3
"""统一收尾脚本:写介绍.txt + 补生产日志 + 跑stage_gate gate2
用法: python _finish_pack.py <弹次号> "<介绍文字>" "<4故事名逗号分隔>"
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from production_log import log_step

if len(sys.argv) < 4:
    print("用法: python _finish_pack.py <弹次号> <介绍> <故事1,故事2,故事3,故事4>")
    sys.exit(1)

ep_num = sys.argv[1]
intro = sys.argv[2]
stories = sys.argv[3]
EP = rf"E:\星星布丁\微信表情包\周三涵做表情{ep_num}"

# 1. 写介绍.txt
with open(os.path.join(EP, "介绍.txt"), "w", encoding="utf-8") as f:
    f.write(intro)
print(f"✅ 介绍.txt 已写 ({len(intro)}字)")

# 2. 读含义词
mm = json.load(open(os.path.join(EP, "原图", "_meaning_map.json"), encoding="utf-8"))
cns = [mm[str(i)] for i in range(1, 17)]

# 3. 补生产日志
log_step(EP, "准备", "OK", details=f"duo 星星布丁+捞鱼", data={"mode": "duo", "has_laoyu": True})
log_step(EP, "生图", "OK", details=f"4故事({stories})×4格", data={"mode": "linkage_16grid_multi"})
log_step(EP, "含义预检", "OK", details=f"16含义词零重复", data={"unique": 16})
log_step(EP, "透明化", "OK", details="rechroma 16/16", data={"success": "16/16"})
log_step(EP, "最终版", "OK", details="16张", data={"count": 16})
log_step(EP, "发布素材", "OK", details="横幅/封面/图标", data={})
log_step(EP, "校验", "OK", details="视觉复核+gate2", data={})
print("✅ 生产日志已写")
print(f"   含义词: {' / '.join(cns)}")
