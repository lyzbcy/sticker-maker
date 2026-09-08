"""Replicated submit intentions; an uncertain outcome is never retried blindly."""
import uuid
from datetime import datetime, timezone


def unresolved(runtime):
    items = []
    if not runtime.enabled:
        return items
    for work in runtime.library.list_works(runtime.account_id):
        heads = work.get('heads') or []
        for rev in heads:
            meta = rev['metadata']
            incomplete = work['state'] in ('pending', 'conflict')
            if meta.get('kind') == 'operation' and (incomplete or meta.get('phase') in ('intent', 'unknown')):
                items.append(dict(meta, phase='unknown' if incomplete else meta['phase'],
                                  operation_id=work['work_id'], work_id=meta['target_work']))
                break
    return items


def begin(runtime, work_id, album_name, action='submit'):
    if any(op['work_id'] == work_id for op in unresolved(runtime)):
        raise ValueError('此前提交结果待核对，请到账号与资源库核对平台结果后再操作')
    operation_id = 'operation-' + uuid.uuid4().hex
    runtime.library.write_revision(runtime.account_id, operation_id, {
        'kind': 'operation', 'account_label': runtime.account_label,
        'target_work': work_id, 'album_name': album_name, 'action': action,
        'device_id': runtime.state['device_id'], 'phase': 'intent',
        'started_at': datetime.now(timezone.utc).isoformat()}, {}, parents=[])
    return operation_id


def finish(runtime, operation_id, success):
    work = runtime.library.read_work(runtime.account_id, operation_id)
    if not work.get('revision'):
        return {'phase': 'unknown', 'message': '提交记录不完整或存在冲突，请核对平台结果'}
    rev = work['revision']
    metadata = dict(rev['metadata'], phase='succeeded' if success else 'unknown')
    runtime.library.write_revision(runtime.account_id, operation_id, metadata, {},
                                    parents=[rev['revision_id']])


def reconcile(runtime, operation_id, outcome):
    if outcome not in ('submitted', 'not_submitted'):
        raise ValueError('请选择已经在平台核实的提交结果')
    work = runtime.library.read_work(runtime.account_id, operation_id)
    heads = work.get('heads') or []
    if not heads or any(r['metadata'].get('kind') != 'operation' for r in heads):
        raise ValueError('未找到对应提交记录')
    metadata = dict(heads[0]['metadata'], phase='confirmed_' + outcome,
                    confirmed_at=datetime.now(timezone.utc).isoformat())
    runtime.library.write_revision(runtime.account_id, operation_id, metadata, {},
                                   parents=[r['revision_id'] for r in heads])


def verify_target(runtime, page, path, edit):
    from ..config.series import load_meta, save_meta
    from ..publish.platform_data import read_json, parse_list, LIST_URL
    from ..publish.status import normalize_name
    meta = load_meta(path)
    if meta.account_id != runtime.account_id:
        raise ValueError('作品所属账号与发布账号不一致')
    if any(op['work_id'] == meta.work_id for op in unresolved(runtime)):
        raise ValueError('此前提交结果待核对，请先在平台核实')
    if meta.series_id and meta.number is not None:
        for work in runtime.works():
            if work['work_id'] == meta.work_id or work['state'] == 'deleted':
                continue
            for revision in work.get('heads', []):
                peer = revision.get('metadata', {})
                if peer.get('series_id') == meta.series_id and peer.get('number') == meta.number:
                    raise ValueError('同一系列存在重复编号，请先调整编号后再发布')
    rows = parse_list(read_json(page, LIST_URL))
    matches = [r for r in rows if normalize_name(r['Name']) == normalize_name(meta.album_name)]
    if meta.platform_item_id:
        targets = [r for r in rows if r['StikerID'] == meta.platform_item_id]
        if len(targets) != 1:
            raise ValueError('当前账号中未找到原平台作品，请先更新并核对账号')
        if targets[0]['Status'] == 2:
            raise ValueError('作品仍在待审核，请等待审核结果后再操作')
        if targets[0]['Status'] in (5, 7):
            raise ValueError('作品已审核通过或上架，无需再次提交；可使用一键上架')
        if any(r['StikerID'] != meta.platform_item_id for r in matches):
            raise ValueError('平台存在其他同名作品，请先修改名称')
        return True
    if matches:
        if meta.published and len(matches) == 1:
            meta.platform_item_id = matches[0]['StikerID']; save_meta(path, meta)
            return verify_target(runtime, page, path, True)
        raise ValueError('平台已有同名作品，请先一键更新并关联，避免重复提交')
    if edit:
        raise ValueError('整改作品缺少平台 ID，请先一键更新')
    return False
