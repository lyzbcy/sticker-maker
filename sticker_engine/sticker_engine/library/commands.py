"""JSON-lines command adapters; transfer safety lives below the UI boundary."""
from pathlib import Path
import threading
import uuid

from .runtime import LibraryRuntime, account_key
from .catalog import ResourceLibrary
from .transfer import TransferManager

COMMANDS = ('status', 'bind_account', 'preview', 'execute', 'connect', 'import', 'reconcile',
            'refresh', 'resolve', 'delete', 'handoff', 'capture')
LOCK = threading.RLock()


def dispatch(cli, name, req_id, args):
    rt = LibraryRuntime(cli._ensure_engine().config.paths.user_data)
    manager = TransferManager(rt.local / 'transfers')
    if name == 'status':
        return rt.status()
    if name == 'bind_account':
        result = rt.bind(args.get('account'), bool(args.get('confirm_legacy')))
        cli._engine = None
        return result
    if name == 'connect':
        result = rt.connect(args.get('path') or '')
        cli._engine = None
        return result
    if name == 'refresh':
        return rt.refresh()
    if name == 'capture':
        return rt.capture(args.get('episode_dir') or '')
    if name == 'resolve':
        return rt.resolve(args.get('work_id'), args.get('revision_id'), args.get('action', 'choose'))
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
        rt.capture_all()
        status = rt.status()
        if (args.get('mode', 'backup') == 'migration' and args.get('cleanup')
                and status.get('settings_missing')):
            raise ValueError('共享设置仍有缺失资源，已阻止迁移清理；请先完成同步后重试')
        plan = manager.preview_library([str(rt.library.root)], args['target'],
                                       mode=args.get('mode', 'backup'),
                                       cleanup=bool(args.get('cleanup')))
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
            def progress(*items):
                cli._emit({'id': req_id, 'type': 'progress', 'stage': 'library',
                    'message': ' '.join(str(i) for i in items), 'percent': None})
            result = manager.execute(args.get('plan_id'), activate=activate,
                                     should_stop=stop.is_set, progress=progress)
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
            return dict(rt.status(), imported=summary)
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
        return dict(rt.status(), imported=result)
    raise ValueError('未知资源库操作')


def register(cli):
    def handler(name):
        def call(req_id, args):
            if not LOCK.acquire(blocking=False):
                cli._result(req_id, 'fail', errors=[{'message': '资源任务正在进行，请等待完成或先取消'}])
                return
            try:
                data = dispatch(cli, name, req_id, args)
                cli._result(req_id, 'ok', data=data)
            except Exception as exc:
                cli._result(req_id, 'fail', errors=[{'message': str(exc)}])
            finally:
                LOCK.release()
        return call
    for name in COMMANDS:
        cli.HANDLERS['library_' + name] = handler(name)
