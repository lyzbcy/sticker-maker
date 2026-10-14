"""Bounded, cancellable GET-only detail reader using a verified session.

Playwright sync objects never cross threads. Only an in-memory session snapshot
goes to a separate async request context; no browser, cookie file or credentials
are exported. Metadata writes remain on the caller's locked command thread.
"""
import asyncio
import queue
import threading
import time
from collections import deque
from urllib.parse import quote

from .platform_data import ORIGIN, PlatformDataError, _check


async def _download_details(client, ids, cancelled, emit, concurrency=3,
                            timeout_ms=12000):
    pending = deque(ids)
    throttle = {'limit': concurrency, 'until': 0.0}

    async def worker(index):
        while pending and not cancelled.is_set() and index < throttle['limit']:
            sid = pending.popleft()
            error = None
            for attempt in range(2):
                response = None
                try:
                    delay = throttle['until'] - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    if cancelled.is_set():
                        return
                    response = await client.get(
                        ORIGIN + '/cgi-bin/mmemoticon-bin/stikerpage?stikerid='
                        + quote(sid, safe='') + '&f=json', timeout=timeout_ms,
                        max_redirects=0)
                    if response.status in (429, 503):
                        throttle['limit'] = 1
                        try:
                            delay = min(10.0, max(1.0, float(response.headers.get('retry-after', '2'))))
                        except (ValueError, TypeError):
                            delay = 2.0
                        throttle['until'] = time.monotonic() + delay
                        emit(('notice', '平台请求繁忙：并发降为 1，等待后重试'))
                        raise PlatformDataError('平台请求繁忙，稍后重试')
                    if not response.ok:
                        raise PlatformDataError(f'平台详情读取失败（HTTP {response.status}）')
                    body = _check(await response.json())
                    if body.get('StikerID') != sid:
                        raise PlatformDataError('平台详情身份不一致')
                    emit(('result', (sid, body, None)))
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    error = (exc if isinstance(exc, PlatformDataError) else
                             PlatformDataError('详情请求超时或网络异常，下次同步将重试'))
                    if attempt:
                        emit(('result', (sid, None, error)))
                    elif throttle['until'] <= time.monotonic():
                        await asyncio.sleep(0.25)
                finally:
                    if response is not None:
                        await response.dispose()

    tasks = [asyncio.create_task(worker(i)) for i in range(concurrency)]

    async def watch_cancel():
        while not all(t.done() for t in tasks):
            if cancelled.is_set():
                for task in tasks:
                    task.cancel()
                return
            await asyncio.sleep(0.1)

    watcher = asyncio.create_task(watch_cancel())
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        # Cancellation preserves completed responses already handed to caller.
        if not cancelled.is_set():
            raise
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


def iter_details_parallel(page, ids, should_stop, say):
    if not ids or should_stop():
        return
    # The BrowserSession has already checked the resource-library account proof.
    state = page.context.storage_state()
    user_agent = page.evaluate('navigator.userAgent')
    messages = queue.Queue()
    cancelled = threading.Event()

    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            client = await pw.request.new_context(storage_state=state, user_agent=user_agent)
            try:
                await _download_details(client, ids, cancelled, messages.put)
            finally:
                await client.dispose()

    def entry():
        try:
            asyncio.run(run())
        except Exception:
            messages.put(('fatal', PlatformDataError('并发详情读取中断，已完成结果保留，下次补录剩余理由')))
        finally:
            messages.put(('done', None))

    thread = threading.Thread(target=entry, name='platform-detail-reader', daemon=True)
    thread.start()
    completed = set()
    say(f'接口补录 {len(ids)} 单驳回理由（最多 3 并发；可取消）')
    try:
        while True:
            if should_stop():
                cancelled.set()
            try:
                kind, value = messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if kind == 'done':
                break
            if kind == 'notice':
                say(value)
            elif kind == 'result':
                completed.add(value[0])
                yield value
            elif kind == 'fatal' and not cancelled.is_set():
                for sid in ids:
                    if sid not in completed:
                        yield sid, None, value
    finally:
        cancelled.set()
        thread.join(timeout=20)
        if thread.is_alive():
            raise PlatformDataError('网络进程正在退出，请稍后重试')
