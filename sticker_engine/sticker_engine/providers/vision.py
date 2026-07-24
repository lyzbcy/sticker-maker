"""含义预检 + 介绍文案 provider（决策 K：全走 codex）。

移植自现有 check_and_rename.py 的优化思路：N 张拼 1 张大图，
1 次 codex 调用完成识图命名，避免 N 次往返。

决策 K（已完成）：
- ``interpret`` 拼大图 → ``codex.exec_text(识图 prompt, refs=[大图])`` → 解析 JSON
- ``write_intro`` 调 ``codex.exec_text(介绍 prompt)`` → 截断 80 字
- codex 文本能力由 ``CodexProvider.exec_text`` 提供（捕获 stdout）
- 失败时优雅降级（含义词 → ``含义{i}``、介绍 → 基于含义词的模板），管线不崩

本机无 codex（决策 A1：用户自备），故无端到端测试；单元测试用 MagicMock
注入 codex 的 ``exec_text`` 返回值。
"""
import json
import logging
import re
from pathlib import Path

from PIL import Image

from .codex import CodexProvider


logger = logging.getLogger(__name__)


class VisionProvider:
    """
    含义预检 + 介绍文案（决策 K：全走 codex）。
    N 张拼 1 张大图，1 次调用识图（移植 check_and_rename.py 优化）。
    """

    def __init__(self, codex: CodexProvider):
        self.codex = codex

    def interpret(self, panel_paths: list) -> dict:
        """对 N 张 panel 图返回 {1: 含义词, ..., N: 含义词}。

        流程：拼大图 → codex.exec_text(识图 prompt, refs=[大图]) → 解析 JSON。
        codex 失败 / 文本不可解析时降级到 ``含义{i}``（保持管线不崩，但这是降级不是默认）。
        """
        if not panel_paths:
            return {}
        contact = self._make_contact_sheet(panel_paths)
        n = len(panel_paths)
        prompt = (
            f"这是一张包含 {n} 个表情的拼图，从左到右、从上到下编号 1..{n}。"
            "请为每个表情给一个 2-4 字中文含义词。"
            "只返回 JSON，格式：{\"1\":\"含义\",\"2\":\"含义\",...}，含义词不能重复。"
        )
        # refs 传大图路径，让 codex 能看图识图。codex 不支持 -i 时返回空，下游降级。
        text = self.codex.exec_text(prompt=prompt, refs=[contact])
        return self._parse_meanings_from_text(text, n)

    def write_intro(self, meanings: list, episode_name: str = "") -> str:
        """写 1-80 字软萌介绍。

        codex 成功 → 返回 codex 文本（硬截断 80 字）。
        codex 失败（空串）→ 降级到一个基于含义词的简单模板（非固定字面量）。
        """
        prompt = (
            f"为表情包《{episode_name}》写一句 1-80 字的软萌介绍，不要模板腔。"
            f"这些表情的含义：{','.join(meanings[:8])}。只返回介绍文本。"
        )
        text = self.codex.exec_text(prompt=prompt)
        text = (text or "").strip()
        if text:
            return text[:80]
        # 降级模板（基于含义词 / 名字，不是固定字面量）
        names = [m for m in (meanings or []) if m][:4]
        if names:
            base = f"《{episode_name}》系列：{''.join(names)}，软萌日常表情。"
        else:
            base = f"《{episode_name}》软萌日常表情包。"
        return base[:80]

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

    def _parse_meanings_from_text(self, text: str, n: int) -> dict:
        """从 codex 文本输出解析含义词为 {1..n: 含义词}。

        健壮解析：codex 返回可能含 ```json ... ``` 围栏、纯 JSON、或散文包裹的 JSON。
        策略：提取第一个 ``{...}`` 块（贪婪、跨行），json.loads。
        解析失败（空文本 / 无 JSON / JSONDecodeError）→ 记 WARN + 降级 ``含义{i}``。

        参数为 ``text: str``（不再是 Path/raw），语义对齐 codex.exec_text 的 stdout 输出。
        """
        if not text:
            logger.warning("VisionProvider.interpret: codex 返回空文本，降级到 含义{i}")
            return {i: f"含义{i}" for i in range(1, n + 1)}
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            logger.warning(
                "VisionProvider.interpret: codex 文本未含 JSON 块，降级到 含义{i}。原文：%s",
                text[:120],
            )
            return {i: f"含义{i}" for i in range(1, n + 1)}
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            logger.warning(
                "VisionProvider.interpret: codex JSON 解析失败，降级到 含义{i}。原文：%s",
                text[:120],
            )
            return {i: f"含义{i}" for i in range(1, n + 1)}
        if not isinstance(obj, dict):
            logger.warning("VisionProvider.interpret: codex JSON 非 dict，降级。")
            return {i: f"含义{i}" for i in range(1, n + 1)}
        # 只要数字键，键转 int
        parsed = {int(k): str(v) for k, v in obj.items() if str(k).isdigit()}
        if not parsed:
            logger.warning("VisionProvider.interpret: codex JSON 无数字键，降级。")
            return {i: f"含义{i}" for i in range(1, n + 1)}
        return parsed
