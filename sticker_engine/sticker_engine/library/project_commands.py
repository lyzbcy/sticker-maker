"""Project commands share the existing generation/publishing mutation lock."""
import copy
from pathlib import Path

from .commands import LOCK, _LOCK_OWNER, _STATUS_CACHE, _progress_emitter
from .runtime import runtime_for_user_data, read_json
from ..project import atomic_json, read_project


def register(cli):
    def handler(name):
        def call(req_id, args):
            if not LOCK.acquire(blocking=False):
                cli._result(req_id, 'fail', errors=[{'message': '生成、投稿或资源任务正在进行，请完成后再操作工程'}])
                return
            _LOCK_OWNER.update(cmd='project_' + name, at=__import__('time').monotonic())
            try:
                rt = runtime_for_user_data(cli._ensure_engine().config.paths.user_data)
                from .project_transfer import (preview_migration, execute_migration,
                                               preview_slim, execute_slim, resume_cleanup,
                                               preview_old_copies, execute_old_copies,
                                               preview_normalize, execute_normalize)
                def progress(event):
                    cli._emit({'id':req_id,'type':'progress','stage':'library',
                               'percent':None,**event})
                if name == 'location_inspect':
                    from .locations import inspect_location
                    data = inspect_location(args.get('path'))
                elif name == 'location_connect':
                    from .locations import connect_location
                    data = connect_location(rt, args)
                elif name == 'migration_preview':
                    data = preview_migration(rt, args.get('target') or '', progress)
                elif name == 'migration_execute':
                    data = execute_migration(rt, args.get('plan_id'), progress)
                elif name == 'slim_preview':
                    data = preview_slim(rt, args.get('paths') or [], args.get('delete_sources') is True)
                elif name == 'slim_execute':
                    data = execute_slim(rt, args.get('plan_id'), args.get('confirm_discard_sources') is True)
                elif name == 'old_copies_preview':
                    data = preview_old_copies(rt, args.get('migration_id'), progress)
                elif name == 'old_copies_execute':
                    data = execute_old_copies(rt, args.get('plan_id'), progress)
                elif name == 'normalize_preview':
                    data = preview_normalize(rt)
                elif name == 'normalize_execute':
                    data = execute_normalize(rt, args.get('plan_id'))
                elif name == 'cleanup_resume':
                    path = Path(args.get('episode_dir') or '').resolve()
                    if path.parent != rt.output_root or not read_project(path):
                        raise ValueError('不属于当前工程目录')
                    resume_cleanup(path)
                    data = {'resumed': True}
                elif name == 'connect':
                    root = Path(args.get('path') or '').resolve()
                    collection = read_json(root / 'projects.json')
                    if collection.get('format') != 'sticker-maker-project-collection':
                        raise ValueError('请选择包含 projects.json 的规范工程根目录')
                    rt.require_account()
                    previous = copy.deepcopy(rt.state)
                    rt.state.update(storage_mode='projects', project_root=str(root),
                                    library_id=collection['library_id'], last_rows=[])
                    rt.save()
                    try:
                        new = runtime_for_user_data(rt.user_data)
                        data = new.status()
                        if data.get('offline'):
                            raise ValueError('工程目录不可用')
                    except Exception:
                        atomic_json(rt.config_file, previous)
                        raise
                else:
                    raise ValueError('未知工程命令')
                _STATUS_CACHE.update(at=0.0, data=None)
                cli._engine = None
                cli._result(req_id, 'ok', data=data)
            except Exception as exc:
                cli._result(req_id, 'fail', errors=[{'message': str(exc)}])
            finally:
                _LOCK_OWNER.update(cmd='', at=0.0)
                LOCK.release()
        return call
    for name in ('migration_preview', 'migration_execute', 'slim_preview', 'slim_execute',
                 'cleanup_resume', 'connect', 'old_copies_preview', 'old_copies_execute',
                 'normalize_preview', 'normalize_execute', 'location_inspect', 'location_connect'):
        cli.HANDLERS['project_' + name] = handler(name)
