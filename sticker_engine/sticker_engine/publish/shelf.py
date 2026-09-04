"""Shelf: 批量预约上架（7 步迁移自现有 shelf skill）。

扫描微信表情开放平台「审核通过」的专辑，从最后一页往前逐页处理，
点详情→上架→选今日→预约，保证先通过审核的先上架。
复用 BrowserSession 的登录态。
"""
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from .config import PublishConfig
from .browser import BrowserSession
from . import selectors as S


@dataclass
class ShelfResult:
    """单个专辑的上架结果。"""
    name: str
    status: str   # OK / FAIL / SKIP / UNKNOWN
    reason: str = ""


class Shelf:
    """批量预约上架。"""

    def __init__(self, config: PublishConfig, session: BrowserSession):
        self.config = config
        self.session = session

    def shelve_all(self, max_pages: int = 5, limit: Optional[int] = None,
                   dry_run: bool = False, headless: Optional[bool] = None) -> dict:
        """扫描审核通过的专辑并预约上架。

        - max_pages: 最大翻页数（从 min(max_pages, 总页数) 往前到第 1 页）
        - limit: 限制本次处理的总数（成功/失败都计数）
        - dry_run: 只点详情不点上架（验证用）
        返回 {summary, results}
        """
        page = self.session.start(headless=headless)
        results = []
        try:
            if not self.session.ensure_login(page):
                return {"summary": {"ok": 0, "fail": 0, "skip": 0, "unknown": 0},
                        "results": [], "error": "登录失败"}
            page.goto(S.HOME_URL, timeout=self.config.navigation_timeout_ms)
            time.sleep(2)
            total_pages = self._get_total_pages(page)
            start_page = min(max_pages, total_pages)
            processed = 0
            # 从最后一页往前到第 1 页（保证先通过的先上架）
            for p in range(start_page, 0, -1):
                if limit is not None and processed >= limit:
                    break
                self._goto_page(page, p)
                time.sleep(1)
                # 处理本页所有「审核通过」的行
                page_results = self._process_page(page, dry_run=dry_run,
                                                   remaining=(limit - processed) if limit is not None else None)
                results.extend(page_results)
                processed += len(page_results)
                # 自我审查：刷新本页确认无残留（仅本页有处理结果时——
                # 空页复查纯属再翻一遍页面，2026-09-03 提速砍掉）
                if page_results:
                    self._refresh_and_recheck(page, p, dry_run=dry_run)
            summary = self._summarize(results)
            return {"summary": summary, "results": results}
        except Exception as e:
            try:
                # /tmp 在 Windows 不存在，用系统临时目录
                page.screenshot(path=str(Path(tempfile.gettempdir()) / "_shelf_error.png"))
            except Exception:
                pass
            return {"summary": self._summarize(results), "results": results,
                    "error": f"{type(e).__name__}: {e}"}
        finally:
            self.session.close()

    def _get_total_pages(self, page) -> int:
        """总页数（分页标签的最后一个数字）。"""
        try:
            labels = page.query_selector_all(S.SHELF_PAGINATION_TOTAL)
            if len(labels) >= 2:
                return int(labels[-1].inner_text().strip())
            if labels:
                return int(labels[0].inner_text().strip())
        except Exception:
            pass
        return 1

    def _goto_page(self, page, n: int) -> None:
        """跳到第 n 页。"""
        try:
            page.fill(S.SHELF_PAGINATION_INPUT, str(n))
            page.press(S.SHELF_PAGINATION_INPUT, "Enter")
            # networkidle 在 SPA 常态 3-5s——domcontentloaded+固定等待够用
            try:
                page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:   # noqa: BLE001
                pass
            time.sleep(0.8)
        except Exception:
            # 回退：用「上一页」按钮
            try:
                for _ in range(n):
                    page.click(S.PAGINATION_PREV, timeout=2000)
                    page.wait_for_load_state("networkidle")
            except Exception:
                pass

    def _process_page(self, page, dry_run: bool, remaining=None) -> list:
        """处理本页所有「审核通过」的行。"""
        results = []
        rows = page.query_selector_all("tbody.table_body > tr.table_tr")
        for row in rows:
            if remaining is not None and remaining <= 0:
                break
            try:
                status_text = row.query_selector("span.emotion_status").inner_text().strip()
            except Exception:
                continue
            if status_text != S.SHELF_STATUS_PASS:
                continue   # 只处理审核通过
            name = self._get_row_name(row)
            if dry_run:
                results.append(ShelfResult(name=name, status="SKIP", reason="dry-run"))
                if remaining is not None:
                    remaining -= 1
                continue
            status, reason = self._shelve_one(page, row)
            results.append(ShelfResult(name=name, status=status, reason=reason))
            if remaining is not None:
                remaining -= 1
            time.sleep(1)
        return results

    def _get_row_name(self, row) -> str:
        try:
            return row.query_selector("td").inner_text().strip()
        except Exception:
            return "未知"

    def _shelve_one(self, page, row) -> tuple:
        """对一行执行上架 7 步。返回 (status, reason)。"""
        try:
            # 步骤2：点详情（单曲 a[href="javascript:;"]，区别于形象 ip/detail）
            detail = row.query_selector(f'a[href="javascript:;"]')
            if not detail:
                return ("SKIP", "无详情链接（可能已上架）")
            detail.click()
            # 2026-09-04：networkidle 在详情页常态等不到（轮询请求）→默认
            # 30s 超时，132/146/150 三单 33s 失败即此。domcontentloaded+固定等待
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:   # noqa: BLE001
                pass
            # 详情页 SPA 渲染 6-10s：直接等「上架」按钮出现（盲等 2.5s 时
            # 页面还在转圈 → 永远无按钮 → 65/64/92/148 四单 33s 失败即此）
            try:
                page.wait_for_selector(
                    f'button:has-text("{S.SHELF_BUTTON_TEXT}")', timeout=15000)
            except Exception:   # noqa: BLE001
                pass
            time.sleep(0.5)
            # 步骤4：点「上架」按钮
            # data-v-xxx 是构建期 hash，平台前端重编译即失效——先试通用定位
            shelf_btn = page.query_selector(f'button:has-text("{S.SHELF_BUTTON_TEXT}")')
            if not shelf_btn:
                # 回退：用文本定位
                try:
                    page.click(f'button:has-text("{S.SHELF_BUTTON_TEXT}")', timeout=3000)
                except Exception:
                    return ("SKIP", "无上架按钮（状态可能已变）")
            else:
                shelf_btn.click()
            time.sleep(1)
            # 步骤5：预约弹窗点「今日」（默认已选中，显式点保险）
            try:
                page.click(S.SHELF_TODAY_CELL, timeout=3000)
            except Exception:
                pass
            # 步骤6：点「预约」
            try:
                page.click(f'div.weui-desktop-dialog__ft button:has-text("{S.SHELF_CONFIRM_TEXT}")', timeout=3000)
            except Exception:   # noqa: BLE001
                # 2026-09-04：平台弹层从 dialog 改 popover 过一次（撤回确认框
                # 同款）——popover 结构兜底
                try:
                    page.click(f'button:visible:has-text("{S.SHELF_CONFIRM_TEXT}")', timeout=3000)
                except Exception:
                    return ("UNKNOWN", "未确认预约成功")
            time.sleep(2)
            # 步骤7：确认成功（弹窗消失 / 成功文案）
            if self._is_shelved_success(page):
                return ("OK", "")
            return ("UNKNOWN", "未确认成功")
        except Exception as e:
            return ("FAIL", f"{type(e).__name__}: {e}")
        finally:
            # 返回列表页
            try:
                page.go_back()
                # networkidle 在此页同样常态超时（30s/单的另一半）
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:   # noqa: BLE001
                    pass
                time.sleep(1.5)
            except Exception:
                page.goto(S.HOME_URL, timeout=self.config.navigation_timeout_ms)

    def _is_shelved_success(self, page) -> bool:
        """预约成功判定：弹窗消失 或 出现成功文案。"""
        try:
            body = page.inner_text("body")
            for keyword in ["已预约", "预约成功", "上架成功"]:
                if keyword in body:
                    return True
            # 弹窗消失
            dialog = page.query_selector("div.dialog_shelf")
            if dialog:
                style = dialog.get_attribute("style") or ""
                if "display: none" in style or "display:none" in style:
                    return True
            return False
        except Exception:
            return False

    def _refresh_and_recheck(self, page, page_num: int, dry_run: bool) -> None:
        """每页处理完刷新复查（自我审查，防残留）。"""
        try:
            self._goto_page(page, page_num)
            time.sleep(1)
            rows = page.query_selector_all("tbody.table_body > tr.table_tr")
            for row in rows:
                try:
                    status_text = row.query_selector("span.emotion_status").inner_text().strip()
                    if status_text == S.SHELF_STATUS_PASS and not dry_run:
                        # 残留：补处理
                        name = self._get_row_name(row)
                        self._shelve_one(page, row)
                except Exception:
                    continue
        except Exception:
            pass

    def _summarize(self, results: list) -> dict:
        summary = {"ok": 0, "fail": 0, "skip": 0, "unknown": 0}
        for r in results:
            key = r.status.lower()
            if key in summary:
                summary[key] += 1
        return summary
