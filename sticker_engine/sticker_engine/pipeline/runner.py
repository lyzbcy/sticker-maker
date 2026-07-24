import threading
from typing import Callable, List, Optional, Tuple

from .context import GateError, PipelineContext, ProgressEvent


class StopRequested(Exception):
    """stop_event 被置位时抛出，run 应捕获并清理。"""


# 归一化后的 step：("stage"|"gate", obj, label)
_Step = Tuple[str, object, str]


class PipelineRunner:
    """
    顺序执行 Stage，阶段间嵌 Gate 关卡门禁（FAIL 必停），发进度事件，响应 stop_event。

    构造兼容两种传参：
      - 位置：PipelineRunner([...])  -> steps
      - 关键字：PipelineRunner(stages=[...])  -> stages（测试用这种）

    列表元素是 2 元素元组，支持两种写法（label 永远是 str）：
      - ("S0", stage_obj)         stage 在前 label 在后（stage 形式）
      - (gate_obj, "after_S0")    gate 在前 label 在后（gate 形式）
    区分 stage/gate 靠方法签名：有 check 方法的是 gate，有 run 方法的是 stage。
    """

    def __init__(self, steps: Optional[List] = None, *, stages: Optional[List] = None):
        raw = stages if stages is not None else (steps or [])
        self.steps: List[_Step] = [self._normalize(item) for item in raw]

    @staticmethod
    def _normalize(item) -> _Step:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError(f"每个 step 必须是 2 元素元组，收到：{item!r}")
        a, b = item
        # label 永远是 str，据此定位 obj 和 label
        if isinstance(a, str):
            obj, label = b, a
        elif isinstance(b, str):
            obj, label = a, b
        else:
            # 都不是 str：用 obj 的 name 属性做 label
            obj = a
            label = getattr(a, "name", type(a).__name__)

        if hasattr(obj, "check") and callable(getattr(obj, "check")):
            kind = "gate"
        elif hasattr(obj, "run") and callable(getattr(obj, "run")):
            kind = "stage"
        else:
            raise TypeError(f"无法识别 step 对象类型（既无 check 也无 run）：{obj!r}")
        return (kind, obj, label)

    def run(
        self,
        ctx: PipelineContext,
        progress_callback: Optional[Callable[[ProgressEvent], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        n = len(self.steps)
        for i, (kind, obj, label) in enumerate(self.steps):
            # 阶段之间检查 stop_event（上一阶段执行中可能置位）
            if stop_event is not None and stop_event.is_set():
                raise StopRequested()

            pct = i / n if n > 0 else 1.0
            self._emit(progress_callback, ProgressEvent(
                stage=label, phase=f"start_{kind}",
                message=f"开始 {label}", percent=pct))

            if kind == "gate":
                result = obj.check(ctx)
                if not result.ok:
                    # 错误里记录 gate 自身身份（obj.name），不是位置 label
                    gate_name = getattr(obj, "name", label)
                    ctx.add_error(GateError(
                        gate=gate_name, message=result.message, guidance=result.guidance))
                    self._emit(progress_callback, ProgressEvent(
                        stage=label, phase="gate_fail",
                        message=f"关卡 {gate_name} 未通过：{result.message}", percent=pct))
                    return  # 关卡 FAIL 必停
            else:
                obj.run(ctx)

            pct_after = (i + 1) / n if n > 0 else 1.0
            self._emit(progress_callback, ProgressEvent(
                stage=label, phase=f"end_{kind}",
                message=f"完成 {label}", percent=pct_after))

    @staticmethod
    def _emit(cb: Optional[Callable[[ProgressEvent], None]], ev: ProgressEvent) -> None:
        if cb is not None:
            cb(ev)
