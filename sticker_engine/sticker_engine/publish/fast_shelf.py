"""Verified platform reservation POST; one write, read-only reconciliation.

Contract captured from the current platform UI on 2026-10-14:
POST stikeroper?stikerid=...&opentime=YYYY-MM-DD HH:mm:ss&oper=open.
An HTTP/UI success is not a confirmed booking; require exact-ID status 6/7.
"""
import time
from datetime import datetime, timedelta, timezone

from .platform_data import ORIGIN, STATUS, SHELFABLE_CODES, detail_url, read_detail


class ShelfCancelled(RuntimeError):
    """Cancelled before sending the write."""


class ShelfNotEligible(RuntimeError):
    """Fresh exact-ID preflight no longer permits reservation."""


class ShelfOutcomeUnknown(RuntimeError):
    """A POST may have arrived; never replay it automatically."""


def reserve_today(page, item_id, *, should_stop=lambda: False,
                  before_write=lambda: None, now=None, sleep=time.sleep):
    started = time.monotonic()
    if should_stop():
        raise ShelfCancelled('已取消：未发送预约请求')
    detail = read_detail(page, item_id)
    if detail['Status'] not in SHELFABLE_CODES:
        raise ShelfNotEligible('当前不是审核通过或预约上架失败状态，请更新后重试')
    if should_stop():
        raise ShelfCancelled('已取消：未发送预约请求')
    current = now or datetime.now(timezone(timedelta(hours=8)))
    day = current.strftime('%Y-%m-%d')
    params = {'stikerid': item_id, 'opentime': current.strftime('%Y-%m-%d %H:%M:%S'), 'oper': 'open'}
    # Durable operation intent must be created before the ONLY write attempt.
    before_write()
    response = None
    response_ret = None
    request_error = None
    request_started = time.monotonic()
    try:
        response = page.context.request.post(
            ORIGIN + '/cgi-bin/mmemoticon-bin/stikeroper', params=params,
            headers={'Referer': detail_url(item_id), 'Origin': ORIGIN},
            timeout=15000, max_retries=0)
        body = response.json()
        if isinstance(body, dict):
            response_ret = body.get('base_resp', {}).get('ret')
        if not response.ok or response_ret != 0:
            request_error = '平台未返回有效预约成功回执'
    except Exception as exc:
        request_error = f'预约请求结果待核对：{type(exc).__name__}'
    finally:
        if response is not None:
            try:
                response.dispose()
            except Exception:
                pass
    request_seconds = time.monotonic() - request_started
    # Even a timeout/nonzero/malformed response may have accepted the write.
    # Reads are allowed after cancellation to settle the already-sent operation.
    last_error = request_error
    for attempt in range(3):
        try:
            observed = read_detail(page, item_id)
            open_time = str(observed.get('OpenTime') or '')
            if observed['Status'] in (6, 7) and open_time[:10] == day:
                return {'item_id': item_id, 'status': observed['Status'],
                        'status_text': STATUS[observed['Status']], 'open_time': open_time,
                        'response_ret': response_ret, 'request_seconds': round(request_seconds, 3),
                        'elapsed_seconds': round(time.monotonic() - started, 3), 'source': 'api'}
            last_error = '尚未确认今日预约结果，请核对平台状态后再操作'
        except Exception as exc:
            last_error = f'预约后核验失败：{type(exc).__name__}'
        if attempt < 2:
            sleep(0.5)
    raise ShelfOutcomeUnknown(last_error or '预约结果待核对，未重复请求')
