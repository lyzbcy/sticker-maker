"""Read-only per-sticker daily report. Cache is private, scoped, and atomic."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import uuid
from urllib.parse import quote

from .platform_data import PlatformDataError, _check, read_json, read_detail, parse_list, LIST_URL, ORIGIN


def _count(value):
    if type(value) is int and 0 <= value <= 9007199254740991:
        return value
    if isinstance(value, str) and re.fullmatch(r'\d+', value) and int(value) <= 9007199254740991:
        return int(value)
    raise PlatformDataError('单图发送次数格式无效，已保留旧数据')


def parse_report(report, detail, item_id, album_name, account, captured_at=None):
    _check(report)
    _check(detail)
    if (not isinstance(report.get('Summary'), dict) or detail.get('StikerID') != item_id or report['Summary'].get('StikerID') != item_id
            or detail.get('Status') not in (7, 8, 9, 10)):
        raise PlatformDataError('单图报告身份或状态不一致')
    raw_items = detail.get('StikerJson', {}).get('Item')
    rows = report.get('Report')
    if not isinstance(raw_items, list) or not isinstance(rows, list) or not raw_items or not rows or max(len(raw_items), len(rows)) > 1000:
        raise PlatformDataError('平台暂无单图报告；不以空结果覆盖缓存')
    known = {}
    for item in raw_items:
        md5 = item.get('md5', '') if isinstance(item, dict) else ''
        if not isinstance(md5, str) or not re.fullmatch(r'[a-fA-F0-9]{32}', md5) or md5.lower() in known:
            raise PlatformDataError('平台表情图片身份缺失或重复')
        known[md5.lower()] = item
    captured_at = captured_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    capture_date = datetime.fromisoformat(captured_at).astimezone(timezone(timedelta(hours=8))).date().isoformat()
    records, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise PlatformDataError('单图报告格式已变化')
        md5, date = row.get('Md5'), row.get('DataTime')
        if (not isinstance(md5, str) or not re.fullmatch(r'[a-fA-F0-9]{32}', md5)
                or not isinstance(date, str) or not date.strip() or len(date) > 50):
            raise PlatformDataError('单图报告图片身份或统计日期缺失')
        md5, date = md5.lower(), date.strip()
        if (md5, date) in seen:
            raise PlatformDataError('单图报告包含重复记录')
        seen.add((md5, date))
        item = known.get(md5, {})
        meaning = item.get('meaning', {})
        units = meaning.get('Unit', []) if isinstance(meaning, dict) else []
        unit = next((x for x in units if isinstance(x, dict) and x.get('lang') == 'zh_cn'), {})
        label = str(unit.get('content') or '')[:200]
        records.append({'md5': md5, 'index': str(item.get('index') or ''), 'meaning': label,
                        'sends': _count(row.get('SendNum')), 'data_time': date, 'matched': md5 in known})
    summary = report['Summary']
    return {'schema': 1, 'account': account, 'item_id': item_id, 'album_name': str(album_name)[:300],
            'captured_at': captured_at, 'capture_date': capture_date, 'platform_status': detail['Status'],
            'source': '/cgi-bin/mmemoticon-bin/stikerreport', 'period_kind': 'platform_daily',
            'summary_date': str(summary.get('DataTime') or ''),
            'summary_sends': _count(summary['SendNum']) if summary.get('SendNum') is not None else None,
            'platform_item_count': len(known), 'matched_count': sum(r['matched'] for r in records),
            'items': records}


def _cache_path(user_data, account, item_id):
    digest = lambda s: hashlib.sha256(str(s).encode('utf-8')).hexdigest()
    return Path(user_data) / 'sticker_metrics' / digest(account) / (digest(item_id) + '.json')


def save_snapshot(user_data, account, snapshot):
    if snapshot['account'] != account:
        raise ValueError('单图缓存账号不一致')
    path = _cache_path(user_data, account, snapshot['item_id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_snapshots(user_data, account, works):
    albums, errors, seen = [], [], set()
    for work in works:
        sid = work.get('platform_item_id')
        if not sid or sid in seen:
            continue
        seen.add(sid)
        path = _cache_path(user_data, account, sid)
        if not path.exists():
            continue
        try:
            body = json.loads(path.read_text('utf-8'))
            if (body.get('schema') != 1 or body.get('account') != account or body.get('item_id') != sid
                    or body.get('period_kind') != 'platform_daily' or not isinstance(body.get('items'), list) or not body.get('items')
                    or not body.get('captured_at') or not body.get('capture_date')):
                raise ValueError('缓存身份或结构异常')
            for row in body['items']:
                _count(row['sends'])
                if not row.get('md5') or not row.get('data_time'):
                    raise ValueError('缓存记录不完整')
            albums.append(body)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({'item_id': sid, 'message': '单图缓存读取失败，原文件已保留'})
    return {'albums': albums, 'cache_errors': errors, 'cached_albums': len(albums), 'scope_albums': len(seen)}


def _account(engine):
    from ..library.hooks import runtime_for
    runtime = runtime_for(engine)
    if runtime:
        runtime.require_account()
        # Recheck the on-disk binding before every commit, not only this runtime object.
        device = Path(engine.config.paths.user_data) / 'resource_library/device.json'
        if device.exists():
            binding = json.loads(device.read_text('utf-8'))
            if binding.get('account_id') != runtime.account_id:
                raise ValueError('设备绑定已切换，请重新打开看板')
        return runtime.account_id, runtime
    return 'legacy-profile', None


def current_scope(engine):
    account, runtime = _account(engine)
    if runtime:
        return account, runtime.rows()
    from ..project import episode_directories
    from ..config.series import load_meta
    works = []
    for path in episode_directories(engine.config.paths.output_root):
        meta = load_meta(path)
        works.append({'platform_item_id': meta.platform_item_id, 'platform_status': meta.platform_status,
                      'album_name': meta.album_name, 'path': str(path)})
    return 'legacy-profile', works


def get_metrics(engine):
    account, works = current_scope(engine)
    return load_snapshots(engine.config.paths.user_data, account, works)


def sync_reports(page, works, user_data, account, *, item_ids=None, should_stop=lambda: False,
                 on_status=lambda message: None, guard=lambda: None, reader=read_json, detail_reader=read_detail):
    visible = {w['platform_item_id']: w for w in works if w.get('platform_item_id')}
    if item_ids is not None and (not isinstance(item_ids, list) or not all(isinstance(s, str) and s in visible for s in item_ids)):
        raise ValueError('请选择当前账号作品，不能读取其他平台ID')
    result = {'updated': 0, 'failures': [], 'cancelled': False, 'complete': True, 'metadata_committed': True}
    if should_stop():
        return {**result, 'cancelled': True, 'complete': False, 'total': 0}
    fresh = {r['StikerID']: r for r in parse_list(reader(page, LIST_URL), allow_unknown=True)}
    selected = list(dict.fromkeys(item_ids)) if item_ids is not None else [sid for sid in visible if fresh.get(sid, {}).get('Status') == 7]
    result['total'] = len(selected)
    failures = 0
    for index, sid in enumerate(selected, 1):
        if should_stop():
            result.update(cancelled=True, complete=False)
            break
        guard()
        try:
            if sid not in fresh or fresh[sid]['Status'] not in (7, 8, 9, 10):
                raise PlatformDataError('作品已不属于当前平台列表或没有可用统计状态')
            detail = detail_reader(page, sid)
            report = reader(page, ORIGIN + '/cgi-bin/mmemoticon-bin/stikerreport?stikerid=' + quote(sid, safe='') + '&f=json')
            snapshot = parse_report(report, detail, sid, fresh[sid]['Name'], account)
            guard()
            if should_stop():
                result.update(cancelled=True, complete=False)
                break
            save_snapshot(user_data, account, snapshot)
            result['updated'] += 1
            failures = 0
        except (PlatformDataError, OSError, ValueError) as exc:
            result['complete'] = False
            result['failures'].append({'item_id': sid, 'message': str(exc)})
            failures += 1
        on_status(f'单图报告 {index}/{len(selected)}：成功 {result["updated"]}，失败 {len(result["failures"])}（失败保留旧缓存）')
        if failures >= 3:
            on_status('连续3套读取失败，已停止本批；保留已完成与旧缓存，请核对登录或网络')
            break
    return result


def sync_metrics(engine, *, paginated=False, item_ids=None, on_status=lambda message: None, should_stop=lambda: False):
    from .browser import BrowserSession
    from .config import PublishConfig
    from playwright.sync_api import sync_playwright
    account, works = current_scope(engine)
    visible = {w.get('platform_item_id') for w in works}
    if item_ids is not None and (not isinstance(item_ids, list) or not all(isinstance(s, str) and s in visible for s in item_ids)):
        raise ValueError('请选择当前账号的作品')
    from ..library.hooks import runtime_for
    binding_file=Path(engine.config.paths.user_data)/'resource_library/device.json'
    def stamp():
        try:
            info=binding_file.stat()
            return info.st_mtime_ns,info.st_size
        except FileNotFoundError:
            return None
    binding_stamp=stamp()
    def guard():
        nonlocal binding_stamp
        runtime=runtime_for(engine)
        current=runtime.account_id if runtime else 'legacy-profile'
        changed=stamp()
        if current!=account or (binding_stamp is not None and changed is None):
            raise ValueError('账号已切换，停止单图统计读取')
        if changed!=binding_stamp:
            # A device snapshot can be several MB; reparse only when changed.
            if account=='legacy-profile' or _account(engine)[0]!=account:
                raise ValueError('设备绑定已变化，停止单图统计读取')
            binding_stamp=changed
    if should_stop():
        return {'cancelled': True, 'complete': False, 'updated': 0, 'total': 0, 'metadata_committed': True}
    with sync_playwright() as pw:
        session = BrowserSession(PublishConfig(), playwright=pw)
        try:
            on_status('正在复用平台登录，只读单图发送报告，不投稿、不改作品…')
            page = session.start()
            # Fresh owned list also verifies the reusable session; no silent unauthenticated scrape.
            verified = False
            if session.can_reuse_session:
                try:
                    read_json(page, LIST_URL)
                    verified = True
                except PlatformDataError:
                    pass
            if not verified:
                if not session.ensure_login(page, on_status=on_status, should_stop=should_stop):
                    if should_stop():
                        return {'cancelled': True, 'complete': False, 'updated': 0, 'total': 0, 'metadata_committed': True}
                    raise PlatformDataError('平台登录失败，请检查发布账号')
            result = sync_reports(page, works, engine.config.paths.user_data, account, item_ids=item_ids,
                                  should_stop=should_stop, on_status=on_status, guard=guard)
            guard()
            return result if paginated else {**get_metrics(engine), **result}
        finally:
            session.close()

def page_metrics(data, works, args):
    """Only a bounded page crosses IPC; resolve original bytes for visible rows only."""
    limit = 20
    try:
        offset = max(0, int(args.get('offset', 0)))
    except (TypeError, ValueError):
        offset = 0
    groups, rows = {}, []
    for album in data.get('albums', []):
        for item in album['items']:
            key = album['capture_date'] + ' | ' + item['data_time']
            groups[key] = {'key': key, 'label': '抓取 ' + album['capture_date'] + ' / 平台 ' + item['data_time']}
            rows.append({**item, 'item_id': album['item_id'], 'album_name': album['album_name'],
                         'captured_at': album['captured_at'], 'observation': key})
    groups = sorted(groups.values(), key=lambda g: g['key'], reverse=True)
    observation = args.get('observation') or (groups[0]['key'] if groups else '')
    query = str(args.get('query') or '').strip().casefold()[:200]
    selected = [r for r in rows if r['observation'] == observation
                and (not args.get('album_id') or r['item_id'] == args['album_id'])
                and (not query or query in (r.get('meaning', '') + ' ' + r['album_name']).casefold())]
    selected.sort(key=lambda r: ((r['sends'] if args.get('sort') == 'asc' else -r['sends']), r['album_name'], r['md5']))
    total_sends = sum(r['sends'] for r in selected)
    visible = [dict(r, image_path='', share=(r['sends']/total_sends if total_sends else 0)) for r in selected[offset:offset+limit]]
    paths = {w.get('platform_item_id'): w.get('path') for w in works
             if not w.get('offline') and w.get('resource_state') not in ('conflict', 'pending', 'placeholder')}
    images = {}
    for row in visible:
        sid = row['item_id']
        if sid not in images:
            images[sid] = {'hashes': {}, 'meanings': {}}
            root = paths.get(sid)
            if root:
                try:
                    for p in (Path(root) / '最终版').glob('*.png'):
                        images[sid]['hashes'][hashlib.md5(p.read_bytes()).hexdigest()] = str(p)
                        images[sid]['meanings'].setdefault(p.stem, []).append(str(p))
                except OSError:
                    pass
        row['image_path'] = images[sid]['hashes'].get(row['md5'], '')
        row['image_match'] = 'md5' if row['image_path'] else ''
        # Platform can re-encode PNG bytes. Offer the actual local original, explicitly
        # distinguished from a byte-verified platform image; never use fuzzy/suffix matching.
        candidates = images[sid]['meanings'].get(row.get('meaning'), [])
        if not row['image_path'] and row.get('matched') and len(candidates) == 1:
            row['image_path'] = candidates[0]
            row['image_match'] = 'local_meaning'
    return {k: v for k, v in data.items() if k != 'albums'} | {
        'rows': visible, 'groups': groups, 'observation': observation, 'total': len(selected),
        'offset': offset, 'limit': limit, 'summary': {'sends': total_sends,
        'nonzero': sum(r['sends'] > 0 for r in selected), 'zero': sum(r['sends'] == 0 for r in selected)}}


def get_metrics_page(engine, args):
    import time
    account, works = current_scope(engine)
    # mtime fingerprint detects external sync without reparsing every JSON at each click.
    stamps = []
    for w in works:
        sid = w.get('platform_item_id')
        if sid:
            p = _cache_path(engine.config.paths.user_data, account, sid)
            try:
                s = p.stat(); stamps.append((sid, s.st_mtime_ns, s.st_size))
            except OSError:
                stamps.append((sid, None, None))
    key = (account, str(engine.config.paths.user_data), tuple(stamps))
    cached = getattr(engine, '_metrics_page_cache', None)
    if not cached or cached[0] != key:
        cached = (key, load_snapshots(engine.config.paths.user_data, account, works))
        engine._metrics_page_cache = cached
    return page_metrics(cached[1], works, args)
