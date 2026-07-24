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


def cmd_list_characters(req_id, args):
    engine = _ensure_engine()
    engine._ensure_characters()
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
        _result(req_id, "ok", data={"path": str(path)})


def cmd_run(req_id, args):
    engine = _ensure_engine()
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
            "ref_lib_priority": prefs.ref_lib_priority, "story_mode": prefs.story_mode}


def _dict_to_prefs(d):
    mp = d.get("mode_probs", {})
    return Prefs(mode_probs=ModeProbsConfig(
        single=mp.get("single", 0.5), duo=mp.get("duo", 0.3),
        trio=mp.get("trio", 0.0), quad=mp.get("quad", 0.2)),
        single_char_probs=d.get("single_char_probs", {}), base_probs=d.get("base_probs", {}),
        grid_size=d.get("grid_size", 4), transparent_default=d.get("transparent_default", True),
        ref_lib_priority=d.get("ref_lib_priority", True), story_mode=d.get("story_mode", True))


HANDLERS = {
    "check_codex": cmd_check_codex, "get_version": cmd_get_version,
    "load_prefs": cmd_load_prefs, "save_prefs": cmd_save_prefs,
    "list_characters": cmd_list_characters, "generate_base": cmd_generate_base,
    "run": cmd_run, "stop": cmd_stop,
    "list_episodes": cmd_list_episodes, "open_in_finder": cmd_open_in_finder,
    "featured": cmd_featured,
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
