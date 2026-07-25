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

    def _resolve_codex_path(self) -> Optional[str]:
        """多路径探测 codex 可执行文件。

        解决：CLI 没装、只有桌面 App（ChatGPT.app）的场景。
        GUI 应用的 PATH 不含 nvm/homebrew，shutil.which 单点探测会漏。
        """
        # 1) 用户显式指定的绝对路径（prefs 配置）
        if self.codex_exec and self.codex_exec != "codex" and Path(self.codex_exec).is_file():
            return self.codex_exec
        # 2) PATH 里能找到（终端启动 / 正常 CLI 安装）
        found = shutil.which("codex")
        if found:
            return found
        # 3) 已知安装位置 fallback
        home = Path.home()
        candidates = [
            # 桌面 App 的 CLI（ChatGPT.app 用户最常见，本机就是这种）
            home / ".codex" / "plugins" / ".plugin-appserver" / "codex",
            Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
            Path("/usr/local/bin/codex"),
            Path("/opt/homebrew/bin/codex"),
            home / ".local" / "bin" / "codex",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        # 4) nvm 下任意 node 版本的 codex（用户 node 版本会变，glob 找）
        nvm_root = home / ".nvm" / "versions" / "node"
        if nvm_root.exists():
            hits = sorted(nvm_root.glob("*/bin/codex"))
            if hits:
                return str(hits[-1])
        return None

    def check(self) -> CodexStatus:
        # 1) 多路径探测 codex 可执行文件（修复 GUI 应用 PATH 缺失 + 桌面 App 场景）
        resolved = self._resolve_codex_path()
        if resolved is None:
            return CodexStatus(
                installed=False, logged_in=False, image_ready=False,
                guidance_msg="未找到 codex。可通过软件的「一键安装」按钮安装，"
                             "或手动运行：curl -fsSL https://chatgpt.com/codex/install.sh | sh"
            )
        # 用绝对路径，后续 subprocess 不再依赖 PATH
        self.codex_exec = resolved
        # 2) 试跑 --version 确认可调用
        try:
            r = subprocess.run([self.codex_exec, "--version"], capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return CodexStatus(True, False, False, "codex 存在但 --version 失败，可能未登录。")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return CodexStatus(True, False, False, "codex 调用超时或失败。")
        # 3) 登录态：检查 ~/.codex/auth 或 ~/.codex/auth.json（两种都认）
        codex_dir = Path.home() / ".codex"
        logged = (codex_dir / "auth").exists() or (codex_dir / "auth.json").exists()
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
