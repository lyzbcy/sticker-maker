import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


def _flatten_prompt(prompt: str) -> str:
    """把 prompt 压成单行（换行→空格）。

    2026-08-27 事故根因：Windows 下经 npm 的 codex.cmd（cmd.exe 包装）调用时，
    含换行的 prompt 参数会破坏参数解析——codex 把 -i 参考图全部静默丢弃
    （会话 input_image=0、无任何报错），模型看不到角色 base 图，凭空造出
    非 IP 角色或输出全黑废图。实测同一路径单行 prompt 100% 正常附加。
    模板无需换行（模型对单行同样敏感），统一拍平以绝后患。
    """
    return " ".join(str(prompt).split()) if prompt else prompt


def _install_guidance() -> str:
    """手动安装指引，按平台给可用命令。"""
    if sys.platform == "win32":
        return ("未找到 codex。可通过软件的「一键安装」按钮安装，"
                "或先安装 Node.js 22+（nodejs.org），再在命令行运行：npm i -g @openai/codex")
    return ("未找到 codex。可通过软件的「一键安装」按钮安装，"
            "或手动运行：curl -fsSL https://chatgpt.com/codex/install.sh | sh")


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
                 timeout: int = 600):
        self.codex_exec = codex_exec
        self.output_dir = Path(output_dir) if output_dir else Path.home() / ".codex" / "generated_images"
        self.timeout = timeout   # 4×4 网格 codex 会自我迭代多轮（初稿→修分隔线→重绘），300s 不够
        # 等待 codex 期间的心跳间隔（秒），测试时可调小
        self.heartbeat_interval = 5.0
        # 最近一次 generate 的失败原因（人类可读，供上层展示；成功时为空串）
        self.last_error = ""

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
        if sys.platform == "win32":
            candidates = [
                # npm 全局 bin（Windows 默认装到 %APPDATA%\npm）
                Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd",
                Path(os.environ.get("APPDATA", "")) / "npm" / "codex.ps1",
                # Node.js 默认安装位置（系统 PATH 可能没带上的场景）
                Path(os.environ.get("PROGRAMFILES", "")) / "nodejs" / "codex.cmd",
            ]
            for c in candidates:
                if c.is_file():
                    return str(c)
            return None
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
                guidance_msg=_install_guidance(),
            )
        # 用绝对路径，后续 subprocess 不再依赖 PATH
        self.codex_exec = resolved
        # 2) 试跑 --version 确认可调用
        try:
            r = subprocess.run([self.codex_exec, "--version"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15)
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
        """构建 codex exec 命令。返回参数数组（安全，不经 shell）。

        参数顺序是 codex 0.134+ (clap) 的硬性要求，错一个就挂：
        - prompt 必须放在 -i 之前：-i/--image 是多值参数，会贪婪吞掉其后的
          所有位置参数（原实现把 prompt 放最后，被当成第二个图片文件名，
          codex 转而读 stdin 并永远挂起 → 300s 超时零输出）。
        - --skip-git-repo-check：引擎的工作目录不在 git 仓库内，
          没有该 flag 时 codex 直接拒绝执行（Not inside a trusted directory）。
        """
        cmd = [self.codex_exec, "exec", "--skip-git-repo-check",
               "--enable", "image_generation", "--sandbox", "read-only"]
        cmd.append(_flatten_prompt(prompt))
        for r in refs:
            cmd += ["-i", str(r)]
        return cmd

    def _stage_refs_ascii(self, refs: list) -> list:
        """把参考图复制到纯 ASCII 临时路径后再传给 codex（2026-08-27 事故修复）。

        复盘：在 App（GUI 无控制台）环境下经 cmd.exe 包装调 codex 时，路径含
        中文（如 base_images\\捞鱼\\base2.png）的 -i 图片会被 codex 静默丢弃
        ——会话里 input_image=0、无任何报错，模型只能凭空造角色/输出废图；
        而纯 ASCII 路径的图片 100% 正常附加。终端环境虽能附加中文路径，但
        为统一行为、彻底规避编码类问题，一律暂存为 ASCII 路径再传。
        顺带剔除不存在的路径，不让 codex 白吞。
        """
        staged = []
        for i, r in enumerate(refs):
            p = Path(r)
            try:
                if not p.is_file():
                    continue
                s = str(p.resolve())
                if s.isascii():
                    staged.append(p)
                    continue
                base = None
                for cand in (Path(tempfile.gettempdir()), Path("C:/Temp"),
                             Path("C:/Windows/Temp")):
                    if str(cand).isascii():
                        base = cand / "sticker_refs" / uuid.uuid4().hex[:12]
                        break
                if base is None:
                    continue
                base.mkdir(parents=True, exist_ok=True)
                dst = base / f"ref{i}{p.suffix or '.png'}"
                shutil.copy2(p, dst)
                staged.append(dst)
            except Exception:
                continue
        return staged

    def generate(self, prompt: str, refs: list = None, timeout: int = None,
                 on_wait: Callable[[int, str], None] = None) -> Optional[Path]:
        """调用 codex 生图，返回最新生成图的路径。失败返回 None。

        - on_wait(elapsed_seconds, output_tail)：等待期间的心跳回调，
          每 ~5 秒一次，用于向上层报告"在等什么"（codex 静默期长，必须有心跳）。
        - 失败原因写入 self.last_error（超时/退出码/输出尾部/无产出图），
          供调用方展示给用户，不再静默吞掉。
        """
        import threading
        refs = self._stage_refs_ascii(refs or [])
        cmd = self.build_generate_command(prompt, refs)
        self.last_error = ""
        deadline_secs = timeout or self.timeout
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,   # 显式空 stdin：codex 在管道环境会附加读取 stdin，不给会挂住
                text=True, encoding="utf-8", errors="replace")
        except (FileNotFoundError, OSError) as e:
            self.last_error = f"无法启动 codex：{e}"
            return None

        # 后台线程持续泵取输出（避免 PIPE 缓冲区满导致死锁，也攒出"尾部"给心跳）
        chunks = {"out": [], "err": []}

        def _pump(stream, key):
            try:
                for line in iter(stream.readline, ""):
                    chunks[key].append(line)
            except Exception:
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        pump_out = threading.Thread(target=_pump, args=(proc.stdout, "out"), daemon=True)
        pump_err = threading.Thread(target=_pump, args=(proc.stderr, "err"), daemon=True)
        pump_out.start()
        pump_err.start()

        start = time.time()
        deadline = start + deadline_secs
        last_beat = 0.0
        while proc.poll() is None:
            time.sleep(0.5)
            now = time.time()
            if now >= deadline:
                proc.kill()
                proc.wait()
                tail = ("".join(chunks["out"]) + "".join(chunks["err"]))[-200:].strip()
                # 超时收割：codex 迭代期间可能已写出中间版图片，杀了进程也先扫一次，
                # 有图就宽容地用上（用户体验远好于直接判死）
                img = self.scan_latest_image()
                if img is not None:
                    self.last_error = (
                        f"codex 超时（{deadline_secs}s）被终止，但已收割到此前生成的图片。"
                        f"最后输出：{tail or '（无输出）'}")
                    return img
                self.last_error = (
                    f"codex 超时（{deadline_secs}s）被终止。"
                    f"最后输出：{tail or '（无输出）'}")
                return None
            # 每 heartbeat_interval 秒发一次心跳（elapsed 秒数 + codex 输出尾部）
            if on_wait is not None and now - last_beat >= self.heartbeat_interval:
                last_beat = now
                # codex 的进度信息可能在 stdout 或 stderr，都带上
                tail = ("".join(chunks["out"]) + "".join(chunks["err"]))[-200:].strip()
                try:
                    on_wait(int(now - start), tail)
                except Exception:
                    pass

        elapsed = int(time.time() - start)
        stdout = "".join(chunks["out"])
        stderr = "".join(chunks["err"])

        if proc.returncode != 0:
            err_tail = stderr.strip()[-300:] or stdout.strip()[-300:]
            self.last_error = (
                f"codex 退出码 {proc.returncode}（耗时 {elapsed}s）。"
                f"输出尾部：{err_tail or '（无输出）'}")
            return None

        img = self.scan_latest_image()
        if img is None:
            out_tail = stdout.strip()[-300:]
            self.last_error = (
                f"codex 正常退出（耗时 {elapsed}s）但没有产出新图。"
                f"输出尾部：{out_tail or '（无输出）'}")
        return img

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
        refs = self._stage_refs_ascii(refs or [])
        # 文本任务：普通 codex exec，不带 image_generation flag
        # 参数顺序同 build_generate_command：prompt 必须在 -i 之前（-i 是多值参数会吞掉它），
        # 且需要 --skip-git-repo-check（工作目录不在 git 仓库时 codex 拒绝执行）
        cmd = [self.codex_exec, "exec", "--skip-git-repo-check"]
        cmd.append(_flatten_prompt(prompt))
        for r in refs:
            cmd += ["-i", str(r)]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, timeout=timeout or self.timeout, check=False,
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
