"""D: AI agent HTTP 服务（Flask）。

薄层：直接调 A 的 StickerEngine + C 的 publish，不经过 CLI 子进程（更高效）。
暴露 HTTP 端点给外部 agent，SSE 流式推送 run 进度。
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify, Response, send_file

from .. import StickerEngine, Config, resources_path
from ..config.paths import resolve_paths, current_platform
from ..config.loader import load_prefs_from_file, save_prefs


def _create_app(token: str, scheduler=None) -> Flask:
    app = Flask(__name__)
    app.config["TOKEN"] = token
    app.config["SCHEDULER"] = scheduler

    # 全局引擎实例（复用，避免重复加载剧本库）
    engine_state = {"engine": None, "current_run_id": None, "stop_events": {}}

    def _get_engine() -> StickerEngine:
        if engine_state["engine"] is None:
            config = Config.placeholder()
            config.paths = resolve_paths(current_platform())
            prefs = load_prefs_from_file(config.paths.prefs_file)
            if prefs is not None:
                config.prefs = prefs
            engine_state["engine"] = StickerEngine(config)
        return engine_state["engine"]

    # ---- 认证中间件 ----

    @app.before_request
    def _auth():
        # /agent-prompt 和 /health 不需认证
        if request.path in ("/agent-prompt", "/health"):
            return None
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "缺少 Authorization Bearer token"}), 401
        if auth[7:] != app.config["TOKEN"]:
            return jsonify({"error": "token 无效"}), 401
        return None

    # ---- 端点 ----

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/agent-prompt")
    def agent_prompt():
        return send_file(Path(__file__).parent / "AGENT_PROMPT.md", mimetype="text/plain")

    @app.get("/status")
    def status():
        from ..providers.codex import CodexProvider
        engine = _get_engine()
        provider = CodexProvider(codex_exec=engine.config.paths.codex_exec,
                                 output_dir=engine.config.paths.codex_output_dir)
        codex_status = provider.check()
        # 历史作品
        episodes = []
        root = engine.config.paths.output_root
        if root.exists():
            for ep in sorted(root.iterdir(), reverse=True)[:10]:
                if ep.is_dir():
                    episodes.append({"name": ep.name, "path": str(ep)})
        return jsonify({
            "codex_ready": codex_status.image_ready,
            "codex_guidance": codex_status.guidance_msg,
            "prefs": engine.config.prefs.__dict__ if hasattr(engine.config.prefs, '__dict__') else None,
            "episodes": episodes,
        })

    @app.post("/run")
    def run():
        """生图。SSE 流式推送进度，最终 result。"""
        req_id = str(uuid.uuid4())[:8]
        stop = threading.Event()
        engine_state["stop_events"][req_id] = stop
        events = []
        events_lock = threading.Lock()
        done = threading.Event()

        def progress_cb(ev):
            with events_lock:
                events.append({"type": "progress", "stage": ev.stage, "phase": ev.phase,
                               "message": ev.message, "percent": ev.percent,
                               "eta_seconds": ev.eta_seconds})

        def run_thread():
            engine = _get_engine()
            try:
                episode = engine.run(progress_callback=progress_cb, stop_event=stop)
                result = {"type": "result", "success": episode.success,
                          "episode_dir": str(episode.episode_dir) if episode.episode_dir else None,
                          "stickers": len(episode.stickers),
                          "errors": [{"gate": e.gate, "message": e.message} for e in episode.errors],
                          "aborted_reason": episode.aborted_reason}
            except Exception as e:
                result = {"type": "result", "success": False,
                          "errors": [{"message": f"{type(e).__name__}: {e}"}]}
            finally:
                engine_state["stop_events"].pop(req_id, None)
            with events_lock:
                events.append(result)
            done.set()

        t = threading.Thread(target=run_thread, daemon=True)
        t.start()

        def stream():
            sent = 0
            while not (done.is_set() and sent >= len(events)):
                with events_lock:
                    new_events = events[sent:]
                    sent = len(events)
                for ev in new_events:
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    if ev.get("type") == "result":
                        return
                time.sleep(0.1)
        return Response(stream(), mimetype="text/event-stream")

    @app.post("/stop")
    def stop():
        # 停所有活跃 run
        for ev in engine_state["stop_events"].values():
            ev.set()
        return jsonify({"ok": True})

    @app.post("/publish")
    def publish():
        """发布一弹（转发到 C 的 Publisher）。"""
        data = request.get_json() or {}
        episode_dir = data.get("episode_dir")
        if not episode_dir:
            return jsonify({"error": "缺少 episode_dir"}), 400
        # 在后台线程跑（发布是长任务）
        result_holder = {}
        def do_publish():
            from ..publish.config import PublishConfig
            from ..publish.publisher import Publisher
            from ..publish.browser import BrowserSession
            cfg = PublishConfig.from_env()
            session = BrowserSession(cfg)
            publisher = Publisher(cfg, session)
            result_holder["result"] = publisher.publish(episode_dir, headless=data.get("headless", False))
        # 同步执行（agent 可接受几分钟等待；若要异步用 /batch 模式）
        t = threading.Thread(target=do_publish)
        t.start()
        t.join(timeout=600)   # 最长 10 分钟
        return jsonify(result_holder.get("result", {"success": False, "error": "超时"}))

    @app.post("/shelf")
    def shelf():
        from ..publish.config import PublishConfig
        from ..publish.shelf import Shelf
        from ..publish.browser import BrowserSession
        data = request.get_json() or {}
        cfg = PublishConfig.from_env()
        session = BrowserSession(cfg)
        sh = Shelf(cfg, session)
        result = sh.shelve_all(max_pages=data.get("max_pages", 5),
                                limit=data.get("limit"),
                                dry_run=data.get("dry_run", False),
                                headless=data.get("headless", False))
        return jsonify(result)

    @app.post("/batch")
    def batch():
        """批量发布（后台任务）。返回 job_id，agent 轮询 /status。"""
        data = request.get_json() or {}
        from ..publish.config import PublishConfig
        from ..publish.batch import BatchPublisher
        cfg = PublishConfig.from_env()
        engine = _get_engine()
        bp = BatchPublisher(cfg, engine.config.paths.output_root)
        job_id = str(uuid.uuid4())[:8]
        def run_batch():
            bp.run(start=data.get("start"), end=data.get("end"),
                   only=data.get("only"), resume=data.get("resume", False),
                   retry=data.get("retry", 2))
        threading.Thread(target=run_batch, daemon=True).start()
        return jsonify({"job_id": job_id, "status": "started"})

    # ---- 定时任务 ----

    @app.post("/schedule")
    def add_schedule():
        sched = app.config.get("SCHEDULER")
        if not sched:
            return jsonify({"error": "scheduler 未启用"}), 500
        data = request.get_json() or {}
        job = sched.add(cron=data.get("cron", "* * * * *"),
                        action=data.get("action", "run"),
                        args=data.get("args", {}))
        return jsonify({"job_id": job.job_id, "cron": job.cron, "action": job.action})

    @app.get("/schedules")
    def list_schedules():
        sched = app.config.get("SCHEDULER")
        if not sched:
            return jsonify({"jobs": []})
        from dataclasses import asdict
        return jsonify({"jobs": [asdict(j) for j in sched.list()]})

    @app.delete("/schedule/<job_id>")
    def del_schedule(job_id):
        sched = app.config.get("SCHEDULER")
        if not sched:
            return jsonify({"error": "scheduler 未启用"}), 500
        ok = sched.remove(job_id)
        return jsonify({"ok": ok})

    return app
