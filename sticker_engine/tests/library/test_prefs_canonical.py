import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.library.settings import SharedSettings


def prefs(tmp_path):
    rt=LibraryRuntime(tmp_path/'device');rt.bind('fixture@example.com',True)
    settings=SharedSettings(rt);settings.root.mkdir(parents=True,exist_ok=True)
    data={'grid_size':4,'background_mode':'solid','sticker_text':True,'base_probs':{'role':{'z':.2,'a':.8}}}
    (settings.root/'prefs.yaml').write_text(yaml.safe_dump(data,sort_keys=False),encoding='utf-8')
    settings.capture()
    work=next(w for w in rt.library.list_works() if w['heads'][0]['metadata'].get('setting_type')=='prefs')
    return rt,settings,work,data


def fork(tmp_path, change=False):
    rt,s,w,data=prefs(tmp_path);a=w['revision'];metadata=copy.deepcopy(a['metadata'])
    if change:
        data['grid_size']=3;metadata['payload']['grid_size']=3
    raw=yaml.safe_dump(dict(reversed(list(data.items()))),allow_unicode=True,sort_keys=False).encode()
    p=tmp_path/'alternate.yaml';p.write_bytes(raw)
    b=rt.library.write_revision(rt.account_id,w['work_id'],metadata,{'prefs.yaml':rt.library.put_file(p)},parents=[])
    return rt,s,a,b


def test_yaml_stable_across_hash_seeds_and_nested_input_order():
    code="from sticker_engine.library.settings import SharedSettings as S;print(S._dump_yaml(S._sanitize_prefs({'sticker_text':True,'grid_size':4,'background_mode':'solid','base_probs':{'r':{'z':0.2,'a':0.8}}})).hex())"
    values=[]
    for seed in ('1','2','10'):
        env=os.environ.copy();env['PYTHONHASHSEED']=seed
        values.append(subprocess.check_output([sys.executable,'-c',code],env=env,cwd=str(Path(__file__).parents[2]),text=True))
    assert len(set(values))==1
    assert SharedSettings._dump_yaml({'z':{'b':1,'a':2},'a':True})==SharedSettings._dump_yaml({'a':True,'z':{'a':2,'b':1}})


def test_same_value_forks_merge_keep_history_and_refresh_never_forks(tmp_path):
    rt,s,a,b=fork(tmp_path)
    old=copy.deepcopy(rt.library.revisions(rt.account_id,a['work_id']))
    result=s.repair_equivalent_prefs(a['work_id'],[a['revision_id'],b['revision_id']])
    assert result['state']=='available'
    for i in range(3):
        fresh=LibraryRuntime(rt.user_data);status=fresh.refresh()
        assert status['settings_conflicts']==[]
        assert fresh.library.read_work(rt.account_id,a['work_id'])['revision']['revision_id']==result['revision_id']
    assert all(r in rt.library.revisions(rt.account_id,a['work_id']) for r in old)


def test_true_settings_change_is_not_merged(tmp_path):
    rt,s,a,b=fork(tmp_path,change=True)
    with pytest.raises(ValueError,match='设置值'):
        s.repair_equivalent_prefs(a['work_id'],[a['revision_id'],b['revision_id']])
    assert rt.library.read_work(rt.account_id,a['work_id'])['state']=='conflict'


def test_local_authored_change_and_stale_preview_are_preserved(tmp_path):
    rt,s,a,b=fork(tmp_path)
    with pytest.raises(ValueError,match='版本头'):
        s.repair_equivalent_prefs(a['work_id'],[a['revision_id']])
    (s.root/'prefs.yaml').write_text('grid_size: 3\n',encoding='utf-8')
    with pytest.raises(ValueError,match='本机偏好'):
        s.repair_equivalent_prefs(a['work_id'],[a['revision_id'],b['revision_id']])


def test_old_serialization_adopts_peer_head_but_real_edit_still_forks(tmp_path):
    rt,s,w,data=prefs(tmp_path);a=w['revision']
    p=tmp_path/'old-order.yaml';p.write_text(yaml.safe_dump(dict(reversed(list(data.items()))),sort_keys=False),encoding='utf-8')
    b=rt.library.write_revision(rt.account_id,w['work_id'],a['metadata'],{'prefs.yaml':rt.library.put_file(p)},parents=[a['revision_id']])
    s.capture()
    assert rt.library.read_work(rt.account_id,w['work_id'])['revision']['revision_id']==b['revision_id']
    assert rt.state['settings_versions'][w['work_id']]['revision_id']==b['revision_id']
    # Now the peer changes values while this device independently edits too.
    peer=copy.deepcopy(b['metadata']);peer['payload']['grid_size']=3
    p.write_text(yaml.safe_dump(peer['payload']),encoding='utf-8')
    rt.library.write_revision(rt.account_id,w['work_id'],peer,{'prefs.yaml':rt.library.put_file(p)},parents=[b['revision_id']])
    local=dict(data,grid_size=2);(s.root/'prefs.yaml').write_text(yaml.safe_dump(local),encoding='utf-8')
    s.capture();assert rt.library.read_work(rt.account_id,w['work_id'])['state']=='conflict'


def test_settings_choose_materializes_merged_head_not_discarded_id(tmp_path):
    rt,s,a,b=fork(tmp_path,change=True)
    rt.resolve(a['work_id'],b['revision_id'])
    assert yaml.safe_load((s.root/'prefs.yaml').read_text(encoding='utf-8'))['grid_size']==3
    assert rt.status()['settings_conflicts']==[]


def test_apply_new_device_adopts_same_values_without_marker(tmp_path):
    rt,s,w,data=prefs(tmp_path);a=w['revision']
    p=tmp_path/'old-order.yaml';p.write_text(yaml.safe_dump(dict(reversed(list(data.items()))),sort_keys=False),encoding='utf-8')
    b=rt.library.write_revision(rt.account_id,w['work_id'],a['metadata'],{'prefs.yaml':rt.library.put_file(p)},parents=[a['revision_id']])
    rt.state['settings_versions'].pop(w['work_id'])
    result=s.apply()
    assert result['conflicts']==[]
    assert rt.state['settings_versions'][w['work_id']]['revision_id']==b['revision_id']
