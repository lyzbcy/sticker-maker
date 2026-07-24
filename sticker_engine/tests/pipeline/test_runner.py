import threading
import pytest
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec, LogEntry
from sticker_engine.pipeline.runner import PipelineRunner, StopRequested
from sticker_engine.pipeline.gates import Gate, GateResult


class FakeStage:
    """记录是否被执行。"""
    def __init__(self, name):
        self.name = name
        self.executed = False
    def run(self, ctx):
        self.executed = True
        ctx.log(LogEntry(stage=self.name, status="OK", message=f"{self.name} done"))


class AlwaysFailGate(Gate):
    name = "fail_gate"
    def check(self, ctx) -> GateResult:
        return GateResult(ok=False, message="故意失败", guidance="修这里")


class AlwaysPassGate(Gate):
    name = "pass_gate"
    def check(self, ctx) -> GateResult:
        return GateResult(ok=True)


def _make_ctx():
    return PipelineContext(config=None, episode=EpisodeSpec.placeholder())


def test_runner_executes_stages_and_gates_in_order():
    s0, s1 = FakeStage("S0"), FakeStage("S1")
    gate = AlwaysPassGate()
    runner = PipelineRunner(stages=[("S0", s0), (gate, "after_S0"), ("S1", s1)])
    events = []
    runner.run(_make_ctx(), progress_callback=lambda ev: events.append(ev))
    assert s0.executed and s1.executed
    assert len(events) >= 2


def test_runner_stops_when_gate_fails():
    s0, s1 = FakeStage("S0"), FakeStage("S1")
    gate = AlwaysFailGate()
    runner = PipelineRunner(stages=[("S0", s0), (gate, "after_S0"), ("S1", s1)])
    ctx = _make_ctx()
    runner.run(ctx)
    assert s0.executed          # gate 之前的执行了
    assert not s1.executed      # gate 失败，S1 没执行
    assert len(ctx.errors) == 1
    assert ctx.errors[0].gate == "fail_gate"


def test_runner_respects_stop_event_between_stages():
    s0, s1 = FakeStage("S0"), FakeStage("S1")
    stop = threading.Event()
    # 在 S0 执行后、S1 之前置位 stop
    class StopAfterS0:
        def run(self, ctx):
            stop.set()
    gate = AlwaysPassGate()
    runner = PipelineRunner(stages=[("S0", s0), (gate, "after_S0"), ("StopAfterS0", StopAfterS0()), ("S1", s1)])
    with pytest.raises(StopRequested):
        runner.run(_make_ctx(), stop_event=stop)


def test_runner_emits_progress_events_with_increasing_percent():
    s0, s1 = FakeStage("S0"), FakeStage("S1")
    runner = PipelineRunner(stages=[("S0", s0), ("S1", s1)])
    events = []
    runner.run(_make_ctx(), progress_callback=lambda ev: events.append(ev))
    percents = [e.percent for e in events]
    # 至少单调不降，且最后到 1.0
    assert percents == sorted(percents)
    assert abs(percents[-1] - 1.0) < 1e-9
