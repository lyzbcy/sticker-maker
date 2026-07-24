from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class GateResult:
    ok: bool
    message: str = ""
    guidance: str = ""


class Gate(Protocol):
    """关卡：检查 ctx，返回 GateResult。FAIL 则 runner 停止。"""
    name: str
    def check(self, ctx) -> GateResult: ...


class Gate0PreGenerate:
    """关卡0：base 图、参考图库、codex 可用。"""
    name = "Gate0_pre_generate"

    def __init__(self, codex_provider):
        self.codex_provider = codex_provider

    def check(self, ctx) -> GateResult:
        if ctx.config.paths is None:
            return GateResult(False, "配置缺失 paths", "请先初始化 Paths")
        status = self.codex_provider.check()
        if not status.image_ready:
            return GateResult(
                False, f"codex 不可用：{status.guidance_msg}", status.guidance_msg)
        return GateResult(True)


class Gate1PostGenerateRaw:
    """关卡1：grid 图存在且非空。"""
    name = "Gate1_post_generate_raw"

    def check(self, ctx) -> GateResult:
        if ctx.grid_image is None or not Path(ctx.grid_image).exists():
            return GateResult(False, "生图产物缺失", "重试生图")
        return GateResult(True)


class Gate2PostGenerate:
    """关卡2：数量/含义词。"""
    name = "Gate2_post_generate"

    def check(self, ctx) -> GateResult:
        if not ctx.stickers:
            return GateResult(False, "无成品表情", "检查 S2 后处理")
        meanings = list(ctx.meaning_map.values())
        if len(meanings) != len(set(meanings)):
            return GateResult(False, "含义词重复", "修正含义预检")
        return GateResult(True)
