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
# Verified against the platform's List renderer (26052800 home bundle), not
# EmojiList's different enum. One status=11 previously forced all 605 rows to DOM.
STATUS = {1: '已保存', 2: '待审核', 3: '审核中', 4: '未通过审核', 5: '审核通过',
          6: '已预约上架', 7: '已上架', 8: '已下架', 9: '强制下架',
          10: '预约上架失败', 11: '限制投稿'}
# Verified 2026-10-19: Status10's exact-ID detail still offers 上架.
# This permits a new explicit reservation, not re-submission or automatic replay.
SHELFABLE_CODES = frozenset((5, 10))
SHELFABLE_STATUSES = frozenset(STATUS[code] for code in SHELFABLE_CODES)
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


def parse_list(body, allow_unknown=False):
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
        if row['Status'] not in STATUS and not allow_unknown:
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


def _reason_strings(values):
    """从 Reason 值里提取字符串理由列表。

    已知形态：字符串；字符串列表；字典列表（2026-09-11 平台改版新增，
    如 emotion: [{"item":"1","failMsg":["图中含有边框线…"]}]——递归抽取
    其中的字符串值）。未知形态抛错交人工。
    """
    out = []
    for v in values:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for inner in v.values():
                if isinstance(inner, str):
                    out.append(inner)
                elif isinstance(inner, list):
                    out.extend(s for s in inner if isinstance(s, str))
        else:
            raise PlatformDataError('驳回理由格式已变化')
    return out


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
        if not isinstance(values, list):
            raise PlatformDataError('驳回理由格式已变化')
        values = list(dict.fromkeys(v.strip() for v in _reason_strings(values) if v.strip()))
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
    if meta.platform_reject_reason and not any(
            h.get('cycle') == meta.platform_review_cycle and h.get('reason') == meta.platform_reject_reason
            for h in meta.platform_review_history):
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
    from .status import normalize_name, episode_has_files
    from ..project import episode_directories
    locals_ = [(p, load_meta(p)) for p in episode_directories(root)]
    if account_id:
        locals_ = [(p, m) for p, m in locals_ if m.account_id == account_id]
    counts = Counter(normalize_name(r['Name']) for r in rows)
    # 2026-09-10 同步克隆行修复：library 模式下 item_id 匹配不到（或归一化
    # 兜底因同名 0 文件占位符歧义而失败）的平台行，先在「有文件的」本地
    # 作品里找专辑名完全相等的唯一真身兜底（懒建索引；多个同名=歧义不绑，
    # 宁可不匹配也不绑错；0 文件占位符不参与，否则占位符会抢走绑定，真身
    # 丢平台身份，又长出一行 0 张克隆）。仍无匹配才由 sync_rows 走
    # placeholder_factory。
    exact_index = None   # 懒建：album_name -> 唯一「有文件且未绑 ID」本地作品
    result, unmatched = [], []
    for row in rows:
        hits = [(p, m) for p, m in locals_ if m.platform_item_id == row['StikerID']]
        if len(hits) > 1:
            # 2026-09-12：同一作品常有多个投影目录（时间戳名 + work_id 名）
            # 且都带同一 platform_item_id——先按 work_id 去重（一个作品一个
            # 匹配）；若仍是多个不同 work 同 sid（真身 + 带绑定的壳兄弟），
            # 让「有文件的那个」胜出，0 文件壳/占位让位——两边都不唯一才
            # 是真歧义，交 unmatched 处理。
            _by_wid = {}
            for p, m in hits:
                _by_wid.setdefault(getattr(m, 'work_id', '') or str(p), (p, m))
            cand = list(_by_wid.values())
            if len(cand) > 1:
                with_files = [(p, m) for p, m in cand if episode_has_files(p)]
                if len(with_files) == 1:
                    cand = with_files
            if len(cand) == 1:
                hits = cand
        if not hits and counts[normalize_name(row['Name'])] == 1:
            hits = [(p, m) for p, m in locals_ if not m.platform_item_id
                    and normalize_name(m.album_name or p.name) == normalize_name(row['Name'])]
            if len(hits) != 1 and account_id:
                if exact_index is None:
                    grouped = {}
                    seen_works = set()
                    for p, m in locals_:
                        # 同一作品常有多个投影目录（时间戳名 + work_id 名），
                        # 不去重会把"唯一真身"误判成同名歧义 → 不绑定 →
                        # 同步给平台行建 0 文件壳（2026-09-11 85 个半成品根因）
                        wid = getattr(m, 'work_id', '') or str(p)
                        if wid in seen_works:
                            continue
                        seen_works.add(wid)
                        if not m.platform_item_id and m.album_name and episode_has_files(p):
                            grouped.setdefault(m.album_name, []).append((p, m))
                    exact_index = {n: h[0] for n, h in grouped.items() if len(h) == 1}
                exact = exact_index.get(row['Name'])
                hits = [exact] if exact else []
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
              should_stop=None, account_id=None, placeholder_factory=None,
              detail_reader=None, on_meta_saved=None):
    stopped = should_stop or (lambda: False)
    started = time.monotonic()
    total = len(rows)
    unknown = [{'item_id': r['StikerID'], 'name': r['Name'], 'status_code': r['Status']}
               for r in rows if r['Status'] not in STATUS]
    rows = [r for r in rows if r['Status'] in STATUS]
    if unknown:
        say(f'接口返回 {total} 弹，其中 {len(unknown)} 弹为未识别状态；'
            '保留这些作品原数据，其余作品继续快速同步（不转逐页翻页）')
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
              'platform_total': total, 'source': 'api', 'complete': not unknown,
              'list_complete': not unknown, 'unmatched_platform': unmatched,
              'unknown_statuses': unknown,
              'persistence_failures': [],
              'reasons_fetched': 0, 'reasons_skipped': 0, 'reason_failures': [],
              'fresh_passed': [], 'fresh_shelfable': [], 'created': created}
    queue = []

    def persist(path, meta):
        save_meta(path, meta)
        if on_meta_saved:
            try:
                on_meta_saved(path, meta)
            except (OSError, ValueError) as exc:
                result['complete'] = False
                result['list_complete'] = False
                result['persistence_failures'].append({'name': meta.album_name, 'message': str(exc)})
                say(f'状态已保留在本机，资源库待处理：{meta.album_name}（{exc}）')

    cancelled_before_write = False
    for row, path in matches:
        if stopped():
            cancelled_before_write = True
            say(f'收到取消请求：已更新 {result["updated"]} 弹状态，'
                f'剩余 {len(matches) - result["updated"]} 弹未写入')
            result['cancelled'] = True
            result['complete'] = False
            result['list_complete'] = False
            break
        meta = load_meta(path)
        ensure_history(meta)
        state = STATUS[row['Status']]
        modified = str(row.get('ModifyTime') or '')
        if state in ('待审核', '审核中') and meta.platform_status not in ('待审核', '审核中'):
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
        # 2026-09-10 平台改版修正：管理列表的 DownloadNum/SendNum 变成了
        # 近期值（实测 No.6：DownloadNum=2/SendNum=95），累计真值在
        # TotalDownloadNum/TotalSendNum（同单 168/4882）。用户口径是累计
        # 总量；无 Total 字段时回落旧字段（旧数据兼容）。
        meta.platform_downloads = str(row['TotalDownloadNum'] if row.get('TotalDownloadNum') is not None
                                      else row.get('DownloadNum', '-'))
        meta.platform_sends = str(row['TotalSendNum'] if row.get('TotalSendNum') is not None
                                  else row.get('SendNum', '-'))
        meta.platform_tips = str(row['Rewards'] if row.get('Rewards') is not None else '-')
        meta.platform_updated_at = time.strftime('%Y-%m-%d %H:%M:%S')
        if state != '未通过审核':
            meta.platform_reject_reason = ''
        if state in ('已上架', '待审核', '审核中', '审核通过', '已预约上架', '已下架', '预约上架失败'):
            meta.published = True
        if state == '审核通过':
            result['fresh_passed'].append(str(path))
        if row['Status'] in SHELFABLE_CODES:
            result['fresh_shelfable'].append(str(path))
        if state == '未通过审核' and fetch_reasons:
            if (not force_reasons and meta.platform_reject_reason
                    and meta.platform_reject_checked_cycle == meta.platform_review_cycle):
                result['reasons_skipped'] += 1
            else:
                queue.append((path, row['StikerID'], meta.platform_review_cycle))
        persist(path, meta)
        result['updated'] += 1
        if result['updated'] % 100 == 0:
            say(f'接口状态已写入 {result["updated"]}/{len(matches)} 弹')
    result['status_seconds'] = round(time.monotonic() - started, 3)
    result['reasons_total'] = len(queue)
    if not cancelled_before_write:
        say(f'已更新 {result["updated"]} 弹状态（平台共 {total} 弹，耗时 {result["status_seconds"]:.1f} 秒）；需补录 {len(queue)} 弹理由，跳过 {result["reasons_skipped"]} 弹已录入理由')

    def serial_details():
        for path, sid, cycle in queue:
            if stopped():
                break
            try:
                yield sid, read_detail(page, sid), None
            except Exception as exc:
                yield sid, None, exc

    by_id = {sid: (path, cycle) for path, sid, cycle in queue}
    detail_started = time.monotonic()
    details = (detail_reader(page, list(by_id), stopped, say)
               if detail_reader and queue and not stopped() else serial_details())
    for i, (sid, detail, error) in enumerate(details, 1):
        path, cycle = by_id[sid]
        try:
            if error:
                raise error
            if detail.get('StikerID') != sid:
                raise PlatformDataError('平台详情身份不一致')
            if detail['Status'] != 4:
                raise PlatformDataError('审核状态已变化，请重新更新列表')
            reason = parse_reason(detail.get('Reason'))
            meta = load_meta(path)
            if meta.platform_review_cycle != cycle or meta.platform_item_id != sid:
                raise PlatformDataError('作品已发生变更，请重新更新')
            record_reason(meta, reason)
            meta.platform_reject_checked_cycle = cycle
            persist(path, meta)
            result['reasons_fetched'] += 1
        except Exception as exc:
            result['complete'] = False
            result['reason_failures'].append({'name': load_meta(path).album_name,
                                               'message': str(exc)})
            say(f'理由读取失败，已保留状态：{load_meta(path).album_name}')
        say(f'补录驳回理由 {i}/{len(queue)}：成功 {result["reasons_fetched"]}，'
            f'失败 {len(result["reason_failures"])}，耗时 {time.monotonic()-detail_started:.1f} 秒')
    if stopped():
        result.update(cancelled=True, complete=False)
        say(f'收到取消请求：已保留 {result["reasons_fetched"]} 弹理由，剩余下次补录')
    result['reason_seconds'] = round(time.monotonic() - detail_started, 3)
    return result
