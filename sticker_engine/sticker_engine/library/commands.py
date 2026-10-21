"""JSON-lines command adapters; transfer safety lives below the UI boundary."""
from pathlib import Path
import threading
import uuid

from .runtime import LibraryRuntime, account_key, runtime_for_user_data
from .catalog import ResourceLibrary
from .transfer import TransferManager

COMMANDS = ('status', 'bind_account', 'preview', 'execute', 'connect', 'import', 'reconcile',
            'refresh', 'resolve', 'delete', 'handoff', 'capture', 'repair_conflicts', 'cleanup_failed', 'materialize', 'repair_settings')
LOCK = threading.RLock()
# 当前持锁任务（hooks.invoke 与本文件 register 共用一把 LOCK，两侧都维护）：
# 拒绝消息据此告诉用户"谁在跑、跑了多久"，而不是一句无主语的"请等待"
_LOCK_OWNER = {'cmd': '', 'at': 0.0}
_TASK_LABELS = {
    'run': '生成表情', 'run_batch': '批量生成', 'publish_episode': '提交作品',
    'fix_and_republish': '整改重发', 'shelf_passed': '上架', 'sync_platform_status': '一键更新',
    'library_preview': '生成迁移预览', 'library_execute': '执行迁移/复制',
    'library_refresh': '刷新资源库', 'library_handoff': '准备切换电脑',
    'library_import': '复制导入', 'library_connect': '连接资源库',
}


def _lock_wait_message(default='资源任务'):
    import time as _time
    held = _time.monotonic() - _LOCK_OWNER['at'] if _LOCK_OWNER['at'] else 0.0
    owner = _TASK_LABELS.get(_LOCK_OWNER['cmd']) or _LOCK_OWNER['cmd'] or default
    return f'「{owner}」正在进行（已 {held:.0f} 秒），完成后即可继续当前操作；详情见底部活动日志'
# status 结果短缓存：一次 status 全量扫库（12k 文件约 20s+ 持锁），UI 又
# 周期轮询——缓存内直接返回快照，把锁和 IO 让给用户主动触发的命令。
# 任何非 status 的 library 命令执行后立即失效（见 register）。
_STATUS_TTL = 20.0
_STATUS_CACHE = {'at': 0.0, 'data': None}


# run_batch 等长任务持锁期间置 True：其工作线程（流水线生成/发布线程）
# 豁免 LOCK 抢锁——RLock 重入是同线程语义，跨线程伙伴会被误拒
# （2026-09-09 流水线事故：批量 5 组在同一秒全部"资源任务正在进行"）
BATCH_LOCK_HELD = False


def batch_lock_held() -> bool:
    return BATCH_LOCK_HELD


def _cached_status(rt):
    import time as _time
    now = _time.monotonic()
    if _STATUS_CACHE['data'] is not None and now - _STATUS_CACHE['at'] < _STATUS_TTL:
        return _STATUS_CACHE['data']
    data = rt.status()
    _STATUS_CACHE.update(at=now, data=data)
    return data


def _progress_emitter(cli, req_id):
    """Build a progress callback that keeps the flat log message but also
    forwards structured counters (completed/total/scanned) to the UI."""
    def progress(*items):
        event = {'id': req_id, 'type': 'progress', 'stage': 'library',
                 'message': ' '.join(str(i) for i in items), 'percent': None}
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ('phase', 'entry', 'scanned', 'done'):
                if key in item:
                    event[key] = item[key]
            completed, total = item.get('completed'), item.get('total')
            if isinstance(completed, int) and isinstance(total, int) and total > 0:
                event['completed'] = completed
                event['total'] = total
                event['percent'] = round(completed * 100.0 / total, 1)
        cli._emit(event)
    return progress


def dispatch(cli, name, req_id, args):
    from .hooks import runtime_for
    engine = cli._ensure_engine()
    rt = runtime_for(engine) or runtime_for_user_data(engine.config.paths.user_data)
    if rt.state.get('storage_mode') == 'projects' and name in {
            'preview', 'execute', 'import', 'connect', 'repair_settings', 'repair_conflicts', 'cleanup_failed'}:
        raise ValueError('当前为规范工程模式：直接复制工程文件夹进行备份，或使用连接规范工程目录')
    manager = TransferManager(rt.local / 'transfers')
    if name == 'status':
        return _cached_status(rt)
    if name == 'bind_account':
        result = rt.bind(args.get('account'), bool(args.get('confirm_legacy')))
        cli._engine = None
        return result
    if name == 'connect':
        result = rt.connect(args.get('path') or '')
        cli._engine = None
        return result
    if name == 'refresh':
        previous = getattr(rt, '_progress_callback', None)
        def report(event):
            cli._emit({'id': req_id, 'type': 'progress', 'stage': 'library',
                       'percent': None, **event})
        rt._progress_callback = report
        try:
            return rt.refresh()
        finally:
            rt._progress_callback = previous
    if name == 'cleanup_failed':
        from .failed_drafts import cleanup
        result=cleanup(rt, bool(args.get('execute')))
        if args.get('execute'):
            cli._engine=None
        return result
    if name == 'repair_conflicts':
        from .reconciliation import propose, repair
        rt.require_account()
        if args.get('execute'):
            rt.capture_all()
        works = [w for w in rt.works() if w['state'] == 'conflict']
        report = {'preview': not bool(args.get('execute')), 'eligible': [], 'merged': [], 'unresolved': []}
        for index, work in enumerate(works):
            plan = propose(rt.library, work)
            if not plan['eligible']:
                report['unresolved'].append({'work_id': work['work_id'], 'reason': plan['reason']})
            elif args.get('execute'):
                result = repair(rt.library, rt.account_id, work['work_id'], plan['parents'])
                report['merged' if result['merged'] else 'unresolved'].append(result)
            else:
                report['eligible'].append({'work_id': work['work_id'], 'parents': plan['parents']})
            if index % 50 == 0:
                _progress_emitter(cli, req_id)({'completed': index+1, 'total': len(works)}, '检查观测/评分冲突')
        if args.get('execute'):
            rt.refresh(capture=False)
            cli._engine = None
        return report
    if name == 'capture':
        return rt.capture(args.get('episode_dir') or '')
    if name == 'resolve':
        return rt.resolve(args.get('work_id'), args.get('revision_id'), args.get('action', 'choose'),
                          expected_heads=args.get('expected_heads'))
    if name == 'materialize':
        return rt.materialize_chosen(args.get('work_id'), args.get('revision_id'))
    if name == 'repair_settings':
        from .settings import SharedSettings
        result = SharedSettings(rt).repair_equivalent_prefs(args.get('work_id'), args.get('expected_heads'))
        result['status'] = rt.refresh(capture=False)
        cli._engine = None
        return result
    if name == 'reconcile':
        from .operations import reconcile
        reconcile(rt, args.get('operation_id'), args.get('outcome'))
        return rt.status()
    if name == 'delete':
        return rt.delete(args.get('work_id'), args.get('action'))
    if name == 'handoff':
        rt.capture_all()
        return {'message': '本机作品已保存到资源库。请确认两台电脑的 Syncthing 均已完成同步，再在另一台电脑开始发布。'}
    if name == 'preview':
        rt.require_account()
        if not args.get('target'):
            raise ValueError('请选择目标目录')
        emit = _progress_emitter(cli, req_id)
        emit('正在保存本机作品快照…')
        rt.capture_all()
        emit('正在扫描资源库文件清单（文件多时需要几分钟，期间请勿关闭应用）…')
        status = rt.status()
        if (args.get('mode', 'backup') == 'migration' and args.get('cleanup')
                and status.get('settings_missing')):
            raise ValueError('共享设置仍有缺失资源，已阻止迁移清理；请先完成同步后重试')
        plan = manager.preview_library([str(rt.library.root)], args['target'],
                                       mode=args.get('mode', 'backup'),
                                       cleanup=bool(args.get('cleanup')),
                                       progress=emit)
        emit('扫描完成，正在汇总迁移清单…')
        blocked = []
        for work in rt.library.list_works():
            revision = work.get('revision') or {}
            for missing in revision.get('metadata', {}).get('missing_resources', []):
                blocked.append({'work_id': work['work_id'], 'logical_path': str(missing),
                                'reason': '原始资源缺失，请补齐后重新预览'})
        blocked.extend({'logical_path': str(item), 'reason': '共享设置资源缺失'}
                       for item in status.get('settings_missing', []))
        plan['blocked_resources'] = blocked
        plan['missing'].extend(blocked)
        if plan['mode'] == 'migration' and (status.get('conflicts') or status.get('settings_conflicts')):
            raise ValueError('请先处理作品或共享设置的版本冲突，再迁移资源库')
        plan['settings_missing'] = status.get('settings_missing', [])
        plan['settings_conflicts'] = status.get('settings_conflicts', [])
        from .maintenance import record_cache_plan
        record_cache_plan(rt, plan)
        manager._save_plan(plan)
        return plan
    if name == 'execute':
        status = rt.status()
        if status.get('offline'):
            raise ValueError('共享资源库当前不可用，已停止写入；请恢复同步目录后重试')
        plan = manager._load_plan(args.get('plan_id'))
        if plan.get('blocked_resources'):
            raise ValueError('导出清单仍有缺失资源，请补齐后重新预览')
        if plan.get('mode') == 'migration' and (
                status.get('settings_missing') or status.get('settings_conflicts') or status.get('conflicts')):
            raise ValueError('资源仍缺失或存在冲突，请处理后重新预览迁移')
        stop = threading.Event()
        cli._stop_events[req_id] = stop
        try:
            def activate(target):
                rt.connect(target)
                cli._engine = None
                check = cli._ensure_engine()
                if check.config.paths.output_root != rt.output_root:
                    raise ValueError('新资源库读取位置校验失败')
            result = manager.execute(args.get('plan_id'), activate=activate,
                                     should_stop=stop.is_set,
                                     progress=_progress_emitter(cli, req_id))
            if result.get('state') == 'completed':
                from .maintenance import cleanup_cache_plan
                cleanup = cleanup_cache_plan(rt, args['plan_id'])
                result['cache_cleaned'] = cleanup['cleaned']
                if cleanup['errors']:
                    result['state'] = 'cleanup_partial'
                    result.setdefault('errors', []).extend(cleanup['errors'])
                    saved = manager._load_plan(args['plan_id'])
                    saved['state'] = 'cleanup_partial'
                    saved['last_errors'] = list(cleanup['errors'])
                    manager._save_plan(saved)
            return result
        finally:
            cli._stop_events.pop(req_id, None)
    if name == 'import':
        rt.require_account()
        if not args.get('path'):
            raise ValueError('请选择导入目录')
        path = Path(args['path']).resolve()
        if (path / 'library.json').is_file():
            rt.capture_all()
            summary = rt.library.merge_from(ResourceLibrary(path))
            rt.refresh(capture=False)
            result = dict(rt.status(), imported=summary)
            cli._engine = None
            return result
        root = path / 'episodes' if (path / 'episodes').is_dir() else path
        from ..config.series import load_meta
        sources = []
        for p in sorted(root.glob('episode*')):
            if not p.is_dir() or p.is_symlink(): continue
            m = load_meta(p)
            if m.account_id and m.account_id != rt.account_id:
                raise ValueError('导入作品属于其他账号，请先切换到对应账号')
            m.account_id, m.account_label = rt.account_id, rt.account_label
            # Legacy imports lack a persisted work ID; derive a stable
            # content/metadata identity so retrying the same directory is
            # idempotent.  Normal generated drafts retain independent UUIDs.
            m.work_id = rt._identity(m, p, stable=True)
            metadata = m.to_dict(); metadata.update(kind='episode', legacy_name=p.name)
            extras = {}
            for field in ('cover_custom', 'banner_custom', 'icon_custom'):
                if metadata.get(field):
                    external = Path(metadata[field])
                    if not external.is_absolute(): external = p / external
                    logical = '_external/' + field + external.suffix.lower()
                    metadata[field] = logical; extras[logical] = str(external)
            sources.append({'path': str(p), 'account_id': rt.account_id,
                'work_id': m.work_id, 'metadata': metadata, 'extra_files': extras})
        if not sources:
            raise ValueError('所选目录不是资源库，也未找到旧版作品目录')
        plan = manager.preview(sources, rt.library.root)
        result = manager.execute(plan['plan_id'])
        rt.refresh(capture=False)
        result = dict(rt.status(), imported=result)
        cli._engine = None
        return result
    raise ValueError('未知资源库操作')


def register(cli):
    def handler(name):
        def call(req_id, args):
            # 短暂排队而非立即拒绝：秒级的 status 轮询与预览撞车时，
            # 用户手动触发的命令应等到锁释放继续执行；
            # 只有长任务（如全量刷新）持锁超过 3 秒才提示稍后重试
            if not LOCK.acquire(timeout=3):
                cli._result(req_id, 'fail', errors=[{'message': _lock_wait_message('资源任务')}])
                return
            _LOCK_OWNER.update(cmd='library_' + name, at=__import__('time').monotonic())
            try:
                data = dispatch(cli, name, req_id, args)
                if name != 'status':
                    # 写类命令改变了库/账号状态，status 快照立即失效
                    _STATUS_CACHE['at'] = 0.0
                cli._result(req_id, 'ok', data=data)
            except Exception as exc:
                cli._result(req_id, 'fail', errors=[{'message': str(exc)}])
            finally:
                _LOCK_OWNER.update(cmd='', at=0.0)
                LOCK.release()
        return call
    for name in COMMANDS:
        cli.HANDLERS['library_' + name] = handler(name)
