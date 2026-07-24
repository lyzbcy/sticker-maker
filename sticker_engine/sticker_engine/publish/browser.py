"""playwright 浏览器会话封装：登录态持久化 + 通用动作。

用 storage_state 替代 puppeteer 的 .browser-data（playwright 原生支持，更干净）。
首次登录后存 storage_state.json，之后自动复用，跳过登录。
"""
import time
from pathlib import Path
from typing import Optional

from .config import PublishConfig
from . import selectors as S


class BrowserSession:
    """playwright 浏览器会话：管理登录态 + 通用页面动作。"""

    def __init__(self, config: PublishConfig, playwright=None):
        self.config = config
        self._playwright = playwright
        self._browser = None
        self._context = None
        self._owns_playwright = False   # 是否由本类启动 playwright（影响清理）

    def start(self, headless: bool = False):
        """启动浏览器。headless=False 便于调试（默认有头）。"""
        if self._playwright is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._owns_playwright = True
        self._browser = self._playwright.chromium.launch(headless=headless)
        # 复用 storage_state（若存在）
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

    # ---- 登录（24步之 1-2）----

    def ensure_login(self, page) -> bool:
        """确保已登录。返回是否需要重新登录（首次）。

        - 若已在主页（非登录页），直接返回 True
        - 若在登录页：切账号密码 tab → 填账号密码 → 点登录 → 存 storage_state
        """
        page.goto(S.HOME_URL, timeout=self.config.navigation_timeout_ms)
        time.sleep(2)
        # 判断是否在登录页
        if "login" not in page.url and self._is_logged_in(page):
            return True
        # 在登录页，走账号密码登录
        return self._do_password_login(page)

    def _is_logged_in(self, page) -> bool:
        """是否已登录（页面有"提交作品"按钮）。"""
        try:
            page.wait_for_selector(f'text="{S.SUBMIT_WORK_BUTTON_TEXT}"', timeout=5000)
            return True
        except Exception:
            return False

    def _do_password_login(self, page) -> bool:
        """账号密码登录（24步之 2）。"""
        # 1. 点"账号密码登录" tab
        page.click(f'text="{S.LOGIN_ACCOUNT_TAB_TEXT}"')
        time.sleep(1)
        # 2. 填账号密码（evaluate 直接设 value，比 type 稳）
        if self.config.account and self.config.password:
            page.evaluate("""([account, password]) => {
                const inputs = document.querySelectorAll('input');
                for (const input of inputs) {
                    if (input.type === 'text') {
                        input.value = account;
                        input.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                    if (input.type === 'password') {
                        input.value = password;
                        input.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                }
            }""", [self.config.account, self.config.password])
        # 3. 点登录
        page.click(f'button:has-text("{S.LOGIN_BUTTON_TEXT}")')
        time.sleep(3)
        # 4. 验证登录成功 + 存 storage_state
        if self._is_logged_in(page):
            self.save_state(page)
            return True
        return False
