"""JSON-lines 路由器：B (Electron) 的子进程入口。

读 stdin 每行一个 JSON 命令，往 stdout 每行写一个 JSON 事件。
所有非协议输出走 stderr（避免污染 stdout 协议流）。
"""
import json
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

from . import StickerEngine, Config
from .config.schema import Paths, Prefs, ModeProbsConfig
from .config.paths import resolve_paths, current_platform
from .config.loader import load_prefs_from_file, save_prefs

VERSION = "0.1.0"

_engine = None
_stop_events = {}
_memory_logs = deque(maxlen=50)
_SENSITIVE_LOG_KEYS = {"token", "password", "authorization", "secret"}
_agent_state = {
    "server": None,
    "thread": None,
    "scheduler": None,
    "token": None,
    "port": None,
}


def _scrub_log_value(value):
    if isinstance(value, dict):
        return {
            key: _scrub_log_value(item)
            for key, item in value.items()
            if str(key).lower() not in _SENSITIVE_LOG_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_log_value(item) for item in value]
    return value


def _log(level, message, **meta):
    """进程内日志；最多 50 条，敏感字段在写入前移除。"""
    _memory_logs.append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "level": str(level),
        "message": str(message),
        "meta": _scrub_log_value(meta),
    })


def _safe_logs():
    return [_scrub_log_value(dict(entry)) for entry in _memory_logs]


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
    _log(
        "info", ev.message, command_id=req_id, stage=ev.stage,
        phase=ev.phase, percent=ev.percent, eta_seconds=ev.eta_seconds,
    )
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


def _login_shell_env():
    """通过 login interactive shell 拿到用户真实 PATH（含 nvm/homebrew）。

    GUI 应用的 PATH 残缺，subprocess 跑 npm/curl 会失败。这里用 zsh -lic
    重新加载用户的 .zshrc/.zprofile，拿到完整 PATH。
    """
    import subprocess as sp
    import os as _os
    env = _os.environ.copy()
    try:
        out = sp.run(["/bin/zsh", "-lic", "print -rn -- $PATH"],
                     capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            env["PATH"] = out.stdout.strip() + _os.pathsep + env.get("PATH", "")
    except Exception:
        pass   # 拿不到就用原 env，至少不崩
    return env


def cmd_install_codex(req_id, args):
    """一键安装 codex（用户友好，初心第3行）。

    策略（按优先级）：
    1. 先探测已有 codex（桌面 App / 之前装过）→ 直接用，不下载
    2. 走 npm 安装（registry.npmjs.org 通常可达）：npm i -g @openai/codex
    3. 回退官方脚本（chatgpt.com，部分网络不通）
    流式把 stdout 行作为 progress 事件发出去，前端实时显示。
    """
    import subprocess as sp
    from .providers.codex import CodexProvider

    # 策略1：先探测是否已有 codex（很多用户装了桌面 App 就有，不用重复下载）
    _emit({"id": req_id, "type": "progress", "stage": "install",
           "message": "检测是否已安装 codex...", "percent": 0.1})
    engine = _ensure_engine()
    provider = CodexProvider(codex_exec="codex", output_dir=engine.config.paths.codex_output_dir)
    resolved = provider._resolve_codex_path()
    if resolved:
        _emit({"id": req_id, "type": "progress", "stage": "install",
               "message": f"✅ 已检测到 codex：{resolved}", "percent": 0.9})
        status = provider.check()
        _result(req_id, "ok" if status.installed else "fail",
                data={"installed": status.installed, "image_ready": status.image_ready,
                      "guidance_msg": status.guidance_msg,
                      "codex_path": resolved,
                      "log": f"已检测到现有 codex: {resolved}"})
        return

    # 策略2：npm 安装（用 login shell 的 PATH，拿到 nvm 的 node）
    _emit({"id": req_id, "type": "progress", "stage": "install",
           "message": "通过 npm 安装 codex...", "percent": 0.3})
    env = _login_shell_env()
    lines = []
    try:
        proc = sp.Popen("npm install -g @openai/codex", shell=True, executable="/bin/zsh",
                        stdout=sp.PIPE, stderr=sp.STDOUT, text=True, env=env)
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                lines.append(line)
                _emit({"id": req_id, "type": "progress", "stage": "install",
                       "message": line, "percent": 0.6})
        proc.wait()
        if proc.returncode == 0:
            _emit({"id": req_id, "type": "progress", "stage": "install",
                   "message": "npm 安装完成，正在验证...", "percent": 0.9})
            status = provider.check()
            _result(req_id, "ok" if status.installed else "fail",
                    data={"installed": status.installed, "image_ready": status.image_ready,
                          "guidance_msg": status.guidance_msg,
                          "log": "\n".join(lines[-10:])})
            return
        npm_err = f"npm 安装退出码 {proc.returncode}"
    except Exception as e:
        npm_err = f"npm 安装异常: {e}"

    # 策略3：回退官方脚本（chatgpt.com，部分网络可能不通）
    _emit({"id": req_id, "type": "progress", "stage": "install",
           "message": "npm 安装未成功，尝试官方脚本...", "percent": 0.7})
    try:
        cmd = "curl -fsSL https://chatgpt.com/codex/install.sh | sh"
        proc = sp.Popen(cmd, shell=True, executable="/bin/zsh",
                        stdout=sp.PIPE, stderr=sp.STDOUT, text=True, env=env)
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                lines.append(line)
                _emit({"id": req_id, "type": "progress", "stage": "install",
                       "message": line, "percent": 0.85})
        proc.wait()
        if proc.returncode == 0:
            status = provider.check()
            _result(req_id, "ok" if status.installed else "fail",
                    data={"installed": status.installed, "image_ready": status.image_ready,
                          "guidance_msg": status.guidance_msg, "log": "\n".join(lines[-10:])})
            return
        _result(req_id, "fail",
                errors=[{"message": f"{npm_err}；官方脚本退出码 {proc.returncode}"}],
                data={"log": "\n".join(lines[-15:]),
                      "hint": "手动安装：终端运行 npm i -g @openai/codex 或 curl -fsSL https://chatgpt.com/codex/install.sh | sh"})
    except Exception as e:
        _result(req_id, "fail", errors=[{"message": f"{npm_err}；官方脚本异常: {e}"}],
                data={"hint": "手动安装：终端运行 npm i -g @openai/codex"})


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
    engine.config.paths.reference_lib = (
        Path(prefs.reference_lib_path)
        if prefs.reference_lib_path
        else engine.config.paths.user_data / "reference_library"
    )
    _apply_base_probs(engine)
    _result(req_id, "ok")


def _sync_custom_bases(engine):
    """C1 集成：把 user_data/custom_bases/ 的图挂进一个'自定义'角色。

    每次 list/add/generate 后调用，保证上传/生成的 base 可见、可选。
    """
    custom_dir = engine.config.paths.user_data / "custom_bases"
    if not custom_dir.exists():
        return
    from .config.schema import Character
    grouped = {}
    for img in sorted(custom_dir.iterdir()):
        if img.is_file() and img.suffix.lower() in (".png", ".jpg", ".jpeg"):
            grouped.setdefault("自定义", {})[img.stem] = str(img)
        elif img.is_dir():
            images = {
                child.stem: str(child)
                for child in sorted(img.iterdir())
                if child.is_file() and child.suffix.lower() in (".png", ".jpg", ".jpeg")
            }
            if images:
                grouped[img.name] = images
    for name, custom_bases in grouped.items():
        existing = engine.config.characters.get(name)
        bases = dict(existing.bases) if existing else {}
        bases.update(custom_bases)
        default_probs = dict(existing.base_probs) if existing else {}
        for key in custom_bases:
            default_probs.setdefault(key, 1.0)
        engine.config.characters[name] = Character(
            name=name, bases=bases, base_probs=default_probs)
    _apply_base_probs(engine)


def _apply_base_probs(engine):
    """把 prefs 中每角色概率应用到当前角色对象，只接受现有 base key。"""
    from .config.schema import normalize_probs
    configured = getattr(engine.config.prefs, "base_probs", {}) or {}
    for name, char in engine.config.characters.items():
        saved = configured.get(name)
        if not saved:
            continue
        probs = {key: max(0.0, float(saved.get(key, 0.0))) for key in char.bases}
        if sum(probs.values()) > 0:
            char.base_probs = normalize_probs(probs)


def _safe_character_name(value):
    name = str(value or "").strip()
    if (
        not name or name in {".", ".."} or len(name) > 64
        or "/" in name or "\\" in name
        or any(ord(ch) < 32 for ch in name)
    ):
        return None
    return name


def cmd_list_characters(req_id, args):
    engine = _ensure_engine()
    engine._ensure_characters()
    _sync_custom_bases(engine)
    _apply_base_probs(engine)
    import sticker_engine as _se
    resources = _se.resources_path()
    chars = {}
    for name, c in engine.config.characters.items():
        preview_bases = {}
        for key, value in c.bases.items():
            path = Path(value)
            preview_bases[key] = str(path if path.is_absolute() else resources / path)
        chars[name] = {"bases": preview_bases, "base_probs": c.base_probs}
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
        character = _safe_character_name(args.get("character") or "自定义")
        if character is None:
            _result(req_id, "fail", errors=[{"message": "角色名不合法"}])
            return
        custom_dir = engine.config.paths.user_data / "custom_bases" / character
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
    character = _safe_character_name(args.get("character") or "自定义")
    if character is None:
        _result(req_id, "fail", errors=[{"message": "角色名不合法"}])
        return
    engine = _ensure_engine()
    custom_dir = engine.config.paths.user_data / "custom_bases" / character
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


def cmd_get_logs(req_id, args):
    _result(req_id, "ok", data={"logs": _safe_logs()})


def cmd_clear_logs(req_id, args):
    _memory_logs.clear()
    _result(req_id, "ok")


def _publish_episode(episode_dir, progress):
    """运行现有微信 Publisher，给桌面层返回结构化结果。"""
    from .publish.browser import BrowserSession
    from .publish.config import PublishConfig
    from .publish.publisher import Publisher

    episode_dir = Path(episode_dir)
    progress("prepare", "正在检查发布素材…", 0.05)
    config = PublishConfig.from_env()
    publisher = Publisher(config, BrowserSession(config))
    progress("browser", "正在打开微信表情开放平台…", 0.15)
    result = publisher.publish(episode_dir, headless=False)
    screenshot = episode_dir / "_publish_error.png"
    if screenshot.exists():
        result["screenshot"] = str(screenshot)
    progress(
        result.get("step", "done"),
        "提交完成" if result.get("success") else "提交未完成",
        1.0,
    )
    return result


def cmd_check_publish(req_id, args):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            ready = executable.exists()
        _result(req_id, "ok" if ready else "fail", data={
            "ready": ready,
            "browser_path": str(executable) if ready else None,
            "guidance": "" if ready else "未找到发布浏览器，请先安装 Google Chrome 或 Playwright Chromium。",
        })
    except Exception as exc:
        _result(req_id, "fail", data={
            "ready": False,
            "guidance": f"发布组件不可用：{type(exc).__name__}: {exc}",
        })


def cmd_publish_episode(req_id, args):
    episode_dir = Path(args.get("episode_dir") or "")
    if not episode_dir.is_dir():
        _result(
            req_id, "fail",
            errors=[{"message": f"作品目录不存在：{episode_dir}"}],
        )
        return

    def progress(stage, message, percent):
        _log(
            "info", message, command="publish_episode",
            command_id=req_id, stage=stage, percent=percent,
        )
        _emit({
            "id": req_id, "type": "progress", "stage": "publish",
            "phase": stage, "message": message, "percent": percent,
            "eta_seconds": None,
        })

    try:
        result = _publish_episode(episode_dir, progress)
    except Exception as exc:
        result = {
            "success": False,
            "step": "runtime",
            "error": f"{type(exc).__name__}: {exc}",
        }
    if result.get("success"):
        _result(req_id, "ok", data=result)
    else:
        _result(
            req_id, "fail", data=result,
            errors=[{"message": result.get("error") or "发布未完成"}],
        )


def _run_scheduled_action(action, args):
    """Scheduler 的真实动作映射；失败进入内存日志。"""
    _log("info", f"定时任务触发：{action}", action=action)
    try:
        if action == "run":
            _ensure_engine().run()
        elif action == "publish":
            _publish_episode(
                args.get("episode_dir"),
                lambda stage, message, percent: _log(
                    "info", message, action=action, stage=stage, percent=percent),
            )
        elif action == "batch":
            from .publish.batch import BatchPublisher
            from .publish.config import PublishConfig
            engine = _ensure_engine()
            BatchPublisher(PublishConfig.from_env(), engine.config.paths.output_root).run(
                start=args.get("start"), end=args.get("end"),
                only=args.get("only"), resume=args.get("resume", False),
                retry=args.get("retry", 2), headless=args.get("headless", False),
            )
        elif action == "shelf":
            from .publish.browser import BrowserSession
            from .publish.config import PublishConfig
            from .publish.shelf import Shelf
            config = PublishConfig.from_env()
            Shelf(config, BrowserSession(config)).shelve_all(
                max_pages=args.get("max_pages", 5), limit=args.get("limit"),
                dry_run=args.get("dry_run", False),
                headless=args.get("headless", False),
            )
        else:
            raise ValueError(f"不支持的定时动作：{action}")
    except Exception as exc:
        _log(
            "error", f"定时任务失败：{action}：{type(exc).__name__}: {exc}",
            action=action,
        )


def _start_agent_server(port=7432):
    """在线程内启动 loopback Agent 服务；重复调用保持幂等。"""
    if _agent_state["server"] is not None:
        return {
            "running": True, "already_running": True,
            "host": "127.0.0.1", "port": _agent_state["port"],
            "token": _agent_state["token"],
        }

    from werkzeug.serving import make_server
    from .agent.cli import _ensure_token
    from .agent.scheduler import Scheduler
    from .agent.server import _create_app

    paths = _ensure_engine().config.paths
    token = _ensure_token(paths)
    scheduler = Scheduler(
        state_file=paths.user_data / "schedules.json",
        trigger_fn=_run_scheduled_action,
    )
    scheduler.start()
    app = _create_app(token=token, scheduler=scheduler)
    server = make_server("127.0.0.1", int(port), app, threaded=True)
    thread = threading.Thread(
        target=server.serve_forever, name="sticker-agent-server", daemon=True)
    thread.start()
    actual_port = int(server.server_port)
    _agent_state.update({
        "server": server, "thread": thread, "scheduler": scheduler,
        "token": token, "port": actual_port,
    })
    _log("info", "AI Agent 服务已启动", host="127.0.0.1", port=actual_port)
    return {
        "running": True, "already_running": False,
        "host": "127.0.0.1", "port": actual_port, "token": token,
    }


def _stop_agent_server():
    server = _agent_state.get("server")
    scheduler = _agent_state.get("scheduler")
    if server is not None:
        server.shutdown()
        server.server_close()
    if scheduler is not None:
        scheduler.shutdown()
    _agent_state.update({
        "server": None, "thread": None, "scheduler": None,
        "token": None, "port": None,
    })
    _log("info", "AI Agent 服务已停止")
    return {"running": False}


def cmd_agent_start(req_id, args):
    try:
        data = _start_agent_server(port=args.get("port", 7432))
        _result(req_id, "ok", data=data)
    except Exception as exc:
        _result(
            req_id, "fail",
            errors=[{"message": f"Agent 启动失败：{type(exc).__name__}: {exc}"}],
        )


def cmd_agent_status(req_id, args):
    running = _agent_state["server"] is not None
    _result(req_id, "ok", data={
        "running": running,
        "host": "127.0.0.1",
        "port": _agent_state["port"],
        "token": _agent_state["token"] if running else None,
    })


def cmd_agent_prompt(req_id, args):
    prompt_path = Path(__file__).parent / "agent" / "AGENT_PROMPT.md"
    _result(req_id, "ok", data={
        "prompt": prompt_path.read_text(encoding="utf-8"),
    })


def cmd_agent_stop(req_id, args):
    _result(req_id, "ok", data=_stop_agent_server())


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
    "check_codex": cmd_check_codex, "install_codex": cmd_install_codex,
    "get_version": cmd_get_version,
    "load_prefs": cmd_load_prefs, "save_prefs": cmd_save_prefs,
    "list_characters": cmd_list_characters, "generate_base": cmd_generate_base,
    "add_base": cmd_add_base,
    "run": cmd_run, "stop": cmd_stop,
    "list_episodes": cmd_list_episodes, "open_in_finder": cmd_open_in_finder,
    "featured": cmd_featured,
    "load_promotion": cmd_load_promotion, "save_promotion": cmd_save_promotion,
    "get_logs": cmd_get_logs, "clear_logs": cmd_clear_logs,
    "check_publish": cmd_check_publish, "publish_episode": cmd_publish_episode,
    "agent_start": cmd_agent_start, "agent_status": cmd_agent_status,
    "agent_prompt": cmd_agent_prompt, "agent_stop": cmd_agent_stop,
}


def _handle_in_thread(req_id, cmd, args):
    """在独立线程执行 handler，避免长任务（run）阻塞 stdin 读取（C1 修复）。"""
    handler = HANDLERS.get(cmd)
    if handler is None:
        _log("error", f"未知命令: {cmd}", command=cmd, command_id=req_id)
        _emit({"id": req_id, "type": "error", "message": f"未知命令: {cmd}"})
        return
    _log("info", f"开始命令：{cmd}", command=cmd, command_id=req_id)
    try:
        handler(req_id, args)
        _log("info", f"完成命令：{cmd}", command=cmd, command_id=req_id)
    except Exception as e:
        _log(
            "error", f"命令失败：{cmd}：{type(e).__name__}: {e}",
            command=cmd, command_id=req_id,
        )
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
