"""Read the platform's own JSON responses using the existing browser session.

No credentials or cookies are exported. Unknown schemas fail closed; submission
and shelving continue to use the platform UI and its success confirmation.
"""
import json
import time
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from ..config.series import load_meta, save_meta

ORIGIN = 'https://sticker.weixin.qq.com'
LIST_URL = ORIGIN + '/cgi-bin/mmemoticon-bin/home?lang=zh_CN&f=json'
STATUS = {2: '待审核', 4: '未通过审核', 5: '审核通过', 7: '已上架', 8: '已下架'}
GROUPS = {'paneliconurl': '聊天页图标', 'bannerurl': '横幅',
          'storebannerurl': '横幅', 'storeiconurl': '封面',
          'stikername': '表情名称', 'stikerdesc': '表情介绍',
          'stikerjson': '表情图', 'begpic': '赞赏引导图', 'thankspic': '赞赏致谢图'}


class PlatformDataError(RuntimeError):
    pass


def _check(body):
    if not isinstance(body, dict) or body.get('base_resp', {}).get('ret') != 0:
        raise PlatformDataError('平台数据无效或登录已失效')
    return body


def read_json(page, url):
    for attempt in range(2):
        response = None
        try:
            response = page.context.request.get(url, timeout=15000)
            if not response.ok:
                raise PlatformDataError('平台读取请求失败')
            return _check(response.json())
        except Exception as exc:
            if attempt:
                raise PlatformDataError('平台读取失败，请检查登录或重试') from exc
        finally:
            if response is not None and hasattr(response, 'dispose'):
                response.dispose()


def parse_list(body):
    rows = _check(body).get('List')
    if not isinstance(rows, list):
        raise PlatformDataError('平台列表结构已变化')
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PlatformDataError('平台作品记录格式异常')
        sid, name = row.get('StikerID'), row.get('Name')
        if (not isinstance(sid, str) or not sid or sid in seen
                or not isinstance(name, str) or not name
                or type(row.get('Status')) is not int):
            raise PlatformDataError('平台作品身份重复或缺失')
        if row['Status'] not in STATUS:
            raise PlatformDataError('平台出现未知状态，需要页面方式核验')
        seen.add(sid)
    return rows


def read_detail(page, item_id):
    body = read_json(page, ORIGIN + '/cgi-bin/mmemoticon-bin/stikerpage?stikerid='
                     + quote(item_id, safe='') + '&f=json')
    if body.get('StikerID') != item_id or body.get('Status') not in STATUS:
        raise PlatformDataError('平台详情身份或状态不一致')
    return body


def detail_url(item_id):
    return (ORIGIN + '/cgi-bin/mmemoticonwebnode-bin/pages/stickerPage/setting?stikerid='
            + quote(item_id, safe=''))


def parse_reason(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise PlatformDataError('驳回理由格式已变化') from exc
    if not isinstance(raw, dict):
        raise PlatformDataError('驳回理由为空或格式已变化')
    parts = []
    for key, values in raw.items():
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise PlatformDataError('驳回理由格式已变化')
        values = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if values:
            parts.extend([GROUPS.get(key.lower(), key), *values])
    if not parts:
        raise PlatformDataError('本次未取得驳回理由')
    return '\n'.join(parts)


def ensure_history(meta):
    """Migrate an existing reason without inventing a historical review number."""
    if not meta.platform_review_cycle:
        meta.platform_review_cycle = uuid.uuid4().hex
        meta.platform_review_source = 'unknown'
    if meta.platform_reject_reason:
        record_reason(meta, meta.platform_reject_reason)


def new_cycle(meta, source):
    ensure_history(meta)
    meta.platform_review_cycle = uuid.uuid4().hex
    meta.platform_review_source = source
    if source in ('submitted', 'observed_pending'):
        meta.platform_review_round += 1
    meta.platform_reject_reason = ''
    meta.platform_reject_checked_cycle = ''


def record_reason(meta, reason):
    if not meta.platform_review_cycle:
        meta.platform_review_cycle = uuid.uuid4().hex
        meta.platform_review_source = 'unknown'
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    existing = next((h for h in meta.platform_review_history
                     if h.get('cycle') == meta.platform_review_cycle), None)
    if existing is None:
        existing = {'cycle': meta.platform_review_cycle,
                    'round': (meta.platform_review_round if meta.platform_review_source
                              in ('submitted', 'observed_pending') else None),
                    'source': meta.platform_review_source, 'first_seen_at': now}
        meta.platform_review_history.append(existing)
    existing.update(reason=reason, last_seen_at=now,
                    platform_date=meta.platform_modified_at,
                    item_id=meta.platform_item_id)
    meta.platform_reject_reason = reason


def _match_rows(rows, root, account_id=None):
    from .status import normalize_name
    locals_ = [(p, load_meta(p)) for p in sorted(Path(root).glob('episode*')) if p.is_dir()]
    if account_id:
        locals_ = [(p, m) for p, m in locals_ if m.account_id == account_id]
    counts = Counter(normalize_name(r['Name']) for r in rows)
    result, unmatched = [], []
    for row in rows:
        hits = [(p, m) for p, m in locals_ if m.platform_item_id == row['StikerID']]
        if not hits and counts[normalize_name(row['Name'])] == 1:
            hits = [(p, m) for p, m in locals_ if not m.platform_item_id
                    and normalize_name(m.album_name or p.name) == normalize_name(row['Name'])]
        if len(hits) != 1:
            unmatched.append({'name': row['Name'], 'status': STATUS[row['Status']],
                              'updated': row.get('ModifyTime', ''), 'item_id': row['StikerID']})
        else:
            result.append((row, hits[0][0]))
    return result, unmatched


def sync_page(page, root, on_status=None, fetch_reasons=True, force_reasons=False,
              should_stop=None):
    """Persist all list statuses first, then incrementally save each rejection."""
    say = on_status or (lambda msg: None)
    rows = parse_list(read_json(page, LIST_URL))  # only pre-write failures can trigger DOM fallback
    return sync_rows(page, root, rows, say, fetch_reasons, force_reasons,
                     should_stop=should_stop)


def sync_rows(page, root, rows, say, fetch_reasons=True, force_reasons=False,
              should_stop=None, account_id=None, placeholder_factory=None):
    stopped = should_stop or (lambda: False)
    matches, unmatched = _match_rows(rows, root, account_id)
    created = 0
    if account_id and placeholder_factory:
        missing_ids = {r['item_id'] for r in unmatched}
        for row in rows:
            if stopped():
                break
            if row['StikerID'] in missing_ids:
                path = placeholder_factory(row)
                matches.append((row, path))
                created += 1
                unmatched = [r for r in unmatched if r['item_id'] != row['StikerID']]
    result = {'matched': len(matches), 'updated': 0, 'pages': 1,
              'platform_total': len(rows), 'source': 'api', 'complete': True,
              'list_complete': True, 'unmatched_platform': unmatched,
              'reasons_fetched': 0, 'reasons_skipped': 0, 'reason_failures': [],
              'fresh_passed': [], 'created': created}
    queue = []
    cancelled_before_write = False
    for row, path in matches:
        if stopped():
            cancelled_before_write = True
            say(f'收到取消请求：已更新 {result["updated"]} 单状态，'
                f'剩余 {len(matches) - result["updated"]} 单未写入')
            result['cancelled'] = True
            result['complete'] = False
            result['list_complete'] = False
            break
        meta = load_meta(path)
        ensure_history(meta)
        state = STATUS[row['Status']]
        modified = str(row.get('ModifyTime') or '')
        if state == '待审核' and meta.platform_status != '待审核':
            new_cycle(meta, 'observed_pending')
        elif (state == '未通过审核' and meta.platform_status == '未通过审核'
              and meta.platform_modified_at and modified != meta.platform_modified_at):
            new_cycle(meta, 'date_changed')
        elif (state == '未通过审核' and meta.platform_status
              not in ('', '未通过审核', '待审核')):
            new_cycle(meta, 'unknown')
        meta.platform_item_id = row['StikerID']
        meta.platform_status = state
        meta.platform_modified_at = modified
        # These are the fields displayed by the management table, not cumulative totals.
        meta.platform_downloads = str(row.get('DownloadNum') or '-')
        meta.platform_sends = str(row.get('SendNum') or '-')
        meta.platform_tips = str(row.get('Rewards') or '-')
        meta.platform_updated_at = time.strftime('%Y-%m-%d %H:%M:%S')
        if state != '未通过审核':
            meta.platform_reject_reason = ''
        if state in ('已上架', '待审核', '审核通过', '已下架'):
            meta.published = True
        if state == '审核通过':
            result['fresh_passed'].append(str(path))
        if state == '未通过审核' and fetch_reasons:
            if (not force_reasons and meta.platform_reject_reason
                    and meta.platform_reject_checked_cycle == meta.platform_review_cycle):
                result['reasons_skipped'] += 1
            else:
                queue.append((path, row['StikerID'], meta.platform_review_cycle))
        save_meta(path, meta)
        result['updated'] += 1
    if not cancelled_before_write:
        say(f'已更新 {result["updated"]} 单状态（平台共 {len(rows)} 单）；需补录 {len(queue)} 单理由，跳过 {result["reasons_skipped"]} 单已录入理由')
    for i, (path, sid, cycle) in enumerate(queue, 1):
        if stopped():
            say(f'收到取消请求：已保留前 {result["reasons_fetched"]} 单理由，'
                f'剩余 {len(queue) - i + 1} 单未读取')
            result['cancelled'] = True
            result['complete'] = False
            break
        say(f'补录驳回理由 {i}/{len(queue)}：{load_meta(path).album_name}')
        try:
            detail = read_detail(page, sid)
            if detail['Status'] != 4:
                raise PlatformDataError('审核状态已变化，请重新更新列表')
            reason = parse_reason(detail.get('Reason'))
            meta = load_meta(path)
            if meta.platform_review_cycle != cycle or meta.platform_item_id != sid:
                raise PlatformDataError('作品已发生变更，请重新更新')
            record_reason(meta, reason)
            meta.platform_reject_checked_cycle = cycle
            save_meta(path, meta)
            result['reasons_fetched'] += 1
        except Exception as exc:
            result['complete'] = False
            result['reason_failures'].append({'name': load_meta(path).album_name,
                                               'message': str(exc)})
            say(f'理由读取失败，已保留状态：{load_meta(path).album_name}')
    return result
