"""JSON-lines 路由器：B (Electron) 的子进程入口。

读 stdin 每行一个 JSON 命令，往 stdout 每行写一个 JSON 事件。
所有非协议输出走 stderr（避免污染 stdout 协议流）。
"""
import json
import sys
import threading
from pathlib import Path

from . import StickerEngine, Config
from .config.schema import Paths, Prefs, ModeProbsConfig
from .config.paths import resolve_paths, current_platform
from .config.loader import load_prefs_from_file, save_prefs

VERSION = "0.1.0"

_engine = None
_stop_events = {}


def _ensure_engine() -> StickerEngine:
    global _engine
    if _engine is not None:
        return _engine
    config = Config.placeholder()
    config.paths = resolve_paths(current_platform())
    prefs = load_prefs_from_file(config.paths.prefs_file)
    if prefs is not None:
        config.prefs = prefs
        # I2：应用用户自定义的参考图库位置
        if prefs.reference_lib_path:
            config.paths.reference_lib = Path(prefs.reference_lib_path)
    _engine = StickerEngine(config)
    return _engine


def _emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(req_id, status, **data):
    _emit({"id": req_id, "type": "result", "status": status, **data})


def _progress(req_id, ev):
    _emit({"id": req_id, "type": "progress", "stage": ev.stage, "phase": ev.phase,
           "message": ev.message, "percent": ev.percent, "eta_seconds": ev.eta_seconds})


def cmd_check_codex(req_id, args):
    engine = _ensure_engine()
    from .providers.codex import CodexProvider
    provider = CodexProvider(codex_exec=engine.config.paths.codex_exec,
                             output_dir=engine.config.paths.codex_output_dir)
    status = provider.check()
    _result(req_id, "ok" if status.image_ready else "fail",
            data={"installed": status.installed, "logged_in": status.logged_in,
                  "image_ready": status.image_ready, "guidance_msg": status.guidance_msg})


def cmd_get_version(req_id, args):
    _result(req_id, "ok", data={"version": VERSION})


def cmd_load_prefs(req_id, args):
    engine = _ensure_engine()
    prefs = load_prefs_from_file(engine.config.paths.prefs_file)
    _result(req_id, "ok", data={"prefs": _prefs_to_dict(prefs), "first_run": prefs is None})


def cmd_save_prefs(req_id, args):
    engine = _ensure_engine()
    prefs = _dict_to_prefs(args.get("prefs", {}))
    save_prefs(prefs, engine.config.paths.prefs_file)
    engine.config.prefs = prefs
    _result(req_id, "ok")


def _sync_custom_bases(engine):
    """C1 集成：把 user_data/custom_bases/ 的图挂进一个'自定义'角色。

    每次 list/add/generate 后调用，保证上传/生成的 base 可见、可选。
    """
    custom_dir = engine.config.paths.user_data / "custom_bases"
    if not custom_dir.exists():
        return
    from .config.schema import Character
    custom_bases = {}
    for img in sorted(custom_dir.iterdir()):
        if img.suffix.lower() in (".png", ".jpg", ".jpeg"):
            # 用相对路径（绝对路径直接存，_pick_base_path 会用）
            custom_bases[img.stem] = str(img)
    if not custom_bases:
        return
    n = len(custom_bases)
    # 均分概率
    probs = {k: 1.0 / n for k in custom_bases}
    engine.config.characters["自定义"] = Character(
        name="自定义", bases=custom_bases, base_probs=probs)


def cmd_list_characters(req_id, args):
    engine = _ensure_engine()
    engine._ensure_characters()
    _sync_custom_bases(engine)
    chars = {}
    for name, c in engine.config.characters.items():
        chars[name] = {"bases": c.bases, "base_probs": c.base_probs}
    _result(req_id, "ok", data={"characters": chars})


def cmd_generate_base(req_id, args):
    engine = _ensure_engine()
    engine._ensure_characters()
    from .providers.codex import CodexProvider
    provider = CodexProvider(codex_exec=engine.config.paths.codex_exec,
                             output_dir=engine.config.paths.codex_output_dir)
    path = provider.generate_base_image(args.get("prompt", ""))
    if path is None:
        _result(req_id, "fail", errors=[{"message": "base 图生成失败"}])
    else:
        # C1 集成：把生成的 base 复制到 custom_bases，挂进"自定义"角色
        import shutil
        custom_dir = engine.config.paths.user_data / "custom_bases"
        custom_dir.mkdir(parents=True, exist_ok=True)
        dst = custom_dir / f"ai_{Path(path).name}"
        shutil.copy2(path, dst)
        _sync_custom_bases(engine)
        _result(req_id, "ok", data={"path": str(dst), "name": dst.name})


def cmd_add_base(req_id, args):
    """C1：用户上传的 base 图复制到 custom_bases/，并挂进'自定义'角色。"""
    import shutil
    src = args.get("path")
    if not src or not Path(src).exists():
        _result(req_id, "fail", errors=[{"message": f"源文件不存在: {src}"}])
        return
    engine = _ensure_engine()
    custom_dir = engine.config.paths.user_data / "custom_bases"
    custom_dir.mkdir(parents=True, exist_ok=True)
    dst = custom_dir / Path(src).name
    shutil.copy2(src, dst)
    _sync_custom_bases(engine)   # 立即挂进角色，list 能看到
    _result(req_id, "ok", data={"path": str(dst), "name": dst.name})


def cmd_run(req_id, args):
    engine = _ensure_engine()
    _sync_custom_bases(engine)   # C1：run 前同步自定义 base，保证可选
    stop = threading.Event()
    _stop_events[req_id] = stop
    try:
        episode = engine.run(
            progress_callback=lambda ev: _progress(req_id, ev),
            stop_event=stop)
        _result(req_id, "ok" if episode.success else "fail",
                data={"episode_dir": str(episode.episode_dir) if episode.episode_dir else None,
                      "stickers": len(episode.stickers),
                      "meaning_map": episode.meaning_map},
                errors=[{"gate": e.gate, "message": e.message} for e in episode.errors],
                aborted_reason=episode.aborted_reason)
    finally:
        _stop_events.pop(req_id, None)


def cmd_stop(req_id, args):
    target = args.get("target_id") or args.get("target")
    ev = _stop_events.get(target)
    if ev is not None:
        ev.set()
        _result(req_id, "ok")
    else:
        _result(req_id, "fail", errors=[{"message": f"无正在运行的任务 {target}"}])


def cmd_list_episodes(req_id, args):
    engine = _ensure_engine()
    root = engine.config.paths.output_root
    episodes = []
    if root.exists():
        for ep_dir in sorted(root.iterdir(), reverse=True):
            if ep_dir.is_dir():
                stickers = list((ep_dir / "最终版").glob("*.png")) if (ep_dir / "最终版").exists() else []
                episodes.append({"name": ep_dir.name, "path": str(ep_dir), "sticker_count": len(stickers)})
    _result(req_id, "ok", data={"episodes": episodes})


def cmd_featured(req_id, args):
    """E：随机抽 N 张精选表情（初心第85行：软件里多用精选）。"""
    from .promotion.featured import sample_featured, featured_count
    n = args.get("n", 8)
    sample = sample_featured(n=n)
    _result(req_id, "ok", data={
        "count": featured_count(),
        "sample": [{"name": p.stem, "path": str(p)} for p in sample],
    })


def cmd_load_promotion(req_id, args):
    """E：读三码推广配置（从用户数据目录 promotion.json 读，开发者本地配置）。"""
    import json as _json
    engine = _ensure_engine()
    promo_file = engine.config.paths.user_data / "promotion.json"
    data = {"reward_qr": None, "group_qr": None, "sticker_qr": None, "author_name": "捞鱼真不吃鱼"}
    if promo_file.exists():
        saved = _json.loads(promo_file.read_text(encoding="utf-8"))
        data.update(saved)
    _result(req_id, "ok", data=data)


def cmd_save_promotion(req_id, args):
    """E：保存三码推广配置到 promotion.json。"""
    import json as _json
    engine = _ensure_engine()
    promo_file = engine.config.paths.user_data / "promotion.json"
    promo_file.parent.mkdir(parents=True, exist_ok=True)
    promo_file.write_text(_json.dumps(args.get("config", {}), ensure_ascii=False, indent=2),
                          encoding="utf-8")
    _result(req_id, "ok")


def cmd_open_in_finder(req_id, args):
    import subprocess as sp
    path = args.get("path")
    if path and Path(path).exists():
        sp.run(["open", path], check=False)
        _result(req_id, "ok")
    else:
        _result(req_id, "fail", errors=[{"message": f"路径不存在: {path}"}])


def _prefs_to_dict(prefs):
    if prefs is None:
        return None
    mp = prefs.mode_probs
    return {"mode_probs": {"single": mp.single, "duo": mp.duo, "trio": mp.trio, "quad": mp.quad},
            "single_char_probs": prefs.single_char_probs, "base_probs": prefs.base_probs,
            "grid_size": prefs.grid_size, "transparent_default": prefs.transparent_default,
            "ref_lib_priority": prefs.ref_lib_priority, "story_mode": prefs.story_mode,
            "reference_lib_path": prefs.reference_lib_path}


def _dict_to_prefs(d):
    mp = d.get("mode_probs", {})
    return Prefs(mode_probs=ModeProbsConfig(
        single=mp.get("single", 0.5), duo=mp.get("duo", 0.3),
        trio=mp.get("trio", 0.0), quad=mp.get("quad", 0.2)),
        single_char_probs=d.get("single_char_probs", {}), base_probs=d.get("base_probs", {}),
        grid_size=d.get("grid_size", 4), transparent_default=d.get("transparent_default", True),
        ref_lib_priority=d.get("ref_lib_priority", True), story_mode=d.get("story_mode", True),
        reference_lib_path=d.get("reference_lib_path"))


HANDLERS = {
    "check_codex": cmd_check_codex, "get_version": cmd_get_version,
    "load_prefs": cmd_load_prefs, "save_prefs": cmd_save_prefs,
    "list_characters": cmd_list_characters, "generate_base": cmd_generate_base,
    "add_base": cmd_add_base,
    "run": cmd_run, "stop": cmd_stop,
    "list_episodes": cmd_list_episodes, "open_in_finder": cmd_open_in_finder,
    "featured": cmd_featured,
    "load_promotion": cmd_load_promotion, "save_promotion": cmd_save_promotion,
}


def _handle_in_thread(req_id, cmd, args):
    """在独立线程执行 handler，避免长任务（run）阻塞 stdin 读取（C1 修复）。"""
    handler = HANDLERS.get(cmd)
    if handler is None:
        _emit({"id": req_id, "type": "error", "message": f"未知命令: {cmd}"})
        return
    try:
        handler(req_id, args)
    except Exception as e:
        _emit({"id": req_id, "type": "error", "message": f"{type(e).__name__}: {e}"})


def main():
    """常驻读 stdin，每行一个命令 JSON。

    C1 修复：每个命令在独立线程执行，主线程立即返回继续读 stdin。
    这样 run（分钟级长任务）期间仍能读取 stop 命令并置位 stop_event。
    """
    print(f"[sticker-engine-cli] v{VERSION} 等待命令...", file=sys.stderr)
    active_threads = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            _emit({"id": None, "type": "error", "message": f"JSON 解析失败: {e}"})
            continue
        req_id = req.get("id")
        cmd = req.get("cmd")
        args = req.get("args", {})
        # stop 命令同步执行（要立即置位 stop_event，不能排队）
        if cmd == "stop":
            _handle_in_thread(req_id, cmd, args)
        else:
            t = threading.Thread(target=_handle_in_thread, args=(req_id, cmd, args), daemon=True)
            t.start()
            active_threads.append(t)
    # stdin EOF：等所有活跃命令线程完成再退出，避免 daemon 被杀导致响应丢失
    for t in active_threads:
        t.join(timeout=30)


if __name__ == "__main__":
    main()
