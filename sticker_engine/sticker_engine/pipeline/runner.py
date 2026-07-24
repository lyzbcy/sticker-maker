import threading
import time
from typing import Callable, List, Optional, Tuple

from .context import GateError, PipelineContext, ProgressEvent


class StopRequested(Exception):
    """stop_event 被置位时抛出，run 应捕获并清理。"""


# C5 修复：全局 stage 历史耗时（跨多次 run 滑动平均，算 ETA 用）
_stage_durations: dict = {}
_HIST_KEEP = 5


def _record_stage_time(label: str, seconds: float) -> None:
    _stage_durations.setdefault(label, []).append(seconds)
    if len(_stage_durations[label]) > _HIST_KEEP:
        _stage_durations[label] = _stage_durations[label][-_HIST_KEEP:]


def _estimate_remaining(steps: list, current_idx: int) -> Optional[int]:
    """基于历史耗时估算剩余秒数。无历史数据返回 None。"""
    remaining = steps[current_idx + 1:]
    if not remaining:
        return 0
    total = 0.0
    has_any = False
    for kind, obj, label in remaining:
        hist = _stage_durations.get(label)
        if hist:
            total += sum(hist) / len(hist)
            has_any = True
        else:
            total += 30
    return int(total) if has_any else None


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
            # C5：开始阶段时估算剩余时间（基于历史）
            eta = _estimate_remaining(self.steps, i)
            self._emit(progress_callback, ProgressEvent(
                stage=label, phase=f"start_{kind}",
                message=f"开始 {label}", percent=pct, eta_seconds=eta))

            stage_start = time.time()
            if kind == "gate":
                result = obj.check(ctx)
                if not result.ok:
                    gate_name = getattr(obj, "name", label)
                    ctx.add_error(GateError(
                        gate=gate_name, message=result.message, guidance=result.guidance))
                    self._emit(progress_callback, ProgressEvent(
                        stage=label, phase="gate_fail",
                        message=f"关卡 {gate_name} 未通过：{result.message}", percent=pct))
                    return  # 关卡 FAIL 必停
            else:
                obj.run(ctx)
            _record_stage_time(label, time.time() - stage_start)

            pct_after = (i + 1) / n if n > 0 else 1.0
            self._emit(progress_callback, ProgressEvent(
                stage=label, phase=f"end_{kind}",
                message=f"完成 {label}", percent=pct_after, eta_seconds=_estimate_remaining(self.steps, i)))

    @staticmethod
    def _emit(cb: Optional[Callable[[ProgressEvent], None]], ev: ProgressEvent) -> None:
        if cb is not None:
            cb(ev)
