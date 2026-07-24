#!/usr/bin/env python3
"""自适应生图：先短超时探测额度/容量，模型可用才投入完整大图生成。

应对 codex 的两种间歇性阻塞：
  1. gpt-5.5 'at capacity'（秒级波动）
  2. usage limit 耗尽（提示 'try again at HH:MM'，需等待重置）

用法：
  python adaptive_generate.py --state "弹次目录/prep_state.json" [--max-minutes 25] [--probe-delay 30]
"""
import sys, os, time, subprocess, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
gen_path = os.path.join(HERE, "generate_from_prep_state.py")
spec = importlib.util.spec_from_file_location("gen_mod", gen_path)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

def log(msg):
    print(msg, flush=True)

def probe_capacity(timeout=90):
    """轻量探测：发一个不生图的请求，看是否满载/限额。必须 shell=True 让 PATH 解析 codex.cmd。"""
    try:
        r = subprocess.run(
            "codex exec --enable image_generation --skip-git-repo-check "
            "--sandbox read-only --ephemeral \"reply READY\"",
            shell=True, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="ignore")
        out = (r.stdout or "") + (r.stderr or "")
        lo = out.lower()
        if "at capacity" in lo:
            return False, "满载"
        if "usage limit" in lo or "try again at" in lo:
            return False, "额度耗尽: " + out.strip()[-200:]
        return True, out.strip()[-200:]
    except subprocess.TimeoutExpired:
        return True, "probe超时(视为可用)"
    except Exception as e:
        return False, f"探测异常: {e}"

def build(state_path, config_path, force_ai=False, no_linkage=False, script_id=None):
    state = gen.load_state(state_path)
    config = gen.load_config(config_path)
    output_dir = state["output_dir"].replace("/", os.sep)
    raw_dir = os.path.join(output_dir, "原图")
    ref_dir = os.path.join(output_dir, "参考图")
    os.makedirs(raw_dir, exist_ok=True)
    refs = gen.get_local_references(ref_dir, gen.PANEL_COUNT, state["mode"])
    linkage_meaning_map = None
    if len(refs) >= gen.PANEL_COUNT and not force_ai:
        prompt, inputs = gen.build_16grid_reference(config, state, refs)
        mode = "reference_16grid"
    elif not no_linkage:
        scripts = gen.load_linkage_scripts()
        sel = gen.pick_linkage_scripts(scripts, gen.SCRIPT_GROUPS, characters=state.get("characters", []), preferred_id=script_id)
        prompt, inputs, linkage_meaning_map, _ = gen.build_16grid_linkage(config, state, sel)
        mode = "linkage_16grid_multi"
        log(f"🎬 剧本: {[s['name'] for s in sel]}")
    else:
        emo = gen.get_state_ai_combinations(state, gen.PANEL_COUNT) or gen.get_unique_combinations(gen.PANEL_COUNT)
        prompt, inputs = gen.build_16grid_ai(config, state, emo)
        mode = "ai_16grid"
    return state, output_dir, raw_dir, prompt, inputs, linkage_meaning_map, mode

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--config", default=os.path.join(gen.SKILL_DIR, "config.yaml"))
    ap.add_argument("--gen-timeout", type=int, default=380)
    ap.add_argument("--max-minutes", type=int, default=25)
    ap.add_argument("--probe-delay", type=int, default=30)
    ap.add_argument("--force-ai", action="store_true")
    ap.add_argument("--no-linkage", action="store_true")
    ap.add_argument("--script", default=None)
    args = ap.parse_args()

    state, output_dir, raw_dir, prompt, inputs, linkage_map, mode = build(
        args.state, args.config, args.force_ai, args.no_linkage, args.script)
    log(f"{'='*60}\n自适应生图 | {state['episode_name']} | 模式={mode}\n{'='*60}")

    deadline = time.time() + args.max_minutes * 60
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        log(f"\n[{time.strftime('%H:%M:%S')}] 探测 #{attempt}...")
        ok, info = probe_capacity(90)
        if not ok:
            log(f"  ❌ {info}，等 {args.probe_delay}s")
            time.sleep(args.probe_delay); continue
        log(f"  ✅ 可用！投入生图(timeout={args.gen_timeout}s)...")
        try:
            latest = gen.run_codex(prompt, inputs, args.gen_timeout)
            import shutil, json
            target = os.path.join(raw_dir, "grid_4x4.png")
            shutil.copy2(latest, target)
            log(f"📁 已保存: {target}")
            if linkage_map:
                with open(os.path.join(raw_dir, "_meaning_map.json"), "w", encoding="utf-8") as f:
                    json.dump(linkage_map, f, ensure_ascii=False, indent=2)
                log(f"📝 含义词: {list(linkage_map.values())}")
            try:
                from production_log import log_step
                from PIL import Image as _I
                w, h = _I.open(target).size
                log_step(output_dir, "生图", "OK", f"自适应(探测{attempt}次后成功)，{mode}，{w}x{h}", {"mode": mode, "grid": "4x4", "size": [w, h]})
            except Exception as e:
                log(f"⚠️ 日志: {e}")
            log(f"\n✅✅ {state['episode_name']} 生图成功！")
            return 0
        except Exception as e:
            log(f"  ⚠️ 生图失败: {str(e)[:180]}")
            time.sleep(args.probe_delay)
    log(f"\n🔴 用尽 {args.max_minutes} 分钟未成功。")
    return 1

if __name__ == "__main__":
    sys.exit(main())
