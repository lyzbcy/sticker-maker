"""stage_progress 细粒度进度注入 + S1 打点 + codex 心跳/诊断 的回归测试。

背景：用户反馈"卡在 开始 S1 没有任何日志"。S1 的 codex.generate 是
分钟级阻塞调用，此前零进度零日志，失败时 stderr 被丢弃。
"""
import time
from pathlib import Path

import pytest

from sticker_engine.pipeline.context import (
    EpisodeSpec, PipelineContext, ProgressEvent)
from sticker_engine.pipeline.runner import PipelineRunner
from sticker_engine.stages.generate import GenerateStage


def _make_ctx():
    return PipelineContext(config=None, episode=EpisodeSpec.placeholder())


# ---------- runner 注入 ctx.stage_progress ----------

class EmittingStage:
    """在 run 内部用 ctx.stage_progress 发细粒度进度。"""
    def run(self, ctx):
        cb = getattr(ctx, "stage_progress", None)
        assert cb is not None, "runner 必须注入 stage_progress"
        cb("第一步：准备输入")
        cb("第二步：等待外部服务")


def test_runner_injects_stage_progress_to_ctx():
    runner = PipelineRunner(stages=[("S1", EmittingStage())])
    events = []
    runner.run(_make_ctx(), progress_callback=lambda ev: events.append(ev))

    details = [e for e in events if e.phase == "stage_progress"]
    assert [e.message for e in details] == ["第一步：准备输入", "第二步：等待外部服务"]
    assert all(e.stage == "S1" for e in details)
    # stage 结束后通道应关闭
    assert getattr(_make_ctx(), "stage_progress", None) is None


def test_stage_progress_cleared_after_stage():
    ctx = _make_ctx()
    seen = {}
    runner = PipelineRunner(stages=[("S1", EmittingStage())])
    runner.run(ctx, progress_callback=lambda ev: None)
    # finally 分支应把通道置回 None，防止泄漏到后续阶段
    seen["after"] = ctx.stage_progress
    assert seen["after"] is None


def test_no_progress_callback_still_runs():
    # 无 progress_callback 时 stage_progress 为 None，stage 内部需容忍
    class TolrantStage:
        def run(self, ctx):
            cb = getattr(ctx, "stage_progress", None)
            if cb:
                cb("不应出现")

    runner = PipelineRunner(stages=[("S1", TolrantStage())])
    runner.run(_make_ctx())  # 不传 callback，不应抛错


# ---------- GenerateStage 打点 ----------

class FakeCodex:
    """记录调用、模拟生图结果。"""
    def __init__(self, result=None, error=""):
        self.result = result   # Optional[Path]：成功时应传真实存在的临时文件
        self.last_error = error
        self.calls = []

    def generate(self, prompt, refs=None, timeout=None, on_wait=None):
        self.calls.append({"prompt": prompt, "refs": refs, "on_wait": on_wait})
        if on_wait:
            on_wait(5, "codex 正在画图…")   # 模拟一次心跳
        return self.result


def _gen_ctx(tmp_path):
    from sticker_engine.config.schema import Config, Paths
    paths = Paths(user_data=tmp_path, output_root=tmp_path / "e",
                  reference_lib=tmp_path / "ref", prefs_file=tmp_path / "p.yaml",
                  codex_exec="codex", codex_output_dir=tmp_path / "codex")
    config = Config.placeholder()
    config.paths = paths
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path / "e1"
    ctx.episode_dir.mkdir()
    ctx.selected_characters = ["星星布丁"]
    ctx.selected_bases = [tmp_path / "base1.png"]
    (tmp_path / "base1.png").write_bytes(b"fake")
    return ctx


def test_generate_stage_emits_detailed_progress(tmp_path):
    fake_img = tmp_path / "fake_grid.png"
    fake_img.write_bytes(b"png")
    codex = FakeCodex(result=fake_img)
    stage = GenerateStage(codex=codex, story_selector=None, keywords=None, seed=1)
    messages = []
    stage._emit = lambda ctx, msg: messages.append(msg)   # 直接截获打点

    ctx = _gen_ctx(tmp_path)
    stage.run(ctx)

    # 用户四要素齐备：做什么 / 输入 / 在等什么（心跳）/ 输出
    assert any("生成模式已选定" in m for m in messages)
    assert any("输入就绪" in m and "prompt" in m for m in messages)
    assert any("调用 codex" in m for m in messages)
    assert any("等待 codex 响应… 已等 5s" in m for m in messages)
    assert any("输出就绪" in m for m in messages)
    assert codex.calls[0]["on_wait"] is not None


def test_generate_stage_failure_shows_reason(tmp_path):
    codex = FakeCodex(result=None, error="codex 超时（300s）被终止。最后输出：（无输出）")
    stage = GenerateStage(codex=codex, story_selector=None, keywords=None, seed=1)
    messages = []
    stage._emit = lambda ctx, msg: messages.append(msg)

    ctx = _gen_ctx(tmp_path)
    stage.run(ctx)

    # 失败时必须把 codex 的具体原因带出来，不再是一句干巴巴的"生图失败"
    fail_msgs = [m for m in messages if "codex 生图失败" in m]
    assert fail_msgs and "超时" in fail_msgs[0]
    assert any(e.status == "FAIL" for e in ctx.production_log)
