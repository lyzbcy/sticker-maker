"""Explicit lossless repair of observational-only episode forks.

No last-writer-wins artwork rule: authored metadata, deletion intent, platform
identity and every material resource must agree. Rating additions are unioned;
different scores/notes for the same item remain a real conflict. All original
immutable revisions survive and the merge names every inspected head as parent.
"""
import copy
import hashlib
import json
import tempfile
from pathlib import Path


def observational(key):
    return ((key.startswith('platform_') and key != 'platform_item_id')
            or key in ('published', 'published_at', 'legacy_name'))


def authored_metadata(metadata):
    return {k: v for k, v in metadata.items() if not observational(k)}


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _object_json(library, resource):
    digest = resource['sha256']
    path = library.root / 'objects' / digest[:2] / digest
    if path.is_symlink() or not path.is_file():
        raise ValueError('评分资源未到齐')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest or len(raw) != resource['size']:
        raise ValueError('评分对象校验失败')
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get('ratings', {}), dict):
        raise ValueError('评分结构需要人工核查')
    return data


def propose(library, work):
    heads = work.get('heads') or []
    if work.get('state') != 'conflict' or len(heads) < 2 or work.get('sync_conflicts'):
        return {'eligible': False, 'reason': '不是完整的普通版本冲突'}
    if any(r['deleted'] for r in heads):
        return {'eligible': False, 'reason': '包含删除意图，保留版本选择'}
    if len({_canonical(authored_metadata(r['metadata'])) for r in heads}) != 1:
        return {'eligible': False, 'reason': '作品名称/身份/素材设置等实际字段不同'}
    material = [{k: v for k, v in r['files'].items()
                 if k not in ('rating.json', '_publish_error.png')} for r in heads]
    if len({_canonical(files) for files in material}) != 1:
        return {'eligible': False, 'reason': '成品、含义或原图不同，保留全部分支'}
    # Timestamp applies to the entire platform observation, never field-by-field
    # maxima (a lower download count or empty reason can be a legitimate reset).
    latest_at = max(str(r['metadata'].get('platform_updated_at') or '') for r in heads)
    newest = [r for r in heads if str(r['metadata'].get('platform_updated_at') or '') == latest_at]
    platform = lambda r: {k:v for k,v in r['metadata'].items()
                          if observational(k) and k not in ('legacy_name', 'platform_review_history')}
    if len({_canonical(platform(r)) for r in newest}) > 1:
        return {'eligible': False, 'reason': '相同同步时间的平台结果不同，待核验'}
    chosen = sorted(newest, key=lambda r:r['revision_id'])[0]
    metadata = copy.deepcopy(chosen['metadata'])
    history = {_canonical(entry): entry for r in heads for entry in r['metadata'].get('platform_review_history', [])}
    metadata['platform_review_history'] = [copy.deepcopy(history[k]) for k in sorted(history)]
    files = copy.deepcopy(material[0])
    rating_resources = {_canonical(r['files']['rating.json']): r['files']['rating.json']
                        for r in heads if 'rating.json' in r['files']}
    rating_bytes = None
    if len(rating_resources) == 1:
        files['rating.json'] = copy.deepcopy(next(iter(rating_resources.values())))
    elif rating_resources:
        documents = [_object_json(library, ref) for ref in rating_resources.values()]
        result = copy.deepcopy(max(documents, key=lambda d:str(d.get('rated_at') or '')))
        ratings = {}
        for doc in documents:
            for name, item in doc.get('ratings', {}).items():
                if name in ratings and ratings[name] != item:
                    return {'eligible': False, 'reason': '同一表情的评分/备注不同，保留人工选择'}
                ratings[name] = copy.deepcopy(item)
        for key in ('overall', 'note'):
            values = [d[key] for d in documents if d.get(key) not in (None, '', 0)]
            if len({_canonical(v) for v in values}) > 1:
                return {'eligible': False, 'reason': '整弹评分/备注不同，保留人工选择'}
            if values:
                result[key] = copy.deepcopy(values[0])
        result['ratings'] = ratings
        rating_bytes = json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')
    errors = {r['files']['_publish_error.png']['sha256']:r['files']['_publish_error.png']
              for r in heads if '_publish_error.png' in r['files']}
    if errors:
        files['_publish_error.png'] = copy.deepcopy(errors[sorted(errors)[0]])
        for digest, ref in errors.items():
            files['_diagnostics/publish-error-'+digest+'.png'] = copy.deepcopy(ref)
    return {'eligible': True, 'metadata': metadata, 'files': files,
            'rating_bytes': rating_bytes, 'parents': sorted(r['revision_id'] for r in heads)}


def repair(library, account_id, work_id, expected_heads=None):
    work = library.read_work(account_id, work_id)
    ids = sorted(r['revision_id'] for r in work.get('heads', []))
    if expected_heads is not None and ids != sorted(expected_heads):
        return {'merged': False, 'reason': '版本头已变化，请重新预览'}
    plan = propose(library, work)
    if not plan['eligible']:
        return {'merged': False, 'reason': plan['reason']}
    if plan['rating_bytes'] is not None:
        with tempfile.TemporaryDirectory(prefix='sticker-rating-merge-') as td:
            p = Path(td)/'rating.json'; p.write_bytes(plan['rating_bytes'])
            plan['files']['rating.json'] = library.put_file(p)
    # Re-read immediately before append; refuse stale preview after peer writes.
    if sorted(r['revision_id'] for r in library.read_work(account_id, work_id)['heads']) != ids:
        return {'merged': False, 'reason': '合并前版本头已变化，请重新预览'}
    revision = library.write_revision(account_id, work_id, plan['metadata'], plan['files'], parents=ids)
    final = library.read_work(account_id, work_id)
    return {'merged': final['state'] == 'available' or final['state'] == 'placeholder',
            'work_id': work_id, 'revision_id': revision['revision_id'], 'parents': ids,
            'state': final['state']}


def choose_preserving_ratings(library, account_id, work_id, revision_id, expected_heads):
    """Explicit artwork choice, with immutable human-rating context retained.

    This is not an automatic artwork merge. A stale preview, deletion, missing
    resources, different platform identity or competing human ratings blocks it.
    An inherited score remains the original score, not a score for new artwork.
    """
    work = library.read_work(account_id, work_id)
    heads = work.get('heads') or []
    ids = sorted(r['revision_id'] for r in heads)
    if expected_heads is None or ids != sorted(expected_heads):
        raise ValueError('版本头已变化，请重新预览')
    if work.get('state') != 'conflict' or work.get('sync_conflicts') or len(heads) < 2:
        raise ValueError('请选择完整的素材冲突')
    if any(r['deleted'] or r['metadata'].get('kind', 'episode') != 'episode' for r in heads):
        raise ValueError('删除或设置分歧需要独立处理')
    if len({r['metadata'].get('platform_item_id', '') for r in heads}) != 1:
        raise ValueError('平台作品身份不同，请核验绑定')
    selected = next((r for r in heads if r['revision_id'] == revision_id), None)
    if selected is None:
        raise ValueError('请选择有效冲突版本')
    refs = {_canonical(r['files']['rating.json']): r['files']['rating.json']
            for r in heads if 'rating.json' in r['files']}
    if len(refs) > 1:
        raise ValueError('存在多份不同人工评分，请先核验评分版本')
    files = copy.deepcopy(selected['files'])
    if refs:
        ref = next(iter(refs.values()))
        _object_json(library, ref)  # Validate bytes before preserving them.
        files['rating.json'] = copy.deepcopy(ref)
        sources = []
        for head in heads:
            if head['files'].get('rating.json') != ref:
                continue
            rid = head['revision_id']
            files['_rating_history/' + rid + '/rating.json'] = copy.deepcopy(ref)
            changed = [name for name, resource in head['files'].items()
                       if name.startswith('最终版/') and selected['files'].get(name) != resource]
            sources.append({'revision_id': rid, 'metadata': copy.deepcopy(head['metadata']),
                            'files': copy.deepcopy(head['files']),
                            'changed_or_removed_final_paths': sorted(changed)})
        provenance = {'schema': 1, 'rating_sha256': ref['sha256'],
                      'selected_revision_id': revision_id, 'sources': sources,
                      'inherited_from_other_artwork': any(s['changed_or_removed_final_paths'] for s in sources),
                      'meaning': '原人工评分与制作上下文保留；变化后的图片尚未重新评分'}
        with tempfile.TemporaryDirectory(prefix='sticker-rating-provenance-') as td:
            p = Path(td) / 'rating_provenance.json'
            p.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
            files['rating_provenance.json'] = library.put_file(p)
    if sorted(r['revision_id'] for r in library.read_work(account_id, work_id)['heads']) != ids:
        raise ValueError('合并前版本头已变化，请重新预览')
    return library.write_revision(account_id, work_id, copy.deepcopy(selected['metadata']),
                                  files, parents=ids)
