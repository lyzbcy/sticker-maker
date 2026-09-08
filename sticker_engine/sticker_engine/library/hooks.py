"""Serialize device mutations and adapt existing handlers without a shared lock."""
from dataclasses import replace
from pathlib import Path

from .commands import LOCK
from .runtime import LibraryRuntime
from .settings import settings_dir

MUTATIONS = {
    'run', 'run_batch', 'publish_episode', 'fix_and_republish', 'shelf_passed',
    'sync_platform_status', 'repolish_finals', 'update_episode_meta',
    'regen_intro', 'regen_assets', 'save_rating', 'delete_episode', 'save_series',
    'save_prefs', 'generate_base', 'add_base', 'remove_base', 'replenish_refs',
    'save_prompt_set', 'delete_prompt_set', 'save_publish_credentials',
    'clear_publish_credentials',
}
READS = {'list_episodes', 'get_episode', 'list_all_stickers', 'load_prefs',
         'list_series', 'list_characters', 'list_prompt_sets'}
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
    cached = getattr(engine, '_library_runtime', None)
    if cached is not None and str(cached.user_data) == str(Path(data)):
        return cached if cached.enabled else None
    rt = LibraryRuntime(Path(data))
    if not rt.enabled:
        return None
    engine._library_runtime = rt
    return rt


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
    if cmd not in MUTATIONS | READS:
        return handler(req_id, args)
    # 2026-09-05 评审根修：CLI 多线程分发 + 非阻塞抢锁 → 前端启动时并发
    # 请求只有 1 个成功、其余全部被"正在生成、同步或迁移资源"拒绝（用户
    # 看到的"不正常"即此）。改为分级：读/轻写排队等锁（毫秒级，安全）；
    # 长任务保持快速失败（防发布中并发发布/同步）。
    blocking = cmd not in LONG_TASKS
    if not LOCK.acquire(blocking=blocking):
        cli._result(req_id, 'fail', errors=[{'message': '正在生成、同步或迁移资源，请等待任务完成后再操作'}])
        return
    try:
        rt = runtime_for(cli._ensure_engine())
        if rt:
            status = rt.refresh(capture=True, max_age=120)
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
        result = handler(req_id, args)
        if rt and cmd in MUTATIONS:
            # Reload config: an explicit account switch may have changed it.
            current = runtime_for(cli._ensure_engine())
            if current:
                status = current.refresh(capture=True, max_age=120)
                sync = status.get('settings_sync') if isinstance(status, dict) else None
                if isinstance(sync, dict) and sync.get('applied'):
                    cli._engine = None
        return result
    finally:
        LOCK.release()
