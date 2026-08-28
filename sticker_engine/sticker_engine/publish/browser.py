"""playwright 浏览器会话封装：登录态持久化 + 通用动作。

登录策略（用户需求：不用扫码——登录态半天就失效；用账号密码自动登录，
凭据保存在系统凭据库 keyring，见 credentials.py）：
1. storage_state 缓存有效 → 直接进（省一次登录）；
2. 失效 → 自动账号密码登录（超时页「重新登录」→ 切「账号密码登录」tab →
   填入凭据 → 勾「记住账号」→ 点「登录」→ 验证）；
3. 未配置凭据 → 返回明确指引（去设置里填账号密码），不再等待扫码。
首次登录成功后存 storage_state，仅作为短期加速缓存。
"""
import time
from pathlib import Path
from typing import Optional

from . import selectors as S
from .config import PublishConfig


class BrowserSession:
    """playwright 浏览器会话：管理登录态 + 通用页面动作。"""

    def __init__(self, config: PublishConfig, playwright=None):
        self.config = config
        self._playwright = playwright
        self._browser = None
        self._context = None
        self._owns_playwright = False   # 是否由本类启动 playwright（影响清理）
        self.last_login_error = ""      # 登录失败原因（人类可读，供上层展示）

    def start(self, headless: bool = False):
        """启动浏览器。headless=False 便于调试（默认有头）。

        --remote-debugging-port：开 CDP 监测口（prompt「网页回归测试」——
        发布期间允许监测 Agent（kimi bridge / CDP）连上浏览器实时盯每一步
        表单填写，出调试报告）。不占用常见端口，仅本机可连。
        """
        if self._playwright is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._owns_playwright = True
        launch_args = ["--remote-debugging-port=9223"]
        self._browser = self._playwright.chromium.launch(
            headless=headless, args=launch_args)
        # 复用 storage_state（若存在）——仅作加速缓存，失效自动转密码登录
        storage = self.config.storage_state
        if storage.exists():
            self._context = self._browser.new_context(storage_state=str(storage))
        else:
            self._context = self._browser.new_context()
        self._context.set_default_timeout(self.config.action_timeout_ms)
        return self._context.new_page()

    def save_state(self, page) -> None:
        """保存当前 context 的登录态到 storage_state。"""
        self.config.storage_state.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=str(self.config.storage_state))

    def close(self) -> None:
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._owns_playwright and self._playwright:
            self._playwright.stop()
            self._playwright = None

    # ---- 登录 ----

    def ensure_login(self, page, on_status=None) -> bool:
        """确保已登录（账号密码自动登录，storage_state 只作加速缓存）。

        on_status(message)：登录过程上报（供进度直播）。
        """
        self.last_login_error = ""
        page.goto(S.HOME_URL, timeout=self.config.navigation_timeout_ms)
        time.sleep(2)
        if self._is_logged_in(page):
            return True

        # storage_state 失效 → 账号密码自动登录
        account, password = self._load_credentials()
        if account and password:
            if on_status:
                on_status("登录态已过期，正在用保存的账号密码自动登录…")
            if self._do_password_login(page, account, password):
                return True
            if not self.last_login_error:
                self.last_login_error = (
                    "账号密码登录失败：请到 设置 → 发布账号 检查账号密码，"
                    "或账号是否被限制登录。")
            return False

        # 未配置凭据：明确指引（不再等待扫码）
        self.last_login_error = (
            "未配置发布账号密码。请到 设置 → 发布账号 填写微信表情开放平台的"
            "账号（邮箱）和密码（安全保存在系统凭据库，不会上传）。")
        return False

    def _load_credentials(self):
        """凭据来源：keyring（优先，用户在设置里填的）→ 旧 .env 机制兼容。"""
        from .credentials import load_credentials
        account, password = load_credentials()
        if account and password:
            return account, password
        return self.config.account, self.config.password

    def _is_logged_in(self, page) -> bool:
        """是否已登录（页面有"提交作品"按钮）。"""
        try:
            page.wait_for_selector(f'text="{S.SUBMIT_WORK_BUTTON_TEXT}"', timeout=5000)
            return True
        except Exception:
            return False

    def _do_password_login(self, page, account: str, password: str) -> bool:
        """账号密码自动登录（基于 2026-08 实测页面结构）。

        流程：超时页「重新登录」→ 切「账号密码登录」tab → 填账号
        （placeholder=输入账号 (邮箱地址)）/ 密码（placeholder=输入密码）→
        勾「记住账号」→ 点「登录」→ 验证 → 存 storage_state。
        """
        # 0) 超时页上有「重新登录」按钮，先进登录页
        try:
            relogin = page.query_selector('button:has-text("重新登录")')
            if relogin:
                relogin.click()
                time.sleep(2)
        except Exception:
            pass

        # 1) 切到「账号密码登录」tab（默认可能是扫码）
        try:
            tab = page.query_selector('span:has-text("账号密码登录")')
            if tab:
                tab.click()
                time.sleep(1.5)
        except Exception:
            pass   # 可能已在账号密码面板

        # 2) 填账号密码（placeholder 定位 + 派发事件）
        filled = page.evaluate("""([account, password]) => {
          let okAccount = false, okPassword = false;
          for (const input of document.querySelectorAll('input')) {
            if (input.type === 'text' && input.placeholder.includes('输入账号')) {
              input.value = account;
              input.dispatchEvent(new Event('input', {bubbles: true}));
              okAccount = true;
            }
            if (input.type === 'password' && input.placeholder.includes('输入密码')) {
              input.value = password;
              input.dispatchEvent(new Event('input', {bubbles: true}));
              okPassword = true;
            }
          }
          return okAccount && okPassword;
        }""", [account, password])
        if not filled:
            self.last_login_error = "登录页上找不到账号/密码输入框（页面可能改版）"
            return False

        # 3) 勾「记住账号」（尽量延长登录态寿命）
        try:
            remember = page.query_selector('input[type="checkbox"]')
            if remember and not remember.is_checked():
                remember.click()
        except Exception:
            pass

        # 4) 点「登录」（取文案恰为「登录」的可见按钮，避开「重新登录」）
        try:
            clicked = page.evaluate("""() => {
              for (const btn of document.querySelectorAll('button')) {
                const t = (btn.innerText || '').trim();
                if (t === '登录' && btn.offsetParent) { btn.click(); return true; }
              }
              return false;
            }""")
            if not clicked:
                page.click('button:has-text("登录")', timeout=5000)
        except Exception:
            pass
        time.sleep(4)

        # 5) 验证 + 存 storage_state（加速下次）
        if self._is_logged_in(page):
            self.save_state(page)
            return True
        return False
