from dataclasses import dataclass
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
