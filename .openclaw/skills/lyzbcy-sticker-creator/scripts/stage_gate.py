#!/usr/bin/env python3
"""
关卡控制器 / Stage Gate
========================
每个关卡 = 跑 validate.py → PASS 继续 / FAIL 停止 + 输出修复指引。

这是给"笨蛋AI"用的：不需要理解细节，只需要知道关卡号。

用法：
    python stage_gate.py --dir "E:\星星布丁\微信表情包\周三涵做表情1" --gate 0
    python stage_gate.py --dir "..." --gate 1
    python stage_gate.py --dir "..." --gate 2
    python stage_gate.py --dir "..." --gate 3
    python stage_gate.py --dir "..." --gate all     # 全部关卡

关卡说明：
    关卡 0 = pre_generate   → 生成前
    关卡 1 = post_generate  → 裁剪/重命名后  
    关卡 2 = pre_publish    → 横幅/封面/图标生成后
    关卡 3 = (同关卡2)       → 发布前最终确认
"""

import os
import sys
import json
import subprocess
import argparse

# Windows 编码修复
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

VALIDATE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate.py")

GATES = {
    0: {"stage": "pre_generate", "name": "关卡 0: 生成前校验", "desc": "检查 base图/参考图/Codex CLI"},
    1: {"stage": "post_generate", "name": "关卡 1: 生成后校验", "desc": "检查 尺寸/格式/透明/含义词/数量"},
    2: {"stage": "pre_publish", "name": "关卡 2: 发布前校验", "desc": "检查 横幅/封面/图标/所有素材"},
    3: {"stage": "pre_publish", "name": "关卡 3: 最终确认", "desc": "发布前最后一次全面检查"},
}

EMOJI = {
    "PASS": "✅",
    "FAIL": "❌",
    "WARN": "⚠️"
}


def run_gate(gate_num, base_dir, config_path=None):
    """运行指定关卡"""
    if gate_num not in GATES:
        print(f"❌ 未知关卡: {gate_num}")
        return False
    
    gate = GATES[gate_num]
    
    print()
    print("=" * 70)
    print(f"🚧 {gate['name']}")
    print(f"   {gate['desc']}")
    print("=" * 70)
    
    cmd = [
        sys.executable, VALIDATE_SCRIPT,
        "--dir", base_dir,
        "--stage", gate["stage"],
        "--json"
    ]
    
    if config_path:
        cmd.extend(["--config", config_path])
    
    # 运行 validate.py
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    
    if result.returncode != 0 and result.stdout:
        try:
            data = json.loads(result.stdout)
            # 打印结果
            for r in data.get("results", []):
                icon = EMOJI.get(r["status"], "❓")
                print(f"  {icon} [{r['status']:4s}] {r['check']}: {r['message']}")
                if r.get("fix", ""):
                    print(f"       💡 {r['fix']}")
            
            fail_count = data.get("fail", 0)
            pass_count = data.get("pass", 0)
            warn_count = data.get("warn", 0)
            
            print()
            print(f"📊 关卡 {gate_num} 结果: ✅{pass_count}  ❌{fail_count}  ⚠️{warn_count}")
            
            if fail_count > 0:
                print()
                print("🔴 关卡未通过！")
                print()
                print("请按以上「💡 修复」提示操作，修复后重新跑关卡。")
                fails = [r for r in data.get("results", []) if r["status"] == "FAIL"]
                print()
                print("📋 失败清单:")
                for f in fails:
                    print(f"   ❌ {f['check']}: {f['message']}")
                    if f.get("fix"):
                        print(f"      修复: {f['fix']}")
                return False
            else:
                print()
                print("✅ 关卡通过！可以继续下一步。")
                return True
                
        except json.JSONDecodeError:
            pass
    
    # 如果 JSON 解析失败，返回原始输出
    print(result.stdout or result.stderr)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="关卡控制器")
    parser.add_argument("--dir", required=True, help="表情包目录")
    parser.add_argument("--gate", required=True, help="关卡号: 0/1/2/3/all")
    parser.add_argument("--config", default=None, help="config.yaml (关卡0需要)")
    
    args = parser.parse_args()
    
    if args.gate == "all":
        print("=" * 70)
        print("🏁 全部关卡")
        print("=" * 70)
        
        all_pass = True
        for gate_num in range(4):
            if not run_gate(gate_num, args.dir, args.config):
                all_pass = False
                print(f"\n⛔ 在关卡 {gate_num} 失败，停止后续关卡。")
                break
        
        if all_pass:
            print()
            print("=" * 70)
            print("🎉 全部关卡通过！可以发布了！")
            print("=" * 70)
        
        sys.exit(0 if all_pass else 1)
    else:
        gate_num = int(args.gate)
        ok = run_gate(gate_num, args.dir, args.config)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
