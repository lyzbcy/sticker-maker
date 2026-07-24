import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CodexStatus:
    installed: bool
    logged_in: bool
    image_ready: bool
    guidance_msg: str = ""


class CodexProvider:
    """
    封装 codex CLI 调用：检测 / 生图 / 捞图 / 生成 base。
    外部依赖：用户自备 codex（决策 A1）。
    """

    def __init__(self, codex_exec: str = "codex", output_dir: Optional[Path] = None,
                 timeout: int = 300):
        self.codex_exec = codex_exec
        self.output_dir = Path(output_dir) if output_dir else Path.home() / ".codex" / "generated_images"
        self.timeout = timeout

    def check(self) -> CodexStatus:
        # 1) 可执行文件在不在 PATH
        if shutil.which(self.codex_exec) is None:
            return CodexStatus(
                installed=False, logged_in=False, image_ready=False,
                guidance_msg=f"未找到 codex 可执行文件（'{self.codex_exec}'）。"
                             "请安装 codex CLI 并确保它在 PATH 中。"
            )
        # 2) 试跑 --version 确认可调用
        try:
            r = subprocess.run([self.codex_exec, "--version"], capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return CodexStatus(True, False, False, "codex 存在但 --version 失败，可能未登录。")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return CodexStatus(True, False, False, "codex 调用超时或失败。")
        # 3) 登录态：检查 ~/.codex/auth（启发式，不保证精确）
        auth = Path.home() / ".codex" / "auth"
        logged = auth.exists()
        return CodexStatus(
            installed=True, logged_in=logged, image_ready=logged,
            guidance_msg="" if logged else "codex 已安装但未检测到登录态，请先 `codex login`。"
        )

    def build_generate_command(self, prompt: str, refs: list) -> list:
        """构建 codex exec 命令。返回参数数组（安全，不经 shell）。"""
        cmd = [self.codex_exec, "exec", "--enable", "image_generation", "--sandbox", "read-only"]
        for r in refs:
            cmd += ["-i", str(r)]
        cmd.append(prompt)
        return cmd

    def generate(self, prompt: str, refs: list = None, timeout: int = None) -> Optional[Path]:
        """调用 codex 生图，返回最新生成图的路径。失败返回 None。"""
        refs = refs or []
        cmd = self.build_generate_command(prompt, refs)
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=timeout or self.timeout, check=False)
        except subprocess.TimeoutExpired:
            return None
        return self.scan_latest_image()

    def generate_base_image(self, prompt: str, timeout: int = None) -> Optional[Path]:
        """决策 J1：生成新 base 图（无参考图）。"""
        return self.generate(prompt, refs=[], timeout=timeout)

    def exec_text(self, prompt: str, refs: list = None, timeout: int = None) -> str:
        """决策 K：用 codex exec 跑文本任务（识图命名/介绍文案），返回 stdout 文本。

        与 generate() 的关键差异：
        - 不加 ``--enable image_generation``（生图专用）；纯 ``codex exec``。
        - 不扫图目录，而是捕获 ``subprocess.run(...).stdout`` 返回。
        - refs 作为 ``-i`` 参考图传入（识图任务 codex 需要看图）。

        失败语义：非零退出 / 超时 / 文件缺失 一律返回空字符串 ``""``，
        不抛异常（调用方据空串降级，保持管线不崩）。
        """
        refs = refs or []
        # 文本任务：普通 codex exec，不带 image_generation flag
        cmd = [self.codex_exec, "exec"]
        for r in refs:
            cmd += ["-i", str(r)]
        cmd.append(prompt)
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout or self.timeout, check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return ""
        if r.returncode != 0:
            return ""
        return r.stdout or ""

    def scan_latest_image(self) -> Optional[Path]:
        """扫描 output_dir 下所有 session 的 png，返回最新的。"""
        if not self.output_dir.exists():
            return None
        latest, latest_mtime = None, 0.0
        for session in self.output_dir.iterdir():
            if not session.is_dir():
                continue
            for f in session.iterdir():
                if f.suffix.lower() == ".png" and f.stat().st_mtime > latest_mtime:
                    latest, latest_mtime = f, f.stat().st_mtime
        return latest
