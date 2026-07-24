"""含义预检 + 介绍文案 provider（决策 K：走 codex）。

移植自现有 check_and_rename.py 的优化思路：16 张拼 1 张大图，
1 次 codex 调用完成识图命名，避免 N 次往返。

**有意为之的骨架说明**：
`interpret` / `write_intro` 内部会调 codex exec，但 codex 文本输出的
JSON 解析需要真实 codex 环境调试。本任务（Task 10）先用 `_parse_meanings`
骨架返回 `含义{i}`，真实解析在 Task 12 冒烟或后续集成阶段补。已在代码注释标注。
测试用 MagicMock 注入 vision，不真实调 codex。
"""
import json
import re
from pathlib import Path
from typing import Optional

from PIL import Image

from .codex import CodexProvider


class VisionProvider:
    """
    含义预检 + 介绍文案（决策 K：走 codex）。
    16 张拼 1 张大图，1 次调用识图（移植 check_and_rename.py 优化）。
    """

    def __init__(self, codex: CodexProvider):
        self.codex = codex

    def interpret(self, panel_paths: list) -> dict:
        """对 N 张 panel 图返回 {1: 含义词, ..., N: 含义词}。"""
        if not panel_paths:
            return {}
        # 拼大图（16→1 优化，决策 K）
        contact = self._make_contact_sheet(panel_paths)
        n = len(panel_paths)
        prompt = (
            f"这是一张包含 {n} 个表情的拼图，从左到右、从上到下编号 1..{n}。"
            "请为每个表情给一个 2-4 字中文含义词，输出 JSON: {\"1\":\"xx\",...}。要求含义词不重复。"
        )
        # 真实实现调 codex（返回最新生成图路径；文本输出在 stdout，需集成阶段捕获）
        raw = self.codex.generate(prompt=prompt, refs=[contact])
        return self._parse_meanings(raw, n)

    def write_intro(self, meanings: list, episode_name: str = "") -> str:
        """写 1-80 字介绍。"""
        prompt = (
            f"为表情包《{episode_name}》写一句 1-80 字介绍，"
            f"含义词：{','.join(meanings[:8])}。软萌，不要模板腔。"
        )
        # 同 interpret，真实文本输出解析在集成阶段补（决策 K）
        return "（介绍文案，由 codex 生成）"   # 骨架

    def _make_contact_sheet(self, paths: list) -> Path:
        """把 N 张图拼成一张大图（移植 check_and_rename.py）。"""
        imgs = [Image.open(p).convert("RGBA") for p in paths]
        cols = 4 if len(imgs) >= 4 else len(imgs)
        rows = (len(imgs) + cols - 1) // cols
        w = max(im.width for im in imgs)
        h = max(im.height for im in imgs)
        sheet = Image.new("RGBA", (w * cols, h * rows), (255, 255, 255, 255))
        for i, im in enumerate(imgs):
            r, c = divmod(i, cols)
            sheet.paste(im, (c * w, r * h))
        out = Path(paths[0]).parent / "_contact_sheet.png"
        sheet.save(out)
        return out

    def _parse_meanings(self, raw, n) -> dict:
        """解析 codex 文本输出为 {1..n: 含义词}。

        骨架：codex exec 的文本输出捕获 + JSON 解析需要真实 codex 环境调试，
        本任务先用 `含义{i}` 占位。真实解析在 Task 12 冒烟 / 后续集成阶段补。
        若 raw 是可解析的 JSON 字符串（集成测试可能传入），尽量解析。
        """
        # 尽力解析：若 raw 恰好是 dict 或可解析的 JSON 字符串，直接用
        parsed: Optional[dict] = None
        if isinstance(raw, dict):
            parsed = raw
        elif isinstance(raw, str):
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    obj = json.loads(m.group(0))
                    if isinstance(obj, dict):
                        parsed = obj
                except json.JSONDecodeError:
                    parsed = None
        if parsed:
            return {int(k): str(v) for k, v in parsed.items() if str(k).isdigit()}
        # 骨架兜底
        return {i: f"含义{i}" for i in range(1, n + 1)}
