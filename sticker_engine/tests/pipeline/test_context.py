from sticker_engine.pipeline.context import (
    PipelineContext, ProgressEvent, LogEntry, EpisodeSpec, ModeProbs
)


def test_production_log_keeps_last_50_entries():
    ctx = PipelineContext(config=None, episode=EpisodeSpec.placeholder())
    for i in range(60):
        ctx.log(LogEntry(stage="S1", status="OK", message=f"m{i}"))
    assert len(ctx.production_log) == 50
    assert ctx.production_log[-1].message == "m59"
    assert ctx.production_log[0].message == "m10"


def test_progress_event_normalizes_percent():
    ev = ProgressEvent(stage="S1", phase="x", message="m", percent=1.5)
    assert ev.percent == 1.0
    ev2 = ProgressEvent(stage="S1", phase="x", message="m", percent=-0.1)
    assert ev2.percent == 0.0


def test_mode_probs_sums_to_one():
    m = ModeProbs(single=0.5, duo=0.3, trio=0.0, quad=0.2)
    assert abs(m.sum() - 1.0) < 1e-9


def test_episode_spec_defaults():
    e = EpisodeSpec.placeholder()
    assert e.grid_size == 4
    assert e.transparent_default is True
