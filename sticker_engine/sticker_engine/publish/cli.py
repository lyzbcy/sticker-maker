"""publish-cli: C 子项目的命令行入口（开发者本人用）。

命令：
  publish-cli publish --dir <episode_dir>          单弹发布
  publish-cli batch --start N --end M              批量发布
  publish-cli batch --only 23,51 --resume          指定/续传
  publish-cli shelf --limit 3                      自动上架
  publish-cli login                                手动登录（首次）
  publish-cli logout                               清登录态
"""
import argparse
import sys
from pathlib import Path

from .config import PublishConfig
from .browser import BrowserSession


def main():
    parser = argparse.ArgumentParser(
        prog="publish-cli",
        description="表情包一键制作 · 发布工具（开发者用，提交到微信表情开放平台）")
    sub = parser.add_subparsers(dest="command", required=True)

    # publish
    p_pub = sub.add_parser("publish", help="单弹发布")
    p_pub.add_argument("--dir", required=True, help="episode 目录路径")
    p_pub.add_argument("--headless", action="store_true", help="无头模式")

    # batch
    p_batch = sub.add_parser("batch", help="批量发布")
    p_batch.add_argument("--start", type=int, default=None)
    p_batch.add_argument("--end", type=int, default=None)
    p_batch.add_argument("--only", type=str, default=None, help="指定弹次，逗号分隔")
    p_batch.add_argument("--resume", action="store_true", help="续传（跳过已成功）")
    p_batch.add_argument("--retry", type=int, default=2)
    p_batch.add_argument("--headless", action="store_true")

    # shelf
    p_shelf = sub.add_parser("shelf", help="自动上架审核通过的专辑")
    p_shelf.add_argument("--max-pages", type=int, default=5)
    p_shelf.add_argument("--limit", type=int, default=None)
    p_shelf.add_argument("--dry-run", action="store_true")
    p_shelf.add_argument("--headless", action="store_true")

    # login / logout
    sub.add_parser("login", help="手动登录（首次）")
    sub.add_parser("logout", help="清登录态")

    args = parser.parse_args()
    config = PublishConfig.from_env()

    if args.command == "publish":
        _cmd_publish(config, args)
    elif args.command == "batch":
        _cmd_batch(config, args)
    elif args.command == "shelf":
        _cmd_shelf(config, args)
    elif args.command == "login":
        _cmd_login(config)
    elif args.command == "logout":
        _cmd_logout(config)


def _cmd_publish(config, args):
    from .publisher import Publisher
    session = BrowserSession(config)
    publisher = Publisher(config, session)
    result = publisher.publish(args.dir, headless=args.headless)
    if result.get("success"):
        print(f"✅ 发布成功：{result.get('album_name')}")
    else:
        print(f"❌ 发布失败（步骤 {result.get('step')}）：{result.get('error')}")
        sys.exit(1)


def _cmd_batch(config, args):
    from .batch import BatchPublisher
    from ..config.paths import resolve_paths, current_platform
    paths = resolve_paths(current_platform())
    only = [int(x) for x in args.only.split(",")] if args.only else None
    batch = BatchPublisher(config, paths.output_root)
    result = batch.run(start=args.start, end=args.end, only=only,
                       resume=args.resume, retry=args.retry, headless=args.headless)
    s = result["summary"]
    print(f"批量发布完成：成功 {s['ok']}，失败 {s['fail']}")
    for name, status in result["results"].items():
        print(f"  {name}: {status}")


def _cmd_shelf(config, args):
    from .shelf import Shelf
    session = BrowserSession(config)
    shelf = Shelf(config, session)
    result = shelf.shelve_all(max_pages=args.max_pages, limit=args.limit,
                               dry_run=args.dry_run, headless=args.headless)
    s = result["summary"]
    print(f"上架完成：OK {s['ok']} / FAIL {s['fail']} / SKIP {s['skip']} / UNKNOWN {s['unknown']}")
    if result.get("error"):
        print(f"⚠️ {result['error']}")


def _cmd_login(config):
    """手动登录（首次）。打开浏览器让用户登录，存 storage_state。"""
    import time
    from . import selectors as S
    session = BrowserSession(config)
    page = session.start(headless=False)
    page.goto(S.HOME_URL, timeout=config.navigation_timeout_ms)
    print("浏览器已打开。请在页面完成登录（扫码或账号密码）。")
    print("登录成功后，按回车保存登录态...")
    input()
    session.save_state(page)
    print(f"✅ 登录态已保存到 {config.storage_state}")
    session.close()


def _cmd_logout(config):
    if config.storage_state.exists():
        config.storage_state.unlink()
        print(f"✅ 已清除登录态：{config.storage_state}")
    else:
        print("无登录态文件")


if __name__ == "__main__":
    main()
