"""Generate isolated artwork and exercise packaged resource-location UI."""
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

from PIL import Image
from sticker_engine.config.series import EpisodeMeta
from sticker_engine.library.catalog import ResourceLibrary
from sticker_engine.library.runtime import account_key
from sticker_engine.project import atomic_json, create_project

repo = Path(__file__).resolve().parents[1]
task = Path('C:/sm-qa') / ('gui-' + uuid.uuid4().hex[:6])
parent = task / '资源'
collection = parent / '表情工程'
project = collection / '周三涵做表情37'
project.mkdir(parents=True)
account = account_key('isolated-owner')
meta = EpisodeMeta(work_id='fixture-work', account_id=account, account_label='隔离样例账号',
                   album_name=project.name, intro='仅本地隔离验收', platform_item_id='original-platform-id')
for i in range(1, 9):
    p = project / '最终版' / f'词{i}.png'
    p.parent.mkdir(exist_ok=True)
    Image.new('RGBA', (240, 240), (30+i*10, 100, 70, 255)).save(p)
atomic_json(project/'rating.json', {'overall': 91, 'note': '人工原值'})
atomic_json(collection/'projects.json', dict(format='sticker-maker-project-collection', schema_version=1, library_id=uuid.uuid4().hex))
create_project(project, meta.to_dict(), meanings={str(i): f'词{i}' for i in range(1, 9)})
legacy = ResourceLibrary(parent/'旧资源库', create=True)
files = {str(p.relative_to(project)).replace('\\', '/'): legacy.put_file(p)
         for p in project.rglob('*') if p.is_file() and p.name != 'project.json'}
legacy.write_revision(account, meta.work_id, dict(meta.to_dict(), kind='episode'), files)
protected = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.rglob('*') if p.is_file()}
fixture = dict(task=str(task), parent=str(parent), collection=str(collection), legacy=str(legacy.root))
atomic_json(task/'fixture.json', fixture)
completed = subprocess.run(['node', str(repo/'scripts/verify-resource-location.cjs'), str(task/'fixture.json')], cwd=repo)
assert completed.returncode == 0
assert all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in protected.items())
assert not any(collection.rglob('.sticker-maker-workspaces'))
report = json.loads((task/'report.json').read_text(encoding='utf-8'))
report.update(protected_hashes_preserved=len(protected), fixture=str(task), real_data_modified=False)
atomic_json(repo/'verification/resource-location-20261021/electron-acceptance.json', report)
print(json.dumps(report, ensure_ascii=False, indent=2))
