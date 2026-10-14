"""Quarantine only metadata/role-card shells, never infer garbage from a name."""
import json
import uuid
from pathlib import Path

from ..config.series import load_meta
from .resources import hash_file
from .runtime import write_json

ALLOWED = {'meta.json', '本次制作角色.md'}


def candidates(runtime):
    root=runtime.output_root.resolve()
    result=[]
    for path in sorted(root.glob('episode*')):
        if path.is_symlink() or not path.is_dir() or path.resolve().parent!=root:
            continue
        entries=list(path.rglob('*'))
        if any(p.is_symlink() for p in entries):
            continue
        files=[p for p in entries if p.is_file()]
        if not files or any(p.relative_to(path).as_posix() not in ALLOWED for p in files):
            continue
        meta=load_meta(path)
        if meta.album_name or meta.published or meta.platform_item_id or (meta.account_id and meta.account_id!=runtime.account_id):
            continue
        work=runtime.library.read_work(runtime.account_id,meta.work_id) if meta.work_id else None
        if work and (work['state'] in ('conflict','pending') or work.get('sync_conflicts')):
            continue
        history=runtime.library.revisions(runtime.account_id,meta.work_id) if meta.work_id else []
        if any(r['metadata'].get('platform_item_id') or r['metadata'].get('published')
               or any(name not in ALLOWED for name in r['files']) for r in history):
            continue
        result.append({'path':str(path),'work_id':meta.work_id,
                       'hashes':{p.relative_to(path).as_posix():list(hash_file(p)) for p in files},
                       'heads':[r['revision_id'] for r in (work or {}).get('heads',[])]})
    return result


def cleanup(runtime, execute=False):
    runtime.require_account()
    items=candidates(runtime)
    if not execute:
        return {'preview':True,'candidates':items,'count':len(items)}
    archive=(runtime.workspace_base/'_quarantine'/('failed-drafts-'+uuid.uuid4().hex)).resolve()
    assert runtime.workspace_base.resolve() in archive.parents
    archive.mkdir(parents=True)
    record={'preview':False,'archive':str(archive),'moved':[],'errors':[]}
    write_json(archive/'manifest.json',record)
    for item in items:
        source=Path(item['path']).resolve();dest=archive/source.name
        if source.parent!=runtime.output_root.resolve() or dest.parent!=archive:
            raise ValueError('清理目录校验失败')
        fresh=next((v for v in candidates(runtime) if v['path']==item['path']),None)
        if fresh!=item:
            record['errors'].append({'path':item['path'],'reason':'预览后内容/版本变化，已保留'});continue
        # Persist intent first; rename on the same volume is recoverable and
        # does not copy/remove any objects or version-history manifests.
        entry=dict(item,archive_path=str(dest),state='planned')
        record['moved'].append(entry);write_json(archive/'manifest.json',record)
        source.rename(dest)
        entry['state']='quarantined';write_json(archive/'manifest.json',record)
        if item['work_id']:
            work=runtime.library.read_work(runtime.account_id,item['work_id'])
            if work.get('revision') and work['state']!='deleted':
                rev=work['revision']
                deleted=runtime.library.write_revision(runtime.account_id,item['work_id'],rev['metadata'],rev['files'],parents=item['heads'],deleted=True)
                entry['deleted_revision_id']=deleted['revision_id']
        runtime.state['paths'].pop(str(source),None)
        (runtime.state.get('capture_light') or {}).pop(str(source),None)
        entry['state']='completed';write_json(archive/'manifest.json',record)
    runtime._rows_at=0;runtime._refresh_cache=None;runtime.save()
    record['count']=sum(x['state']=='completed' for x in record['moved'])
    write_json(archive/'manifest.json',record)
    return record
