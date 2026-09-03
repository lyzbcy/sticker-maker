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

VERSION = "0.3.0"

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


# ---------------- Codex 额度查询 ----------------
# 社区已验证的 ChatGPT 后端只读端点（codex CLI 登录态同源）：
# https://github.com/lhl/pi-codex-status（MIT）即调它；返回 5 小时窗 + 周窗
# 的 used_percent / reset_at。仅 GET，不写任何状态。
_CODEX_USAGE_ENDPOINT = "https://chatgpt.com/backend-api/wham/usage"
_CODEX_PLAN_NAMES = {"plus": "ChatGPT Plus", "pro": "ChatGPT Pro", "team": "ChatGPT Team",
                     "business": "ChatGPT Business", "free": "Free", "edu": "ChatGPT Edu"}


def _read_codex_auth():
    """读 ~/.codex/auth.json 的 ChatGPT 登录态。

    返回 {"access_token":…, "account_id":…} 或 None（未登录/文件损坏/非 chatgpt 模式）。
    token 只用于构造请求头，绝不写入日志/命令结果（_scrub_log_value 双保险）。
    """
    auth_file = Path.home() / ".codex" / "auth.json"
    if not auth_file.exists():
        return None
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    tokens = data.get("tokens") or {}
    access = tokens.get("access_token")
    if not access:
        return None
    return {"access_token": access, "account_id": tokens.get("account_id") or ""}


def _fetch_codex_remote_usage(auth, timeout=15):
    """GET wham/usage（只读）。返回原始 dict；网络/HTTP 错误抛异常。"""
    import urllib.request
    req = urllib.request.Request(_CODEX_USAGE_ENDPOINT, method="GET")
    req.add_header("authorization", "Bearer " + auth["access_token"])
    req.add_header("accept", "application/json")
    req.add_header("user-agent", f"sticker-engine-cli/{VERSION}")
    if auth.get("account_id"):
        req.add_header("chatgpt-account-id", auth["account_id"])
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _norm_codex_window(w):
    """归一化一个限额窗口（primary=5 小时 / secondary=周）。"""
    if not isinstance(w, dict):
        return None
    reset_at = w.get("reset_at")
    return {
        "used_percent": w.get("used_percent"),
        "left_percent": (100 - w["used_percent"]) if isinstance(w.get("used_percent"), (int, float)) else None,
        "window_hours": round((w.get("limit_window_seconds") or 0) / 3600, 1),
        "reset_at": datetime.fromtimestamp(reset_at).isoformat(timespec="minutes") if reset_at else None,
        "reset_in_minutes": round((w.get("reset_after_seconds") or 0) / 60),
    }


def _normalize_codex_usage(raw):
    """压缩服务端响应为前端/日志友好结构（丢弃 email/user_id 等账户明细）。"""
    rl = raw.get("rate_limit") or {}
    credits = raw.get("credits") or {}
    plan = raw.get("plan_type")
    return {
        "plan": plan,
        "plan_display": _CODEX_PLAN_NAMES.get(plan, plan),
        "limit_reached": bool(rl.get("limit_reached")),
        "primary_window": _norm_codex_window(rl.get("primary_window")),
        "secondary_window": _norm_codex_window(rl.get("secondary_window")),
        "credits_balance": credits.get("balance"),
    }


def _count_local_codex_images(output_dir):
    """本地兜底：统计 ~/.codex/generated_images 的生图张数（近 7 天逐日 + 今日）。

    不依赖网络/登录态；按文件 mtime 归日（UTC 拆天足够近似）。
    """
    from collections import Counter
    root = Path(output_dir)
    days, total = Counter(), 0
    if root.is_dir():
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=7)
        for p in root.rglob("*"):
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg") or not p.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime)
            except OSError:
                continue
            total += 1
            if mtime >= cutoff:
                days[mtime.strftime("%Y-%m-%d")] += 1
    return {
        "today": days.get(datetime.now().strftime("%Y-%m-%d"), 0),
        "last_7_days": dict(sorted(days.items())),
        "total_images": total,
    }


def cmd_codex_usage(req_id, args):
    """查询 codex（ChatGPT 账号）生图/使用额度。

    优先远程（wham/usage 只读 GET，复用 codex CLI 登录态）；失败降级本地
    generated_images 逐日统计。返回 data.available 标识是否拿到远程真实额度。
    """
    engine = _ensure_engine()
    local = _count_local_codex_images(engine.config.paths.codex_output_dir)
    remote, error = None, None
    auth = _read_codex_auth()
    if auth is None:
        error = "未找到 ~/.codex/auth.json 登录态（或非 ChatGPT 模式）"
    else:
        try:
            remote = _normalize_codex_usage(_fetch_codex_remote_usage(auth))
        except Exception as e:   # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
    if remote is not None:
        _log("info", "codex 额度查询成功（远程端点）", command_id=req_id)
        # 可生张数估算（首页额度卡用）：每张消耗 ≈ 周窗口已用% / 本机累计
        # 生图张数（粗估——窗口内可能混有文本消耗，标注为估算值）
        est = {}
        total_imgs = int(local.get("total_images") or 0)
        sec = remote.get("secondary_window") or {}
        used_pct = float(sec.get("used_percent") or 0)
        per_image = (used_pct / total_imgs) if total_imgs and used_pct > 0 else 0
        for wk, w in (("primary_window", remote.get("primary_window") or {}),
                      ("secondary_window", sec)):
            left = float(w.get("left_percent") or 0)
            est[wk] = {
                "images_left_est": int(left / per_image) if per_image > 0 else None,
                "hours_left": round(float(w.get("reset_in_minutes") or 0) / 60, 1),
                "reset_hhmm": str(w.get("reset_at") or "")[-5:],
            }
        _result(req_id, "ok", data={
            "available": True,
            "method": "chatgpt_backend_api",
            "endpoint": _CODEX_USAGE_ENDPOINT,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "usage": remote,
            "estimate": est,
            "local_images": local,
        })
        return
    # 远程不可用 → 本地统计兜底（数据一定拿得到，只是近似）
    _log("warn", f"codex 额度远程查询失败，降级本地统计：{error}", command_id=req_id)
    _result(req_id, "ok", data={
        "available": False,
        "method": "local_images_fallback",
        "error": error,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "local_images": local,
        "suggestion": "远程额度需 codex 已登录 ChatGPT 账号且能访问 chatgpt.com；"
                      "可在终端运行 codex login 后重试。下方 local_images 为本机"
                      "生图张数统计（近似额度消耗）。",
    })


def _login_shell_env():
    """通过 login interactive shell 拿到用户真实 PATH（含 nvm/homebrew）。

    GUI 应用的 PATH 残缺，subprocess 跑 npm/curl 会失败。这里用 zsh -lic
    重新加载用户的 .zshrc/.zprofile，拿到完整 PATH。
    Windows 没有 zsh：改为把 npm 全局 bin（%APPDATA%\\npm）补进 PATH。
    """
    import subprocess as sp
    import os as _os
    env = _os.environ.copy()
    if sys.platform == "win32":
        npm_bin = _os.path.join(_os.environ.get("APPDATA") or "", "npm")
        if npm_bin and Path(npm_bin).is_dir() and npm_bin not in env.get("PATH", ""):
            env["PATH"] = npm_bin + _os.pathsep + env.get("PATH", "")
        return env
    try:
        out = sp.run(["/bin/zsh", "-lic", "print -rn -- $PATH"],
                     capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            env["PATH"] = out.stdout.strip() + _os.pathsep + env.get("PATH", "")
    except Exception:
        pass   # 拿不到就用原 env，至少不崩
    return env


def _stream_install_proc(cmd, env):
    """启动安装命令并流式读输出。Mac 走 zsh（拿 nvm 的 node），Windows 走 cmd。"""
    import subprocess as sp
    if sys.platform == "darwin":
        return sp.Popen(cmd, shell=True, executable="/bin/zsh",
                        stdout=sp.PIPE, stderr=sp.STDOUT, text=True,
                        encoding="utf-8", errors="replace", env=env)
    return sp.Popen(cmd, shell=True,
                    stdout=sp.PIPE, stderr=sp.STDOUT, text=True,
                    encoding="utf-8", errors="replace", env=env)


def cmd_install_codex(req_id, args):
    """一键安装 codex（用户友好，初心第3行）。

    策略（按优先级）：
    1. 先探测已有 codex（桌面 App / 之前装过）→ 直接用，不下载
    2. 走 npm 安装（registry.npmjs.org 通常可达）：npm i -g @openai/codex
    3. 回退官方脚本（chatgpt.com，部分网络不通；仅 macOS/Linux，Windows 无此脚本）
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
        proc = _stream_install_proc("npm install -g @openai/codex", env)
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

    # 策略3：回退官方脚本（chatgpt.com，部分网络可能不通；Windows 无此脚本）
    if sys.platform == "win32":
        _result(req_id, "fail",
                errors=[{"message": npm_err}],
                data={"log": "\n".join(lines[-15:]),
                      "hint": "手动安装：先安装 Node.js 22+（nodejs.org），"
                              "再在命令行（cmd 或 PowerShell）运行 npm i -g @openai/codex"})
        return
    _emit({"id": req_id, "type": "progress", "stage": "install",
           "message": "npm 安装未成功，尝试官方脚本...", "percent": 0.7})
    try:
        cmd = "curl -fsSL https://chatgpt.com/codex/install.sh | sh"
        proc = _stream_install_proc(cmd, env)
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
    # 防御：default_series_id 必须指向真实存在的系列（防脏数据存入）
    if prefs.default_series_id:
        from .config.series import find_series
        if find_series(prefs.default_series_id) is None:
            prefs.default_series_id = None
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



def _auto_assign_series_name(ep_dir: Path, engine):
    """run 成功后按默认系列自动命名（返回专辑名；无默认系列返回 None）。"""
    from .config.series import load_series, save_series, load_meta, save_meta
    prefs = engine.config.prefs
    if not prefs.default_series_id:
        return None
    series_list = load_series()
    target = next((x for x in series_list if x.id == prefs.default_series_id), None)
    if target is None:
        return None
    n = target.take_number()
    save_series(series_list)
    meta = load_meta(ep_dir)
    meta.series_id = target.id
    meta.series_name = target.name
    meta.number = n
    meta.album_name = target.album_name(n)
    save_meta(ep_dir, meta)
    return meta.album_name


def cmd_run_batch(req_id, args):
    """批量生成：count 组串行；auto_publish 时每组自动命名（默认系列）+提交。

    每组进度经原有 run 的 progress 通道透传；批量粒度进度用 stage="batch"。
    stop 可中断（中断前已完成的组保留结果）。
    """
    # 上限 200（2026-09-03 用户需求：自定义大批量；每组 5-8 分钟串行，
    # 200 组约 20-27 小时，支持随时 stop 中断、已完成组保留）
    count = max(1, min(200, int(args.get("count") or 1)))
    auto_publish = bool(args.get("auto_publish"))
    engine = _ensure_engine()
    _sync_custom_bases(engine)
    stop = threading.Event()
    _stop_events[req_id] = stop
    results = []
    consecutive_fails = 0   # 熔断计数（2026-09-03 事故：额度撞墙时 15 秒一个
    # 空壳目录连刷 66 个——连续失败说明环境坏了，继续跑只会产垃圾）

    def _say(msg):
        _emit({"id": req_id, "type": "progress", "stage": "batch",
               "phase": "batch", "message": msg, "percent": None,
               "eta_seconds": None})

    try:
        for i in range(1, count + 1):
            if stop.is_set():
                _say(f"收到停止请求，批量在完成 {i - 1} 组后中断")
                break
            _say(f"—— 第 {i}/{count} 组开始 ——")
            episode = engine.run(
                progress_callback=lambda ev: _progress(req_id, ev),
                stop_event=stop)
            item = {
                "index": i,
                "success": bool(episode.success),
                "episode_dir": str(episode.episode_dir) if episode.episode_dir else None,
                "stickers": len(episode.stickers),
            }
            if not episode.success:
                errs = "; ".join(e.message for e in episode.errors[:3])
                item["error"] = errs or episode.aborted_reason or "生成未完成"
                _say(f"第 {i} 组未完成：{item['error'][:80]}")
                results.append(item)
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    _say(f"连续 {consecutive_fails} 组失败——疑似额度耗尽或 codex 异常，"
                         f"批量自动中止（已完成 {len(results)} 组）。请查首页额度卡或稍后重跑。")
                    break
                if stop.is_set():
                    break
                continue
            consecutive_fails = 0
            if auto_publish and episode.episode_dir:
                ep_dir = Path(episode.episode_dir)
                # 2026-09-01 图标降级风险：AI 大头照生成失败时 S3 静默退回复用
                # 封面（缩放形态曾被平台驳回）→ 该单跳过自动发布，详情页
                # 「重生成素材」补 AI 图标后手动提交。单次手动生成不阻断。
                if getattr(episode, "icon_fallback", False):
                    item["published"] = False
                    item["publish_skip"] = "图标生成失败，未发布（详情页重生成素材后手动提交）"
                    _say(f"第 {i} 组图标生成失败（已退回复用封面，平台易驳回），"
                         f"跳过自动发布——详情页重生成素材后手动提交")
                else:
                    # 2026-09-02 修复：engine.run() 成功后已按默认系列自动命名
                    # （api.py assign_to_series）——这里绝不能再取号（曾致每组
                    # 跳一个号：71,73,75…）；直接读 meta 里的正式名
                    from .config.series import load_meta as _lm
                    name = (_lm(ep_dir).album_name or "").strip()
                    if not name or name.startswith("episode_"):
                        item["published"] = False
                        item["publish_skip"] = "作品未正式命名（无默认系列？），跳过自动发布（设置→系列与命名→默认系列）"
                        _say(item["publish_skip"])
                    else:
                        _say(f"第 {i} 组命名「{name}」，正在自动提交平台…")
                        r = _publish_episode(
                            ep_dir,
                            lambda stage, message, percent: _emit({
                                "id": req_id, "type": "progress", "stage": "publish",
                                "phase": stage, "message": message,
                                "percent": percent, "eta_seconds": None}))
                        item["published"] = bool(r.get("success"))
                        if r.get("success"):
                            from .config.series import mark_published
                            try:
                                mark_published(ep_dir)
                            except Exception:   # noqa: BLE001
                                pass
                            _say(f"✓ 第 {i} 组「{name}」已提交审核")
                        else:
                            item["publish_error"] = (r.get("error") or "")[:150]
                            _say(f"✗ 第 {i} 组提交未完成：{item['publish_error'][:80]}")
            results.append(item)
            _say(f"—— 第 {i}/{count} 组完成 ——")
        ok = sum(1 for x in results if x.get("success"))
        pub = sum(1 for x in results if x.get("published"))
        _result(req_id, "ok", data={
            "requested": count, "completed": len(results),
            "generated_ok": ok, "published_ok": pub,
            "stopped": stop.is_set(), "results": results})
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
    from .config.series import load_meta
    episodes = []
    if root.exists():
        for ep_dir in sorted(root.iterdir(), reverse=True):
            if ep_dir.is_dir() and ep_dir.name.startswith("episode"):
                stickers = list((ep_dir / "最终版").glob("*.png")) if (ep_dir / "最终版").exists() else []
                cover = ep_dir / "封面" / "封面.png"
                if not cover.exists():
                    cover = stickers[0] if stickers else None
                meta = load_meta(ep_dir)
                episodes.append({
                    "name": ep_dir.name, "path": str(ep_dir),
                    "sticker_count": len(stickers),
                    "cover": str(cover) if cover else "",
                    # 元数据（无 meta.json 的历史作品返回默认值）
                    "album_name": meta.album_name,
                    "series_id": meta.series_id,
                    "series_name": meta.series_name,
                    "number": meta.number,
                    "published": meta.published,
                    "published_at": meta.published_at,
                    "created_at": meta.created_at,
                    # 平台状态（一键更新回写）
                    "platform_status": meta.platform_status,
                    "platform_downloads": meta.platform_downloads,
                    "platform_sends": meta.platform_sends,
                    "platform_tips": meta.platform_tips,
                    "platform_updated_at": meta.platform_updated_at,
                    "platform_reject_reason": meta.platform_reject_reason,
                    "complete": len(stickers) > 0,
                })
    _result(req_id, "ok", data={"episodes": episodes})


# ---------------- 系列 / 作品元数据命令 ----------------

def cmd_list_series(req_id, args):
    from .config.series import load_series
    series = load_series()
    _result(req_id, "ok", data={"series": [{
        **s.to_dict(), "next_number": s.peek_next_number(),
    } for s in series]})


def cmd_save_series(req_id, args):
    """整表保存系列（增删改一体）。保留已有系列的编号进度。"""
    from .config.series import save_series_list_from_dicts, load_series
    items = args.get("series") or []
    # 基本校验：name 必填、start_number >= 1
    for item in items:
        if not str(item.get("name") or "").strip():
            _result(req_id, "fail", errors=[{"message": "系列名称不能为空"}])
            return
    saved = save_series_list_from_dicts(items)
    _result(req_id, "ok", data={"series": [{
        **s.to_dict(), "next_number": s.peek_next_number(),
    } for s in saved]})


def _episode_characters(episode_dir: Path) -> list:
    """从 本次制作角色.md 读角色列表（无文件返回空）。"""
    f = Path(episode_dir) / "本次制作角色.md"
    if not f.exists():
        return []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("角色："):
            return [c for c in line[len("角色："):].split("、") if c]
    return []


def _episode_stickers(episode_dir: Path) -> list:
    """图↔含义配对：按含义词反查文件名锁定（与发布端 from_dir 同一约定）。

    历史 bug：sorted(文件名) × panel 数字序 meanings 的**位置**配对——中文
    字典序和 panel 序天然错开，导致详情页"生气"行显示融化图、打分键错挂
    （68 号单三条用户备注精确命中错位）。文件名==含义词是 A 产出约定，
    此处以名字锁定，不按位置配对。
    """
    final = Path(episode_dir) / "最终版"
    if not final.exists():
        return []
    final_pngs = {p.stem: p for p in final.glob("*.png")}
    stickers = []
    for meaning in _episode_meanings(episode_dir):
        hit = final_pngs.get(meaning)
        if hit is None:
            # 文件名可能带后缀，包含匹配兜底（同 from_dir）
            hit = next((p for s, p in final_pngs.items() if meaning in s), None)
        if hit is not None:
            stickers.append({"file": hit.name, "path": str(hit), "meaning": meaning})
    # meaning_map 没覆盖的文件（改名后 map 未同步）按文件名补齐，不丢图
    if len(stickers) < len(final_pngs):
        seen = {s["file"] for s in stickers}
        for stem, p in sorted(final_pngs.items()):
            if p.name not in seen:
                stickers.append({"file": p.name, "path": str(p), "meaning": stem})
    return stickers


def _episode_meanings(episode_dir: Path) -> list:
    """读含义词列表（按 meaning_map.json 数字序；降级用文件名）。"""
    episode_dir = Path(episode_dir)
    final = episode_dir / "最终版"
    mm = episode_dir / "meaning_map.json"
    if mm.exists():
        try:
            data = json.loads(mm.read_text(encoding="utf-8"))
            return [str(data[k]) for k in sorted(data, key=lambda x: int(x))]
        except (json.JSONDecodeError, ValueError, OSError):
            pass
    if final.exists():
        return [p.stem for p in sorted(final.glob("*.png"), key=lambda x: x.stem)]
    return []


def _regen_episode_assets(episode_dir: Path, meta, series=None) -> list:
    """按 meta 的素材模式重新生成横幅/封面/图标。返回 warnings 列表。"""
    from .stages.assets import make_banner, resize_save
    import shutil as _shutil
    episode_dir = Path(episode_dir)
    final = episode_dir / "最终版"
    paths = sorted(final.glob("*.png"), key=lambda x: x.stem) if final.exists() else []
    warnings = []
    chars = _episode_characters(episode_dir)
    role_map = (series.role_asset_map if series else None) or {}
    # 单人包默认套角色映射（用户需求：单人表情包直接用角色对应素材）
    role_key = next((c for c in chars if c in role_map), None)

    def _copy_or_warn(src, dst, label):
        if src and Path(src).is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(src, dst)
        else:
            warnings.append(f"{label}源文件不存在：{src}")

    # ---- 横幅 ----
    banner_out = episode_dir / "横幅" / "横幅.png"
    if meta.banner_mode == "custom" and meta.banner_custom:
        _copy_or_warn(meta.banner_custom, banner_out, "横幅")
    elif meta.banner_mode == "role" and role_key and role_map[role_key].get("banner"):
        _copy_or_warn(role_map[role_key]["banner"], banner_out, f"角色[{role_key}]横幅")
    else:
        if paths:
            banner_out.parent.mkdir(parents=True, exist_ok=True)
            make_banner(paths[:4], banner_out)
        else:
            warnings.append("无成品图，横幅未生成")

    # ---- 封面 ----
    cover_out = episode_dir / "封面" / "封面.png"
    cover_src = None
    if meta.cover_mode == "custom" and meta.cover_custom:
        if Path(meta.cover_custom).is_file():
            _copy_or_warn(meta.cover_custom, cover_out, "封面")
        else:
            warnings.append(f"封面源文件不存在：{meta.cover_custom}")
    elif meta.cover_mode == "role" and role_key and role_map[role_key].get("cover"):
        _copy_or_warn(role_map[role_key]["cover"], cover_out, f"角色[{role_key}]封面")
    else:
        if meta.cover_mode == "pick":
            idx = int(meta.cover_pick or 0)
            if 0 <= idx < len(paths):
                cover_src = paths[idx]
            else:
                warnings.append(f"封面选图越界（第 {idx + 1} 张不存在），回退第 1 张")
        if cover_src is None and paths:
            cover_src = paths[0]
        if cover_src is not None:
            cover_out.parent.mkdir(parents=True, exist_ok=True)
            resize_save(cover_src, cover_out, 240, 240)
        elif not paths:
            warnings.append("无成品图，封面未生成")

    # ---- 图标（50×50；custom/role 直接复制，否则优先 AI 大头照，再退封面） ----
    icon_out = episode_dir / "图标" / "图标.png"
    if meta.icon_mode == "custom" and meta.icon_custom:
        _copy_or_warn(meta.icon_custom, icon_out, "图标")
    elif meta.icon_mode == "role" and role_key and role_map[role_key].get("icon"):
        _copy_or_warn(role_map[role_key]["icon"], icon_out, f"角色[{role_key}]图标")
    else:
        # F1（评审）：管线 S3 生成的 AI 图标原图优先——之前这里无条件用封面源
        # 覆盖，用户一点「重生成素材」就把合规的头部照静默回滚成不合规形态
        icon_raw = episode_dir / "图标" / "_icon_raw.png"
        src = None
        if icon_raw.exists():
            src = icon_raw
            warnings.append("图标沿用 AI 生成的大头照（平台要求纯头部正面像）")
        elif cover_src is not None:
            src = cover_src
            warnings.append("图标退回复用封面（无 AI 大头照；平台可能驳回，建议重生成本组）")
        elif cover_out.exists():
            src = cover_out
            warnings.append("图标退回封面成品（无 AI 大头照；平台可能驳回，建议重生成本组）")
        if src is not None:
            icon_out.parent.mkdir(parents=True, exist_ok=True)
            resize_save(src, icon_out, 50, 50)
        elif not paths:
            warnings.append("无成品图，图标未生成")
    return warnings


def cmd_repolish_finals(req_id, args):
    """对已生成作品的成品跑 P2 双层防御（抠边缘连通背景 + trim 残留带）。

    救活 P2 上线前生成的单（如 61-68 的"多余边框线"驳回）：原图备份到
    原图/_finals_backup/，成品原位更新。不调 codex、秒级完成。
    """
    import shutil
    from PIL import Image
    from .stages.postprocess import remove_edge_background, trim_border_band, ensure_size
    ep_dir = Path(args.get("episode_dir") or "")
    final = ep_dir / "最终版"
    if not final.is_dir():
        _result(req_id, "fail", errors=[{"message": f"无成品目录：{final}"}])
        return
    backup = ep_dir / "原图" / "_finals_backup"
    backup.mkdir(parents=True, exist_ok=True)
    # R3（评审）：ref_library 保留背景模式（prompt.txt 的 # mode:）不跑第一层
    # 抠边缘背景——只 trim，尊重"保留参考图原有背景"策略矩阵
    mode = ""
    pf = ep_dir / "原图" / "prompt.txt"
    if pf.exists():
        try:
            for line in pf.read_text(encoding="utf-8").splitlines():
                if line.startswith("# mode:"):
                    mode = line.replace("# mode:", "").strip()
                    break
        except OSError:
            pass
    skip_bg = mode == "ref_library"
    fixed = []
    for p in sorted(final.glob("*.png")):
        bak = backup / p.name
        if not bak.exists():
            shutil.copy2(p, bak)   # 只备份第一手原图，重跑不叠加
        img = Image.open(bak).convert("RGBA")
        out = img if skip_bg else remove_edge_background(img)
        out = ensure_size(trim_border_band(out))
        out.save(p)
        fixed.append(p.name)
    _result(req_id, "ok", data={"fixed": fixed, "count": len(fixed),
                                "backup": str(backup)})


def _reject_fix_fields(reason: str) -> set:
    """从驳回理由原文推断编辑器里要改的字段（精准修改，2026-08-29 用户 SOP：
    只改有问题的部分，不全量重传）。"""
    f = set()
    if "空格" in reason:
        f.add("album")
    if "图标" in reason:
        f.add("icon")
    if "边框" in reason:
        f.update({"stickers", "cover"})
    if "角色" in reason or "合辑" in reason:
        f.add("role")
    if "含义" in reason:
        f.add("meanings")
    if "赞赏" in reason:
        f.add("tips")
    if "封面" in reason:
        f.add("cover")
    if "横幅" in reason:
        f.add("banner")
    return f



def cmd_shelf_passed(req_id, args):
    """「一键发布」：把所有"审核通过"的作品逐个上架（预约今日）。

    流程（2026-09-01 用户 SOP+实测）：sync 刷新状态 → 对每个审核通过单：
    管理页 → 详情页 → 点「上架」→ 弹窗默认已选今日 → 点「预约」。
    成功后本地 meta.platform_status="已上架"。
    """
    from pathlib import Path as _P
    from .config.series import load_meta, save_meta
    from .publish.status import sync_status
    engine = _ensure_engine()
    root = _P(engine.config.paths.output_root)

    def _say(msg):
        try:
            _log("info", msg, command="shelf_passed", command_id=req_id)
            _emit({"id": req_id, "type": "progress", "stage": "shelf",
                   "phase": "shelf", "message": msg, "percent": None,
                   "eta_seconds": None})
        except Exception:
            pass

    # 1) 先刷新状态（拿最新"审核通过"名单）
    _say("正在刷新平台状态（获取最新审核结果）…")
    sync_status(engine, on_status=_say)

    passed = []
    for ep_dir in sorted(root.iterdir()) if root.exists() else []:
        if not (ep_dir.is_dir() and ep_dir.name.startswith("episode")):
            continue
        meta = load_meta(ep_dir)
        if (meta.platform_status or "") == "审核通过":
            passed.append((ep_dir, meta))
    if not passed:
        _result(req_id, "ok", data={"published": 0,
                                    "message": "没有「审核通过待发布」的作品"})
        return
    _say(f"共 {len(passed)} 个作品审核通过，开始逐个上架…")

    from .publish.config import PublishConfig
    from .publish.browser import BrowserSession
    from .publish.status import HOME_URL, normalize_name
    from playwright.sync_api import sync_playwright

    published, failed = [], []
    with sync_playwright() as pw:
        session = BrowserSession(PublishConfig(), playwright=pw)
        page = session.start()
        try:
            if not session.ensure_login(page, on_status=_say):
                _result(req_id, "fail",
                        errors=[{"message": "登录失败，无法上架"}])
                return
            for ep_dir, meta in passed:
                album = meta.album_name or ep_dir.name
                _say(f"正在上架「{album}」…")
                tn = normalize_name(album)
                try:
                    page.goto(HOME_URL, wait_until="domcontentloaded",
                              timeout=45000)
                    page.wait_for_timeout(4000)
                    links = page.locator("a:has-text('详情'), td:has-text('详情')")
                    hit = False
                    for _pg in range(12):   # 翻页查找（2026-09-02：62/59
                        # 在第 2 页，旧实现只扫第 1 页导致上架全失败）
                        for i in range(links.count()):
                            el = links.nth(i)
                            try:
                                in_tr = el.evaluate("e=>e.closest('tr')!==null")
                                row_txt = (
                                    el.locator("xpath=ancestor::tr[1]")
                                    .inner_text(timeout=2000) if in_tr
                                    else el.inner_text(timeout=2000))
                            except Exception:
                                continue
                            if tn in normalize_name(row_txt):
                                el.click()
                                hit = True
                                break
                        if hit:
                            break
                        nb = page.locator("a:has-text('下一页')")
                        if not nb.count():
                            break
                        nb.first.click(timeout=3000)
                        page.wait_for_timeout(2200)
                    if not hit:
                        failed.append((album, "管理页未找到作品行"))
                        continue
                    page.wait_for_timeout(7000)
                    try:
                        page.wait_for_load_state("domcontentloaded",
                                                 timeout=30000)
                    except Exception:
                        pass
                    page.wait_for_timeout(2500)
                    # 详情页「上架」
                    shelf = page.locator(
                        "button:has-text('上架'), a:has-text('上架'), "
                        "span:has-text('上架')")
                    if not shelf.count():
                        failed.append((album, "详情页无「上架」按钮"))
                        continue
                    shelf.first.click()
                    page.wait_for_timeout(2500)
                    # 弹窗默认已选今日 → 点「预约」
                    confirm = page.locator(
                        '.weui-desktop-dialog:visible '
                        'button:has-text("预约")')
                    if not confirm.count():
                        failed.append((album, "未找到预约按钮（弹窗未出现？）"))
                        continue
                    confirm.first.click()
                    page.wait_for_timeout(4000)
                    body = page.inner_text("body")
                    if "预约成功" in body or "已上架" in body:
                        meta.platform_status = "已上架"
                        meta.published = True
                        save_meta(ep_dir, meta)
                        published.append(album)
                        _say(f"✓「{album}」已预约今日上架")
                    else:
                        failed.append((album, "预约后未见成功标志"))
                        try:
                            page.screenshot(
                                path=str(ep_dir / "_shelf_error.png"))
                        except Exception:
                            pass
                except Exception as e:   # noqa: BLE001
                    failed.append((album, f"{type(e).__name__}: {e}"))
        finally:
            session.close()
    _say(f"一键发布完成：成功 {len(published)}，失败 {len(failed)}")
    _result(req_id, "ok", data={
        "published": len(published), "published_names": published,
        "failed": [{"name": n, "reason": r} for n, r in failed]})


def cmd_fix_and_republish(req_id, args):
    """「修改完毕，去平台重新提交」：按驳回理由精准修复 + 编辑器精准重提。

    fix="auto"（默认）：从 meta.platform_reject_reason 推断要改的字段；
    本地修复只做选中字段相关的部分；publish=True 时打开平台编辑器
    （详情页→编辑→新标签）只改这些字段后点提交。
    """
    import shutil
    from PIL import Image as _Im
    from .stages.postprocess import remove_edge_background, trim_border_band, ensure_size
    ep_dir = Path(args.get("episode_dir") or "")
    do_publish = bool(args.get("publish", False))
    if not ep_dir.is_dir():
        _result(req_id, "fail", errors=[{"message": f"作品目录不存在：{ep_dir}"}])
        return
    from .config.series import load_meta, save_meta
    engine = _ensure_engine()
    meta = load_meta(ep_dir)
    actions = []
    final = ep_dir / "最终版"
    final_pngs = sorted(final.glob("*.png")) if final.is_dir() else []
    reason = meta.platform_reject_reason or ""
    fields = _reject_fix_fields(reason)
    explicit = args.get("fix_fields")
    if explicit:
        # 显式指定字段（运维覆盖入口）：驳回理由关键词覆盖不了的场景
        # （如只重传表情图、跳过误推断的 cover）
        fields = {str(f).strip() for f in explicit if str(f).strip()}
    if not fields:
        # 驳回理由没有可识别关键词 → 全量重走（最稳）
        fields = {"album", "stickers", "icon", "cover", "tips", "role",
                  "categories", "price"}
    # cover 选中（68 驳回"表情封面含边框线"）：用 repolish 后的成品重做封面
    if "cover" in fields and final_pngs:
        try:
            from .stages.assets import AssetsStage
            from .providers.codex import CodexProvider
            from .providers.vision import VisionProvider
            engine = _ensure_engine()
            provider = VisionProvider(CodexProvider(
                codex_exec=engine.config.paths.codex_exec,
                output_dir=engine.config.paths.codex_output_dir))
            cover_dir = ep_dir / "封面"; cover_dir.mkdir(exist_ok=True)
            best = AssetsStage(provider)._pick_best_face(
                [str(p) for p in final_pngs])
            from .stages.assets import resize_save as _rs
            _rs(best, cover_dir / "封面.png", 240, 240)
            actions.append("封面：已用去边框成品重做")
        except Exception as e:   # noqa: BLE001
            actions.append(f"封面重做失败（{type(e).__name__}: {e}）")

    result = {"actions": actions, "fields": sorted(fields), "published": False}

    # 1) 成品 repolish（边框线，62/68 驳回）——仅当选了 stickers/cover
    if final.is_dir() and ({"stickers", "cover"} & fields):
        backup = ep_dir / "原图" / "_finals_backup"
        backup.mkdir(parents=True, exist_ok=True)
        n = 0
        for p in sorted(final.glob("*.png")):
            bak = backup / p.name
            if not bak.exists():
                shutil.copy2(p, bak)
            img = _Im.open(bak).convert("RGBA")
            ensure_size(trim_border_band(remove_edge_background(img))).save(p)
            n += 1
        actions.append(f"成品去边框 {n} 张")

    # 1.5) 横幅重做（68 驳回"横幅元素拉伸变形"）——用 2026-09-02 新版
    # 等比缩放拼贴（卡片式，不变形）覆盖旧版硬拉横幅
    if "banner" in fields and final_pngs:
        try:
            from .stages.assets import make_banner
            banner_dir = ep_dir / "横幅"; banner_dir.mkdir(exist_ok=True)
            make_banner([str(p) for p in final_pngs],
                        banner_dir / "横幅.png")
            actions.append("横幅：已用新版等比拼贴重做（不变形）")
        except Exception as e:   # noqa: BLE001
            actions.append(f"横幅重做失败（{type(e).__name__}: {e}）")

    # 2) 专辑名去空格（61-64/68/69 驳回）；介绍.txt 不含专辑名，无需同步
    if "album" in fields and meta.album_name and " " in meta.album_name:
        meta.album_name = meta.album_name.replace(" ", "")
        save_meta(ep_dir, meta)
        actions.append(f"专辑名去空格 → {meta.album_name}")

    # 3) AI 图标（61/63/64/65/66/68/69 驳回）——老单没有 _icon_raw，补生成
    icon_raw = ep_dir / "图标" / "_icon_raw.png"
    if "icon" in fields and not icon_raw.exists():
        try:
            from .stages.assets import AssetsStage, resize_save
            from .providers.codex import CodexProvider
            from .providers.vision import VisionProvider
            engine = _ensure_engine()
            # F2（评审）：StickerEngine 无 vision/codex 属性——按 cmd_check_codex
            # 同款方式从 paths 构造
            _codex = CodexProvider(
                codex_exec=engine.config.paths.codex_exec,
                output_dir=engine.config.paths.codex_output_dir)
            _status = _codex.check()   # 解析 codex 绝对路径（三层探测）
            if not _status.image_ready:
                raise RuntimeError(_status.guidance_msg or "codex 不可用")
            provider = VisionProvider(_codex)
            stage = AssetsStage(provider)
            bases = []
            # R6（评审）：base*.png 约定在真实单 0 命中——base 在参考图库，
            # 按角色名匹配；匹配不到退第 1 张成品（弱参考，actions 里注明）
            md = ep_dir / "本次制作角色.md"
            char_names = []
            if md.exists():
                for line in md.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("角色："):
                        char_names = [c for c in line[len("角色："):].split("、") if c]
                        break
            reflib = Path(engine.config.paths.reference_lib)
            if reflib.is_dir() and char_names:
                for c in char_names:
                    hits = [p for p in sorted(reflib.rglob("*.png"))
                            if c in p.stem]
                    if hits:
                        bases = [str(hits[0])]
                        break
            if not bases and final_pngs:
                bases = [str(final_pngs[0])]
                weak_ref = True
            else:
                weak_ref = False
            out = stage._make_ai_icon(
                type("C", (), {"episode_dir": ep_dir, "selected_bases": bases})(), final_pngs)
            if out is not None:
                # F3（评审）：_make_ai_icon 只写 _icon_raw——必须回写正式图标
                resize_save(out, ep_dir / "图标" / "图标.png", 50, 50)
                note = "图标：AI 生成纯头部正面照（已更新 50×50）"
                if weak_ref:
                    note += "（参考为成品图，保真可能偏弱，建议重生成本组获得最佳图标）"
                actions.append(note)
            else:
                why = getattr(stage, "_icon_last_error", "") or "未知原因"
                actions.append(f"图标：AI 生成失败（{why[:80]}），沿用旧图标")
        except Exception as e:   # noqa: BLE001
            actions.append(f"图标：生成异常（{type(e).__name__}: {e}），沿用旧图标")

    # 4) 赞赏图（69 驳回）——本组角色派生
    tip_dir = ep_dir / "赞赏图"
    if "tips" in fields and not (tip_dir / "赞赏引导图.png").exists() and final_pngs:
        try:
            from .stages.assets import AssetsStage
            from .providers.codex import CodexProvider
            from .providers.vision import VisionProvider
            engine = _ensure_engine()
            provider = VisionProvider(CodexProvider(
                codex_exec=engine.config.paths.codex_exec,
                output_dir=engine.config.paths.codex_output_dir))
            cover_src = ep_dir / "封面" / "封面.png"
            AssetsStage(provider)._make_tip_images(
                [str(p) for p in final_pngs],
                str(cover_src) if cover_src.exists() else str(final_pngs[0]), tip_dir)
            actions.append("赞赏图：已用本组角色生成")
        except Exception as e:   # noqa: BLE001
            actions.append(f"赞赏图生成失败（{type(e).__name__}: {e}）")

    # 5) 编辑重提（平台编辑器全流程重填 + 提交）
    if do_publish:
        from .publish.config import PublishConfig
        from .publish.browser import BrowserSession
        from .publish.publisher import Publisher
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            session = BrowserSession(PublishConfig(), playwright=pw)
            vision = None
            if "meanings" in fields:
                from .providers.codex import CodexProvider as _CP
                from .providers.vision import VisionProvider as _VP
                _c = _CP(codex_exec=engine.config.paths.codex_exec,
                         output_dir=engine.config.paths.codex_output_dir)
                if not _c.check().image_ready:
                    raise RuntimeError('codex 不可用，无法识图重填含义词')
                vision = _VP(_c)
            publisher = Publisher(PublishConfig(), session, vision=vision)
            _r = publisher.publish(ep_dir, edit=True,
                                   fix_fields=fields)
            result["publish"] = _r
            result["published"] = bool(_r.get("success"))
            if result["published"]:
                meta.platform_status = "待审核"
                meta.published = True
                meta.platform_reject_reason = ""   # S2（评审）：清旧驳回理由
                save_meta(ep_dir, meta)
    _result(req_id, "ok", data=result)


def cmd_sync_platform_status(req_id, args):
    """一键更新：打开平台管理页抓取全部作品状态，回写本地 meta.json。"""
    from .publish.status import sync_status
    engine = _ensure_engine()

    def _say(msg):
        try:
            _log("info", msg, command="sync_platform_status", command_id=req_id)
            _emit({"id": req_id, "type": "progress", "stage": "sync",
                   "phase": "sync", "message": msg, "percent": None,
                   "eta_seconds": None})
        except Exception:
            pass

    res = sync_status(engine, on_status=_say)
    if "error" in res:
        _result(req_id, "fail", errors=[{"message": res["error"]}])
        return
    _result(req_id, "ok", data=res)


def cmd_delete_episode(req_id, args):
    """物理删除：连同 episode 本地文件夹一起删掉。

    纪律（doc/reference/series.md）：
    - 路径必须在 episodes 输出目录内（防误删任意目录）
    - 若该作品占着系列的最后一个编号（number == next_number-1），回滚
      next_number，编号不浪费；中间编号删除则留空档（盲回滚会撞号）
    """
    import shutil
    from .config.series import load_series, save_series
    engine = _ensure_engine()
    root = engine.config.paths.output_root.resolve()
    ep_dir = Path(args.get("episode_dir") or "").resolve()
    if not ep_dir.is_dir() or root not in ep_dir.parents:
        _result(req_id, "fail",
                errors=[{"message": f"非法的作品目录：{ep_dir}"}])
        return
    from .config.series import load_meta
    meta = load_meta(ep_dir)
    # 编号回滚（仅当占的是该系列最新一号）
    rolled_back = None
    if meta.series_id and meta.number is not None:
        series_list = load_series()   # list[Series]（dataclass）
        for s in series_list:
            if s.id == meta.series_id and s.next_number == meta.number + 1:
                s.next_number = meta.number
                save_series(series_list)
                rolled_back = f"{s.name} next_number → {meta.number}"
                break
    shutil.rmtree(ep_dir)
    _result(req_id, "ok", data={"deleted": str(ep_dir), "rolled_back": rolled_back})


def cmd_get_episode(req_id, args):
    """作品详情：meta + 表情列表 + 含义词 + 素材文件 + 角色。"""
    episode_dir = Path(args.get("episode_dir") or "")
    if not episode_dir.is_dir():
        _result(req_id, "fail", errors=[{"message": f"作品目录不存在：{episode_dir}"}])
        return
    from .config.series import load_meta
    meta = load_meta(episode_dir)
    final = episode_dir / "最终版"
    stickers = []
    if final.exists():
        stickers = _episode_stickers(episode_dir)
    def _exists(sub):
        f = episode_dir / sub
        return str(f) if f.exists() else None
    _result(req_id, "ok", data={
        "name": episode_dir.name, "path": str(episode_dir),
        "meta": meta.to_dict(),
        "stickers": stickers,
        "characters": _episode_characters(episode_dir),
        "banner": _exists("横幅/横幅.png"),
        "cover": _exists("封面/封面.png"),
        "icon": _exists("图标/图标.png"),
        "grid": _exists("原图/grid_4x4.png") or _exists("原图"),
        "intro_file": _exists("介绍.txt"),
    })


def cmd_update_episode_meta(req_id, args):
    """更新作品元数据：改名 / 编入系列 / 介绍 / 素材设置。

    args: {episode_dir, album_name?, assign_series_id?, intro?, regen_assets?,
           cover_mode?, cover_pick?, cover_custom?, banner_mode?, banner_custom?,
           icon_mode?, icon_custom?}
    """
    from .config import series as S
    episode_dir = Path(args.get("episode_dir") or "")
    if not episode_dir.is_dir():
        _result(req_id, "fail", errors=[{"message": f"作品目录不存在：{episode_dir}"}])
        return
    meta = S.load_meta(episode_dir)

    if args.get("assign_series_id"):
        target = S.find_series(str(args["assign_series_id"]))
        if target is None:
            _result(req_id, "fail", errors=[{"message": "系列不存在"}])
            return
        meta = S.assign_to_series(episode_dir, target)
        all_series = S.load_series()
        for s in all_series:
            if s.id == target.id:
                s.next_number = target.next_number
        S.save_series(all_series)

    if "album_name" in args:
        meta = S.rename_album(episode_dir, str(args.get("album_name") or ""))

    if "intro" in args:
        meta.intro = str(args.get("intro") or "")[:80]
        (episode_dir / "介绍.txt").write_text(meta.intro, encoding="utf-8")
        S.save_meta(episode_dir, meta)

    for key in ("cover_mode", "cover_pick", "cover_custom",
                "banner_mode", "banner_custom", "icon_mode", "icon_custom"):
        if key in args:
            setattr(meta, key, args.get(key))
    S.save_meta(episode_dir, meta)

    warnings = []
    if args.get("regen_assets"):
        series = S.find_series(meta.series_id) if meta.series_id else None
        warnings = _regen_episode_assets(episode_dir, meta, series)
        S.save_meta(episode_dir, meta)
        if warnings:
            _log("warn", "素材重生成警告：" + "；".join(warnings), command_id=req_id)

    _result(req_id, "ok", data={"meta": meta.to_dict(), "warnings": warnings})


def cmd_regen_intro(req_id, args):
    """AI 重新生成介绍（系列提示词优先，回退全局默认模板）。"""
    episode_dir = Path(args.get("episode_dir") or "")
    if not episode_dir.is_dir():
        _result(req_id, "fail", errors=[{"message": f"作品目录不存在：{episode_dir}"}])
        return
    from .config.series import load_meta, find_series, save_meta
    from .providers.codex import CodexProvider
    from .providers.vision import VisionProvider
    meta = load_meta(episode_dir)
    series = find_series(meta.series_id) if meta.series_id else None
    album = meta.album_name or episode_dir.name
    meanings = _episode_meanings(episode_dir)
    vision = VisionProvider(CodexProvider())
    intro = vision.write_intro(
        meanings, episode_name=album,
        custom_prompt=(series.intro_prompt if series else ""))
    meta.intro = intro
    (episode_dir / "介绍.txt").write_text(intro, encoding="utf-8")
    save_meta(episode_dir, meta)
    _result(req_id, "ok", data={"intro": intro, "meta": meta.to_dict()})


def cmd_regen_assets(req_id, args):
    """按 meta 素材设置重新生成横幅/封面/图标。"""
    episode_dir = Path(args.get("episode_dir") or "")
    if not episode_dir.is_dir():
        _result(req_id, "fail", errors=[{"message": f"作品目录不存在：{episode_dir}"}])
        return
    from .config.series import load_meta, find_series, save_meta
    meta = load_meta(episode_dir)
    series = find_series(meta.series_id) if meta.series_id else None
    warnings = _regen_episode_assets(episode_dir, meta, series)
    save_meta(episode_dir, meta)
    _result(req_id, "ok", data={"meta": meta.to_dict(), "warnings": warnings,
                                "banner": str(episode_dir / "横幅" / "横幅.png"),
                                "cover": str(episode_dir / "封面" / "封面.png"),
                                "icon": str(episode_dir / "图标" / "图标.png")})


def cmd_replenish_refs(req_id, args):
    """补弹：把某作品的成品贴纸去重后导入参考图库（弹药模型闭环）。

    去重用 dhash 感知哈希（64bit，海明距离<=8 视为雷同）：
    - 和库里在役图比对（防重复合入相同内容）
    - 和 _used_* 归档比对（防"从参考图生成的贴纸"再回流成自复制）
    """
    engine = _ensure_engine()
    ep_dir = Path(args.get("episode_dir") or "")
    final = ep_dir / "最终版"
    if not final.is_dir():
        _result(req_id, "fail", errors=[{"message": f"作品没有成品贴纸：{ep_dir}"}])
        return
    from PIL import Image
    lib = engine.config.paths.reference_lib
    lib.mkdir(parents=True, exist_ok=True)

    def _dhash(path, size=8):
        try:
            g = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
            px = list(g.getdata())
            bits = 0
            for row in range(size):
                for col in range(size):
                    bits = (bits << 1) | (1 if px[row * (size + 1) + col] > px[row * (size + 1) + col + 1] else 0)
            return bits
        except Exception:
            return None

    def _hamming(a, b):
        return bin(a ^ b).count("1")

    # 现有指纹：在役 + 已归档
    import glob as _glob
    existing = []
    for p in list(lib.glob("*.png")) + list(lib.glob("*.jpg")) + list(lib.glob("*.jpeg")):
        h = _dhash(p)
        if h is not None:
            existing.append((p, h))
    for archived in lib.glob("_used_*"):
        for p in archived.glob("*.png"):
            h = _dhash(p)
            if h is not None:
                existing.append((p, h))

    import shutil as _shutil
    copied, skipped = [], []
    for src in sorted(final.glob("*.png")):
        h = _dhash(src)
        if h is None:
            skipped.append({"name": src.name, "reason": "无法读取"})
            continue
        dup = next((p for p, eh in existing if _hamming(h, eh) <= 8), None)
        if dup:
            skipped.append({"name": src.name, "reason": f"与库里 {dup.name} 雷同"})
            continue
        dst = lib / src.name
        i = 2
        while dst.exists():
            dst = lib / f"{src.stem}-{i}{src.suffix}"
            i += 1
        _shutil.copy2(src, dst)
        existing.append((dst, h))
        copied.append(dst.name)
    _result(req_id, "ok", data={
        "imported": copied, "skipped": skipped,
        "library_count": len([p for p in lib.iterdir()
                              if p.suffix.lower() in (".png", ".jpg", ".jpeg")])})


def cmd_list_prompt_sets(req_id, args):
    """列出全部 Prompt 方案（用户文件 + 内置兜底）。"""
    engine = _ensure_engine()
    from .config.prompts import list_sets
    _result(req_id, "ok", data={
        "sets": [s.to_dict() for s in list_sets(engine.config.paths.user_data)],
        "active": engine.config.prefs.prompt_set_id or "builtin-2026-08-28-moe"})


def cmd_save_prompt_set(req_id, args):
    """新建/更新一套 Prompt 方案；is_default=true 时同时设为默认。"""
    engine = _ensure_engine()
    from .config.prompts import save_set, find_set
    data = args.get("set") or {}
    if not str(data.get("name") or "").strip():
        _result(req_id, "fail", errors=[{"message": "方案名不能为空"}])
        return
    ps = save_set(engine.config.paths.user_data, data)
    if args.get("is_default"):
        engine.config.prefs.prompt_set_id = ps.id
        save_prefs(engine.config.prefs, engine.config.paths.prefs_file)
    _result(req_id, "ok", data={"set": ps.to_dict(),
                               "active": engine.config.prefs.prompt_set_id or ""})


def cmd_delete_prompt_set(req_id, args):
    engine = _ensure_engine()
    from .config.prompts import delete_set, is_builtin
    set_id = args.get("id") or ""
    ok = delete_set(engine.config.paths.user_data, set_id)
    if ok and engine.config.prefs.prompt_set_id == set_id:
        engine.config.prefs.prompt_set_id = None
        save_prefs(engine.config.prefs, engine.config.paths.prefs_file)
    _result(req_id, "ok" if ok else "fail",
            errors=None if ok else [{"message": "内置方案不可删除"}])


def cmd_build_feedback_prompt(req_id, args):
    """一键生成"发给 AI 的反哺提示词"（含评分语义说明 + 打分数据 + 当次 prompt）。

    评分语义（用户 2026-08-28 口径）：未打分 ≠ 差——可能是没来得及打，
    也可能是平平常常（无亮点也无槽点）；有问题的用户一般都会打分。
    """
    import json as _json
    engine = _ensure_engine()
    ep_dir = Path(args.get("episode_dir") or "")
    rating_file = ep_dir / "rating.json"
    if not rating_file.exists():
        _result(req_id, "fail",
                errors=[{"message": "还没有打分记录：先在详情页给表情打分，再来复制。"}])
        return
    rating = _json.loads(rating_file.read_text(encoding="utf-8"))
    prompts_dir = engine.config.paths.user_data / "prompts"
    text = f"""你是「表情包一键制作」的生图 prompt 优化助手。下面是一次作品的打分数据与制作过程，请反哺优化生图 prompt。

## 评分语义（重要）
- 有分数 = 用户有明确感受：高分（4-5）= 亮点，低分（1-2）= 有问题（配合备注看具体哪里不行）。
- 没打分的格子 ≠ 差：可能是用户还没来得及打，也可能是平平常常（没有特别大的亮点，也没什么槽点）。有问题的一般用户都会尽量打分，所以请把分析重心放在已打分的格子上。

## 你的任务
1. 对比低分格（尤其带备注的）与当次 prompt，定位是哪条指令导致的问题（如：比例/动作/情绪描述/风格块某行）。
2. 总结高分格的共同特征，判断哪些指令在起正作用。
3. 产出优化建议：给出修改后的风格块（STYLE）和/或各模式附加指令的完整文本。
4. 如果你在用户本机运行（ZCode 等代理）："Prompt 方案"文件存在 {prompts_dir}/*.json，可直接修改或新建方案文件，并提示用户到 设置→Prompt 方案 里设为默认。

## 打分数据
{_json.dumps(rating, ensure_ascii=False, indent=2)}
"""
    _result(req_id, "ok", data={"text": text})


def cmd_build_all_rejects_prompt(req_id, args):
    """一键汇总复制**所有**未通过审核作品的驳回理由（喂 AI 分析共性+逐单修改）。"""
    engine = _ensure_engine()
    root = Path(engine.config.paths.output_root)
    from .config.series import load_meta
    blocks = []
    for ep_dir in sorted(root.iterdir()) if root.exists() else []:
        if not (ep_dir.is_dir() and ep_dir.name.startswith("episode")):
            continue
        meta = load_meta(ep_dir)
        reason = (meta.platform_reject_reason or "").strip()
        if "未通过" not in (meta.platform_status or "") or not reason:
            continue
        pfile = ep_dir / "原图" / "prompt.txt"
        prompt_head = ""
        if pfile.exists():
            try:
                prompt_head = pfile.read_text(encoding="utf-8")[:800]
            except OSError:
                prompt_head = ""
        blocks.append(
            f"### 《{meta.album_name or ep_dir.name}》\n"
            f"平台状态：{meta.platform_status}\n"
            f"驳回理由（原文）：\n{reason}\n"
            + (f"当次生图 prompt（截取）：\n{prompt_head}\n" if prompt_head else ""))
    if not blocks:
        _result(req_id, "fail",
                errors=[{"message": "没有抓到任何未通过审核的驳回理由：先在作品库点「一键更新」。"}])
        return
    text = f"""以下是微信表情开放平台**多个作品**的审核驳回记录（{len(blocks)} 个未通过）。请做两件事：

## 任务一：提炼共性问题
逐条比对驳回理由，指出哪些问题在多个作品中重复出现（如命名规则、图标规格、画面元素），并判断各属于管线哪个环节（生图 prompt / 切图 / 抠图 / 素材生成 / 命名）。

## 任务二：逐单修改清单
对每个作品给出具体可执行的修改步骤（能重生成的标注"重新生成一单"，能改名的给出新名字，能只改素材的标注"详情页→重生成素材"）。

## 背景知识
- 表情主图 240×240、聊天页图标 50×50，由 4×4 网格成图自动切图缩放生成；图标已支持单独 AI 生成纯头部正面照。
- 平台规则示例：表情名称不能含空格；图标要求"只含形象头部的正面图像"；表情图不能有多余边框线。

---

""" + "\n".join(blocks)
    _result(req_id, "ok", data={"text": text, "count": len(blocks)})


def cmd_build_reject_review_prompt(req_id, args):
    """一键生成"审核驳回评审 prompt"：平台驳回理由 + 当次制作过程 → 交给 AI 分析怎么改。

    驳回理由来自「一键更新」抓取（详情页→未通过审核→表情驳回理由）。
    """
    engine = _ensure_engine()
    ep_dir = Path(args.get("episode_dir") or "")
    if not ep_dir.is_dir():
        _result(req_id, "fail", errors=[{"message": f"作品目录不存在：{ep_dir}"}])
        return
    from .config.series import load_meta
    meta = load_meta(ep_dir)
    reason = (meta.platform_reject_reason or "").strip()
    if not reason:
        _result(req_id, "fail", errors=[{"message": "该作品没有抓到驳回理由：先在作品库点「一键更新」。"}])
        return
    prompt_txt = ""
    pfile = ep_dir / "原图" / "prompt.txt"
    if pfile.exists():
        prompt_txt = pfile.read_text(encoding="utf-8")[:3000]
    prompts_dir = engine.config.paths.user_data / "prompts"
    text = f"""你是「表情包一键制作」的审核驳回评审助手。作品《{meta.album_name or ep_dir.name}》被微信表情平台驳回，请分析原因并给出修改方案。

## 平台驳回理由（原文）
{reason}

## 背景知识（本软件的素材管线）
- 表情主图 240x240、聊天页图标 50x50，均由同一张 4x4 网格成图自动切图缩放生成；聊天页图标来自本组表情之一缩放，**不会额外加文字**——但若成图格子本身含小字/复杂装饰，缩到 50px 就会糊成一团。
- 驳回常见根因：格子内小文字/装饰过多（缩放后不可辨认）、格子间内容粘连、图标选了最复杂的一张。

## 你的任务
1. 逐句解读驳回理由，指出它对应管线中的哪个环节（生图 prompt 的哪类指令 / 切图 / 图标选张）。
2. 结合下面的当次生图 prompt，定位最可能导致驳回的具体指令（如 STYLE 块或某格描述里的文字/装饰元素）。
3. 产出可执行修改：给出修改后的风格块（STYLE）或指令文本；若是图标选张问题，说明应选哪类格子（最简单/最大图形的那张）。
4. 如果你在用户本机运行（ZCode 等代理）："Prompt 方案"文件在 {prompts_dir}/*.json，可直接修改方案文件并提示用户到 设置→Prompt 方案 设为默认；修改完成后提示用户重新生成一单并重新提交。

## 当次生图 prompt（截取）
{prompt_txt or '（当次 prompt 未落盘，可能是历史作品）'}
"""
    _result(req_id, "ok", data={"text": text})



def _album_series_number(meta, ep_dir):
    """从 meta/专辑名解析 (系列名, 编号)。专辑名形如「周三涵做表情157」，
    系列名=去掉尾部数字；编号优先 meta.number，兜底专辑名尾数字。"""
    import re
    album = meta.album_name or ep_dir.name
    m = re.match(r"^(.*?)(\d+)$", album.strip())
    series = m.group(1).strip() if m else album.strip()
    number = None
    if getattr(meta, "number", None):
        number = int(meta.number)
    elif m:
        number = int(m.group(2))
    return series, number


def cmd_list_all_stickers(req_id, args):
    """全部表情视图：跨作品列出每张贴纸（图/含义/所属/现有打分）。

    group 带 series_name/number（前端按系列筛选 + 编号降序）；
    响应带 series 列表与 default_series（设置里的默认系列）。
    """
    import json as _json
    engine = _ensure_engine()
    root = Path(engine.config.paths.output_root)
    from .config.series import load_meta
    groups, series_seen = [], []
    for ep_dir in sorted(root.iterdir(), reverse=True) if root.exists() else []:
        if not (ep_dir.is_dir() and ep_dir.name.startswith("episode")):
            continue
        meta = load_meta(ep_dir)
        stickers = _episode_stickers(ep_dir)
        if not stickers:
            continue
        rating = {}
        rf = ep_dir / "rating.json"
        if rf.exists():
            try:
                rating = _json.loads(rf.read_text(encoding="utf-8")).get("ratings") or {}
            except Exception:   # noqa: BLE001
                rating = {}
        series_name, number = _album_series_number(meta, ep_dir)
        if series_name and series_name not in series_seen:
            series_seen.append(series_name)
        groups.append({
            "episode_dir": str(ep_dir),
            "album_name": meta.album_name or ep_dir.name,
            "series_name": series_name,
            "number": number,
            "stickers": stickers,
            "ratings": rating,
            "overall": (rf.exists() and _json.loads(rf.read_text(encoding="utf-8")).get("overall")) or None,
        })
    # 默认系列（用户在设置里指定的），回落到作品数最多的系列
    default_series = ""
    sid = getattr(engine.config.prefs, "default_series_id", None)
    if sid:
        from .config.series import find_series
        s = find_series(sid)
        default_series = s.name if s else ""
    if not default_series and series_seen:
        cnt = {}
        for g in groups:
            if g["series_name"]:
                cnt[g["series_name"]] = cnt.get(g["series_name"], 0) + 1
        default_series = max(cnt, key=cnt.get) if cnt else ""
    _result(req_id, "ok", data={"groups": groups,
                                "total": sum(len(g["stickers"]) for g in groups),
                                "series": series_seen,
                                "default_series": default_series})


def cmd_build_all_ratings_prompt(req_id, args):
    """一键复制全部打分信息与 Prompt（路径引用式：不内联打分明细，
    只给 rating.json / prompt.txt 等数据库文件路径，AI 自行读取）。

    支持 series（系列名）/ from_no / to_no（第几弹范围）过滤——
    用户只想让 AI 分析某系列、或最近某一段作品时不再全量导出。
    """
    import json as _json
    engine = _ensure_engine()
    root = Path(engine.config.paths.output_root)
    from .config.series import load_meta
    series_filter = str(args.get("series") or "").strip()
    try:
        from_no = int(args["from_no"]) if args.get("from_no") else None
        to_no = int(args["to_no"]) if args.get("to_no") else None
    except (TypeError, ValueError):
        from_no = to_no = None
    skipped = 0
    blocks = []
    for ep_dir in sorted(root.iterdir(), reverse=True) if root.exists() else []:
        if not (ep_dir.is_dir() and ep_dir.name.startswith("episode")):
            continue
        meta = load_meta(ep_dir)
        series_name, number = _album_series_number(meta, ep_dir)
        if series_filter and series_name != series_filter:
            continue
        if from_no is not None and (number is None or number < from_no):
            skipped += 1
            continue
        if to_no is not None and (number is None or number > to_no):
            skipped += 1
            continue
        rf = ep_dir / "rating.json"
        if not rf.exists():
            continue
        try:
            rating = _json.loads(rf.read_text(encoding="utf-8"))
        except Exception:   # noqa: BLE001
            continue
        n_rated = len(rating.get("ratings") or {})
        if not n_rated and not rating.get("overall"):
            continue   # 完全没打分的单不占篇幅
        album = meta.album_name or ep_dir.name
        nl = chr(10)
        blocks.append(
            f"### 《{album}》（{n_rated} 张已打分）" + nl +
            f"- 打分数据库：{rf}" + nl +
            f"- 当次生图 prompt：{ep_dir / '原图' / 'prompt.txt'}" + nl +
            f"- 含义映射：{ep_dir / 'meaning_map.json'}" + nl +
            f"- 表情成品目录：{ep_dir / '最终版'}" + nl +
            f"- 素材目录：横幅 {ep_dir / '横幅' / '横幅.png'} | "
            f"封面 {ep_dir / '封面' / '封面.png'} | "
            f"图标 {ep_dir / '图标' / '图标.png'}")
    if not blocks:
        _result(req_id, "fail", errors=[{"message":
            "范围内没有已打分的作品：调整系列/弹数范围，或先去打分。"}])
        return
    reflib = Path(engine.config.paths.reference_lib)
    scope = ""
    if series_filter:
        scope += f"「{series_filter}」系列 "
    if from_no is not None or to_no is not None:
        scope += f"第 {from_no or '…'}–{to_no or '…'} 弹 "
    if skipped:
        scope += f"（{skipped} 单在范围外/无编号被跳过）"
    text = f"""你是「表情包一键制作」的批量优化助手。以下是{(" " + scope) if scope else ""}共 {len(blocks)} 个已打分作品的**数据库文件路径**（打分明细不内联，请用文件工具逐个读取 rating.json——含每张表情的 1-5 分与用户备注）。

## 评分语义（重要）
- 有分数 = 用户有明确感受：高分（4-5）= 亮点，低分（1-2）= 有问题（配合备注看）。
- 没打分 ≠ 差：可能没来得及打，也可能平平常常。有问题的用户一般都会打分。
- 备注是用户原话，指出具体问题（如"脸歪了""边框线""不萌"），是最高优先级信号。

## 你的任务（跨作品全局优化，不是逐单流水账）
1. **通读全部 rating.json**，聚类共性问题（同类备注跨作品重复出现 = 系统性问题）。
2. **优化方向（用户指定，按需扩展）**：
   a. 参考图库（{reflib}，生成表情的素材仓库）：哪些参考图产出的单普遍低分？建议淘汰/补充什么风格的参考图？
   b. 横幅/封面美观度：横幅是 4 张拼贴（750x400），用户觉得不好看——分析低分单的横幅共性，给出新的横幅生成方案（构图/底色/间距/是否用 AI 整图生成）。
   c. 生图 prompt（各单 prompt.txt）：低分集中的指令模式是什么？
3. 产出可执行修改清单：能改参考图库的列具体文件操作；能改管线的指出代码/方案；能改 prompt 的给出修改后的文本。
4. 如果你在用户本机运行（ZCode 等代理）：可直接读取上述路径的文件、修改参考图库与 %APPDATA%/StickerEngine/prompts/*.json 方案文件。

## 已打分作品清单（{len(blocks)} 个）
""" + chr(10).join(blocks)
    _result(req_id, "ok", data={"text": text, "count": len(blocks)})


def cmd_save_rating(req_id, args):
    """保存打分到 episode/rating.json（自动嵌入当次 prompt/模式 = AI 反哺原料）。"""
    import json as _json
    import time as _time
    engine = _ensure_engine()
    ep_dir = Path(args.get("episode_dir") or "")
    if not ep_dir.is_dir():
        _result(req_id, "fail", errors=[{"message": f"作品目录不存在：{ep_dir}"}])
        return
    from .config.series import load_meta
    meta = load_meta(ep_dir)
    prompt_txt = ""
    pfile = ep_dir / "原图" / "prompt.txt"
    if pfile.exists():
        prompt_txt = pfile.read_text(encoding="utf-8")
    mm_path = ep_dir / "meaning_map.json"
    meaning_map = {}
    if mm_path.exists():
        try:
            meaning_map = _json.loads(mm_path.read_text(encoding="utf-8"))
        except Exception:
            meaning_map = {}
    rating = {
        "album_name": meta.album_name or ep_dir.name,
        "episode_dir": str(ep_dir),
        "created_at": meta.created_at,
        "rated_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
        # ---- 过程数据（AI 反哺的上下文）----
        "production": {
            "mode": (prompt_txt.splitlines()[0].replace("# mode:", "").strip()
                     if prompt_txt.startswith("# mode:") else ""),
            "prompt_file_content": prompt_txt,
            "meaning_map": meaning_map,
            "characters": (ep_dir / "本次制作角色.md").read_text(encoding="utf-8")
                          if (ep_dir / "本次制作角色.md").exists() else "",
        },
        # ---- 用户打分 ----
        "overall": args.get("overall"),
        "note": args.get("note", ""),
        "ratings": args.get("ratings") or {},   # {含义词: {"score":1-5,"note":""}}
    }
    (ep_dir / "rating.json").write_text(
        _json.dumps(rating, ensure_ascii=False, indent=2), encoding="utf-8")
    _result(req_id, "ok", data={"path": str(ep_dir / "rating.json"),
                                "rated": len(rating["ratings"])})


def cmd_get_rating(req_id, args):
    engine = _ensure_engine()
    ep_dir = Path(args.get("episode_dir") or "")
    f = ep_dir / "rating.json"
    if not f.exists():
        _result(req_id, "ok", data={"ratings": {}, "overall": None, "note": ""})
        return
    import json as _json
    try:
        _result(req_id, "ok", data=_json.loads(f.read_text(encoding="utf-8")))
    except Exception:
        _result(req_id, "ok", data={"ratings": {}, "overall": None, "note": ""})


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
    from .promotion.config import PromotionConfig
    engine = _ensure_engine()
    promo_file = engine.config.paths.user_data / "promotion.json"
    defaults = PromotionConfig()
    data = {
        "reward_qr": str(defaults.reward_qr),
        "group_qr": str(defaults.group_qr),
        "sticker_qr": str(defaults.sticker_qr),
        "author_name": defaults.author_name,
        "studio_name": defaults.studio_name,
        "homepage_url": defaults.homepage_url,
        "avatar_url": defaults.avatar_url,
        "repo_url": defaults.repo_url,
        "discussions_url": defaults.discussions_url,
    }
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
    """在系统文件管理器中打开目录（命令名保持不变，协议兼容）。

    darwin → open（Finder）；win32 → os.startfile（资源管理器）；其他 → xdg-open。
    """
    import subprocess as sp
    path = args.get("path")
    if path and Path(path).exists():
        if sys.platform == "win32":
            import os
            os.startfile(str(path))
        elif sys.platform == "darwin":
            sp.run(["open", path], check=False)
        else:
            sp.run(["xdg-open", path], check=False)
        _result(req_id, "ok")
    else:
        _result(req_id, "fail", errors=[{"message": f"路径不存在: {path}"}])


def cmd_install_chromium(req_id, args):
    """下载发布用 Chromium（playwright install chromium）。

    打包版内置 playwright driver 但不含浏览器二进制；首次提交微信前调用。
    Mac/Windows 通用：driver 缺浏览器时它会下载到用户缓存目录。
    """
    import subprocess as sp

    def progress(message, percent):
        _emit({"id": req_id, "type": "progress", "stage": "install",
               "message": message, "percent": percent})

    progress("正在下载发布浏览器（Chromium，约 150MB，只需一次）...", 0.05)
    try:
        if getattr(sys, "frozen", False):
            # 打包版：直接调 playwright 自带的 node driver
            from playwright._impl._driver import compute_driver_executable, get_driver_env
            cmd = [str(compute_driver_executable()), "install", "chromium"]
            env = get_driver_env()
        else:
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            env = None
        proc = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.STDOUT, text=True,
                        encoding="utf-8", errors="replace", env=env)
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                progress(line, 0.5)
        proc.wait()
        # 校验浏览器就位
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            ready = Path(playwright.chromium.executable_path).exists()
        ok = proc.returncode == 0 and ready
        _result(req_id, "ok" if ok else "fail", data={
            "ready": ready,
            "guidance": "" if ok else "Chromium 下载未完成，请检查网络后重试。",
        })
    except Exception as exc:
        _result(req_id, "fail", errors=[{"message": f"安装浏览器失败：{type(exc).__name__}: {exc}"}])


def cmd_get_logs(req_id, args):
    _result(req_id, "ok", data={"logs": _safe_logs()})


def cmd_clear_logs(req_id, args):
    _memory_logs.clear()
    _result(req_id, "ok")


def _publish_episode(episode_dir, progress):
    """运行现有微信 Publisher，给桌面层返回结构化结果。"""
    try:
        from .publish.browser import BrowserSession
        from .publish.config import PublishConfig
        from .publish.publisher import Publisher
    except ImportError as exc:
        # 发布组件缺失时给出可操作的指引，而不是裸 ModuleNotFoundError
        return {"success": False, "step": "browser", "error":
                f"发布组件未安装（{exc}）。"
                "开发预览环境请运行：pip install playwright && python -m playwright install chromium；"
                "正式安装包请联系作者更新版本。"}

    episode_dir = Path(episode_dir)
    progress("prepare", "正在检查发布素材…", 0.05)
    config = PublishConfig.from_env()
    publisher = Publisher(config, BrowserSession(config), progress=progress)
    progress("browser", "正在打开微信表情开放平台…", 0.15)
    result = publisher.publish(episode_dir)
    screenshot = episode_dir / "_publish_error.png"
    if screenshot.exists():
        result["screenshot"] = str(screenshot)
    progress(
        result.get("step", "done"),
        "提交完成" if result.get("success") else "提交未完成",
        1.0,
    )
    return result


def cmd_save_publish_credentials(req_id, args):
    """保存发布账号密码到系统凭据库（Win 凭据管理器 / Mac 钥匙串）。"""
    from .publish.credentials import save_credentials
    try:
        info = save_credentials(str(args.get("account") or ""), str(args.get("password") or ""))
        _result(req_id, "ok", data=info)
    except ValueError as e:
        _result(req_id, "fail", errors=[{"message": str(e)}])


def cmd_publish_credentials_status(req_id, args):
    """凭据配置状态（不回传密码本体）。"""
    from .publish.credentials import credentials_status
    _result(req_id, "ok", data=credentials_status())


def cmd_clear_publish_credentials(req_id, args):
    from .publish.credentials import clear_credentials
    clear_credentials()
    _result(req_id, "ok")


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

    # 前置校验：专辑名必须是正式命名。时间戳目录名（episode_xxx）或空名
    # 提交出去就是平台上的作品名——先阻断，指引到详情页命名。
    from .config.series import load_meta
    meta = load_meta(episode_dir)
    album = (meta.album_name or "").strip()
    if not album or album.startswith("episode_"):
        _result(
            req_id, "fail",
            data={"success": False, "step": "prepare",
                  "error": "作品还没有正式命名（当前是时间戳目录名）。请先打开作品详情页：编入系列自动编号（如「周思涵做表情 61」）或手动命名，然后再提交。"},
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
        # 发布成功：回写作品元数据（作品库显示已发布）
        try:
            from .config.series import mark_published
            mark_published(Path(episode_dir))
        except Exception:
            pass
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
                retry=args.get("retry", 2), headless=args.get("headless"),
            )
        elif action == "shelf":
            from .publish.browser import BrowserSession
            from .publish.config import PublishConfig
            from .publish.shelf import Shelf
            config = PublishConfig.from_env()
            Shelf(config, BrowserSession(config)).shelve_all(
                max_pages=args.get("max_pages", 5), limit=args.get("limit"),
                dry_run=args.get("dry_run", False),
                headless=args.get("headless"),
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
            "reference_lib_path": prefs.reference_lib_path,
            "prompt_set_id": prefs.prompt_set_id,
            "vision_calls": prefs.vision_calls,
            "browser_headless": prefs.browser_headless,
            "sticker_price": prefs.sticker_price,
            "default_series_id": prefs.default_series_id}


def _dict_to_prefs(d):
    mp = d.get("mode_probs", {})
    return Prefs(mode_probs=ModeProbsConfig(
        single=mp.get("single", 0.5), duo=mp.get("duo", 0.3),
        trio=mp.get("trio", 0.0), quad=mp.get("quad", 0.2)),
        single_char_probs=d.get("single_char_probs", {}), base_probs=d.get("base_probs", {}),
        grid_size=d.get("grid_size", 4), transparent_default=d.get("transparent_default", True),
        ref_lib_priority=d.get("ref_lib_priority", True),
        ref_consume=d.get("ref_consume", True),
        story_mode=d.get("story_mode", True),
        reference_lib_path=d.get("reference_lib_path"),
        default_series_id=d.get("default_series_id"),
        prompt_set_id=d.get("prompt_set_id"),
        vision_calls=d.get("vision_calls", False),
        browser_headless=d.get("browser_headless", False),
        sticker_price=int(d.get("sticker_price", 0) or 0))


HANDLERS = {
    "check_codex": cmd_check_codex, "install_codex": cmd_install_codex,
    "codex_usage": cmd_codex_usage,
    "get_version": cmd_get_version,
    "load_prefs": cmd_load_prefs, "save_prefs": cmd_save_prefs,
    "list_characters": cmd_list_characters, "generate_base": cmd_generate_base,
    "add_base": cmd_add_base,
    "run": cmd_run,
    "run_batch": cmd_run_batch,
    "list_all_stickers": cmd_list_all_stickers,
    "build_all_ratings_prompt": cmd_build_all_ratings_prompt, "stop": cmd_stop,
    "list_episodes": cmd_list_episodes, "open_in_finder": cmd_open_in_finder,
    "list_series": cmd_list_series, "save_series": cmd_save_series,
    "sync_platform_status": cmd_sync_platform_status,
    "repolish_finals": cmd_repolish_finals,
    "fix_and_republish": cmd_fix_and_republish,
    "shelf_passed": cmd_shelf_passed,
    "replenish_refs": cmd_replenish_refs,
    "list_prompt_sets": cmd_list_prompt_sets,
    "save_prompt_set": cmd_save_prompt_set,
    "delete_prompt_set": cmd_delete_prompt_set,
    "save_rating": cmd_save_rating,
    "build_feedback_prompt": cmd_build_feedback_prompt,
    "build_reject_review_prompt": cmd_build_reject_review_prompt,
    "build_all_rejects_prompt": cmd_build_all_rejects_prompt,
    "get_rating": cmd_get_rating,
    "delete_episode": cmd_delete_episode,
    "get_episode": cmd_get_episode, "update_episode_meta": cmd_update_episode_meta,
    "regen_intro": cmd_regen_intro, "regen_assets": cmd_regen_assets,
    "featured": cmd_featured,
    "load_promotion": cmd_load_promotion, "save_promotion": cmd_save_promotion,
    "get_logs": cmd_get_logs, "clear_logs": cmd_clear_logs,
    "check_publish": cmd_check_publish, "publish_episode": cmd_publish_episode,
    "save_publish_credentials": cmd_save_publish_credentials,
    "publish_credentials_status": cmd_publish_credentials_status,
    "clear_publish_credentials": cmd_clear_publish_credentials,
    "install_chromium": cmd_install_chromium,
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


def _force_utf8_stdio():
    """强制 stdio 走 UTF-8。

    Windows 管道默认用系统区域编码（中文系统是 GBK），JSON-lines 协议里的
    中文/emoji（如 "✅"）会触发 UnicodeEncodeError，stdin 的中文入参也会乱码。
    Mac/Linux 默认就是 UTF-8，reconfigure 无副作用。
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass   # 流被替换/关闭时静默跳过


def main():
    """常驻读 stdin，每行一个命令 JSON。

    C1 修复：每个命令在独立线程执行，主线程立即返回继续读 stdin。
    这样 run（分钟级长任务）期间仍能读取 stop 命令并置位 stop_event。
    """
    _force_utf8_stdio()
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
