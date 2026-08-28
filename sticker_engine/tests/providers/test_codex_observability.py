"""CodexProvider.generate 的可观测性改造测试：心跳 / 超时诊断 / 退出码诊断。

背景：generate 原来是 subprocess.run 阻塞最长 300s，期间零输出零日志，
失败时 stderr 被直接丢弃（用户看到的是"卡在开始 S1"然后无声失败）。
"""
import time
from unittest.mock import patch, MagicMock

from sticker_engine.providers.codex import CodexProvider


def _provider(tmp_path, timeout=6, heartbeat=0.5):
    p = CodexProvider(codex_exec="codex", output_dir=tmp_path, timeout=timeout)
    p.heartbeat_interval = heartbeat   # 测试时调快心跳
    return p


class _FakeProc:
    """可控的假 Popen：按脚本推进 poll/returncode。"""

    def __init__(self, script, stdout_text="", stderr_text=""):
        # script: list of (seconds_to_run, returncode)
        self._script = list(script)
        self._start = time.time()
        self.returncode = None
        # readline 必须返回 str（"" = EOF），供 iter(readline, "") 正常结束
        out_lines = iter([stdout_text] if stdout_text else [])
        err_lines = iter([stderr_text] if stderr_text else [])
        self.stdout = MagicMock()
        self.stderr = MagicMock()
        self.stdout.readline = lambda: next(out_lines, "")
        self.stderr.readline = lambda: next(err_lines, "")
        self.killed = False

    def poll(self):
        if self.killed:
            return self.returncode
        for dur, code in self._script:
            if time.time() - self._start >= dur:
                self.returncode = code
                return code
        return None

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        while self.poll() is None:
            time.sleep(0.05)
        return self.returncode


def test_generate_sends_heartbeats_while_waiting(tmp_path):
    """等待 codex 期间按间隔发心跳（elapsed + 输出尾部）。"""
    provider = _provider(tmp_path, timeout=30, heartbeat=0.3)
    proc = _FakeProc([(1.2, 0)], stdout_text="working...")
    provider.scan_latest_image = lambda: None
    with patch("sticker_engine.providers.codex.subprocess.Popen", return_value=proc):
        beats = []
        result = provider.generate(
            "prompt", on_wait=lambda elapsed, tail: beats.append((elapsed, tail)))
    assert result is None   # scan_latest_image 被 mock 成 None
    assert len(beats) >= 2  # 1.2s 等待期 + 0.3s 间隔至少两次心跳
    assert beats[0][0] >= 0


def test_generate_timeout_reports_last_output(tmp_path):
    """超时被终止时，last_error 必须带超时时长和 codex 的最后输出。"""
    provider = _provider(tmp_path, timeout=1)
    proc = _FakeProc([(999, 0)], stdout_text="still drawing grid...")
    provider.scan_latest_image = lambda: None
    with patch("sticker_engine.providers.codex.subprocess.Popen", return_value=proc):
        result = provider.generate("prompt")
    assert result is None
    assert "超时" in provider.last_error
    assert "still drawing grid" in provider.last_error


def test_generate_nonzero_exit_captures_stderr_tail(tmp_path):
    """非零退出码时，last_error 带退出码和 stderr 尾部（原来直接丢弃）。"""
    provider = _provider(tmp_path, timeout=30)
    proc = _FakeProc([(0.3, 1)], stdout_text="", stderr_text="Error: auth expired")
    with patch("sticker_engine.providers.codex.subprocess.Popen", return_value=proc):
        result = provider.generate("prompt")
    assert result is None
    assert "退出码 1" in provider.last_error
    assert "auth expired" in provider.last_error


def test_generate_success_clears_last_error(tmp_path):
    provider = _provider(tmp_path, timeout=30)
    proc = _FakeProc([(0.2, 0)], stdout_text="done")
    provider.last_error = "上次失败的残留"
    provider.scan_latest_image = lambda: tmp_path / "img.png"
    with patch("sticker_engine.providers.codex.subprocess.Popen", return_value=proc) as pop:
        result = provider.generate("prompt")
    assert result == tmp_path / "img.png"
    assert provider.last_error == ""
    # 回归守护：stdin 必须 DEVNULL —— 管道环境下 codex 会附加读取 stdin，不给会永久挂起
    assert pop.call_args.kwargs.get("stdin") is not None


def test_generate_command_order_and_flags(tmp_path):
    """命令构造的顺序守护：prompt 在 -i 之前 + --skip-git-repo-check。"""
    provider = _provider(tmp_path)
    cmd = provider.build_generate_command("画一只猫", [tmp_path / "a.png", tmp_path / "b.png"])
    assert cmd.index("画一只猫") < cmd.index("-i")
    assert "--skip-git-repo-check" in cmd
    assert cmd[-1].endswith("b.png")   # -i 参数在最后，不再吞 prompt
