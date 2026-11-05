"""Separate a complete platform list from unrelated local save failures."""

def sync_warnings_for_shelf(result, load_meta):
    """Return warnings, or None when the batch must remain blocked.

    Only API runs that processed every platform row may tolerate save failures.
    Any failure involving a freshly shelfable work still blocks the entire batch.
    Per-work resource, account, operation and exact-ID checks remain with shelf.
    """
    if result.get('error') or result.get('cancelled'):
        return None
    if result.get('list_complete'):
        return []
    total = result.get('platform_total')
    failures = result.get('persistence_failures')
    if (result.get('source') != 'api' or type(total) is not int or total <= 0
            or result.get('matched') != total or result.get('updated') != total
            or result.get('unknown_statuses') or result.get('reason_failures')
            or not isinstance(failures, list) or not failures
            or not isinstance(result.get('fresh_shelfable'), list)):
        return None
    from .platform_data import SHELFABLE_STATUSES
    names = set()
    try:
        for path in result['fresh_shelfable']:
            meta = load_meta(path)
            if (not meta.album_name or not meta.platform_item_id
                    or meta.platform_status not in SHELFABLE_STATUSES):
                return None
            names.add(meta.album_name)
    except (OSError, ValueError, TypeError):
        return None
    if any(not isinstance(f, dict) or not f.get('name') or f['name'] in names
           for f in failures):
        return None
    return [{'name': f['name'], 'message': '平台名单已完整读取；此非上架候选的本地状态未写入共享库：' + str(f.get('message', ''))}
            for f in failures]
