"""Serialize device mutations and adapt existing handlers without a shared lock."""
import time
from dataclasses import replace
from pathlib import Path

from .commands import LOCK, _LOCK_OWNER, _TASK_LABELS
from .runtime import LibraryRuntime, runtime_for_user_data
from .settings import settings_dir

MUTATIONS = {
    'run', 'run_batch', 'publish_episode', 'fix_and_republish', 'shelf_passed',
    'sync_platform_status', 'repolish_finals', 'update_episode_meta',
    'regen_intro', 'regen_assets', 'delete_episode', 'save_series',
    'save_prefs', 'generate_base', 'add_base', 'remove_base', 'replenish_refs',
    'save_prompt_set', 'delete_prompt_set', 'save_publish_credentials',
    'clear_publish_credentials',
}
# save_rating 移出 MUTATIONS（2026-09-12 用户实测两次丢分根因）：打分只写
# 本地 rating.json，与资源库无关——此前每次点星星都先跑 1~3 分钟的前置
# 快照同步（用户看到的"打开打分卡提示正在同步本地资源卡"），用户等不
# 及切走 → 400ms 防抖窗口 × 切页中断 → 分数无声丢失。直通即时保存。
# 读命令一律直通（2026-09-05 两轮事故根修）：
# ①首屏：load_prefs 读本地 yaml 却被锁内 40s 冷刷新拖住 → 前端超时踢向导
# ②启动窗口：list_episodes 等读命令在锁内跑冷刷新，期间用户点同步/生成
#   被"正在生成、同步或迁移资源"秒拒。读命令的数据源（runtime.rows()）
#   本来就是上次 refresh 的快照——读前刷新毫无必要，快照旧一点无碍
#   （作品状态只在 sync/publish 后才变，那些是写命令，写前会刷新）。
FAST_LOCAL = {'load_prefs', 'list_series', 'list_prompt_sets',
              'list_episodes', 'get_episode', 'list_all_stickers',
              'list_characters', 'get_income'}
RESOURCE_EDITS = {'publish_episode', 'fix_and_republish', 'repolish_finals',
                  'update_episode_meta', 'regen_intro', 'regen_assets', 'save_rating'}
PLATFORM = {'publish_episode', 'fix_and_republish', 'shelf_passed', 'sync_platform_status'}
# 长任务：执行分钟级且操作平台/数据，互相排斥（快速失败防并发平台操作）
LONG_TASKS = {'run', 'run_batch', 'publish_episode', 'fix_and_republish',
              'shelf_passed', 'sync_platform_status'}


def runtime_for(engine):
    config = getattr(engine, 'config', None)
    paths = getattr(config, 'paths', None)
    data = getattr(paths, 'user_data', None)
    if not isinstance(data, (str, Path)):
        return None
    # 2026-09-05 性能根修②：runtime 实例挂到 engine 单例复用——此前每条
    # 命令新建 LibraryRuntime，refresh 的 TTL 缓存随实例丢弃永不命中
    # （每条读命令都持全局锁跑 ~40s 全量轻快照扫描）。bind/connect 等
    # 账号变更命令会将 cli._engine 置空，缓存随引擎重建自然失效。
    rt = runtime_for_user_data(data)
    engine._library_runtime = rt
    return rt if rt.enabled else None


def reload_engine_config(engine, runtime):
    """Refresh an already-running API engine after shared settings apply.

    The CLI can discard its singleton and rebuild it.  Direct ``StickerEngine``
    callers keep the same object, so update its paths and Prefs in place.
    """
    if engine is None or runtime is None:
        return engine
    config = getattr(engine, 'config', None)
    current = getattr(config, 'paths', None)
    if config is None or current is None:
        return engine
    assets_root = settings_dir(runtime)
    output_root = runtime.output_root
    try:
        updated = replace(current, output_root=output_root,
                          reference_lib=assets_root / 'reference_library',
                          prefs_file=assets_root / 'prefs.yaml',
                          assets_root=assets_root)
    except TypeError:
        updated = current
        updated.output_root = output_root
        updated.reference_lib = assets_root / 'reference_library'
        updated.prefs_file = assets_root / 'prefs.yaml'
        if hasattr(updated, 'assets_root'):
            updated.assets_root = assets_root
    config.paths = updated
    try:
        from ..config.loader import load_prefs_from_file
        prefs = load_prefs_from_file(updated.prefs_file)
        if prefs is not None:
            config.prefs = prefs
            raw = prefs.reference_lib_path
            if raw:
                reference = Path(raw).expanduser()
                if not reference.is_absolute():
                    reference = assets_root / reference
                config.paths.reference_lib = reference
    except (OSError, ValueError):
        # Keep the prior in-memory settings if a local file is incomplete;
        # SharedSettings.apply reports the issue through runtime status.
        pass
    # A long-lived API engine may already have loaded character/base paths
    # from the previous settings workspace.  Rebuild those maps after the
    # workspace switch so direct callers do not keep stale absolute paths.
    try:
        config.characters = {}
        ensure_characters = getattr(engine, '_ensure_characters', None)
        if callable(ensure_characters):
            ensure_characters()
        from .. import cli as _cli
        sync_bases = getattr(_cli, '_sync_custom_bases', None)
        if callable(sync_bases):
            sync_bases(engine)
    except (OSError, ValueError, TypeError):
        # Configuration reload remains usable when optional custom assets are
        # incomplete; the next refresh will expose the missing diagnostics.
        pass
    return engine


def invoke(cli, req_id, cmd, args, handler):
    if cmd == 'save_rating':
        # Legacy ratings retain their immediate-save behavior. Direct projects
        # serialize the small rating write and update just this file's manifest.
        runtime = runtime_for(cli._ensure_engine())
        if runtime and getattr(runtime, 'state', {}).get('storage_mode') == 'projects':
            from ..project import project_lock
            with project_lock(Path(args.get('episode_dir') or '')):
                result = handler(req_id, args)
                runtime.capture(Path(args.get('episode_dir') or ''))
                return result
        return handler(req_id, args)
    if cmd not in MUTATIONS:
        return handler(req_id, args)
    # 2026-09-05 评审根修：CLI 多线程分发 + 非阻塞抢锁 → 前端启动时并发
    # 请求只有 1 个成功、其余全部被"正在生成、同步或迁移资源"拒绝（用户
    # 看到的"不正常"即此）。改为分级：读/轻写排队等锁（毫秒级，安全）；
    # 长任务保持快速失败（防发布中并发发布/同步）。
    blocking = cmd not in LONG_TASKS
    if not LOCK.acquire(blocking=blocking):
        held = time.monotonic() - _LOCK_OWNER['at'] if _LOCK_OWNER['at'] else 0.0
        owner = _TASK_LABELS.get(_LOCK_OWNER['cmd']) or _LOCK_OWNER['cmd'] or '资源任务'
        cli._result(req_id, 'fail', errors=[{'message': f'「{owner}」正在进行（已 {held:.0f} 秒），完成后即可继续当前操作；详情见底部活动日志'}])
        return
    _LOCK_OWNER.update(cmd=cmd, at=time.monotonic())
    rt = None
    previous_progress = None
    try:
        rt = runtime_for(cli._ensure_engine())
        if rt:
            previous_progress = getattr(rt, '_progress_callback', None)
            def library_progress(event):
                cli._emit({'id': req_id, 'type': 'progress', 'stage': 'prepare',
                           'percent': None, 'eta_seconds': None, **event})
            rt._progress_callback = library_progress
            # 2026-09-12 用户反馈"同步中但一直不动、日志不说话"：前置刷新
            # 在首次/有变更时要全量扫描+哈希几分钟，之前全程静默。先说一句
            # 在干嘛（快时一闪而过，慢时用户知道没死）。
            preparation = ('正在校验账号与资源库连接（仅同步平台状态，不扫描素材）…'
                           if cmd == 'sync_platform_status' else
                           '正在校验当前工程…' if getattr(rt,'state',{}).get('storage_mode')=='projects' else
                           '正在同步本地资源库快照（有变更时要一会儿，日志会持续播报）…')
            cli._emit({"id": req_id, "type": "progress", "stage": "prepare",
                       "phase": "prepare", "percent": None, "eta_seconds": None,
                       "message": preparation})
            # 平台读/写类命令（sync/shelf）不改本地资源文件——前置只需
            # 库快照（capture=False，秒级）；本地资源入库由命令结束后的
            # 后置 refresh(capture=True) 兜底。前置全量捕获（capture_all
            # 1000+ 目录 stat ~106s）是"一键更新卡几分钟"的主因（09-12）。
            capture = cmd not in ('sync_platform_status', 'shelf_passed',
                                  'get_income', 'sync_platform_status_page')
            if cmd == 'sync_platform_status':
                # This command observes platform metadata, not artwork. Validate
                # the binding/mount now; commit_platform_metadata checks each
                # exact parent. Asset-edit/publish commands retain full refresh.
                rt.require_account()
                rt.library
                status = {}
            else:
                status = rt.refresh(capture=capture, max_age=120)
            if cmd in MUTATIONS and isinstance(status, dict) and status.get('offline'):
                raise ValueError('共享资源库当前不可用，已停止写入；请恢复同步目录后重试')
            # Applying shared prefs/series/bases changes the configuration
            # roots and the engine's in-memory Prefs.  Recreate it before the
            # handler runs so the command observes the just-applied state.
            sync = status.get('settings_sync') if isinstance(status, dict) else None
            if isinstance(sync, dict) and sync.get('applied'):
                cli._engine = None
            if cmd in RESOURCE_EDITS:
                path = Path(args.get('episode_dir') or '').resolve()
                m = next((r for r in rt.rows() if Path(r['path']).resolve() == path), None)
                if not m or not m['can_edit']:
                    raise ValueError('作品原文件未齐、账号不一致或存在版本冲突，当前不能修改/提交')
                if cmd == 'publish_episode' and not m['can_publish']:
                    raise ValueError('发布素材不完整，请补齐表情、横幅、封面、图标、含义词和介绍')
        if cmd == 'sync_platform_status':
            stop = cli._stop_events.get(req_id)
            if stop is not None and stop.is_set():
                cli._result(req_id, 'ok', data={'cancelled': True, 'complete': False,
                            'list_complete': False, 'updated': 0, 'matched': 0})
                return
        edited_work_id = m['work_id'] if rt and cmd in RESOURCE_EDITS else None
        result = handler(req_id, args)
        if edited_work_id and rt and getattr(rt, 'state', {}).get('storage_mode') == 'projects':
            # A rename may have moved the folder; resolve by stable identity.
            rt.capture(rt.path_for(edited_work_id))
        metadata_only = (cmd in {'sync_platform_status', 'shelf_passed'} and isinstance(result, dict)
                         and result.get('metadata_committed') is True)
        if rt and cmd in MUTATIONS and not metadata_only:
            # Reload config: an explicit account switch may have changed it.
            current = runtime_for(cli._ensure_engine())
            if current:
                status = current.refresh(capture=True, max_age=120)
                sync = status.get('settings_sync') if isinstance(status, dict) else None
                if isinstance(sync, dict) and sync.get('applied'):
                    cli._engine = None
        return result
    finally:
        if rt is not None:
            rt._progress_callback = previous_progress
        _LOCK_OWNER.update(cmd='', at=0.0)
        LOCK.release()
