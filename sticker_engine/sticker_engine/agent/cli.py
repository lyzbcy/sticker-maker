"""agent-server: D 的启动入口。

启动 HTTP 服务（localhost:7432）+ scheduler。
首次启动生成 token，存到用户数据目录。
"""
import argparse
import os
import uuid
from pathlib import Path

from ..config.paths import resolve_paths, current_platform


def _ensure_token(paths) -> str:
    """首次启动生成 token，之后复用。"""
    token_file = paths.user_data / "agent_token.txt"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    token = uuid.uuid4().hex
    token_file.write_text(token, encoding="utf-8")
    print(f"[agent] 首次启动，生成 token：{token}")
    print(f"[agent] token 存于：{token_file}")
    return token


def main():
    parser = argparse.ArgumentParser(prog="agent-server",
                                     description="表情包一键制作 · AI Agent HTTP 服务")
    parser.add_argument("--port", type=int, default=7432)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-scheduler", action="store_true", help="不启动定时任务")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    paths = resolve_paths(current_platform())
    token = _ensure_token(paths)

    from .server import _create_app
    from .scheduler import Scheduler

    # scheduler 的触发函数：被定时调用时执行 action
    def trigger_fn(action: str, action_args: dict):
        print(f"[scheduler] 触发 {action} {action_args}")
        # 这里简化：触发 run（真实场景可扩展）
        if action == "run":
            import threading
            from .. import StickerEngine, Config
            from ..config.loader import load_prefs_from_file
            config = Config.placeholder()
            config.paths = paths
            prefs = load_prefs_from_file(paths.prefs_file)
            if prefs:
                config.prefs = prefs
            engine = StickerEngine(config)
            threading.Thread(target=engine.run, daemon=True).start()

    scheduler = None if args.no_scheduler else Scheduler(
        state_file=paths.user_data / "schedules.json", trigger_fn=trigger_fn)
    if scheduler:
        scheduler.start()

    app = _create_app(token=token, scheduler=scheduler)
    print(f"[agent] 服务启动：http://{args.host}:{args.port}")
    print(f"[agent] agent prompt: http://{args.host}:{args.port}/agent-prompt")
    print(f"[agent] token: {token}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
