"""S3 素材生成阶段：横幅 750×400 / 封面 240×240 / 图标 50×50 / 介绍.txt。

**教训14（封面 ≠ 横幅源）**：封面应是单角色特写（最具辨识度的正面像），
横幅是横向宽幅拼贴。两者源图不同——横幅取前 4 张拼贴，封面取 `_pick_best_face`
（简化：第 1 张；真实项目移植 asset_selection.py 的 face_detect 选最大脸）。

移植自现有 make_assets.py，适配 sticker_engine 的 stage/provider 框架。
"""
from pathlib import Path

from PIL import Image

from ..pipeline.context import PipelineContext, LogEntry
from ..providers.vision import VisionProvider

# 微信平台素材目标尺寸（spec）
_BANNER_W, _BANNER_H = 750, 400
_COVER_SIZE = 240
_ICON_SIZE = 50
_INTRO_MAX = 80   # 微信介绍 80 字硬限制


class AssetsStage:
    """S3：横幅 750×400 / 封面 240×240 / 图标 50×50 / 介绍.txt。"""

    def __init__(self, vision: VisionProvider):
        self.vision = vision

    def run(self, ctx: PipelineContext) -> None:
        stickers = ctx.stickers
        if not stickers:
            ctx.log(LogEntry(stage="S3", status="FAIL", message="无成品图，跳过素材生成"))
            return
        paths = [Path(s.path) for s in stickers]

        # 横幅：取前 4 张横向拼贴（750×400）
        banner_dir = ctx.episode_dir / "横幅"; banner_dir.mkdir(exist_ok=True)
        self._make_banner(paths[:4], banner_dir / "横幅.png")

        # 封面：单张最佳图特写（教训14：不复用横幅源）—— 取最具辨识度正面像
        cover_dir = ctx.episode_dir / "封面"; cover_dir.mkdir(exist_ok=True)
        cover_src = self._pick_best_face(paths)
        self._resize_save(cover_src, cover_dir / "封面.png", _COVER_SIZE, _COVER_SIZE)

        # 图标：同封面源，50×50（聊天页小图）
        icon_dir = ctx.episode_dir / "图标"; icon_dir.mkdir(exist_ok=True)
        self._resize_save(cover_src, icon_dir / "图标.png", _ICON_SIZE, _ICON_SIZE)

        # 介绍：1-80 字，硬截断防超限（str() 兜底：write_intro 契约返回 str，
        # 防御 provider 异常返回非 str；真实 VisionProvider 返回 str 时为恒等）
        meanings = [Path(s.path).stem for s in stickers]
        intro = str(self.vision.write_intro(meanings, episode_name=ctx.episode_dir.name))
        intro = intro[:_INTRO_MAX]
        (ctx.episode_dir / "介绍.txt").write_text(intro, encoding="utf-8")

        ctx.log(LogEntry(stage="S3", status="OK",
                         message="横幅/封面/图标/介绍 生成完成"))

    def _make_banner(self, src_paths: list, out: Path) -> None:
        """前 4 张横向拼成 750×400 宽幅拼贴（横幅）。"""
        cell_w = _BANNER_W // max(len(src_paths), 1)
        banner = Image.new("RGBA", (_BANNER_W, _BANNER_H), (255, 255, 255, 0))
        for i, p in enumerate(src_paths):
            im = Image.open(p).convert("RGBA").resize((cell_w, _BANNER_H), Image.LANCZOS)
            banner.paste(im, (i * cell_w, 0), im)
        banner.save(out)

    def _pick_best_face(self, paths: list) -> Path:
        """选最具辨识度的正面像做封面源。

        简化：取第 1 张（真实项目移植 asset_selection.py 的 face_detect，
        按人脸占比/清晰度排序选最佳）。教训14 关键：封面源 ≠ 横幅拼贴源。
        """
        return paths[0]

    def _resize_save(self, src: Path, out: Path, w: int, h: int) -> None:
        Image.open(src).convert("RGBA").resize((w, h), Image.LANCZOS).save(out)
