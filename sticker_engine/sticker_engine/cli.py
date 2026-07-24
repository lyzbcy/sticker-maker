from . import StickerEngine
from .config.schema import Config
from .config.paths import resolve_paths, current_platform


def main():
    config = Config.placeholder()
    config.paths = resolve_paths(current_platform())
    engine = StickerEngine(config)
    print("表情包一键制作 · CLI 冒烟测试")
    print(f"用户数据目录：{config.paths.user_data}")
    print("开始 run（真实 codex）...")
    episode = engine.run(
        progress_callback=lambda ev: print(
            f"  [{ev.stage}] {ev.message} ({ev.percent:.0%})"))
    print(f"\n完成。episode_dir={episode.episode_dir}")
    print(f"成品数：{len(episode.stickers)}")


if __name__ == "__main__":
    main()
